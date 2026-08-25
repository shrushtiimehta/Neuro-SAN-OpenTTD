"""What happened, at two scales: this session so far, and every session ever.

The evidence half of the learning loop. A trial is judged against these numbers, so the shape of
what is recorded decides what can be learned.

**Two scopes, one module.** `SessionTelemetry` answers "how is this session going", which is what
the watcher needs mid-run. `RunTelemetry` answers "how does it compare to the best one so far",
which is what the planner needs at a boundary. They read the same files and differ only in which
rows they look at, so keeping them apart would mean two definitions of a turn row.

**Ranking is `company_value`, tie-broken by `total_cargo`.** Not a metric chosen here: it is what
the leaderboard ranks on, and both come straight from the game. Anything else this module reports is
context for a decision, not a score.

**Why the runner writes these rows rather than reading nttd's `result.parquet`.** Parquet would mean
installing the engine into this studio, and the whole point of the HTTP boundary is that it is not
needed. It also means the telemetry exists for a session that was abandoned halfway, which is
exactly the session a planner most wants to look at.

The rating deserves a note. OpenTTD answers -1 until it has a full quarter of history, and reading
that as a score makes a healthy young company look catastrophic, so it is passed through as "not
computed yet" rather than as a number.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools import paths
from coded_tools import session_number
from coded_tools.file_io import FileIO

logger = logging.getLogger(__name__)

# The game answers this until a full quarter has elapsed.
RATING_UNAVAILABLE = -1


# --- reading the logs ----------------------------------------------------------------------


def session_rows(include_archived: bool | None = None) -> list[dict[str, Any]]:
    """One row per finished session, newest last.

    Archived runs are included by default: the point of the seed surviving a fresh start is that
    progress accumulates, and a champion that reset with the logs would have the agents aiming at
    their own worst recent attempt.
    """
    if include_archived is None:
        include_archived = paths.include_archived()
    rows = [row for row in FileIO.read_jsonl(paths.SESSION_LOG_PATH) if isinstance(row, dict)]
    if include_archived:
        return rows
    return [row for row in rows if not row.get("archived")]


def turn_rows(session: int) -> list[dict[str, Any]]:
    """Every turn row for one session, in order."""
    return [row for row in FileIO.read_jsonl(paths.turn_log(session)) if isinstance(row, dict)]


def rank_key(row: dict[str, Any]) -> tuple[int, int]:
    """How the board orders two runs: company value, then cargo as the tiebreak."""
    return (
        FileIO.to_int(row.get("company_value"), 0) or 0,
        FileIO.to_int(row.get("total_cargo"), 0) or 0,
    )


def champion(include_archived: bool | None = None) -> dict[str, Any] | None:
    """The best session so far, or None when none has finished."""
    rows = [row for row in session_rows(include_archived) if not row.get("aborted")]
    if not rows:
        # An aborted session is still better evidence than nothing when it is all there is.
        rows = session_rows(include_archived)
    return max(rows, key=rank_key) if rows else None


def readable_rating(value: Any) -> Any:
    """The rating, or a phrase when the game has not computed one yet."""
    number = FileIO.to_int(value, RATING_UNAVAILABLE)
    return "not computed yet" if number is None or number <= RATING_UNAVAILABLE else number


def headline(row: dict[str, Any]) -> dict[str, Any]:
    """The figures a decision turns on, named the same way everywhere."""
    return {
        "session": row.get("session", ""),
        "session_number": row.get("session_number"),
        "company_value": FileIO.to_int(row.get("company_value"), 0),
        "total_cargo": FileIO.to_int(row.get("total_cargo"), 0),
        "performance_rating": readable_rating(row.get("performance_rating")),
        "game_days": FileIO.to_int(row.get("game_days"), 0),
        "turns": FileIO.to_int(row.get("turns"), 0),
        "mode": row.get("mode", ""),
        "scenario": row.get("scenario", ""),
        "aborted": bool(row.get("aborted")),
        "end_reason": row.get("end_reason", ""),
        "spend_usd": FileIO.to_float(row.get("spend_usd"), 0.0),
    }


# --- the tools -----------------------------------------------------------------------------


class RunTelemetry(CodedTool):
    """Every finished session, the best one, and how the last one compared to it."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Args (from the model): none. Args (from the registry): none."""
        del args, sly_data

        rows = session_rows()
        if not rows:
            return {
                "status": "ok",
                "sessions": 0,
                "note": (
                    "no session has finished yet, so there is no baseline to beat. Plan from the "
                    "playbook and say plainly that this is the first run."
                ),
            }

        best = champion()
        last = rows[-1]
        report: dict[str, Any] = {
            "status": "ok",
            "sessions": len(rows),
            "best_so_far": headline(best) if best else None,
            "most_recent": headline(last),
            "history": [headline(row) for row in rows[-8:]],
            "ranked_on": (
                "company_value, with total_cargo breaking a tie. Both come straight from the "
                "game; nothing here recomputes the marking scheme."
            ),
        }
        if best and best is not last:
            report["last_against_best"] = {
                "company_value": rank_key(last)[0] - rank_key(best)[0],
                "total_cargo": rank_key(last)[1] - rank_key(best)[1],
                "note": "negative means the last session was worse than the best one.",
            }
        return report

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)


