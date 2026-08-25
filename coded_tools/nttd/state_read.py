"""Read one knowledge file by its logical name.

The single entry point every agent uses to see what past sessions learned. A player agent reads
its own playbook and the trials in force; the watcher reads the same plus the telemetry; the
planner reads everything, because deciding what to promote means comparing the rule against the
outcome it produced.

**Line ranges and a character cap, because a playbook grows.** Promotion appends, so a playbook
that has run twenty sessions is longer than one that has run two, and the whole of it in every
turn is context spent on advice the agent has already followed. The cap is a backstop rather
than a plan: if a playbook is regularly hitting it, the promotion logic is keeping rules it
should have demoted, and truncating in silence would hide exactly that.

The reply echoes `file_path`. Not for the model, which has no use for it, but for the log: when
a run reads the wrong playbook the fastest way to see it is a transcript that says which file
came back.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd.file_io import FileIO
from coded_tools.nttd.name_map import NameMap


class StateRead(CodedTool):
    """Read a knowledge file the registry has named."""

    # A playbook or a ledger that has grown past this is a bug in promotion, not a file to
    # paste into a prompt.
    MAX_BODY_BYTES: ClassVar[int] = 4 * 1024 * 1024
    DEFAULT_MAX_CHARS: ClassVar[int] = 20_000

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Resolve `name` through the operator's `name_map` and return the body.

        Args (from the model): `name`, and optionally `start_line`, `end_line`,
        `max_content_chars`.
        Args (from the registry): `name_map`.
        """
        del sly_data

        problem = NameMap.validate(args)
        if problem is not None:
            return problem

        name = str(args["name"])
        path = NameMap.resolve(args)

        body = FileIO.read_capped(path, self.MAX_BODY_BYTES, self.logger)
        if body.startswith("ERROR:"):
            # A missing playbook is worth saying plainly rather than as a bare path error: on a
            # first-ever run it means the seeding step has not happened, which is a different
            # thing from a file the operator mapped wrongly.
            if "file_not_found" in body:
                return (
                    f"ERROR: nothing recorded yet for '{name}' ({path}). On a first session "
                    "this is expected: the seeding step has not run. Carry on without it and "
                    "say so rather than inventing what it would have said."
                )
            return body

        sliced, total_lines = self._slice(body, args.get("start_line"), args.get("end_line"))
        cap = FileIO.to_int(args.get("max_content_chars"), self.DEFAULT_MAX_CHARS) or self.DEFAULT_MAX_CHARS
        truncated = len(sliced) > cap
        if truncated:
            sliced = sliced[:cap]

        return {
            "status": "ok",
            "name": name,
            "file_path": path,
            "content": sliced,
            "line_count": total_lines,
            "truncated": truncated,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _slice(self, body: str, start: Any, end: Any) -> tuple[str, int]:
        """The requested inclusive line range, and how many lines the file has.

        The total is returned whatever the slice, so a model that asked for lines 1 to 50 of a
        400 line playbook can tell that there are 350 more rather than concluding it has read
        the whole thing.
        """
        lines = body.splitlines(keepends=True)
        total = len(lines)
        first = max(0, (FileIO.to_int(start, 1) or 1) - 1)
        last = min(total, FileIO.to_int(end, total) or total)
        if first >= last:
            return "", total
        return "".join(lines[first:last]), total
