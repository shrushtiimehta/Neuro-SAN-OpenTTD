"""The commons: one claim per record, and the gates that decide what may be written.

This replaces the older trial/outcome files. The difference is not cosmetic. The old schema let a
session write `falsified` with a forty-character note, which is exactly how a team gets locked
onto a confident-but-wrong early verdict — usually a "this doesn't work" that was really caused
by a condition nobody satisfied. Everything here exists to make that hard.

**The ledger is append-only, and the current view is computed rather than stored.**

Every write appends a block. A status change appends a NEW block for the same id rather than
editing the old one, so a claim that was supported in session 3 and refuted in session 5 has both
blocks, and a reader can see the order they arrived in. Folding is what produces "where does this
claim stand now": group by id, latest revision wins for the headline, and the whole history stays
visible underneath. Nothing is ever silently overwritten, because nothing is overwritten at all.

**A null result is not a refutation.** "Nothing happened" can equally mean the action never took
effect, a precondition was unmet, or the check happened under the wrong conditions. So `refuted`
requires `REFUTED_DESPITE`: a specific observation where the condition being dismissed WAS
satisfied and the effect still did not occur. Without it the write is downgraded to `open` and
the condition is recorded as an open question. That is Gate 1, and it is enforced here rather
than requested in a prompt.

**Repeats are not tests.** Trying something five times with the same suspected condition held
fixed is one test run five times; it re-runs any systematic error five times too. So confidence
is gated on `VARIED`: what was actually changed between observations. `high` needs at least two
varied conditions, `med` needs one. That is Gate 2.

**A negative claim with no way back is invalid.** Anything `refuted`, and anything at `low`
confidence, must carry `RE-TEST WHEN`: the trigger that reopens it. A claim that cannot be
reopened is team policy, not knowledge.

**Forbidden phrasing is rejected outright.** No "always", no "never", no "dead", and no claim
whose text tells a future agent to stop testing something. A wrong verdict frozen into policy is
the single failure this whole file is built to prevent, and the cheapest place to stop it is at
the point of writing.

The on-disk format is a block of `KEY: value` lines separated by `---`. Blocks rather than one
line per claim because there are ten fields and several are prose; text rather than JSON because
these files are read by a model, which reads a labelled line better than a nested object, and by
a person diffing session five against session three, which a re-serialised array ruins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from coded_tools.nttd import paths
from coded_tools.nttd.file_io import FileIO

# --- vocabulary ---------------------------------------------------------------------------

# Three, not five. The older schema had `not_applied` and `carried_over` beside `inconclusive`,
# and all three mean the same thing for what happens next: the question is still open. Collapsing
# them removes the temptation to file an untested idea as a soft failure.
STATUSES = ("open", "supported", "refuted")

# Ordered, so a comparison can ask "is this at least med".
CONFIDENCES = ("low", "med", "high")

ORIGINS = ("planner", "watcher")

# How many varied conditions each level of confidence demands. Gate 2, as a table.
#
# `high` needs two because one varied condition rules out one systematic error, and the claim is
# about to be relied on by every future session. `low` needs none, which is what makes it the
# honest default for a single observation.
VARIED_REQUIRED = {"low": 0, "med": 1, "high": 2}

# Words that turn a finding into policy. Matched on word boundaries so "nevertheless" and
# "deadline" are not caught, and case-insensitively because a model shouting NEVER is the case
# that matters.
_FORBIDDEN = re.compile(r"\b(always|never|dead)\b", re.IGNORECASE)

# Phrasing that tells a future agent to stop looking. Separate from the word list because these
# are the dangerous constructions rather than dangerous words, and a claim can contain one
# without using any forbidden word at all.
_STOP_TESTING = re.compile(
    r"\b(stop|don'?t|do not|no need to|pointless to|waste of time to)\s+"
    r"(testing|test|trying|try|retest|re-test|investigat\w*|explor\w*)\b",
    re.IGNORECASE,
)

# Fields a block may carry, in the order they are written. Order is fixed rather than sorted
# because these are read by people, and the reading order is: what is claimed, how it stands,
# under what, on what evidence, and what would reopen it.
FIELDS = (
    "ID",
    "REV",
    "DOMAIN",
    "ORIGIN",
    "CLAIM",
    "STATUS",
    "CONFIDENCE",
    "CONDITIONS",
    "EVIDENCE",
    "VARIED",
    "REFUTED_DESPITE",
    "RE-TEST WHEN",
    "NOTE",
)

_BLOCK_SPLIT = re.compile(r"^---\s*$", re.MULTILINE)
_FIELD_RE = re.compile(r"^([A-Z][A-Z_ -]*[A-Z]):\s*(.*)$")


# --- the record ---------------------------------------------------------------------------


@dataclass
class Claim:  # pylint: disable=too-many-instance-attributes
    # Thirteen fields because the on-disk block has thirteen. See FIELDS above:
    # the record and its serialised form are deliberately one-to-one.
    """One revision of one claim, as written."""

    id: str = ""
    rev: int = 0
    domain: str = ""
    origin: str = ""
    claim: str = ""
    status: str = "open"
    confidence: str = "low"
    conditions: str = ""
    evidence: str = ""
    varied: list[str] = field(default_factory=list)
    refuted_despite: str = ""
    retest_when: str = ""
    note: str = ""

    def as_block(self) -> str:
        """The record as it goes on disk."""
        pairs = [
            ("ID", self.id),
            ("REV", self.rev),
            ("DOMAIN", self.domain),
            ("ORIGIN", self.origin),
            ("CLAIM", self.claim),
            ("STATUS", self.status),
            ("CONFIDENCE", self.confidence),
            ("CONDITIONS", self.conditions),
            ("EVIDENCE", self.evidence),
            ("VARIED", "; ".join(self.varied)),
            ("REFUTED_DESPITE", self.refuted_despite),
            ("RE-TEST WHEN", self.retest_when),
            ("NOTE", self.note),
        ]
        lines = ["---"]
        for key, value in pairs:
            text = _one_line(value)
            if text:
                lines.append(f"{key}: {text}")
        return "\n".join(lines) + "\n"

    def summary(self) -> dict[str, Any]:
        """The record as a tool hands it back."""
        out: dict[str, Any] = {
            "id": self.id,
            "revision": self.rev,
            "domain": self.domain,
            "claim": self.claim,
            "status": self.status,
            "confidence": self.confidence,
            "conditions": self.conditions,
        }
        for key, value in (
            ("evidence", self.evidence),
            ("varied", self.varied),
            ("refuted_despite", self.refuted_despite),
            ("re_test_when", self.retest_when),
            ("note", self.note),
            ("origin", self.origin),
        ):
            if value:
                out[key] = value
        return out


def _one_line(value: Any) -> str:
    """A field value flattened to one line.

    Newlines are turned into spaces rather than escaped. The format has no continuation
    mechanism on purpose: a parser that had to handle one would be the next thing to get wrong,
    and every field here is a sentence rather than a paragraph.
    """
    return re.sub(r"\s+", " ", str(value or "")).strip()


# --- reading ------------------------------------------------------------------------------


def parse(text: str) -> list[Claim]:
    """Every revision in the ledger, in the order it was written."""
    found: list[Claim] = []
    for raw in _BLOCK_SPLIT.split(text):
        fields: dict[str, str] = {}
        for line in raw.splitlines():
            match = _FIELD_RE.match(line.strip())
            if match:
                fields[match.group(1)] = match.group(2).strip()
        if not fields.get("ID") or not fields.get("CLAIM"):
            # Not a record: the file header, a blank, a note somebody added by hand.
            continue
        found.append(
            Claim(
                id=fields["ID"],
                rev=FileIO.to_int(fields.get("REV"), 0) or 0,
                domain=fields.get("DOMAIN", ""),
                origin=fields.get("ORIGIN", ""),
                claim=fields["CLAIM"],
                status=(fields.get("STATUS") or "open").lower(),
                confidence=(fields.get("CONFIDENCE") or "low").lower(),
                conditions=fields.get("CONDITIONS", ""),
                evidence=fields.get("EVIDENCE", ""),
                varied=[v.strip() for v in (fields.get("VARIED") or "").split(";") if v.strip()],
                refuted_despite=fields.get("REFUTED_DESPITE", ""),
                retest_when=fields.get("RE-TEST WHEN", ""),
                note=fields.get("NOTE", ""),
            )
        )
    return found


def read_all() -> list[Claim]:
    """Every revision in the ledger, oldest first. Fold it to get where a claim stands now."""
    return parse(FileIO.read_text(paths.CLAIMS_PATH))


def fold(revisions: list[Claim]) -> dict[str, list[Claim]]:
    """`{id: [every revision, oldest first]}`.

    The current standing of a claim is the LAST revision; the earlier ones are its history and
    are never discarded. When two revisions disagree, both are here, which is the point: a
    reader can see that session 5 refuted what session 3 supported, and under which conditions
    each was written.
    """
    grouped: dict[str, list[Claim]] = {}
    for revision in revisions:
        grouped.setdefault(revision.id, []).append(revision)
    return grouped


def current(revisions: list[Claim] | None = None) -> dict[str, Claim]:
    """`{id: the latest revision}`."""
    grouped = fold(revisions if revisions is not None else read_all())
    return {claim_id: history[-1] for claim_id, history in grouped.items()}


def next_id(session: int, existing: set[str]) -> str:
    """The next free id for this session, as `s<session>_<n>`.

    Numbered within the session so an id says when the claim was first raised. A claim first
    raised in session 3 and revised in session 7 keeps `s3_1`, which is how a reader sees it took
    four sessions to settle.
    """
    index = 1
    while f"s{session}_{index}" in existing:
        index += 1
    return f"s{session}_{index}"


def append(claim: Claim, logger: Any = None) -> str | None:
    """Add one revision. `None` on success, an `ERROR:` string otherwise."""
    return FileIO.append_guarded(paths.CLAIMS_PATH, claim.as_block(), logger)


# --- the gates ----------------------------------------------------------------------------


@dataclass
class Verdict:
    """What the gates made of a proposed write."""

    ok: bool
    problems: list[str] = field(default_factory=list)
    # What the gates changed rather than rejected, so the caller can say so out loud.
    downgrades: list[str] = field(default_factory=list)


def check_wording(text: str) -> list[str]:
    """Forbidden phrasing in a claim. Empty when it is acceptable."""
    problems: list[str] = []
    banned = {m.group(0).lower() for m in _FORBIDDEN.finditer(text or "")}
    if banned:
        problems.append(
            f"the claim uses {sorted(banned)}. A claim is provisional, so it cannot be phrased "
            "as a universal or as something finished. Say the conditions it held under instead: "
            "'below 200k cash on flat maps' rather than 'always'."
        )
    if _STOP_TESTING.search(text or ""):
        problems.append(
            "the claim tells a future agent to stop testing something. That is the one thing a "
            "claim may never do — a wrong verdict frozen into policy is what this process exists "
            "to prevent. Down-rank it as low priority WITH a RE-TEST WHEN trigger instead."
        )
    return problems


def gate(claim: Claim) -> Verdict:
    """Run every gate over a proposed revision, adjusting it in place where it can be saved.

    Adjust-and-say rather than reject-outright wherever the honest version of the write is
    obvious: a `refuted` with no exhibited observation IS an `open`, and turning it into one
    loses nothing while refusing it loses the observation that was made. Only a write that
    cannot be repaired is rejected.
    """
    problems: list[str] = []
    downgrades: list[str] = []

    if not claim.claim.strip():
        problems.append("CLAIM is required: one testable sentence.")
    problems.extend(check_wording(claim.claim))

    if claim.status not in STATUSES:
        problems.append(f"STATUS must be one of {list(STATUSES)}.")
    if claim.confidence not in CONFIDENCES:
        problems.append(f"CONFIDENCE must be one of {list(CONFIDENCES)}.")
    if not claim.conditions.strip():
        problems.append(
            "CONDITIONS is required: the state this held under — the scenario, the mode, the "
            "session, what was present. Without it nobody can tell whether it applies to them."
        )

    # --- Gate 1: refuted needs an exhibited observation --------------------------------------
    if claim.status == "refuted" and not claim.refuted_despite.strip():
        claim.status = "open"
        downgrades.append(
            "STATUS was lowered from refuted to open. To record a refutation you must exhibit an "
            "observation where the condition you are dismissing WAS satisfied and the effect "
            "still did not occur (REFUTED_DESPITE). A failure while a required condition was "
            "unmet is untried, not refuted — so this is filed as open and the condition belongs "
            "in the open questions."
        )

    # --- Gate 2: confidence is bought with varied conditions ---------------------------------
    needed = VARIED_REQUIRED.get(claim.confidence, 0)
    if len(claim.varied) < needed:
        for level in ("med", "low"):
            if len(claim.varied) >= VARIED_REQUIRED[level]:
                downgrades.append(
                    f"CONFIDENCE was lowered from {claim.confidence} to {level}: "
                    f"{claim.confidence} needs {needed} varied condition(s) and "
                    f"{len(claim.varied)} were given. Repeating a test with the same condition "
                    "fixed is one test run twice, not two tests — it re-runs any systematic "
                    "error along with it."
                )
                claim.confidence = level
                break

    # --- RE-TEST WHEN is mandatory on anything negative or weak ------------------------------
    if not claim.retest_when.strip() and (claim.status == "refuted" or claim.confidence == "low"):
        problems.append(
            "RE-TEST WHEN is required for a refuted or low-confidence claim: name the trigger "
            "that reopens it — a variable crossing a threshold, a prerequisite appearing. A "
            "negative claim with no way back is not knowledge, it is policy."
        )

    if claim.status == "supported" and not claim.evidence.strip():
        problems.append("EVIDENCE is required to support a claim: the observations you made.")

    return Verdict(ok=not problems, problems=problems, downgrades=downgrades)


def needs_retest(claim: Claim, conditions_now: str) -> str:
    """Why this inherited claim should be re-tested before being relied on, or "".

    Gate 3. Two triggers, and the first is the one that catches most bad inheritance: the claim
    was established under conditions that are not the ones in force now. The comparison is
    deliberately crude — a token overlap rather than anything clever — because the useful output
    is "look at this yourself", and a cheap check that fires slightly too often is better than a
    subtle one that misses.
    """
    if not conditions_now.strip() or not claim.conditions.strip():
        return ""
    theirs = set(re.findall(r"[a-z0-9][a-z0-9._-]+", claim.conditions.lower()))
    ours = set(re.findall(r"[a-z0-9][a-z0-9._-]+", conditions_now.lower()))
    if not theirs:
        return ""
    shared = len(theirs & ours) / len(theirs)
    if shared < 0.5:
        return (
            f"established under '{claim.conditions}', which shares little with the conditions "
            "now. Inherited knowledge tells you where to look, not what to conclude — re-test "
            "before relying on it."
        )
    if claim.status == "refuted" or claim.confidence == "low":
        return (
            f"{claim.status} at {claim.confidence} confidence, reopens when: "
            f"{claim.retest_when or 'no trigger recorded'}. Check whether that has happened."
        )
    return ""
