"""The documented failure signatures, detected rather than noticed.

Every trap in `nttd/docs/gameplay_guide.md` section 4 produced "a fleet that existed, had correct
orders, and delivered nothing" — a run that looks busy from the inside and scores nothing. They
are all cheap to detect and all easy to miss, which is the worst combination to leave to a model
reading a wall of numbers. So they are `if` statements here instead.

**This tool names what is wrong. It does not say what to do about it.**

That line is deliberate and it is the whole reason this lives in the knowledge layer rather than
growing into a strategy engine. What a signature *means for play* is exactly what the claims and
the playbooks are for: a rule earns its place by being tested and cited, not by being written into
Python by whoever last read the guide. A detector that also prescribed would compete with the
learning loop and win by default, because code outranks a playbook line in an agent's attention —
and it would do so with strategy nobody had tested. Detection is objective. The response is not,
and it is supposed to be learned.

Read-only over telemetry the runner already writes. No game action, no credentials — the same
split every tool in this package keeps.
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools import session_number
from coded_tools import telemetry

# How many consecutive turns a symptom must hold before it is reported.
#
# Not one. A single turn of zero cargo is the normal state of a route that was finished this turn
# and has not run yet, and reporting it would train everyone to ignore this tool. Three is enough
# to separate "still starting up" from "not working".
SUSTAINED_TURNS = 3

# How many times one action must be refused before the repetition is the story. The measured
# failure was 35 identical submissions; the guide's own example is `connect_rail: 22 submitted,
# 16 refused`. Four is well below both and still far above ordinary trial and error.
REPEAT_REFUSALS = 4

# What fraction of the fleet must be carrying a problem before it reads as fleet-wide rather than
# as a few bad vehicles. The signature being caught is `start_vehicle` called twice, which stops
# EVERY vehicle, so this is deliberately near the top.
FLEET_WIDE = 0.9

# A company value of exactly 1 is the engine's floor for assets-minus-loan gone negative. Not a
# rounding error and not a bug: the company owes more than it owns.
VALUE_FLOOR = 1


def _int(row: dict[str, Any], key: str) -> int:
    try:
        return int(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _tail(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    return rows[-count:] if len(rows) >= count else []


def _value_floor(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Company value pinned at the floor: assets minus loan has gone negative."""
    hit = [r for r in rows if _int(r, "company_value") == VALUE_FLOOR]
    if not hit:
        return None
    return {
        "signature": "company_value_at_floor",
        "what_the_engine_is_saying": (
            f"company value is exactly {VALUE_FLOOR} on {len(hit)} turn(s), most recently turn "
            f"{_int(hit[-1], 'turn')}. That is the engine's floor for assets minus loan going "
            "negative — the company owes more than it owns. Drawing more loan cannot raise it, "
            "because the loan is subtracted again."
        ),
        "turns": [_int(r, "turn") for r in hit][-8:],
    }


def _built_but_idle(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Stations exist, nothing is being delivered. The depot usually cannot reach the line."""
    recent = _tail(rows, SUSTAINED_TURNS)
    if not recent:
        return None
    if not all(_int(r, "stations") > 0 and _int(r, "cargo_delivered") == 0 for r in recent):
        return None
    last = recent[-1]
    return {
        "signature": "built_but_delivering_nothing",
        "what_the_engine_is_saying": (
            f"{_int(last, 'stations')} station(s) and {_int(last, 'vehicles')} vehicle(s) exist, "
            f"and cargo delivered has stayed at 0 for {len(recent)} turns. The guide's note on "
            "this one is to trace from the depot rather than between platforms."
        ),
        "turns": [_int(r, "turn") for r in recent],
    }


def _fleet_wide_stall(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Nearly every vehicle carrying a problem at once — the double-`start_vehicle` shape."""
    if not rows:
        return None
    last = rows[-1]
    vehicles, problems = _int(last, "vehicles"), _int(last, "problems")
    if vehicles <= 0 or problems < vehicles * FLEET_WIDE:
        return None
    return {
        "signature": "fleet_wide_stall",
        "what_the_engine_is_saying": (
            f"turn {_int(last, 'turn')}: {problems} problem(s) against {vehicles} vehicle(s) — "
            "the fault is fleet-wide, not a few bad vehicles. The guide's first trap is "
            "`start_vehicle` called twice, where the second call stops what the first started."
        ),
        "problem_kinds": dict(last.get("problem_kinds") or {}),
        "turns": [_int(last, "turn")],
    }


def _repeated_refusals(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """One call failing over and over, which a total hides."""
    if not rows:
        return None
    # The ledger is cumulative for the session, so the newest row carries the whole history.
    latest = dict(rows[-1].get("refusals") or {})
    repeated = {a: n for a, n in latest.items() if n >= REPEAT_REFUSALS}
    if not repeated:
        return None
    worst = max(repeated.items(), key=lambda pair: pair[1])
    return {
        "signature": "repeated_refusals",
        "what_the_engine_is_saying": (
            f"{worst[0]} has been refused {worst[1]} times. A call failing repeatedly is a "
            "different fault from many calls each failing once, and the totals hide it. The next "
            "attempt has to differ in whatever the error names."
        ),
        "refused_by_action": dict(sorted(repeated.items(), key=lambda p: -p[1])),
        "turns": [_int(rows[-1], "turn")],
    }


CHECKS = (_value_floor, _built_but_idle, _fleet_wide_stall, _repeated_refusals)


def run(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every signature that fires over these turn rows, in the order they are defined."""
    return [found for check in CHECKS if (found := check(rows))]


class Diagnose(CodedTool):
    """The documented failure signatures over one session's telemetry."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Args: `session_number`, optional — defaults to the counter on disk."""
        del sly_data
        number = session_number.resolve(args.get("session_number"))
        rows = telemetry.turn_rows(number)
        if not rows:
            return {
                "status": "ok",
                "session_number": number,
                "turns": 0,
                "note": f"no turns recorded yet for session {number}; nothing to diagnose.",
            }

        found = run(rows)
        reply: dict[str, Any] = {
            "status": "ok",
            "session_number": number,
            "turns": len(rows),
            "signatures": found,
        }
        if not found:
            reply["note"] = (
                "None of the known failure signatures fired. That is not the same as the run "
                "going well — it means none of the four traps that produce a busy-looking run "
                "worth nothing are present. Judge the numbers on their own."
            )
        else:
            reply["how_to_read_this"] = (
                "These are detections, not instructions. What to do about a signature is a "
                "question for the claims and the playbooks, where a rule has to be tested before "
                "it is relied on. Raise a claim rather than treating this as an answer."
            )
        return reply

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
