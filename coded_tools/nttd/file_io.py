"""File reads, writes and value coercion, in one place.

Every tool in the knowledge layer touches a file and coerces a model-supplied argument, and
without a shared home each grows its own `_int` and its own open-and-write block. Those drift:
the version this is modelled on ended up with three subtly different integer coercions before
they were consolidated.

**The load-bearing convention is that a failure comes back as a string, not an exception.** A
raised exception out of a coded tool reaches the model as a framework error with no reason
attached, which is the one form a model cannot act on. So the helpers here return
`"ERROR: <what_went_wrong>: <detail>"` and callers detect it with `str.startswith("ERROR:")`.
The prefix is machine-checkable and the rest is written for a reader.

`read_text` and `read_capped` differ deliberately. `read_text` answers "the body, or this
default" and never fails, which is what a tool wants when a missing file simply means "nothing
learned yet". `read_capped` distinguishes missing from unreadable from too-large, which is what
a tool wants when the file is the thing the model asked for and its absence is news.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any


class FileIO:
    """A namespace of static helpers. Nothing here holds state or wants instantiating."""

    # ----- value coercion ----------------------------------------------------------------

    @staticmethod
    def to_int(value: Any, default: int | None = None) -> int | None:
        """`int(value)`, or `default` when it will not coerce.

        `int()` already strips surrounding whitespace from a string, so this also covers the
        `int(str(value).strip())` spelling that parsing a regex group wants.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def to_float(value: Any, default: float = 0.0) -> float:
        """`float(value)`, or `default` when it will not coerce."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    # ----- directories and writing -------------------------------------------------------

    @staticmethod
    def ensure_parent(path: str) -> None:
        """Create the parent directory of `path`, if it has one."""
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    @staticmethod
    def write_text(path: str, content: str) -> None:
        """Overwrite `path`, creating parents. Raises `OSError`; see `write_guarded`."""
        FileIO.ensure_parent(path)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(content)

    @staticmethod
    def append_text(path: str, content: str) -> None:
        """Append to `path`, creating parents.

        Empty content is a no-op that does NOT create the file, so an append-only ledger is
        never brought into existence by something with nothing to say.
        """
        if not content:
            return
        FileIO.ensure_parent(path)
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(content)

    @staticmethod
    def write_guarded(path: str, content: str, logger: logging.Logger | None = None) -> str | None:
        """Overwrite `path`. `None` on success, an `ERROR:` string otherwise."""
        try:
            FileIO.write_text(path, content)
            return None
        except OSError as failure:
            if logger is not None:
                logger.error("Could not write %s: %s", path, failure)
            return f"ERROR: could_not_write: {path}: {failure}"

    @staticmethod
    def append_guarded(path: str, content: str, logger: logging.Logger | None = None) -> str | None:
        """Append to `path`. `None` on success, an `ERROR:` string otherwise.

        Separate from `write_guarded` because the append-only ledgers are the files whose
        history is the whole value: an outcome row lost to a silent exception is a judgement
        the next session will make again from scratch.
        """
        try:
            FileIO.append_text(path, content)
            return None
        except OSError as failure:
            if logger is not None:
                logger.error("Could not append to %s: %s", path, failure)
            return f"ERROR: could_not_append: {path}: {failure}"

    # ----- reading -----------------------------------------------------------------------

    @staticmethod
    def read_text(path: str, default: str = "") -> str:
        """The body, or `default` when the file is missing or unreadable. Never raises."""
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return default

    @staticmethod
    def read_capped(path: str, max_bytes: int, logger: logging.Logger | None = None) -> str:
        """The body, or a descriptive `ERROR:` string, enforcing a size ceiling.

        The ceiling exists because these files are handed to a model. A playbook that has
        grown to a megabyte is a bug in the promotion logic rather than something to paste
        into a prompt, and saying so is more useful than truncating in silence.
        """
        if not os.path.exists(path):
            return f"ERROR: file_not_found: {path}."
        try:
            size = os.path.getsize(path)
        except OSError as failure:
            return f"ERROR: could_not_stat: {path}: {failure}"
        if size > max_bytes:
            return f"ERROR: file_too_large: {path} exceeds {max_bytes} bytes."
        try:
            with open(path, encoding="utf-8") as handle:
                return handle.read()
        except OSError as failure:
            if logger is not None:
                logger.error("Could not read %s: %s", path, failure)
            return f"ERROR: could_not_read: {path}: {failure}"

    # ----- json --------------------------------------------------------------------------

    @staticmethod
    def read_json(path: str, default: Any = None) -> Any:
        """Parsed JSON, or `default` when the file is missing, unreadable or malformed.

        Malformed counts as missing on purpose. These files are written by this process and
        read by the next one; a half-written one means a run died mid-write, and the useful
        response is to carry on from the seed rather than to fail the session that found it.
        """
        body = FileIO.read_text(path)
        if not body:
            return default
        try:
            return json.loads(body)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def write_json(path: str, payload: Any, logger: logging.Logger | None = None) -> str | None:
        """Write JSON, sorted and indented. `None` on success, an `ERROR:` string otherwise.

        Sorted and indented because these files are read by people diffing two sessions to
        work out what the agents learned, and a one-line dump makes that unreadable.
        """
        return FileIO.write_guarded(path, json.dumps(payload, indent=2, sort_keys=True) + "\n", logger)

    @staticmethod
    def append_jsonl(path: str, row: Any, logger: logging.Logger | None = None) -> str | None:
        """Append one JSON object as a line. `None` on success, an `ERROR:` string otherwise."""
        try:
            line = json.dumps(row, sort_keys=True) + "\n"
        except (TypeError, ValueError) as failure:
            return f"ERROR: could_not_encode: {failure}"
        return FileIO.append_guarded(path, line, logger)

    @staticmethod
    def read_jsonl(path: str) -> list[Any]:
        """Every parsable line of a JSONL file, skipping any that will not parse.

        Skipping rather than failing: a truncated last line is what a killed process leaves
        behind, and the two hundred good rows above it are still the run's history.
        """
        rows: list[Any] = []
        for line in FileIO.read_text(path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except (ValueError, TypeError):
                continue
        return rows
