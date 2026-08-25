"""Where the knowledge lives, and what the sections are.

One module, because a path spelled twice is a path that will be spelled differently once. Every
tool in the knowledge layer resolves its files through here.

**Three directories, and the difference between them is the whole design.**

`config_files/` holds the SEED. It is the hand-authored baseline plus, beneath a per-section
header, every rule a past session confirmed. This is the only directory that survives a fresh
start, so it is the memory that crosses runs.

`state/` holds the WORKING copy. A fresh start resets the playbook here from the seed; a resumed
run leaves it alone. Everything a session learns is written here first.

`logs/nttd/` holds the TELEMETRY: one JSONL row per turn, one per finished session. It is how
"the best session so far" is computed, and it is deliberately derived from what the runner
observed over HTTP rather than from nttd's own `result.parquet`, because reading parquet would
mean installing the engine into this studio and the whole point is that it is not needed.

**One playbook per agent, plus `common`.** An agent is handed only what its job requires: the
scout does not carry the retirement state machine and the fleet does not carry the water-crossing
failure. `common` is the exception and everybody reads it, because five copies of one rule become
five different rules.

**One append-only commons.** `claims.md` holds every revision of every claim; the current standing
of a claim is computed by folding the file rather than stored, so nothing is ever overwritten and
two revisions that disagree are both still readable. `current_best_plan.md` is the compiled
strategy, which names the claims it rests on and may not be more confident than the weakest of
them. `open_questions.md` holds what could not be settled.

A claim's `domain` is the playbook a supported claim would be promoted into.
"""

from __future__ import annotations

import os
import re
from typing import Final

# --- directories --------------------------------------------------------------------------

# Relative to the repository root, which is where `ns run` and the runner are started from.
# Relative rather than absolute so a checkout can be moved or cloned twice without editing
# anything, which is also how neuro-san-studio's own AGENT_MANIFEST_FILE is written.
CONFIG_DIR: Final = "coded_tools/nttd/config_files"
STATE_DIR: Final = "coded_tools/nttd/state"
HISTORY_DIR: Final = "coded_tools/nttd/state/playbook_history"
LOG_DIR: Final = "logs/nttd"

# --- the playbooks ------------------------------------------------------------------------

# ONE FILE PER AGENT, plus `common`, so an agent is handed only what its job requires.
#
# The alternative — one document with a section each — was tried first and abandoned. Every
# agent then read every section, so the scout carried the retirement state machine and the
# fleet carried the water-crossing failure, five sixths of it advice for somebody else. On a
# turn-per-request network that is paid for on every turn of every session.
#
# `common` is the exception and is read by everybody: the rules that hold whatever is being
# moved, and what the score measures. Five copies of one rule become five different rules, so
# there is one copy.


def playbook(section: str) -> str:
    """The working copy of one agent's playbook."""
    return os.path.join(STATE_DIR, f"playbook_{section}.md")


def seed(section: str) -> str:
    """One agent's seed: baseline plus everything promoted so far. Survives a fresh start."""
    return os.path.join(CONFIG_DIR, f"seed_playbook_{section}.md")


# One per agent in a player network. The names are the job rather than the class, so a section
# reads as advice to somebody with that job, and so the same playbook serves air and rail
# without either having to read past the other's strategy.
#
#   common      what holds whatever is being moved, and what the score measures
#   strategist  what matters now: expand, consolidate, or repair
#   scout       where a corridor should go, and which sites earn
#   builder     turning a chosen corridor into something that actually carries
#   fleet       what to buy, how many, and getting it moving
#   care        keeping what exists earning, and knowing when it cannot be saved
SECTIONS: Final = ("common", "strategist", "scout", "builder", "fleet", "care")

# What a trial's `domain` may be. The same tuple: a trial edits exactly one section.
DOMAINS: Final = SECTIONS

# The agent networks that hold a scratchpad. Each gets its own pad, bound in the registry, so
# one network cannot read or clobber another's note.
PADS: Final = ("player", "watcher", "planner")


