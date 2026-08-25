"""What the commons currently holds, and which of it should not be trusted as-is.

The read side, and it does more than list. Three of the four gates are read-time concerns, so
this is where they land.

**Gate 3 — inherited knowledge tells you where to look, not what to conclude.** Every claim is
returned with the conditions it was established under, and any claim whose conditions differ from
the ones in force now is flagged `re_test_before_relying`. That flag is the mechanism that stops
a verdict established on a flat 256 map propagating silently onto a hilly 512 one.

**Gate 4 — don't idle on a cheap question.** Open claims and recorded open questions come back
together under `worth_probing`, so an agent with a spare action has somewhere to spend it other
than re-running settled work.

**Conflicts are shown, not resolved.** When a claim has revisions that disagree, all of them are
returned in order. A reader needs to see that session 3 supported what session 5 refuted, and
under which conditions each was written; collapsing that to the latest verdict is exactly the
silent propagation the whole scheme exists to prevent.

**A player agent sees the claim and its conditions; it does not see the criteria.** An agent told
"this is a hypothesis and here is what would falsify it" starts optimising for the criterion
instead of playing the game. `with_evidence` is bound only by the curator networks.
"""

from __future__ import annotations

import logging
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools import claims
from coded_tools import paths
from coded_tools.file_io import FileIO


class ReadClaims(CodedTool):
    """The commons: what stands, what conflicts, and what is worth testing next."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:  # pylint: disable=too-many-locals,too-many-branches
        # One linear gate-then-reply pass. Splitting it to satisfy a counter would
        # scatter a single decision across helpers and hide the order it is made in.
        """
        Args (from the model): `domain`, `status`, `conditions_now`.
        Args (from the registry): `with_evidence`.
        """
        del sly_data

        wanted_domain = str(args.get("domain") or "").strip().lower()
        if wanted_domain and wanted_domain not in paths.DOMAINS:
            return (
                f"ERROR: unknown_domain: '{wanted_domain}'. One of "
                f"{', '.join(sorted(paths.DOMAINS))}, or omit it for all."
            )
        wanted_status = str(args.get("status") or "").strip().lower()
        if wanted_status and wanted_status not in claims.STATUSES:
            return f"ERROR: unknown_status: one of {list(claims.STATUSES)}, or omit it."

        conditions_now = str(args.get("conditions_now") or "").strip()
        with_evidence = bool(args.get("with_evidence"))

        history = claims.fold(claims.read_all())
        if not history:
            return {
                "status": "ok",
                "count": 0,
                "claims": [],
                "note": (
                    "the commons is empty. Nothing has been established yet, so play the "
                    "playbook as written and say plainly that this is the first run."
                ),
            }

        listed: list[dict[str, Any]] = []
        conflicted: list[str] = []
        probe: list[dict[str, Any]] = []

        for claim_id in sorted(history):
            revisions = history[claim_id]
            latest = revisions[-1]
            if wanted_domain and latest.domain != wanted_domain:
                continue
            if wanted_status and latest.status != wanted_status:
                continue

            entry = (
                latest.summary()
                if with_evidence
                else {
                    "id": latest.id,
                    "domain": latest.domain,
                    "claim": latest.claim,
                    "status": latest.status,
                    "confidence": latest.confidence,
                    "conditions": latest.conditions,
                }
            )

            # Gate 3.
            reason = claims.needs_retest(latest, conditions_now)
            if reason:
                entry["re_test_before_relying"] = reason

            # Conflicting revisions, shown in full.
            statuses = {r.status for r in revisions}
            if len(revisions) > 1 and len(statuses) > 1:
                conflicted.append(claim_id)
                entry["revisions"] = [
                    {
                        "revision": r.rev,
                        "status": r.status,
                        "confidence": r.confidence,
                        "conditions": r.conditions,
                        "evidence": r.evidence,
                    }
                    for r in revisions
                ]
                entry["conflict"] = (
                    "revisions of this claim disagree. Both are kept. Read the conditions each "
                    "was written under before relying on either; do not inherit the latest "
                    "verdict just because it is latest."
                )

            listed.append(entry)

            # Gate 4.
            if latest.status == "open" or latest.confidence == "low":
                probe.append(
                    {
                        "id": latest.id,
                        "claim": latest.claim,
                        "why": (
                            "open"
                            if latest.status == "open"
                            else f"only {latest.confidence} confidence — "
                            f"{len(latest.varied)} varied condition(s) so far"
                        ),
                        "re_test_when": latest.retest_when,
                    }
                )

        reply: dict[str, Any] = {
            "status": "ok",
            "count": len(listed),
            "domain": wanted_domain or "all",
            "claims": listed,
        }
        if conflicted:
            reply["claims_with_conflicting_revisions"] = conflicted
        if probe:
            reply["worth_probing"] = probe
            reply["gate_4"] = (
                "these are open or weakly held, and testing one is affordable. Spend a spare "
                "action probing the most informative of them rather than re-running settled "
                "work — and coordinate, so two agents do not run the same test."
            )

        questions = FileIO.read_text(paths.OPEN_QUESTIONS_PATH).strip()
        if questions:
            reply["open_questions"] = questions[-2000:]

        if conditions_now:
            reply["conditions_compared_against"] = conditions_now
        else:
            reply["gate_3_warning"] = (
                "no 'conditions_now' was given, so nothing could be checked for stale "
                "inheritance. Pass the current scenario, mode and session so claims established "
                "elsewhere can be flagged."
            )
        return reply

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
