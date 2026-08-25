"""Which session this is, read from a file rather than bound in a registry.

Its own module because almost every knowledge tool needs it and the alternative was binding it in
HOCON. That looked fine and was wrong: a registry argument is fixed for the life of the server, so
`session_number = 3` in a `.hocon` file means every session after the third is also recorded as the
third, the trial ids collide, and two sessions write into one turn log. The value has to come from
somewhere that changes without a restart, so it comes from disk.

Kept apart from `advance_session` so that a tool needing only the number does not import the
boundary machinery, and so there is no cycle between the two.

The counter is authoritative and is NOT derived from the telemetry log. A session that was
abandoned before it wrote a result row still used up a number, and deriving the next one from the
log would hand that number out twice.
"""

from __future__ import annotations

import logging
from datetime import datetime
from datetime import timezone

from coded_tools.nttd import paths
from coded_tools.nttd.file_io import FileIO

logger = logging.getLogger(__name__)


def current() -> int:
    """The session in progress. Zero before the first has been opened."""
    stored = FileIO.read_json(paths.SESSION_COUNTER_PATH, {}) or {}
    return FileIO.to_int(stored.get("session_number"), 0) or 0


def open_next() -> int:
    """Bump the counter and return the new number. Called by the runner, not by an agent.

    A model must never move this. The number identifies which session's turn log is being written
    and which trials belong to now; an agent that could increment it could orphan its own run.
    """
    number = current() + 1
    FileIO.write_json(
        paths.SESSION_COUNTER_PATH,
        {
            "session_number": number,
            "opened_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        logger,
    )
    return number


def resolve(supplied: object) -> int:
    """The session number a tool should use: what it was given, or what is on disk.

    Tools accept an override so a test can pin one, and fall back to the counter so a registry
    never has to carry a value that changes every session.
    """
    given = FileIO.to_int(supplied)
    return given if given is not None else current()
