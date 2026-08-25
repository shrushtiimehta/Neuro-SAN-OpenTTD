"""Record a claim, or revise one, with the gates applied.

The only way anything enters the commons. Both the planner (at a session boundary) and the
watcher (mid-session) use it, and the gates are identical for both — an observation made
mid-session is not held to a lower standard than one made at a boundary.

**Revising is the same call as logging.** Pass an existing `id` and this appends a new revision
rather than editing the old one, which is what keeps the ledger append-only. Two revisions that
disagree both survive; folding decides which is current, and the history stays readable
underneath.

**The gates adjust rather than refuse, where the honest write is obvious.** A `refuted` with no
exhibited observation IS an `open`, so it is filed as one and the caller is told why. Refusing it
outright would lose the observation that was actually made. Only a write that cannot be repaired
— no claim text, no conditions, a forbidden phrasing, a negative with no way back — is rejected.

What comes back always says what the gates changed. A tool that quietly downgraded a confidence
would teach the caller nothing, and next session it would ask for `high` again.
"""

from __future__ import annotations

import logging
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd import claims
from coded_tools.nttd import paths
from coded_tools.nttd import session_number
from coded_tools.nttd.file_io import FileIO


class LogClaim(CodedTool):
    """Add a claim to the commons, or revise one that is already there."""

    # How many claims may be open at once. A session testing nine things is testing nothing:
    # whatever happens, several will have fired together and no outcome can be attributed.
    MAX_OPEN: ClassVar[int] = 6

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:  # pylint: disable=too-many-locals,too-many-branches
        # One linear gate-then-reply pass. Splitting it to satisfy a counter would
        # scatter a single decision across helpers and hide the order it is made in.
        """
        Args (from the model): `claim`, `domain`, `conditions`, `status`, `confidence`,
        `evidence`, `varied`, `refuted_despite`, `re_test_when`, `note`, and `id` to revise.
        Args (from the registry): `origin`.
        """
        del sly_data

        domain = str(args.get("domain") or "").strip().lower()
        if domain not in paths.DOMAINS:
            return f"ERROR: invalid_input: 'domain' must be one of {sorted(paths.DOMAINS)}."

        origin = str(args.get("origin") or "planner").strip().lower()
        if origin not in claims.ORIGINS:
            origin = "planner"

        session = session_number.resolve(args.get("session_number"))
        existing = claims.current()

        claim_id = str(args.get("id") or "").strip()
        revising = bool(claim_id)
        if revising and claim_id not in existing:
            return {
                "status": "not_found",
                "id": claim_id,
                "known": sorted(existing),
                "why": (
                    "no claim with that id is in the commons. Omit 'id' to raise a new one, or read the commons first."
                ),
            }
        if not revising:
            open_now = [c for c in existing.values() if c.status == "open"]
            if len(open_now) >= self.MAX_OPEN:
                return {
                    "status": "refused",
                    "reason": "too_many_open",
                    "open_count": len(open_now),
                    "limit": self.MAX_OPEN,
                    "why": (
                        f"{len(open_now)} claims are already open and the limit is "
                        f"{self.MAX_OPEN}. A session testing more than that can attribute no "
                        "outcome to any of them. Resolve one, or revise an existing claim "
                        "instead of raising another."
                    ),
                    "open": [f"{c.id}: {c.claim}" for c in sorted(open_now, key=lambda c: c.id)],
                }
            claim_id = claims.next_id(session, set(existing))

        varied = args.get("varied")
        if isinstance(varied, str):
            varied = [part.strip() for part in varied.split(";") if part.strip()]
        elif isinstance(varied, list):
            varied = [str(part).strip() for part in varied if str(part).strip()]
        else:
            varied = []

        record = claims.Claim(
            id=claim_id,
            rev=session,
            domain=domain,
            origin=origin,
            claim=str(args.get("claim") or "").strip(),
            status=str(args.get("status") or "open").strip().lower(),
            confidence=str(args.get("confidence") or "low").strip().lower(),
            conditions=str(args.get("conditions") or "").strip(),
            evidence=str(args.get("evidence") or "").strip(),
            varied=varied,
            refuted_despite=str(args.get("refuted_despite") or "").strip(),
            retest_when=str(args.get("re_test_when") or "").strip(),
            note=str(args.get("note") or "").strip(),
        )

        verdict = claims.gate(record)
        if not verdict.ok:
            refusal: dict[str, Any] = {
                "status": "refused",
                "id": claim_id if revising else "(not assigned)",
                "problems": verdict.problems,
                "why": (
                    "nothing was written. Fix these and call again — the gates exist so that a "
                    "later session can trust what it reads here."
                ),
            }
            if verdict.downgrades:
                # Reported on the FAILURE path too, because the gates cascade: a confidence
                # lowered to `low` then makes RE-TEST WHEN mandatory, and a caller shown only
                # the second half sees "low confidence needs a trigger" after asking for high,
                # cannot tell its confidence was moved, and re-sends the same request.
                refusal["the_gates_also_changed_this"] = verdict.downgrades
                refusal["read_these_together"] = (
                    "one of these problems is a CONSEQUENCE of the change above it. Fix the "
                    "cause: either supply what the higher confidence needs, or accept the lower "
                    "one and give it a re-test trigger."
                )
            return refusal

        problem = claims.append(record, self.logger)
        if problem is not None:
            return problem

        # A downgraded refutation leaves a live question behind. Recorded where an idle agent
        # will look for something worth probing, rather than lost in the reply to one turn.
        # Falsy, not == "". An absent key gives None, and a caller that omitted the field
        # entirely is precisely the one whose refutation was just downgraded — so the
        # equality test missed every case it was written for.
        if verdict.downgrades and record.status == "open" and not record.refuted_despite:
            FileIO.append_guarded(
                paths.OPEN_QUESTIONS_PATH,
                f"- [{record.id}] {record.claim} — could not be refuted: no observation was "
                f"exhibited where the doubted condition was satisfied. Conditions: "
                f"{record.conditions}\n",
                self.logger,
            )

        reply: dict[str, Any] = {
            "status": "ok",
            "id": record.id,
            "revision": record.rev,
            "recorded_as": record.status,
            "confidence": record.confidence,
            "action": "revised" if revising else "raised",
        }
        if verdict.downgrades:
            reply["the_gates_changed_this"] = verdict.downgrades
        if revising:
            history = claims.fold(claims.read_all()).get(record.id, [])
            reply["revisions_now"] = len(history)
            reply["note"] = (
                "the earlier revision is still in the ledger. Nothing here is overwritten, so a "
                "later reader can see both views and the order they arrived in."
            )
        return reply

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