class SessionTelemetry(CodedTool):
    """How the session in progress is going, and how it tracks against the best one.

    The comparison is the useful part, and it is made at the SAME game day rather than against a
    final figure. A session 90 days in is not behind a finished one; it is 90 days in, and a
    watcher told otherwise will abort a run that is doing fine.
    """

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Args: `session_number`, optional — defaults to the counter on disk."""
        del sly_data
        number = session_number.resolve(args.get("session_number"))

        rows = turn_rows(number)
        if not rows:
            return {
                "status": "ok",
                "turns": 0,
                "note": "no turns have been recorded for this session yet.",
            }

        latest = rows[-1]
        here: dict[str, Any] = {
            "status": "ok",
            "turns": len(rows),
            "game_date": FileIO.to_int(latest.get("game_date"), 0),
            "days_remaining": FileIO.to_int(latest.get("days_remaining"), 0),
            "company_value": FileIO.to_int(latest.get("company_value"), 0),
            "cargo_delivered": FileIO.to_int(latest.get("cargo_delivered"), 0),
            "balance": FileIO.to_int(latest.get("balance"), 0),
            "loan": FileIO.to_int(latest.get("loan"), 0),
            "performance_rating": readable_rating(latest.get("performance_rating")),
            "built": {
                "stations": FileIO.to_int(latest.get("stations"), 0),
                "vehicles": FileIO.to_int(latest.get("vehicles"), 0),
                "routes": FileIO.to_int(latest.get("routes"), 0),
            },
            "problems_reported": FileIO.to_int(latest.get("problems"), 0),
            "spend_usd": round(sum(FileIO.to_float(r.get("spend_usd"), 0.0) for r in rows), 4),
        }

        # The trend over the last few turns, because a single reading cannot distinguish a
        # route that is filling up from one that will never carry anything.
        window = rows[-4:]
        if len(window) >= 2:
            here["trend_over_last_turns"] = {
                "turns": len(window),
                "cargo_delivered": (
                    FileIO.to_int(window[-1].get("cargo_delivered"), 0)
                    - FileIO.to_int(window[0].get("cargo_delivered"), 0)
                ),
                "company_value": (
                    FileIO.to_int(window[-1].get("company_value"), 0)
                    - FileIO.to_int(window[0].get("company_value"), 0)
                ),
            }

        here["against_best_at_the_same_day"] = self._compare(number, here["game_date"])
        return here

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _compare(self, number: int, game_date: int) -> dict[str, Any]:
        """The best session's figures at the same game day as this one has reached."""
        best = champion()
        if not best or best.get("session_number") == number:
            return {"note": "no earlier session to compare against."}
        best_number = FileIO.to_int(best.get("session_number"))
        if best_number is None:
            return {"note": "the best session has no turn log to compare against."}

        rows = turn_rows(best_number)
        at_or_before = [r for r in rows if FileIO.to_int(r.get("game_date"), 0) <= game_date]
        if not at_or_before:
            return {
                "note": (
                    f"session {best_number} is the best so far but has no turn recorded by day "
                    f"{game_date}, so there is nothing to compare at this point."
                )
            }
        mark = at_or_before[-1]
        return {
            "best_session_number": best_number,
            "its_game_date": FileIO.to_int(mark.get("game_date"), 0),
            "cargo_delivered": FileIO.to_int(mark.get("cargo_delivered"), 0),
            "company_value": FileIO.to_int(mark.get("company_value"), 0),
            "ahead_by": {
                "cargo_delivered": None,
                "company_value": None,
            },
            "note": (
                "compare against these, not against that session's final figures. A run 90 days "
                "in is not behind a finished one."
            ),
        }


# --- writing, called by the runner rather than by an agent ---------------------------------


def record_turn(row: dict[str, Any]) -> str | None:
    """Append one turn row. Returns an `ERROR:` string on failure, else None."""
    number = FileIO.to_int(row.get("session_number"), 0) or 0
    return FileIO.append_jsonl(paths.turn_log(number), {"kind": "turn", **row}, logger)


def record_session(row: dict[str, Any]) -> str | None:
    """Append one finished-session row. Returns an `ERROR:` string on failure, else None."""
    return FileIO.append_jsonl(paths.SESSION_LOG_PATH, {"kind": "session", **row}, logger)


def write_champion_file() -> dict[str, Any] | None:
    """Write the best session so far to `state/champion.json`, and return it.

    A file as well as a tool because the runner reads it too, to decide whether the session that
    just finished is worth keeping the playbook edits from.
    """
    best = champion()
    if best is None:
        return None
    FileIO.write_json(paths.CHAMPION_PATH, headline(best), logger)
    return best


def archive_marker(session: int) -> str:
    """Where a fresh start moves an old turn log to."""
    return os.path.join(paths.ARCHIVE_DIR, os.path.basename(paths.turn_log(session)))
