"""A few lines one network leaves for its own next run.

Every network here is invoked as a series of short, nearly historyless runs. The player takes
one turn per request; the watcher wakes at intervals; the planner runs twice a session, at the
start and at the end. So a plan that spans two runs has nowhere to live.

`sly_data` carries the *game* state between turns, and that is the right home for a staged plan
or a refusal ledger, because a coded tool enforces it. This is for the other thing: a sentence
of intent that only the next run of the same network can act on. "Sent 214 to the depot, sell it
next turn once it has arrived." "Watched the Tonwood trunk for 30 days; if it is still flat next
look, the corridor is the problem, not the aircraft."

**Read-and-clear.** Reading returns the note and deletes it, so a note is visible for exactly
one run. The alternative was an append log, and an append log of intentions becomes a wall of
stale advice within a session: the note from day 12 saying "buy two more aircraft when cash
allows" is actively wrong by day 200 and nothing was ever going to go back and retract it.

**One pad per network, bound in the registry.** The `pad` argument never comes from the model.
Without that the planner could read and clear the player's note, which is a data race with a
model on one end of it.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd import paths
from coded_tools.nttd.file_io import FileIO


class Scratchpad(CodedTool):
    """Write a note for this network's next run, or read and clear the one it left."""

    # Short on purpose. A pad is a note, and a note long enough to need scrolling is a plan
    # that belonged in a playbook or a decision that belonged in sly_data.
    MAX_LINES: ClassVar[int] = 6
    MAX_CHARS: ClassVar[int] = 800

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Write when given a `note`, read and clear when not.

        Args (from the model): `note`, optional.
        Args (from the registry): `pad`, one of player, watcher, planner.
        """
        del sly_data
        path = _path(args.get("pad"))
        note = str(args.get("note") or "").strip()

        if note:
            trimmed = self._trim(note)
            problem = FileIO.write_guarded(path, trimmed + "\n", self.logger)
            if problem is not None:
                return problem
            return {
                "status": "ok",
                "action": "written",
                "pad": _pad_name(args.get("pad")),
                "note": trimmed,
            }

        existing = FileIO.read_text(path).strip()
        cleared = True
        if existing:
            # TRUNCATED, not deleted. Both empty the pad, but a delete needs permission to
            # unlink and a truncate needs only the permission that just wrote the file. On a
            # read-only or restricted mount the delete fails while the write succeeds, and a
            # failed clear is the worst outcome available here: the note would be served again
            # every run forever, which is precisely the stale-advice problem read-and-clear
            # exists to prevent. Measured on a bind mount that refused unlink with EPERM.
            problem = FileIO.write_guarded(path, "", self.logger)
            cleared = problem is None
        reply: dict[str, Any] = {
            "status": "ok",
            "action": "read_and_cleared" if cleared else "read_but_not_cleared",
            "pad": _pad_name(args.get("pad")),
            "note": existing,
            "note_found": bool(existing),
        }
        if not cleared:
            # Said out loud rather than logged and forgotten. A pad that cannot be cleared will
            # repeat itself, and the network reading it should know that before acting on it a
            # second time.
            reply["warning"] = (
                "the pad could not be cleared, so this same note will come back next run. Treat it as possibly stale."
            )
        return reply

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _trim(self, note: str) -> str:
        """The note, cut to the line and character ceilings."""
        lines = [line for line in note.splitlines() if line.strip()][: self.MAX_LINES]
        return "\n".join(lines)[: self.MAX_CHARS]


def _pad_name(pad: Any) -> str:
    """The pad this is, defaulting to the player.

    Sanitised because `pad` reaches a filesystem path. It comes from the registry rather than
    the model, so this is defence against a typo in HOCON rather than against a prompt, but a
    typo in HOCON would otherwise create a third pad that silently shares nothing with either
    of the two that were meant.
    """
    cleaned = re.sub(r"[^a-z0-9_]", "", str(pad or "").lower())
    return cleaned if cleaned in paths.PADS else "player"


def _path(pad: Any) -> str:
    return paths.scratchpad(_pad_name(pad))
