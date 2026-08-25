"""The compiled working strategy: what to do now, and which claims it rests on.

One living document, revised by append, with the headline recommendation kept current. It is
what a strategist reads to know what to do; the claims are what it reads to know what is
actually established.

**It is not a master document.** That distinction is the whole reason this is a separate file
rather than a section of a playbook. A plan that overrode the claims would let a confident
summary outrank the evidence it was compiled from, and the summary is the part nobody re-checks.
So every recommendation here NAMES the claim ids it rests on, and the tool refuses one that names
none.

**Its confidence is capped by the claim ruling out its biggest untested upside.** That rule is
the interesting one and it is enforced: the plan may not claim `high` while the claim it cites
for its biggest untried alternative is still `open` or `low`. A plan cannot be more certain than
its least-tested assumption, and left unchecked that is exactly where over-confidence enters —
not in the individual claims, which are gated, but in the summary that quietly rounds them up.

**Revised by append.** Each revision is a new dated block; the file grows and the newest block at
the top is the current one. So a reader can see what the plan used to be, which is how you find
out whether a change of plan helped.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd import claims
from coded_tools.nttd import paths
from coded_tools.nttd import session_number
from coded_tools.nttd.file_io import FileIO

_SENTINEL = "<!-- REVISIONS BELOW, NEWEST FIRST -->"

_HEADER = """# Current best plan

The compiled working strategy. Revised by append: the newest block below is current, the older
ones are kept so a reader can see what the plan used to be and whether changing it helped.

**This does not override the claims.** Every recommendation names the claim ids it rests on, and
its confidence cannot exceed that of the claim ruling out its biggest untested upside. When this
and a claim disagree, the claim wins and this needs revising.

