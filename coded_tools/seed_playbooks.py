"""Put the working playbook back to its seed, and make sure the state directory exists.

Called by the runner before a session starts, not by an agent. It is the one step that decides
what a session begins knowing.

**Fresh start:** the working playbook is overwritten from the seed. The seed is baseline plus
every rule promoted so far, so a fresh start is not a reset to zero — it is a reset to
everything learned, with the current session's half-formed edits discarded.

**Resume:** the working copy is left exactly as it is, because a resumed session is mid-flight
and its playbook is the one its earlier turns have been reading.

The asymmetry is the point. Without it, a crash three hours into a session would either lose
every promotion made in it (if resume reseeded) or carry forward a playbook edited by a session
that never finished and was never judged (if a fresh start did not).

The trial files are created empty rather than seeded. A trial belongs to the session that
proposed it; carrying an unresolved one across a fresh start would put a hypothesis in force
that nothing is going to judge.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime
from datetime import timezone
from typing import Any

from coded_tools import paths
from coded_tools.file_io import FileIO

logger = logging.getLogger(__name__)

# The header each commons file opens with, so a file somebody opens by hand explains itself.
_HEADERS = {
    paths.CLAIMS_PATH: (
        "# The commons: one claim per record, append-only\n"
        "#\n"
        "# Every write appends a block. A status change appends a NEW revision for the same id\n"
        "# rather than editing the old one, so a claim supported in one session and refuted in a\n"
        "# later one has both blocks and a reader can see the order they arrived in. The current\n"
        "# standing of a claim is COMPUTED by folding this file, never stored.\n"
        "#\n"
        "# Fields: ID REV DOMAIN ORIGIN CLAIM STATUS CONFIDENCE CONDITIONS EVIDENCE VARIED\n"
        "#         REFUTED_DESPITE 'RE-TEST WHEN' NOTE\n"
    ),
    paths.OPEN_QUESTIONS_PATH: (
        "# Open questions\n"
        "#\n"
        "# Conditions that could not be ruled out, and cheap tests nobody has run. A refutation\n"
        "# that could not exhibit an observation lands here rather than being recorded as\n"
        "# settled, and an agent with a spare action looks here before repeating settled work.\n"
    ),
}


def for_mode(text: str, mode: str) -> str:
    """One seed, with the other modes' sections removed.

    ONE seed set, filtered — not two hand-maintained copies. The seeds share about 87% of their
    text, so a second copy would drift, and a rule fixed in one would stay wrong in the other.

    Keyed on the heading, which the seeds already use: `### Air: ...`, `### Rail: ...`. A section
    whose heading names a mode belongs to that mode; anything unheaded or generically headed
    belongs to every mode. `### Water and road, for when those modes are written` goes for both,
    because neither is written.
    """
    other = [m for m in paths.MODES if m != mode] + ["water and road"]
    out, keep = [], True
    for line in text.splitlines(keepends=True):
        if line.startswith("### "):
            head = line[4:].strip().lower()
            keep = not any(head.startswith(name) for name in other)
        # A learned line names the mode it was learned in; another mode's does not apply here.
        if keep and (paths.learned_mode(line) or mode) == mode:
            out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "".join(out))


def prepare(fresh: bool, mode: str | None = None) -> dict[str, Any]:
    """Get the state directory ready for a session. Returns what it did, for the run log."""
    os.makedirs(paths.STATE_DIR, exist_ok=True)
    os.makedirs(paths.LOG_DIR, exist_ok=True)

    did: dict[str, Any] = {"fresh": fresh}

    # One playbook per agent, so this loops. Each is handled independently: a missing seed for
    # one section must not stop the other five being reset, because a session that starts with
    # five good playbooks and one absent is playable and one that refuses to start is not.
    mode = paths.set_active_mode(mode) if mode else paths.active_mode()
    did["mode"] = mode

    outcome: dict[str, str] = {}
    for section in paths.SECTIONS:
        source, working = paths.seed(section), paths.playbook(section)
        if not os.path.exists(source):
            outcome[section] = "seed_missing"
            logger.warning("No seed at %s; %s is left as-is", source, working)
        elif fresh or not os.path.exists(working):
            FileIO.ensure_parent(working)
            with open(source, encoding="utf-8") as handle:
                body = handle.read()
            with open(working, "w", encoding="utf-8") as handle:
                handle.write(for_mode(body, mode))
            outcome[section] = "reseeded"
        else:
            outcome[section] = "kept"
    did["playbooks"] = outcome

    # NEVER truncated, on a fresh start or otherwise. The commons is the record of what has
    # been learned across every run, and the whole point of the seeds surviving a fresh start is
    # that knowledge accumulates. A reset that wiped this would make every run session one.
    created: list[str] = []
    for path, header in _HEADERS.items():
        if not os.path.exists(path):
            FileIO.write_guarded(path, header, logger)
            created.append(os.path.basename(path))
    did["commons_created"] = created

    return did


def snapshot(tag: str, stats: dict[str, Any] | None = None) -> str | None:
    """Copy the working playbook into the history directory. Returns the directory, or None.

    Taken at every session boundary and never deleted. The value is diffing two of them: when a
    run gets worse, the question is which promoted rule did it, and a directory per boundary is
    what makes that answerable. They are small — one markdown file each.
    """
    present = [s for s in paths.SECTIONS if os.path.exists(paths.playbook(s))]
    if not present:
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(tag or "boundary"))
    where = os.path.join(paths.HISTORY_DIR, f"{stamp}_{safe}")
    os.makedirs(where, exist_ok=True)
    for section in present:
        shutil.copyfile(paths.playbook(section), os.path.join(where, f"playbook_{section}.md"))
    # The commons and the compiled plan go in beside the playbooks: a boundary snapshot
    # is only diffable if it holds the evidence as well as the conclusions.
    for path in (paths.CLAIMS_PATH, paths.BEST_PLAN_PATH, paths.OPEN_QUESTIONS_PATH):
        if os.path.exists(path):
            shutil.copyfile(path, os.path.join(where, os.path.basename(path)))
    if stats:
        FileIO.write_json(os.path.join(where, "stats.json"), stats, logger)
    return where
