"""Resolving a logical name to a path, deny-by-default.

The model never sees a file path. The operator binds a `name_map` in the registry, the model
passes a `name`, and the tool resolves it here.

**Why not just take a path.** A path through a model is three failure modes at once: a typo
that reads as a missing file, an invented directory that reads the same way, and `..` walking
out of the state directory entirely. With a name map the addressable surface is exactly what
the registry lists, and the vocabulary the model sees is semantic rather than path-shaped:
`playbook_air_fleet` and `trial_strategies` rather than two directory levels and an extension.

**Deny-by-default is the part that matters.** A missing or empty `name_map` is an error rather
than a permissive fallback. A tool that read any path when its map was unset would work
perfectly in every test and silently become a file reader the first time a registry forgot to
bind it.

The error strings name the valid keys. A model that asked for `playbook_fleet` when the name is
`playbook_air_fleet` can fix that from the reply; without the list it can only guess again.
"""

from __future__ import annotations

from typing import Any

from coded_tools import paths


class NameMap:
    """Validate a model-supplied `name` against the operator-supplied map."""

    @staticmethod
    def validate(args: dict[str, Any]) -> str | None:
        """`None` when the name resolves, an `ERROR:` string saying why not otherwise."""
        name = args.get("name")
        if not isinstance(name, str) or not name:
            return "ERROR: invalid_input: 'name' is required."

        raw = args.get("name_map")
        if not isinstance(raw, dict) or not raw:
            return (
                "ERROR: invalid_input: the operator must bind 'name_map' in the registry; "
                "this tool is deny-by-default and addresses nothing without it."
            )

        if name not in raw:
            valid = ", ".join(sorted(raw.keys()))
            return f"ERROR: unknown_name: '{name}' is not in name_map. Valid names: {valid}."

        return None

    @staticmethod
    def resolve(args: dict[str, Any]) -> str:
        """The path for a name already known to validate. Call `validate` first.

        `{mode}` in a mapped path expands to the mode being played. The playbooks are per-mode —
        a rail rule is noise an air session cannot act on, and worse, a rule promoted in one mode
        would otherwise become doctrine in the other. The planner and the watcher are single
        networks serving BOTH modes, so their maps cannot name a mode statically; this is what
        lets one binding resolve correctly in either.
        """
        return str(args["name_map"][args["name"]]).replace("{mode}", paths.active_mode())