<!-- REVISIONS BELOW, NEWEST FIRST -->
"""


class WriteCurrentBestPlan(CodedTool):
    """Append a revision of the working strategy."""

    MAX_CHARS: ClassVar[int] = 3_000
    MIN_CHARS: ClassVar[int] = 120

    # Written as an id anywhere in the text: s3_1, s12_4.
    _ID_RE: ClassVar[re.Pattern] = re.compile(r"\bs\d+_\d+\b")

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:  # pylint: disable=too-many-locals,too-many-return-statements,too-many-branches,too-many-statements
        # One linear gate-then-reply pass. Splitting it to satisfy a counter would
        # scatter a single decision across helpers and hide the order it is made in.
        """
        Args (from the model): `headline`, `plan`, `rests_on` (claim ids),
        `biggest_untested_upside`, `upside_claim_id`, `confidence`.
        """
        del sly_data

        headline = str(args.get("headline") or "").strip()
        plan = str(args.get("plan") or "").strip()
        if not headline:
            return (
                "ERROR: invalid_input: 'headline' is required — the one recommendation this plan makes, in a sentence."
            )
        if len(plan) < self.MIN_CHARS:
            return "ERROR: invalid_input: 'plan' is too short. Say what to do, in what order, and what to leave alone."

        problems = claims.check_wording(headline) + claims.check_wording(plan)
        if problems:
            return {
                "status": "refused",
                "problems": problems,
                "why": "nothing was written. The plan is provisional too, and has to read as such.",
            }

        known = claims.current()
        cited = self._cited(args.get("rests_on"), plan, headline)
        if not cited:
            return (
                "ERROR: invalid_input: 'rests_on' is required — the claim ids this plan rests on. "
                "A recommendation that cites no claim is an opinion, and an opinion in this file "
                "would outrank the evidence it was supposed to be compiled from."
            )
        unknown = [c for c in cited if c not in known]
        if unknown:
            return {
                "status": "refused",
                "unknown_claim_ids": unknown,
                "known": sorted(known),
                "why": "a plan cannot rest on a claim that is not in the commons.",
            }

        confidence = str(args.get("confidence") or "low").strip().lower()
        if confidence not in claims.CONFIDENCES:
            confidence = "low"

        upside = str(args.get("biggest_untested_upside") or "").strip()
        upside_id = str(args.get("upside_claim_id") or "").strip()
        capped: str | None = None

        # The cap. Checked against the named upside claim when one is given, and against the
        # weakest cited claim otherwise — a plan resting on a low-confidence claim cannot itself
        # be high, however many well-established ones sit beside it.
        limiter = known.get(upside_id) if upside_id in known else None
        if limiter is None:
            weakest = min(
                (known[c] for c in cited),
                key=lambda c: claims.CONFIDENCES.index(c.confidence),
                default=None,
            )
            limiter = weakest
        if limiter is not None:
            ceiling = "low" if limiter.status == "open" else limiter.confidence
            if claims.CONFIDENCES.index(confidence) > claims.CONFIDENCES.index(ceiling):
                capped = (
                    f"confidence lowered from {confidence} to {ceiling}: it cannot exceed that of "
                    f"{limiter.id}, which is {limiter.status} at {limiter.confidence} and is the "
                    "claim bearing on this plan's biggest untested upside. A plan cannot be more "
                    "certain than its least-tested assumption."
                )
                confidence = ceiling

        session = session_number.resolve(args.get("session_number"))
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")

        block = [
            f"## Revision {session} — {stamp}",
            "",
            f"**{headline}**",
            "",
            f"Confidence: {confidence}. Rests on: {', '.join(sorted(cited))}.",
            "",
            plan[: self.MAX_CHARS],
            "",
        ]
        if upside:
            block += [
                f"Biggest untested upside: {upside}" + (f" (see {upside_id})" if upside_id else ""),
                "",
            ]
        block.append("")

        body = FileIO.read_text(paths.BEST_PLAN_PATH)
        if not body.strip():
            body = _HEADER + "\n"
        # Newest directly under the header, so the current plan is the first thing read and the
        # history sits below it. Anchored on a SENTINEL rather than on a sentence: the first
        # version matched header prose, the prose was worded differently by one word, every
        # revision silently fell through to the append branch, and the oldest plan ended up
        # presented as current. A comment cannot drift out of agreement with itself.
        new_block = "\n".join(block)
        cut = body.find(_SENTINEL)
        if cut == -1:
            # No sentinel: an older file, or one edited by hand. Rebuild the header around what
            # is there rather than appending underneath and leaving the newest at the bottom.
            updated = _HEADER + "\n" + new_block + "\n" + body.split(_SENTINEL)[-1].lstrip("\n")
        else:
            cut += len(_SENTINEL)
            updated = body[:cut] + "\n\n" + new_block + body[cut:]

        problem = FileIO.write_guarded(paths.BEST_PLAN_PATH, updated, self.logger)
        if problem is not None:
            return problem

        reply: dict[str, Any] = {
            "status": "ok",
            "revision": session,
            "path": paths.BEST_PLAN_PATH,
            "headline": headline,
            "confidence": confidence,
            "rests_on": sorted(cited),
        }
        if capped:
            reply["the_cap_applied"] = capped
        if not upside:
            reply["warning"] = (
                "no biggest untested upside was named. That field is what stops a plan settling "
                "on a local optimum: without it nothing records what this plan is choosing not "
                "to try."
            )
        return reply

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _cited(self, given: Any, *texts: str) -> list[str]:
        """Claim ids this plan rests on, from the argument and from the prose.

        Scraped from the text as well as taken from the field, because a plan that names `s3_1`
        in a sentence plainly rests on it and forgetting to repeat it in the list is a slip
        rather than a decision.
        """
        found: set[str] = set()
        if isinstance(given, str):
            found |= set(self._ID_RE.findall(given))
        elif isinstance(given, list):
            for item in given:
                found |= set(self._ID_RE.findall(str(item)))
        for text in texts:
            found |= set(self._ID_RE.findall(text))
        return sorted(found)
