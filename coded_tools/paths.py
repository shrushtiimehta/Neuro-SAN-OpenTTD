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
CONFIG_DIR: Final = "coded_tools/config_files"
STATE_DIR: Final = "state"
HISTORY_DIR: Final = "state/playbook_history"
# TRANSIENT ONLY. Server stdout, engine stdout, the agents' thinking — output you read while
# something is going wrong and delete afterwards. Nothing here is required for the next session
# to run, which is the test for whether a file belongs in logs/ or in state/.
LOG_DIR: Final = "logs/nttd"

# MAINTAINED. The measured record: per-turn telemetry, the finished-session rows the champion is
# computed from, and the archive a fresh start moves old runs into. All of it has to survive a
# `rm -rf logs/`, because the next session reads it to know what beating the best one means.
TELEMETRY_DIR: Final = "state/telemetry"

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


# The mode being played, written by the runner at session start and read by everything else.
#
# Air and rail need SEPARATE playbooks, and the reason is not the tokens — it is that
# `promote_claim` takes a `domain` and no mode, so a rule an air session learned would land in
# the same file a rail session reads. Claims are condition-gated by Gate 3 and would be flagged;
# a promoted playbook line is just text and would not be. That is the leak this closes.
#
# Resolved HERE rather than passed through every tool, because one planner network serves both
# modes — it cannot be bound to one in its registry — and a tool that took a mode argument would
# be a tool a model could get wrong.
MODE_PATH: Final = os.path.join(STATE_DIR, "mode")
MODES: Final = ("air", "rail")
DEFAULT_MODE: Final = "air"


def active_mode() -> str:
    """Which mode this session is playing. Falls back to air if nothing has been written."""
    try:
        with open(MODE_PATH, encoding="utf-8") as handle:
            mode = handle.read().strip().lower()
    except OSError:
        return DEFAULT_MODE
    return mode if mode in MODES else DEFAULT_MODE


def set_active_mode(mode: str) -> str:
    """Record the mode for this session. The runner calls this before anything else reads it."""
    mode = (mode or "").strip().lower()
    if mode not in MODES:
        mode = DEFAULT_MODE
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(MODE_PATH, "w", encoding="utf-8") as handle:
        handle.write(mode + "\n")
    return mode


def mode_dir(mode: str | None = None) -> str:
    """Where one mode's working playbooks live."""
    return os.path.join(STATE_DIR, mode or active_mode())


def playbook(section: str) -> str:
    """The working copy of one agent's playbook."""
    return os.path.join(mode_dir(), f"playbook_{section}.md")


def seed(section: str) -> str:
    """One agent's hand-authored baseline. READ-ONLY: no tool writes here.

    It used to be "baseline plus everything promoted so far", with `promote_claim` appending
    learned rules to it. That put model-generated text into a hand-authored file shipped inside
    the package, mixed both modes' findings into one file, and made the per-mode split depend on
    parsing a tag out of a line. What the loop learns is state, and it lives in state/.
    """
    return os.path.join(CONFIG_DIR, f"seed_playbook_{section}.md")


def learned(section: str, mode: str | None = None) -> str:
    """What the loop promoted for one job in one mode. Append-only, and what survives `--fresh`.

    Separate from the baseline so the two can never be confused: the baseline is authored and
    cited, this is earned and revocable, and only lines here are demotable. Separate per mode
    because a rule an air session established is not rail doctrine — the claim that produced it
    carries CONDITIONS and Gate 3 would flag it, but a promoted line is just text.
    """
    return os.path.join(STATE_DIR, "learned", mode or active_mode(), f"playbook_{section}.md")


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

# The mode is part of the tag, because `promote_claim` mirrors every learned line back into the
# SHARED seed so it survives a `--fresh`. Without the mode in the tag, a rule an air session
# learned would be seeded into rail's playbook on the next reset — around the per-mode split
# rather than through it. The mode group is optional so a tag written before this still matches.
_LEARNED_RE: Final = re.compile(r"\(learned s\d+(?: (?:air|rail))?\)")
_LEARNED_MODE_RE: Final = re.compile(r"\(learned s\d+ (air|rail)\)")


def learned_tag(session_number: int, mode: str | None = None) -> str:
    """The marker appended to a rule promoted in this session, naming the mode it was learned in."""
    return f"{LEARNED_MARKER}{session_number} {mode or active_mode()})"


def learned_mode(line: str) -> str | None:
    """Which mode a promoted line was learned in, or None for an untagged or baseline line."""
    found = _LEARNED_MODE_RE.search(line)
    return found.group(1) if found else None


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
    return os.path.join(TELEMETRY_DIR, f"run.s{session_number:03d}.jsonl")


# One row per FINISHED session: the final figures, which is what "best so far" is computed from.
# Append-only and never archived — a champion that vanished when logs were rotated is a champion
# the next run cannot aim at. That sentence was the argument for moving all of this out of logs/.
SESSION_LOG_PATH: Final = os.path.join(TELEMETRY_DIR, "sessions.jsonl")


# What the AGENTS built up, per turn, from the sly_data they hand back.
#
# Kept because nttd's own artifacts do not have it. `snapshots.parquet` records the world and
# `tiles.parquet` the raw map, but `sites` is the map as the scout SURVEYED it and `decisions` is
# what the strategist chose and why — the reasoning behind an action rather than the action.
# `actions.parquet` has an agent_id column and the workbench leaves it empty, so this is currently
# the only per-agent record there is.
def agent_log(session_number: int) -> str:
    """One JSONL row per turn of what the agents were holding."""
    return os.path.join(TELEMETRY_DIR, f"agents.s{session_number:03d}.jsonl")


# Where archived per-session turn logs go on a fresh start.
ARCHIVE_DIR: Final = os.path.join(TELEMETRY_DIR, "prior-runs")


def include_archived() -> bool:
    """Whether sessions from earlier runs count towards the best-so-far.

    Default yes: the point of the seed surviving a fresh start is that progress accumulates,
    and a champion that reset with the logs would have the agents aiming at their own worst
    recent attempt. `NTTD_INCLUDE_ARCHIVED=0` asks the other question, which is useful when
    comparing two configurations rather than trying to improve one.
    """
    return os.environ.get("NTTD_INCLUDE_ARCHIVED", "1") != "0"
