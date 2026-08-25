"""Regenerate the player registries from nttd-workbench.

    python3 scripts/nttd/sync_player_registries.py

The workbench owns the game layer — the gateway, the plan, the clock, the siting and fleet tools —
and it is under active development. This script keeps our player registries in step with its
networks without copying a line of its Python.

**What it rewrites, and why each rewrite is necessary.**

`class` references. The workbench names its tools FLAT, `ns.read_situation.ReadSituation`, because
it sets `AGENT_TOOL_PATH_ONLY=true`, which loads coded tools as siblings with the package directory
itself on the path. This studio does not set that flag, so its own tools resolve as ordinary
fully-qualified imports. One server cannot do both spellings, so every reference is rewritten to
`agents.neuro_san.coded_tools.ns.…`, which resolves with the workbench checkout on PYTHONPATH and
points at the module in place.

The `include`. The workbench's is written relative to its own root and resolves to the wrong place
from here, so it is dropped and ours is substituted.

The variable names. `ns_llm_config` and friends become the `nttd_` equivalents in
`registries/nttd_common.hocon`.

**What it adds.** The knowledge layer: `read_playbook`, `read_claims`, `scratchpad`. Read-only —
a player never records a verdict, because a verdict needs the whole run in view and a turn has only
the position in front of it. This is the one thing the generated file has that the workbench
network does not, and it is the whole point of the harness: a network that cannot read what past
sessions learned cannot benefit from it.

**What it never touches.** The agent roster, the instructions, the tool descriptions, the caps.
Those are the workbench's judgement and are worth inheriting exactly. If a generated file needs a
change to any of them, make it in the workbench and re-run this.

Run it after pulling nttd-workbench. It overwrites both generated files without asking, which is
safe precisely because nothing hand-written lives in them.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SRC = ROOT / "nttd-workbench" / "agents" / "neuro_san" / "registries"
OUT = ROOT / "registries"

# The workbench networks we generate a player from, and the mode each plays.
NETWORKS = {"air": "ns_air_agent.hocon", "rail": "ns_rail_agent.hocon"}

# Wiring the added tools into the agents that use them.
#
# neuro-san validates REACHABILITY: a tool declared in the top-level array but named by no agent's
# own `tools` list makes the whole registry invalid, and the server skips it. Declaring the
# knowledge tools without wiring them is exactly that failure, and it presents as "only the
# planner and the watcher loaded" — which looks like the PYTHONPATH trap and is not.
#
# `read_playbook` goes to EVERY agent because each has a playbook of its own; the scout's rules
# are not the fleet's. `read_claims` and `scratchpad` go only to the front man: judging what past
# sessions established is strategist work, and the pad is bound to one pad name per network, so
# five agents sharing it would clobber each other's note.
LEAD_TOOLS = ('"read_playbook"', '"read_claims"', '"scratchpad"')
WORKER_TOOLS = ('"read_playbook"',)

# The playbooks a player may read. Its own five jobs plus the shared ground.
PLAYBOOKS = ("playbook_strategist", "playbook_scout", "playbook_builder", "playbook_fleet", "playbook_care")

HEADER = """# GENERATED from nttd-workbench/agents/neuro_san/registries/{src}
#
# Regenerate with: python3 scripts/nttd/sync_player_registries.py
# Do not edit by hand: the next sync overwrites it. Change the workbench network instead.
#
# WHY THIS IS GENERATED RATHER THAN INCLUDING THE WORKBENCH FILE DIRECTLY.
#
# Two things make the workbench registry unusable verbatim from this tree, and both are about
# loading rather than about content:
#
#   1. It names its tools FLAT -- `class = "ns.read_situation.ReadSituation"` -- because the
#      workbench sets AGENT_TOOL_PATH_ONLY=true, which loads coded tools as siblings with the
#      package directory itself on the path. This studio does not set that flag, so its own tools
#      resolve as ordinary fully-qualified imports (`coded_tools.*`). One server cannot do
#      both, so the class references are rewritten to the fully-qualified spelling.
#
#   2. Its `include` is written relative to the workbench root, so it resolves to the wrong place
#      from here.
#
# NO GAME-LAYER PYTHON IS DUPLICATED. Every `class` below points at the workbench module in place,
# so a fix there is a fix here. The only thing this file ADDS is the knowledge layer: the player
# can read its playbook, the claims and the session plan, which is the point of the harness -- a
# network that cannot read what past sessions learned cannot benefit from it.

include "registries/nttd_common.hocon"

