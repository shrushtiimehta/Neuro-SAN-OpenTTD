"""The deterministic playbook editor: promotion and demotion.

The planner DECIDES what to change; this performs the edit. Splitting those two is what makes the
learning loop auditable: a promotion is a file diff with a CLAIM id attached, not a model rewriting
a document from memory.

**Two edits, and no way to overwrite anything.**

`add_line` appends a new rule under the learned-rules heading.
`remove_line` is DEMOTION — taking back a rule this loop promoted, once it has been refuted.
Without it the playbook only ever grows, and a loop that cannot un-learn is not learning, it is
accumulating.

**There is deliberately no `replace_line`.** A swap destroys the record it replaces, and a
destroyed record cannot be re-examined when later evidence contradicts the reason for the swap.
When two rules conflict, BOTH are kept: append the new one with its own conditions and lower the
confidence on the old, and let a refutation under Gate 1 be the only thing that removes either.
A rule superseded silently is a rule whose supersession nobody can audit.

**The baseline is protected.** Only lines tagged with the session that learned them can be removed. The hand-authored
sections of the seed can never be deleted by this tool, however confidently a model asks: the worst
case is a no-op reported as `skipped_not_learned`. That guarantee is why demotion can be handed to a
model at all.

**Every successful edit is mirrored into the seed.** The working playbook is reset from the seed on
a fresh start, so an edit that only landed in the working copy would vanish at the next boundary.
The mirror is what carries a confirmed rule across runs, and it is append-only: the seed must
already carry the section's learned-rules heading, and this never creates one. A missing heading is
reported rather than repaired, because creating it would put learned rules in a section that was
never meant to have any.

The mirror is best-effort. A seed problem never undoes the working-copy edit that already
succeeded — reporting a half-done promotion is better than pretending it did not happen.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.nttd import paths
from coded_tools.nttd import session_number
from coded_tools.nttd.file_io import FileIO


class PromoteClaim(CodedTool):
    """Promote a supported claim into a playbook, or demote a refuted one."""

    EDITS: ClassVar[tuple[str, ...]] = ("add_line", "remove_line")

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:  # pylint: disable=too-many-return-statements
        # One linear gate-then-reply pass. Splitting it to satisfy a counter would
        # scatter a single decision across helpers and hide the order it is made in.
        """
        Args (from the model): `domain` (which playbook), `edit_type`, `new_text`,
        `find_text` (remove_line only), `session_number` (add_line only).
        """
        del sly_data

        domain = str(args.get("domain") or "").strip().lower()
        if domain not in paths.SECTIONS:
            return f"ERROR: invalid_input: 'domain' must be one of {sorted(paths.SECTIONS)}."

        edit = str(args.get("edit_type") or "").strip()
        if edit == "replace_line":
            # Named specifically. It existed until the knowledge model went append-only, so a
            # model working from an older prompt will still reach for it, and "not a valid value"
            # would not tell it what to do instead.
            return (
                "ERROR: replace_line no longer exists: the playbooks are append-only. To supersede "
                "a rule, add_line the better one with its own conditions and leave the old one in "
                "place with lower confidence. Remove a rule only once it is refuted, with "
                "remove_line."
            )
        if edit not in self.EDITS:
            return f"ERROR: invalid_input: 'edit_type' must be one of {list(self.EDITS)}."

        new_text = str(args.get("new_text") or "").strip()
        if edit != "remove_line" and not new_text:
            return "ERROR: invalid_input: 'new_text' is required and must be non-empty."

        # Falls back to the counter on disk rather than demanding it. A registry cannot carry a
        # value that changes every session, and the alternative -- asking the model for it --
        # invites a promotion tagged with the wrong session, which mislabels the audit trail the
        # tag exists to provide.
        session = session_number.resolve(args.get("session_number")) if edit != "remove_line" else 0

        # One playbook per agent now, so the domain chooses the FILE rather than a heading
        # inside a shared one. That is what keeps a promotion scoped: a rule confirmed about
        # siting lands in the scout's file and is never read by the fleet.
        book = paths.playbook(domain)
        if not os.path.exists(book):
            return {
                "action_taken": "skipped_playbook_missing",
                "domain": domain,
                "line": "",
                "seed_mirror": "not_attempted",
            }

        body = FileIO.read_text(book)
        if not body:
            return f"ERROR: could_not_read: {book} is empty or unreadable."

        if edit == "remove_line":
            find = str(args.get("find_text") or "").strip()
            if not find:
                return "ERROR: invalid_input: remove_line requires 'find_text'."
            return self._demote(domain, book, body, find)

        line = f"- {new_text} {paths.learned_tag(session)}"

        # Refused before either edit, because the working playbook has no dedup of its own and
        # a rule promoted twice is a rule that cannot then be demoted: the second call leaves
        # two identical lines, and `remove_line` requires a unique match, so the demotion path
        # answers `skipped_ambiguous` and the loop can no longer take the rule back. Caught by
        # a functional test that promoted the same trial twice on purpose.
        if line in body:
            return {
                "action_taken": "duplicate_skipped",
                "domain": domain,
                "line": line,
                "seed_mirror": "not_attempted",
                "why": (
                    "that exact rule is already in the playbook, tagged with this session. "
                    "Promoting it again would leave two identical lines, and a duplicated rule "
                    "cannot be demoted later because demotion needs a unique match."
                ),
            }

        anchor = paths.LEARNED_HEADER + "\n"
        if anchor not in body:
            return {
                "action_taken": "skipped_section_missing",
                "domain": domain,
                "line": line,
                "seed_mirror": "not_attempted",
                "why": (
                    f"{book} has no '{paths.LEARNED_HEADER}' heading. Every seed ships with one; "
                    "this tool never creates it, because creating it would put learned rules in a "
                    "file that was not meant to carry any."
                ),
            }
        updated = body.replace(anchor, anchor + line + "\n", 1)

        problem = FileIO.write_guarded(book, updated, self.logger)
        if problem is not None:
            return problem

        return {
            "action_taken": "promoted",
            "domain": domain,
            "line": line,
            "seed_mirror": self._mirror(domain, line),
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    # ----- demotion ----------------------------------------------------------------------

    def _demote(self, domain: str, book: str, body: str, find: str) -> dict[str, Any] | str:
        """Remove one learned line from the playbook and the seed.

        Unique-match only. A demotion that removed two lines because the search text was short
        would take out a rule nobody judged, and the loop would have no way to notice.
        """
        lines = body.splitlines()
        matched = [line for line in lines if find in line]
        if not matched:
            return {"action_taken": "skipped_not_found", "domain": domain, "line": "", "seed_mirror": "not_attempted"}
        if len(matched) > 1:
            return {
                "action_taken": "skipped_ambiguous",
                "domain": domain,
                "line": "",
                "seed_mirror": "not_attempted",
                "why": f"{len(matched)} lines contain that text. Give more of the line.",
            }

        target = matched[0]
        if not paths.is_learned(target):
            return {
                "action_taken": "skipped_not_learned",
                "domain": domain,
                "line": target,
                "seed_mirror": "not_attempted",
                "why": (
                    "that line is part of the hand-authored baseline, and this tool only removes "
                    "lines it promoted itself. If the baseline is wrong, that is a change for a "
                    "person to make in the seed."
                ),
            }

        updated = "\n".join(line for line in lines if line != target)
        if updated:
            updated += "\n"
        problem = FileIO.write_guarded(book, updated, self.logger)
        if problem is not None:
            return problem

        return {
            "action_taken": "demoted",
            "domain": domain,
            "line": target,
            "seed_mirror": self._unmirror(domain, target),
        }

    # ----- the seed mirror ---------------------------------------------------------------

    def _mirror(self, domain: str, line: str) -> str:
        """Append the learned line to the seed, under this section's learned heading.

        Returns `appended`, `duplicate_skipped`, `section_missing` or `seed_missing`. Never
        raises: the working-copy edit has already succeeded and a seed problem must not undo it.
        """
        book = paths.seed(domain)
        if not os.path.exists(book):
            return "seed_missing"
        body = FileIO.read_text(book)
        if not body:
            return "seed_missing"
        if line in body:
            # Dedup on the exact line so a re-promotion does not double the seed.
            return "duplicate_skipped"
        anchor = paths.LEARNED_HEADER + "\n"
        if anchor not in body:
            return "section_missing"
        updated = body.replace(anchor, anchor + line + "\n", 1)
        return "appended" if FileIO.write_guarded(book, updated, self.logger) is None else "seed_missing"

    def _unmirror(self, domain: str, line: str) -> str:
        """Remove the same learned line from the seed. `removed`, `not_found` or `seed_missing`."""
        book = paths.seed(domain)
        if not os.path.exists(book):
            return "seed_missing"
        lines = FileIO.read_text(book).splitlines()
        if line not in lines:
            return "not_found"
        updated = "\n".join(existing for existing in lines if existing != line)
        if updated:
            updated += "\n"
        return "removed" if FileIO.write_guarded(book, updated, self.logger) is None else "seed_missing"