# The heading beneath which promoted rules accumulate. One per file, at the foot of each
# playbook. Every seed ships with this line already present: the promoter appends under it and
# deliberately never creates it, so a typo in a seed surfaces as `section_missing` rather than as
# a second heading halfway down the file.
LEARNED_HEADER: Final = "### Learned rules"


def scratchpad(pad: str) -> str:
    """One network's note to its own next run."""
    return os.path.join(STATE_DIR, f"scratchpad_{pad}.md")


# What tags a promoted line. Demotion only touches lines carrying it, which is what stops a
# self-correcting loop from deleting the hand-authored baseline.
#
# Matched as a REGEX requiring the session digits, not as the substring "(learned s". The
# playbook's own header explains the convention and in doing so contains the literal text
# "(learned sN)", so a substring test called that documentation line a promoted rule and made
# it demotable. Requiring \d+ separates a real tag from prose about tags.
LEARNED_MARKER: Final = "(learned s"
_LEARNED_RE: Final = re.compile(r"\(learned s\d+\)")


def learned_tag(session_number: int) -> str:
    """The marker appended to a rule promoted in this session."""
    return f"{LEARNED_MARKER}{session_number})"


def is_learned(line: str) -> bool:
    """Whether this line was promoted by the loop, and may therefore be demoted by it."""
    return bool(_LEARNED_RE.search(line))


# --- the commons --------------------------------------------------------------------------

# ONE append-only ledger, replacing the three trial files.
#
# Every write appends a block; a status change appends a new revision for the same id rather than
# editing the old one. The current standing of a claim is COMPUTED by folding the ledger, so
# nothing is ever silently overwritten and two revisions that disagree are both still there.
#
# The old trial_strategies / _criteria / _outcome trio is gone. It split one record across three
# files, which meant a claim could exist in one and not the others, and the outcome file was the
# only append-only part — so a status could be rewritten with no trace.
CLAIMS_PATH: Final = os.path.join(STATE_DIR, "claims.md")

# The compiled working strategy: what to do now, linking to the claims it rests on. Revised by
# append, headline kept current. Deliberately NOT a master document that overrides the claims:
# its confidence may not exceed the confidence of the claim ruling out its biggest untested
# upside, and it says so at the top of itself.
BEST_PLAN_PATH: Final = os.path.join(STATE_DIR, "current_best_plan.md")

# Conditions that could not be ruled out, and cheap tests nobody has run. What Gate 1 pushes a
# premature refutation into, and what Gate 4 tells an idle agent to spend an action on.
OPEN_QUESTIONS_PATH: Final = os.path.join(STATE_DIR, "open_questions.md")

# Where the session counter, the best-so-far and this session's plan live.
SESSION_COUNTER_PATH: Final = os.path.join(STATE_DIR, "session_number.json")
CHAMPION_PATH: Final = os.path.join(STATE_DIR, "champion.json")
SESSION_PLAN_PATH: Final = os.path.join(STATE_DIR, "session_plan.md")

# --- telemetry ----------------------------------------------------------------------------


def turn_log(session_number: int) -> str:
    """The per-turn telemetry for one session.

    Named by session number so a session lives in exactly one file, and a resumed run appends
    to the one it was already writing rather than starting a second.
    """
    return os.path.join(LOG_DIR, f"run.s{session_number:03d}.jsonl")


# One row per FINISHED session: the final figures, which is what "best so far" is computed
# from. Append-only and never archived, because a champion that vanished when logs were
# rotated is a champion the next run cannot aim at.
SESSION_LOG_PATH: Final = os.path.join(LOG_DIR, "sessions.jsonl")

# Where archived per-session turn logs go on a fresh start.
ARCHIVE_DIR: Final = os.path.join(LOG_DIR, "prior-runs")


def include_archived() -> bool:
    """Whether sessions from earlier runs count towards the best-so-far.

    Default yes: the point of the seed surviving a fresh start is that progress accumulates,
    and a champion that reset with the logs would have the agents aiming at their own worst
    recent attempt. `NTTD_INCLUDE_ARCHIVED=0` asks the other question, which is useful when
    comparing two configurations rather than trying to improve one.
    """
    return os.environ.get("NTTD_INCLUDE_ARCHIVED", "1") != "0"