"""

KNOWLEDGE = """
    # =========================================================================================
    # The knowledge layer. Added here; not present in the workbench network.
    #
    # READ-ONLY, deliberately. A player reads what past sessions established and never records a
    # verdict on it: judging needs the whole run in view, and a turn has only the position in
    # front of it. Recording is the planner's job at a session boundary.
    # =========================================================================================
    {{
        name = "read_playbook"
        function = {{
            description = "The strategy for one job, including every rule promoted by an earlier session. Read your own before deciding anything, and the session plan before your first move."
            parameters = {{
                type = "object"
                properties = {{
                    name = {{ type = "string", description = "One of: playbook_common, {names}, session_plan, current_best_plan." }}
                }}
                required = ["name"]
            }}
        }}
        class = "coded_tools.state_read.StateRead"
        args = {{
            name_map = {{
                playbook_common     = "coded_tools/state/playbook_common.md"
{maps}
                session_plan        = "coded_tools/state/session_plan.md"
                current_best_plan   = "coded_tools/state/current_best_plan.md"
            }}
        }}
    }}

    {{
        name = "read_claims"
        function = {{
            description = "What past sessions established, with the conditions each held under. Anything flagged re_test_before_relying was established elsewhere: it tells you where to look, not what to conclude."
            parameters = {{
                type = "object"
                properties = {{
                    domain = {{ type = "string", description = "Optional: one job only -- common, strategist, scout, builder, fleet or care." }}
                    conditions_now = {{ type = "string", description = "The scenario and mode being played." }}
                }}
            }}
        }}
        class = "coded_tools.read_claims.ReadClaims"
        # `with_evidence` deliberately NOT bound. A player told what would falsify its instruction
        # starts optimising for the criterion instead of playing the game.
    }}

    {{
        name = "scratchpad"
        function = {{
            description = "Leave a note for the next turn, or read and clear the one you left. Reading deletes it, so a note is visible exactly once and never rots into stale advice."
            parameters = {{
                type = "object"
                properties = {{ note = {{ type = "string", description = "Omit to read and clear; give text to replace the pad." }} }}
            }}
        }}
        class = "coded_tools.scratchpad.Scratchpad"
        args = {{ pad = "player" }}
    }}
]
"""


def _wire_knowledge_tools(body: str) -> tuple[str, int]:
    """Name the knowledge tools in each agent's own `tools` list, so they are reachable.

    Keyed on indentation: the registry's top-level `tools` array sits at column 0 and every
    agent's sits indented, so requiring leading whitespace touches the agents and nothing else.
    The first indented array is the front man, which is the one that also gets the claims and
    the pad.
    """
    seen = 0

    def wire(match: re.Match) -> str:
        nonlocal seen
        seen += 1
        indent, inner = match.group("indent"), match.group("inner")
        add = LEAD_TOOLS if seen == 1 else WORKER_TOOLS
        add = tuple(name for name in add if name not in inner)
        if not add:
            return match.group(0)
        if "\n" in inner:  # multi-line list: keep it multi-line
            return f"{indent}tools = [{inner.rstrip()}\n{indent}    {', '.join(add)},\n{indent}]"
        return f"{indent}tools = [{inner.strip()}, {', '.join(add)}]"

    return re.sub(r"^(?P<indent>[ ]+)tools = \[(?P<inner>.*?)\]", wire, body, flags=re.S | re.M), seen


def generate(mode: str, src_name: str) -> tuple[pathlib.Path, int]:
    """Write one player registry from its workbench source. Returns the path and class count."""
    body = (SRC / src_name).read_text()

    body = re.sub(r'^include "agents/neuro_san/registries/ns_common\.hocon"\n', "", body)
    body = body.replace("llm_config = ${ns_llm_config}", "llm_config = ${nttd_llm_config}")
    body = body.replace("allow = ${ns_allow}", "allow = ${nttd_allow}")
    body = body.replace("${ns_ground_rules}", "${nttd_ground_rules}")
    body = body.replace("${ns_worker_conduct}", "${nttd_worker_conduct}")
    body = body.replace('llm_config = { "model_name": "claude-opus" }', "llm_config = ${nttd_llm_config_strong}")
    body = re.sub(r'class = "(ns|ns_air_agent|ns_rail_agent)\.', r'class = "agents.neuro_san.coded_tools.\1.', body)

    body, wired = _wire_knowledge_tools(body)
    if wired < 2:
        raise SystemExit(f"{src_name}: found only {wired} agent tools arrays; the layout changed")

    stripped = body.rstrip()
    if not stripped.endswith("]"):
        raise SystemExit(f"{src_name}: expected the file to end with its tools array")
    maps = "\n".join(f'                {name:<19} = "coded_tools/state/{name}.md"' for name in PLAYBOOKS)
    body = stripped[:-1].rstrip() + "\n" + KNOWLEDGE.format(names=", ".join(PLAYBOOKS), maps=maps)

    out = OUT / f"nttd_{mode}_player.hocon"
    out.write_text(HEADER.format(src=src_name) + body)
    return out, len(re.findall(r'class = "', body))


def main() -> int:
    """Regenerate both player registries from the workbench."""
    if not SRC.is_dir():
        print(f"nttd-workbench registries not found at {SRC}", file=sys.stderr)
        print("Clone it beside this studio, or set the path in this script.", file=sys.stderr)
        return 1
    for mode, src_name in NETWORKS.items():
        out, refs = generate(mode, src_name)
        print(f"{out.relative_to(ROOT)}: {refs} class references, all pointing at {src_name}")
    print("\nValidate with: python3 scripts/nttd/check_wiring.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
