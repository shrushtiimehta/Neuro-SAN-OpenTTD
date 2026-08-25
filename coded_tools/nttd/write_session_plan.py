"""The plan for this session, written once at the start and read by every turn.

What the strategist reads first, before the playbook and before the position. The playbook says what
is true in general; this says what THIS session is going to do about it, given how the last one went
and what the best one managed.

**Why a file and not a prompt.** The player network is invoked once per turn and only its front man
keeps any history, so a plan stated in turn one is gone by turn three. Written down, it is read by
every turn from the same place, and the twentieth turn is still playing the plan the first one
committed to rather than a fresh interpretation of the same position.

That was the measured failure it exists to prevent: without a written plan every turn re-derived its
strategy from the same observation and arrived somewhere slightly different, and a run ended with
four half-built corridors instead of two finished ones.

**Overwrite, not append.** One session, one plan. An appended plan is a history of intentions, and a
strategist reading three of them at turn ten has no way to know which is current.

The plan is deliberately short. A page of prose is a page the strategist reads instead of the
position, and the trials in force already carry the specifics of what is being tested.
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd import paths
from coded_tools.nttd import session_number
from coded_tools.nttd.file_io import FileIO


class WriteSessionPlan(CodedTool):
    """Replace this session's plan with the one just decided."""

    MAX_CHARS: ClassVar[int] = 2_500
    MIN_CHARS: ClassVar[int] = 80

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Args (from the model): `mode`, `plan`, `what_changed_from_last_session`.
        Args (from the registry): `session_number`.
        """
        del sly_data

        plan = str(args.get("plan") or "").strip()
        if len(plan) < self.MIN_CHARS:
            return (
                "ERROR: invalid_input: 'plan' is too short to be a plan. Say what this session "
                "will do differently and why, in a few lines. Every turn will read this."
            )

        mode = str(args.get("mode") or "").strip().lower()
        changed = str(args.get("what_changed_from_last_session") or "").strip()
        number = session_number.resolve(args.get("session_number"))

        body = [
            f"# Session {number} plan",
            "",
            f"Written {datetime.now(timezone.utc).isoformat(timespec='seconds')}."
            + (f" Mode: {mode}." if mode else ""),
            "",
            "## The plan",
            "",
            plan[: self.MAX_CHARS],
            "",
        ]
        if changed:
            body += [
                "## What is different from the last session",
                "",
                changed[: self.MAX_CHARS],
                "",
            ]
        body += [
            "## How to read this",
            "",
            "This is the plan for the whole session. Follow it unless the position makes it "
            "plainly wrong, and if it does, say so rather than quietly playing something else. "
            "The trials in force carry the specifics of what is being tested.",
            "",
        ]

        problem = FileIO.write_guarded(paths.SESSION_PLAN_PATH, "\n".join(body), self.logger)
        if problem is not None:
            return problem

        return {
            "status": "ok",
            "session_number": number,
            "path": paths.SESSION_PLAN_PATH,
            "characters": len(plan),
            "truncated": len(plan) > self.MAX_CHARS,
            "note": "every turn of this session will read this. It replaced any earlier plan.",
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
