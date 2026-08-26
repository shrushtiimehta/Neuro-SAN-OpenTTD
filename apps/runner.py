"""Drive one nttd session, step by step, and close the learning loop around it.

    python -m apps.runner --session <id> --token pt_... --network nttd_air_player

**Stepped, throughout.** The world is paused between steps and the player advances it explicitly,
so a turn may take four minutes of wall clock and one game day. That is the whole reason this
benchmark is worth running against a multi-agent system: deliberation is free, and what is being
measured is judgement rather than reaction speed. Nothing in this file moves the clock — the
player's own tools do, via `POST /step`.

**What this loop decides: nothing about the game.** It asks the player for another turn while the
session is open and stops when the session closes. How long to wait, what to build, when to
consolidate: all of that belongs to the agent, and a runner that woke it every thirty game days
would be answering a question the benchmark is asking.

**What it DOES own** is everything the agent cannot see:

1. The turn stamp. Only the client knows where a turn begins — a coded tool sees one continuous
   stream of calls and cannot tell the last call of one request from the first of the next. The
   day budget in the workbench's `advance_days` reads this stamp, and without it a turn can grow
   until it exceeds the server's execution cap and is cancelled with everything in it lost.
2. Spend reporting. nttd runs no model, so it cannot observe what a turn cost.
3. The telemetry rows the watcher, the opener and the closer judge against.
4. Calling the watcher at intervals, and acting on a `doomed` verdict.
5. Calling the opener and the closer at the session boundaries, so its knowledge outlives it.

**A dropped stream is not the end of the run.** neuro-san streams a turn over one long HTTP
response, and anything interrupting it — a slow provider, a laptop sleeping — raises out of
`process_once`. A turn is retried rather than the process dying: what is lost is that turn's
`sly_data`, which only returns to the client on completion; what survives is the world, which is
on nttd's side, and the conversation, which is in the `chat_context` held here.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from typing import Any

import httpx

from coded_tools import paths
from coded_tools import seed_playbooks
from coded_tools import session_number
from coded_tools import telemetry
from coded_tools.file_io import FileIO

logger = logging.getLogger("nttd.runner")

API_URL = os.environ.get("NTTD_API_URL", "http://127.0.0.1:8000")

# What the board shows in its system type column. Declared here rather than passed in, so a run
# started by hand says the same thing as one started by the script: the runner is the only thing
# that knows what it is.
SYSTEM_TYPE = "neuro-san"

# What the agents accumulate that has no other record. Listed by NAME rather than copied wholesale
# because sly_data also carries the session id and the participant token, and a snapshot written
# to disk is precisely where a credential must not end up.
AGENT_STATE_KEYS = ("sites", "decisions", "routes", "plan", "fleet_seen", "refusals", "turns")

# How long the client waits on a silent stream.
#
# It MUST exceed the server's `max_execution_seconds`, which `nttd_common.hocon` sets to 6000. A
# client that gives up first tears down a turn the server was still entitled to be working on, and
# the traceback that comes back is about connectivity and names nothing that was actually wrong.
STREAM_TIMEOUT_SECONDS = 7200

# How many times one turn is re-attempted after its stream fails. Separate from neuro-san's own
# `max_attempts`, which retries a failing agent run INSIDE the server: this covers the case where
# the server never got the chance to report anything at all.
TURN_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 20

# How often the watcher looks. Every fifth turn rather than every turn: a health check that ran as
# often as the thing it checks would double the cost of the run and tell it nothing new, because
# the figures it reads barely move in one turn.
WATCH_EVERY = 5

# The abort guardrail. A `doomed` verdict late in a run ends it on one strike; early on it takes
# two consecutive strikes, because the documented figures say a run with nothing delivered before
# day 73 is normal and one strike there would abort healthy sessions.
DOOM_STRIKES_EARLY = 2
DOOM_STRIKES_LATE = 1
LATE_FRACTION = 0.5

TURN = (
    "Take the next decision in this session. Read the position first, fix anything that is broken "
    "before building something new, and let time pass when you need the world to run before you "
    "can judge what you did. Say briefly what you did and why."
)

_VERDICT_RE = re.compile(r"VERDICT:\s*(on_track|underperforming|doomed)", re.IGNORECASE)


# --- the game's own view -------------------------------------------------------------------


def status(session: str) -> dict[str, Any]:
    """What the game says about itself. A 404 is the run having ended, not a fault."""
    try:
        reply = httpx.get(f"{API_URL}/v1/public/sessions/{session}/status", timeout=30)
        if reply.status_code == 404:
            return {"ended": True}
        reply.raise_for_status()
        return reply.json()
    except httpx.HTTPError as failure:
        logger.warning("Could not read session status: %r", failure)
        return {"ended": True}


def situation(session: str, token: str) -> dict[str, Any]:
    """The engine's own arithmetic on the position. Used for telemetry, not for deciding.

    Read here rather than derived from the player's chat, because a figure the runner records has
    to be the game's own: a run judged against numbers an agent reported about itself is not a
    measurement.
    """
    try:
        reply = httpx.get(
            f"{API_URL}/v1/participant/sessions/{session}/state/situation",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        reply.raise_for_status()
        return reply.json()
    except httpx.HTTPError as failure:
        logger.warning("Could not read the situation: %r", failure)
        return {}


def company(session: str, token: str, company_id: int = 0) -> dict[str, Any]:
    """The company row: cargo delivered, rating, value.

    A SECOND call, because `situation.earning` does not carry `cargo_delivered_total` — it has
    income and per-vehicle profit and nothing cumulative. Reading it off `earning` returned 0 on
    every turn of every run, which made the board's tiebreak metric dead, made `diagnose` report
    "built but delivering nothing" forever, and fed the opener a false premise to raise claims
    against. Measured against a live session: earning said 0, the company row said 176.
    """
    try:
        reply = httpx.get(
            f"{API_URL}/v1/participant/sessions/{session}/state/company/{company_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        reply.raise_for_status()
        return reply.json()
    except httpx.HTTPError as failure:
        logger.warning("Could not read the company: %r", failure)
        return {}


def declare(session: str, token: str, network: str) -> None:
    """Tell nttd what is playing, since it cannot see it.

    nttd runs no model and watches only actions, so it cannot tell a multi-agent network from a
    scripted policy by looking. What it is told lands in `result.parquet` and becomes the board's
    system type column. Not fatal: losing a label is a smaller loss than refusing to start.
    """
    _report(
        session,
        token,
        {
            "nttd_framework": SYSTEM_TYPE,
            "participant_type": "multi-agent",
            "agent_id": network,
        },
    )


def _report(session: str, token: str, payload: dict[str, Any]) -> None:
    try:
        reply = httpx.post(
            f"{API_URL}/v1/participant/sessions/{session}/report",
            headers={"X-Participant-Token": token},
            json=payload,
            timeout=30,
        )
        reply.raise_for_status()
    except httpx.HTTPError as failure:
        logger.warning("Could not report to nttd: %r", failure)


# --- spend ---------------------------------------------------------------------------------

# The flat keys neuro-san puts beside its per-model breakdown: the whole network's totals for one
# request. Skipped when walking, because the per-model entries below them carry the same numbers
# split up and counting both doubles everything.
_AGGREGATE_KEYS = frozenset(
    {
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "successful_requests",
        "empty_responses",
        "total_cost",
        "time_taken_in_seconds",
        "caveats",
    }
)


def spend_from(accounting: dict) -> list[dict]:
    """neuro-san's token accounting for one turn, as nttd's per-model spend.

    The per-model breakdown is NESTED under `models`. An earlier version walked the top level,
    found the `models` dict itself, and read a provider name as a model with zero tokens.

    **The cost is omitted when neuro-san reports zero.** It prices models from its own table and
    falls back to zero with a log warning when a model is not in it, so a zero far more likely
    means "no price for this model" than "this was free". nttd tells those apart: an absent cost
    leaves the board's cost column blank, while a zero claims the run cost nothing.
    """
    spend: list[dict] = []
    breakdown = (accounting or {}).get("models")
    if not isinstance(breakdown, dict):
        return spend
    for provider, models in breakdown.items():
        if not isinstance(models, dict):
            continue
        for model, stats in models.items():
            if not isinstance(stats, dict):
                continue
            entry = {
                "model": str(model),
                "role": str(provider),
                "prompt_tokens": int(stats.get("prompt_tokens") or 0),
                "completion_tokens": int(stats.get("completion_tokens") or 0),
            }
            cost = float(stats.get("total_cost") or 0.0)
            if cost > 0:
                entry["total_cost_usd"] = cost
            spend.append(entry)
    return spend


def report_spend(session: str, token: str, accounting: dict) -> float:
    """Send one turn's usage and return what it cost. nttd ADDS what it is told.

    Per turn is the honest unit: each turn re-sends the conversation and is re-billed for it, so
    the totals only add up if every turn is counted. neuro-san resets its accounting per request,
    so what arrives here is this turn alone.
    """
    spend = spend_from(accounting)
    if not spend:
        return 0.0
    _report(session, token, {"models": spend})
    return round(sum(float(row.get("total_cost_usd") or 0.0) for row in spend), 6)


# --- talking to a network ------------------------------------------------------------------


def open_session_to(  # pylint: disable=import-outside-toplevel
    network: str, host: str, port: int
):
    """A neuro-san session for one agent network."""
    from neuro_san.session.http_service_agent_session import HttpServiceAgentSession  # noqa: PLC0415

    return HttpServiceAgentSession(
        host=host,
        port=str(port),
        agent_name=network,
        streaming_timeout_in_seconds=STREAM_TIMEOUT_SECONDS,
    )


def ask_once(  # pylint: disable=import-outside-toplevel
    network: str, host: str, port: int, message: str, sly: dict | None = None
) -> str:
    """One request to a network that keeps no state between calls: the watcher, the boundaries.

    A fresh session each time on purpose. These are called at intervals rather than in a
    conversation, and carrying a chat context across a whole run would grow it without limit for
    no benefit — they read files, and the files are the continuity.
    """
    from neuro_san.client.streaming_input_processor import StreamingInputProcessor  # noqa: PLC0415

    processor = StreamingInputProcessor(session=open_session_to(network, host, port))
    state: dict[str, Any] = {
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
        "sly_data": dict(sly or {}),
        "chat_context": {},
        "last_chat_response": None,
        "user_input": message,
    }
    try:
        out = processor.process_once(state)
    except ValueError as broken:
        logger.warning("%s did not answer: %s", network, broken)
        return ""
    return (out.get("last_chat_response") or "").strip()


def take_turn(processor: Any, state: dict, turn: int) -> dict | None:
    """One player turn, re-attempted while the stream keeps failing. None once it runs out.

    Only the STREAM is retried. A turn that completed and said something unhelpful is a turn the
    network is entitled to have, and re-running it would be this loop overruling the thing it is
    supposed to be measuring.

    neuro-san reports a broken stream as a ValueError carrying its connectivity help text, so that
    is what is caught. Not narrowed further: the underlying requests exception is already swallowed
    by neuro-san's own except clause, and matching on the text of a help message would break the
    first time that message is reworded.
    """
    for attempt in range(1, TURN_ATTEMPTS + 1):
        try:
            return processor.process_once(state)
        except ValueError as broken:
            if attempt == TURN_ATTEMPTS:
                logger.error("turn %d failed on attempt %d: %s", turn, attempt, broken)
                return None
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "turn %d lost its stream on attempt %d, retrying in %ds. The world is on nttd's "
                "side and the conversation is still held here, so the turn is simply taken "
                "again: %s",
                turn,
                attempt,
                wait,
                broken,
            )
            time.sleep(wait)
    return None


# --- the loop ------------------------------------------------------------------------------


def doom_limit(game_date: int, started: int, total: int) -> int:
    """How many consecutive `doomed` verdicts end the run, given how far in it is.

    One strike late, two early. The documented figures are the reason: one measured run had
    `cargo_delivered_total` at exactly 0 until day 73, and the far end of a 289-tile trunk saw its
    first aircraft on day 43. A single strike early would abort sessions that were doing fine.
    """
    if not total:
        return DOOM_STRIKES_EARLY
    elapsed = max(0, game_date - started)
    return DOOM_STRIKES_LATE if elapsed >= total * LATE_FRACTION else DOOM_STRIKES_EARLY


def play(  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,import-outside-toplevel
    args: argparse.Namespace,
) -> int:
    """Play one stepped session end to end: open, plan, turn loop with watcher checks, close.

    Long and linear on purpose. This is the turn loop, and the order things happen in — stamp,
    ask, record, check, advance — IS the contract with the engine. Split across helpers it reads
    as five functions that each look fine while the sequence between them goes unstated.
    """
    from neuro_san.client.streaming_input_processor import StreamingInputProcessor  # noqa: PLC0415

    session, token, network = args.session, args.token, args.network
    number = session_number.current() or session_number.open_next()

    opening = status(session)
    if opening.get("ended"):
        print(f"session {session} has already ended")
        return 1
    mode = str(opening.get("mode") or "")
    if mode and "step" not in mode.lower():
        # Refused rather than played badly. In realtime the clock runs whatever the agent does,
        # which makes a slow turn a lost game month and every figure in the playbooks
        # incomparable with every other.
        print(f"session {session} is running in {mode!r}, not stepped.")
        print("These networks play stepped scenarios only, where the world is paused between")
        print("steps and deliberation costs no game time. Start it from a stepped config.")
        return 1

    started = int(opening.get("game_date") or 0)
    horizon = int(opening.get("game_days_total") or 0)
    conditions = f"{args.scenario or 'unknown-scenario'} {mode or 'stepped'} session{number}"
    print(f"session {number}: {session}  mode={mode or 'stepped'}  days={horizon or '?'}")

    declare(session, token, network)

    # --- opening boundary ----------------------------------------------------------------
    if not args.no_planner:
        print("\n-- opener --")
        said = ask_once(
            args.opener,
            args.host,
            args.port,
            f"Open session {number}. Conditions: {conditions}. "
            "Read the commons, compile the plan, and raise the claims to test.",
        )
        print(said or "(nothing was said)")

    processor = StreamingInputProcessor(session=open_session_to(network, args.host, args.port))
    state: dict[str, Any] = {
        # MAXIMAL, because the token accounting arrives as an AgentMessage and the DEFAULT filter
        # is MINIMAL, which drops every accounting message before it leaves. Measured: the runner
        # reported no spend at all while looking like it had — no error, no warning.
        "chat_filter": {"chat_filter_type": "MAXIMAL"},
        # sly_data addresses the company and is deliberately kept out of the chat stream.
        "sly_data": {"session_id": session, "token": token},
        "chat_context": {},
        "last_chat_response": None,
        "user_input": TURN,
    }

    spent = 0.0
    strikes = 0
    aborted = False
    end_reason = ""
    turn = 0

    for turn in range(1, args.max_turns + 1):
        # Stamped here because only the client knows where a turn begins. `advance_days` reads it
        # to bound the game days one turn may spend, which is what stops a turn growing until the
        # server cancels it with everything in it lost.
        state["sly_data"]["turn_stamp"] = turn
        state["user_input"] = TURN

        played = take_turn(processor, state, turn)
        if played is None:
            print(f"  turn {turn}: the stream failed {TURN_ATTEMPTS} times; giving up")
            print("  the session is still open, so it can be picked up again from here")
            end_reason = "stream failed"
            break
        state = played
        spent += report_spend(session, token, state.get("token_accounting") or {})

        now = status(session)
        pos = situation(session, token) if not now.get("ended") else {}
        firm = company(session, token) if not now.get("ended") else {}
        sly = state.get("sly_data") or {}
        telemetry.record_turn(_turn_row(session, number, turn, now, pos, spent, sly, firm))
        # The agents' own accumulated state. Copied BY NAME, never wholesale: the session id and
        # the participant token live in sly_data too, and a file on disk is exactly where a
        # credential must not end up.
        FileIO.append_jsonl(
            paths.agent_log(number),
            {"turn": turn, **{k: sly.get(k) for k in AGENT_STATE_KEYS if k in sly}},
            logger,
        )
        said = (state.get("last_chat_response") or "").strip()
        today = int(now.get("game_date") or 0)
        print(f"  turn {turn} (day {max(0, today - started)}): {said[:400]}")

        if now.get("ended"):
            end_reason = "the game closed the session"
            break

        # --- the watcher, at intervals ---------------------------------------------------
        if not args.no_watcher and turn % WATCH_EVERY == 0:
            verdict, note = _watch(args, number, turn, conditions)
            print(f"  -- watcher (turn {turn}): {verdict or 'no verdict'} --")
            if note:
                print(f"     {note[:300]}")
            if verdict == "doomed":
                strikes += 1
                limit = doom_limit(today, started, horizon)
                print(f"     doomed strike {strikes} of {limit}")
                if strikes >= limit:
                    aborted = True
                    end_reason = f"aborted on a doomed verdict at turn {turn}"
                    break
            else:
                # Consecutive, not cumulative: one bad check followed by a recovery is not a
                # dying run, and counting them cumulatively would abort every long session.
                strikes = 0
            if verdict == "underperforming" and note:
                state["user_input"] = (
                    f"{TURN}\n\nThe run analyst reports: {note}\n"
                    "Take that into account, or say plainly why you disagree."
                )
    else:
        end_reason = f"stopped after {args.max_turns} turns with the session still open"

    # --- closing boundary ----------------------------------------------------------------
    final = status(session)
    pos = situation(session, token)
    telemetry.record_session(
        _session_row(
            session,
            number,
            turn,
            final,
            pos,
            spent,
            aborted,
            end_reason,
            args.scenario,
            mode or "stepped",
            company(session, token),
        )
    )
    print(f"\n{end_reason or 'the session ended'}. spend ${spent:.2f} over {turn} turn(s).")

    if not args.no_planner:
        print("\n-- closer --")
        said = ask_once(
            args.closer,
            args.host,
            args.port,
            f"Close session {number}. Conditions: {conditions}. "
            "Revise the claims against the evidence, promote what held up, and "
            "advance the session.",
        )
        print(said or "(nothing was said)")

    return 1 if aborted else 0


def _watch(args: argparse.Namespace, number: int, turn: int, conditions: str) -> tuple[str, str]:
    """Ask the watcher for a verdict. Returns (verdict, what it said).

    A missing or misspelled verdict is read as no verdict, deliberately. Guessing at one would let
    a garbled answer abort a healthy run.
    """
    said = ask_once(
        args.watcher,
        args.host,
        args.port,
        f"Health check at turn {turn} of session {number}. Conditions: {conditions}.",
    )
    found = _VERDICT_RE.search(said or "")
    return (found.group(1).lower() if found else ""), said


def _turn_row(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    session: str,
    number: int,
    turn: int,
    game: dict,
    pos: dict,
    spent: float,
    sly: dict | None = None,
    firm: dict | None = None,
) -> dict[str, Any]:
    """One JSONL row per turn. Flat by design: the row IS the schema, so it takes the fields.

    `sly` is the sly_data the player handed back. The refusal ledger lives there and nowhere else
    — the player can see it while playing, but it is in-memory and per-session, so unless it is
    copied out here it is gone by the time the closer asks what went wrong. Read from the
    returned sly_data rather than persisted by a tool the player calls, because the runner already
    owns the turn stamp and every telemetry write, and the player should not spend a turn's tool
    call on bookkeeping.
    """
    money = pos.get("money") or {}
    built = pos.get("built") or {}
    earning = pos.get("earning") or {}
    return {
        "session": session,
        "session_number": number,
        "turn": turn,
        "game_date": int(game.get("game_date") or 0),
        "days_remaining": int(game.get("game_days_remaining") or 0),
        "company_value": int(money.get("company_value") or 0),
        "balance": int(money.get("balance") or 0),
        "loan": int(money.get("loan") or 0),
        # Named for what it is. The engine reports its own delivered total; nothing here
        # recomputes it, because a runner that recalculated the marking scheme would duplicate the
        # engine and disagree with it on the first edge case.
        # From the COMPANY row, not from `earning`, which carries neither. See company().
        "cargo_delivered": int((firm or {}).get("cargo_delivered_total") or 0),
        "performance_rating": int((firm or {}).get("performance_rating", -1) or 0),
        "quarter_cargo": int((firm or {}).get("q0_cargo") or 0),
        "quarter_income": int((firm or {}).get("q0_income") or 0),
        # The fleet split: one earner beside two losers is a different turn from three earners,
        # and the totals cannot tell them apart.
        "vehicles_earning": int(earning.get("vehicles_earning") or 0),
        "vehicles_losing": int(earning.get("vehicles_losing") or 0),
        "fleet_profit": int(earning.get("fleet_profit_this_year") or 0),
        "stations": int(built.get("stations") or 0),
        "vehicles": int(built.get("vehicles") or 0),
        "routes": int(built.get("routes") or 0),
        "problems": len(pos.get("problems") or []),
        # The KINDS, not just how many. A count says a turn was unhealthy; the kinds say whether
        # it was one stuck route or a fleet that has stopped moving, and only the second is worth
        # aborting a run over. The engine names them, so nothing here re-derives them.
        "problem_kinds": _tally(pos.get("problems") or [], "problem"),
        # `action -> times refused`. One call failing repeatedly is a different fault from many
        # calls each failing once, and a total hides the difference.
        "refusals": _tally((sly or {}).get("refusals") or [], "action"),
        "spend_usd": spent,
    }


def _tally(entries: list, field: str) -> dict[str, int]:
    """`{value of `field`: how many entries carried it}` — the shape the signatures are read from."""
    counts: dict[str, int] = {}
    for entry in entries:
        if isinstance(entry, dict):
            key = str(entry.get(field) or "?")
            counts[key] = counts.get(key, 0) + 1
    return counts


def _session_row(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    session: str,
    number: int,
    turns: int,
    game: dict,
    pos: dict,
    spent: float,
    aborted: bool,
    end_reason: str,
    scenario: str | None,
    mode: str,
    firm: dict | None = None,
) -> dict[str, Any]:
    money = pos.get("money") or {}
    earning = pos.get("earning") or {}
    return {
        "session": session,
        "vehicles_earning": int(earning.get("vehicles_earning") or 0),
        "vehicles_losing": int(earning.get("vehicles_losing") or 0),
        "session_number": number,
        "scenario": scenario or "",
        "mode": mode,
        "turns": turns,
        "game_days": int(game.get("game_date") or 0),
        "company_value": int(money.get("company_value") or 0),
        "total_cargo": int((firm or {}).get("cargo_delivered_total") or 0),
        "performance_rating": int((firm or {}).get("performance_rating", -1) or 0),
        "aborted": aborted,
        "end_reason": end_reason,
        "spend_usd": spent,
    }


def main() -> int:
    """Parse the run's arguments and play one session."""
    parser = argparse.ArgumentParser(description="Play one stepped nttd session")
    parser.add_argument("--session", required=True, help="Session id from `nttd benchmark`")
    parser.add_argument("--token", default=os.environ.get("NTTD_TOKEN", ""), help="Participant token")
    parser.add_argument("--network", default="nttd_air_player", help="nttd_air_player or nttd_rail_player")
    # Two networks, not one. Opening and closing need different TOOLS: an opener that could
    # promote a rule or advance the session could close a session it never watched.
    parser.add_argument("--opener", default="nttd_opener")
    parser.add_argument("--closer", default="nttd_closer")
    parser.add_argument("--watcher", default="nttd_watcher")
    parser.add_argument("--host", default=os.environ.get("NEURO_SAN_SERVER_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NEURO_SAN_SERVER_HTTP_PORT", "8085")))
    parser.add_argument("--scenario", default="", help="Scenario name, recorded in telemetry")
    # A backstop, not a schedule. The run ends when the world does; this only stops a loop that
    # would otherwise spin forever against a network that has stopped making progress.
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument(
        "--fresh", action="store_true", help="Reset the working playbooks from their seeds before starting"
    )
    parser.add_argument(
        "--new-session",
        action="store_true",
        help="Take the next session number rather than continuing the current one",
    )
    parser.add_argument("--no-watcher", action="store_true")
    parser.add_argument("--no-planner", action="store_true", help="Skip both session boundaries")
    args = parser.parse_args()

    if not args.token:
        parser.error("a participant token is required: --token or NTTD_TOKEN")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # The mode comes from the network being played, not from a separate flag that could disagree
    # with it. `nttd_air_player` plays air; there is no arrangement where those two differ.
    mode = "rail" if "rail" in args.network else "air"
    did = seed_playbooks.prepare(fresh=args.fresh, mode=mode)
    print(f"state: {did}")
    if args.new_session:
        print(f"opened session number {session_number.open_next()}")

    return play(args)


if __name__ == "__main__":
    sys.exit(main())
