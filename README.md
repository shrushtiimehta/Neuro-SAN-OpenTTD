# Neuro-SAN-OpenTTD

A [neuro-san-studio](https://github.com/cognizant-ai-lab/neuro-san-studio) fork that plays the
**nttd** benchmark — long-horizon planning on OpenTTD — with a multi-agent system that **learns
across sessions**.

One run of the benchmark is one session. A session teaches things that die with it unless
something writes them down. This repo is that something: a hypothesis is raised at the start of a
session, judged against telemetry at the end of it, and one that held up is promoted into the
playbook the next session reads first.

The interesting part is not the agents. It is that **the loop is gated in code rather than
requested in a prompt**, because a model asked nicely to be rigorous is a model that will be
rigorous most of the time.

---

## The four gates

A session's findings go into one append-only ledger, `state/claims.md`. Writing to it is refused
unless the write is honest, and the refusals are in [`coded_tools/claims.py`](coded_tools/claims.py),
not in an instruction:

1. **A refutation must exhibit its condition.** `refuted` requires `REFUTED_DESPITE`: an
   observation where the condition being dismissed *was* satisfied and the effect still did not
   occur. Without it the write is downgraded to `open` and the condition goes to the open
   questions. *A failure while a precondition was unmet is untried, not refuted.*
2. **Confidence is bought with varied conditions.** `high` needs two things varied between
   observations, `med` needs one. Five runs with the same condition held fixed is one test run
   five times — and it re-runs any systematic error five times too.
3. **Inherited claims are flagged, not trusted.** A claim whose conditions differ from the ones in
   force comes back marked `re_test_before_relying`. Inherited knowledge says where to look, not
   what to conclude.
4. **What is still open comes back as `worth_probing`.** An untested idea nobody resurfaces is an
   idea lost.

Plus: `RE-TEST WHEN` is mandatory on anything refuted or low-confidence, and the words *always*,
*never*, *dead* — and any phrasing telling a future agent to stop testing something — are rejected
outright. A wrong verdict frozen into policy is the single failure the whole design exists to
prevent.

**Nothing is ever overwritten.** A status change appends a new revision; current standing is
computed by folding the file. Two revisions that disagree both survive. The playbooks are
append-only too — there is deliberately **no `replace_line`**, because a swap destroys the record
it replaces.

---

## What is in here

```text
coded_tools/          the knowledge layer: claims, playbooks, telemetry, diagnose
  config_files/       the hand-authored baseline playbooks. Read-only to every tool.
registries/           five agent networks (see below)
apps/                 the runner and run_all.sh
state/                what the harness writes. claims.md and learned/ are tracked; the rest is derived.
docs/nttd/            HARNESS.md — the design, in depth
```

Three things are kept apart on purpose:

| | where | written by |
|---|---|---|
| **baseline** | `coded_tools/config_files/` | a person. No tool writes here. |
| **earned** | `state/learned/<mode>/` | `promote_claim`. Append-only, revocable. |
| **working** | `state/<mode>/` | composed on start: baseline + earned |

So the baseline cannot be damaged by the loop, only earned lines are demotable, and a rule learned
playing air cannot become rail doctrine — because it is not in rail's directory.

---

## Five networks

| network | job |
|---|---|
| `nttd_air_player` / `nttd_rail_player` | play a turn. Five agents: strategist, Scout, Builder, FleetGrowth, FleetCare |
| `nttd_opener` | opens a session: compiles the plan, raises the claims to test |
| `nttd_closer` | closes it: revises claims against evidence, promotes what held up |
| `nttd_watcher` | every fifth turn: `on_track` / `underperforming` / `doomed` |

The opener and closer are separate because their **powers** differ, not just their prompts. An
opener cannot `promote_claim` or `advance_session`; a closer cannot `write_session_plan`. An opener
able to promote could close a session it never watched; a closer able to rewrite the plan could
revise the target after seeing the score.

Inside a player, each agent is **bound** to its own playbook — `read_playbook_scout` addresses the
shared ground and the scout's playbook and nothing else. Workers come back with two or three
defensible moves and a recommendation; the strategist chooses, and records the option it did *not*
take.

The player registries are **generated** by
[`scripts/nttd/sync_player_registries.py`](scripts/nttd/sync_player_registries.py) from
`nttd-workbench`. Do not hand-edit them; change the workbench network and re-run the sync.

---

## Running it

Needs macOS, [OpenTTD 15.3](https://www.openttd.org/downloads/openttd-releases/latest) with a
graphics baseset, `uv`, and an Anthropic API key.

```bash
git clone https://github.com/shrushtiimehta/Neuro-SAN-OpenTTD && cd Neuro-SAN-OpenTTD
git clone https://github.com/cognizant-ai-lab/nttd
git clone https://github.com/cognizant-ai-lab/nttd-workbench
```

The two clones are the **engine** (wraps an OpenTTD server, exposes it as JSON, scores runs) and
the **game layer** (gateway, plan, clock, siting and fleet tools). Neither is vendored: the player
registries reference the workbench's Python in place, so a fix there is a fix here.

```bash
make install
cd nttd && uv sync && uv run python -m scripts.verify_environment && cd ..
cd nttd-workbench && uv sync --extra neuro-san && cd ..
cp .env.example .env   # then add ANTHROPIC_API_KEY, to .env and nttd-workbench/.env
```

Then:

```bash
source venv/bin/activate && ./apps/run_all.sh --tier t1 --mode air --fresh
```

`--sessions 3` runs three back to back with learning between them; `--fresh` resets the working
playbooks from baseline plus what has been earned, and applies to the first round only.

Watch it: the game itself with an OpenTTD client on the `game_port` printed in
`logs/nttd/benchmark.1.log`, the agents' tool calls live at `http://localhost:4175`, and
`cd nttd && uv run nttd monitor` for the fleet and actions tables.

Validate the wiring without starting anything — parses every registry, imports every tool class,
and checks that no tool is unreachable:

```bash
PYTHONPATH=.:nttd-workbench python3 scripts/nttd/check_wiring.py
```

---

## Traps

**`PYTHONPATH=.:nttd-workbench` is required and `ns run` will not read it from `.env`.** Without
the second path the two players silently fail to load and you get only the boundary agents and the
watcher. `run_all.sh` sets it.

**Stepped play only.** In realtime the clock runs whatever the agent does, so a slow turn is a lost
game month and every measured figure becomes incomparable with every other. The runner checks the
mode and refuses rather than playing it badly.

**The runner owns the turn stamp.** Only the client knows where a turn begins; `advance_days` reads
`sly_data["turn_stamp"]` to bound the per-turn day budget. Without it a turn grows until the server
cancels it and everything in it is lost.

**The `sly_data` allow-list is explicit.** neuro-san's redactor is security-by-default: with nothing
listed, cross-turn memory dies at the turn boundary. That defect is what made an earlier network
resubmit one refused purchase 35 times. Credentials never appear on it.

**Client stream timeout must exceed the server's `max_execution_seconds`** — 7200 against 6000. A
client that gives up first kills turns the server was still entitled to work on.

---

## State of it

The knowledge layer is tested: **84 tests**, `make test` green, covering all four gates, the
plan-confidence cap, the append-only ledger and playbooks, the per-mode split, and the boundary
agents' capabilities.

It has played real sessions, and the run loop works end to end — but only a handful, and
`apps/runner.py` itself has no unit tests because it needs a live engine. Treat measured figures as
provisional until more sessions have run. `docs/nttd/HARNESS.md` records what is verified and what
is not.

---

## Licence

Apache-2.0, inherited from neuro-san-studio. The upstream studio internals are retained; the
example networks, the agent network designer and the deployment tooling were removed.
