"""Close the books on a session and open the next one.

The boundary of the learning loop, and the one place the session counter moves.

**There is no equivalent call in nttd, and that is the design.** The MAPs benchmark this pattern
comes from has an `advance_episode` that resets the park. nttd has nothing like it: a session is a
world generated from a scenario config, and the next one comes from the runner invoking
`nttd benchmark` again. So this tool does not touch the game at all. It rolls the knowledge — bumps
the counter, snapshots the playbook, refreshes the champion file — and the new world arrives from
somewhere else entirely.

**Call it last.** Resolve the trials first, then promote the confirmed ones, then this. The
snapshot it takes is the playbook as the promotions left it, which is the artifact worth keeping:
a directory per boundary, diffable against the one before, so that when a run gets worse the
question "which promoted rule did it" has an answer.

The counter lives in a file rather than being derived from the log, because a session that was
abandoned before writing a result row still used up a number. Deriving it would hand the same
number to two sessions and put their turn rows in one file.
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools import claims
from coded_tools import seed_playbooks
from coded_tools import session_number
from coded_tools import telemetry

logger = logging.getLogger(__name__)


# Re-exported so the boundary module reads as the place the boundary lives, while the counter
# itself has exactly one implementation.
current_number = session_number.current
open_next = session_number.open_next


class AdvanceSession(CodedTool):
    """Snapshot the playbook, refresh the champion, and report what the next session inherits."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Args (from the registry): `session_number`. Args (from the model): none."""
        del sly_data

        number = session_number.resolve(args.get("session_number"))

        still_open = {cid: c for cid, c in claims.current().items() if c.status == "open"}
        best = telemetry.write_champion_file()

        where = seed_playbooks.snapshot(
            tag=f"s{number:03d}-close",
            stats={
                "session_number": number,
                "closed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "claims_still_open": sorted(still_open),
                "champion": best,
            },
        )

        report: dict[str, Any] = {
            "status": "ok",
            "session_number": number,
            "playbook_snapshot": where or "none — no working playbook to snapshot",
            "champion": telemetry.headline(best) if best else None,
            "claims_still_open": sorted(still_open),
        }

        if still_open:
            report["warning"] = (
                f"{len(still_open)} claim(s) are still open and carry into the next "
                "session. That is fine when it is deliberate — a claim about whether a route pays "
                "cannot be settled in one session — but a claim nobody has looked at is "
                "different. Revise anything the evidence can now speak to."
            )
        if not best:
            report["note"] = "no finished session has been recorded, so the next one has no baseline to beat."
        return report

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
