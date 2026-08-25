# Session handoff

Written at the end of the Cowork session that built the learning harness. `CLAUDE.md` at the repo
root is what a fresh Claude Code session reads automatically — this file is the part that doesn't
belong in it: what was *decided and why*, what was *tried and rejected*, and the bugs that were
found the hard way.

Read `CLAUDE.md` first, then this, then `docs/nttd/HARNESS.md` for depth.

---

## Start here in Claude Code

```bash
cd ~/open-ttd-implementation
export PYTHONPATH=.:nttd-workbench

python3 scripts/nttd/check_wiring.py      # 30s, no engine needed — should print "wiring is sound"
```

If that passes, the next action is the smoke test. It has never been run:

```bash
# once
cd nttd && uv sync && uv run python -m scripts.verify_environment && cd ..
cd nttd-workbench && uv sync --extra neuro-san && cd ..
# add ANTHROPIC_API_KEY to .env  (and to nttd-workbench/.env, already written)

./apps/run_all.sh --tier t1 --mode air
```

Expect it to fail the first time. The likely candidates, in order: `AGENT_MANIFEST_FILE` unset so
only 2 of 4 networks load; `PYTHONPATH` missing `nttd-workbench` so the players don't load; Python
3.14 breaking a langchain import; OpenTTD not installed or OpenGFX2 Classic not added.

---

## Decisions worth not re-litigating

**The game layer is referenced, never copied.** The player registries are *generated* from
nttd-workbench by `scripts/nttd/sync_player_registries.py`. I started writing a fresh gateway and
was told to stop — correctly. The workbench's 44 tool modules import cleanly as
`agents.neuro_san.coded_tools.*` with the checkout on `PYTHONPATH`; only its `.hocon` files are
unusable verbatim, because it sets `AGENT_TOOL_PATH_ONLY=true` (flat class names) and its `include`
is relative to its own root.

**Stepped play only, deliberately.** Realtime is refused rather than half-supported. The runner
checks the mode and exits.

**Knowledge networks hold no game credentials.** The watcher and planner read files and telemetry,
never the game. Not an oversight — it makes it *impossible* for a curator to spend a game day.

**Playbooks split per agent, not one file.** Tried one file with six sections first. Every agent
then read every section: the scout carried the retirement state machine, the fleet carried the
water-crossing failure. Five sixths of it was advice for someone else, paid for on every turn.

**No `replace_line` on playbooks.** Dropped at the user's instruction, and it's the right call
under the epistemics spec: a swap destroys the record it replaces, and a destroyed record can't be
re-examined when later evidence contradicts the reason for the swap.

**The trial schema was migrated to the claim schema mid-build.** Old vocabulary
(`confirmed/falsified/inconclusive/not_applied/carried_over`, three files) is gone. If you find a
reference to `trial_parsing`, `log_trial`, `active_trials`, `resolve_trials` or `delete_trial`, it's
a leftover — `check_wiring.py` fails on those deliberately.

**The planner's voice is warm; its verdicts are not.** Explicitly separated in the prompt, because
a curator that's upbeat about its own conclusions is the exact mechanism the gates exist to stop.
Don't "improve" the prompt by making the verdicts encouraging too.

---

## Bugs found, and how

Every one of these came from a *functional* test, not from reading. Worth knowing because the same
classes of bug will recur.

| bug | how it presented | fix |
|---|---|---|
| read-and-clear silently became read-and-keep | `os.remove` failed `EPERM` on a restricted mount; the note would be served every run forever | truncate instead — needs only the permission that just wrote the file |
| a rule promoted twice could never be demoted | seed mirror deduplicated, working copy didn't; two identical lines made `remove_line`'s unique-match answer `skipped_ambiguous` forever | refuse the duplicate before either edit |
| a *documentation* line was demotable | the playbook header explains the convention and so contains the literal `(learned sN)`; a substring marker test matched it | marker is now a regex requiring digits |
| the Gate-1 open-question append never fired | condition was `args.get("refuted_despite") == ""`, but an absent key gives `None` — and a caller who omits the field is exactly the one whose refutation was downgraded | test falsiness |
| newest plan revision landed at the *bottom* | insert anchored on header prose that differed by one word, so every revision fell through to append and the oldest plan was presented as current | anchor on an HTML-comment sentinel |
| `session_number` bound in HOCON | every session after the third would record as the third — colliding claim ids, merged turn logs | read from `state/session_number.json` |
| a cascading gate gave an opaque refusal | `high` with no varied conditions → downgraded to `low` → demanded `RE-TEST WHEN`; caller saw only the second half and would re-send `high` | report downgrades on the refusal path too |

**Lesson for the next session:** these were all found by running the loop and asserting on the
output, never by re-reading the code. There is still no committed test suite — writing one is high
value and item 3 on the outstanding list.

---

## What the user asked for that isn't done

1. **`diagnose` tool** — explicitly requested ("I want my agents to be super good at analyzing the
   system, the run, finding these different issues and fixing them"). Designed, described, not
   built. The material is all there: `nttd/docs/gameplay_guide.md` §4 has the symptom→cause→how-to-
   see table, and the refusal ledger already accumulates in `sly_data`. The point is to compute the
   signature deterministically rather than hope a model spots it — same principle as the gates.
2. **Smoke test** — needs the Mac.
3. **Tests for `coded_tools/`**.

---

## Things I could not do from Cowork

- **Run the engine.** The sandbox is Linux; nttd is macOS-only and wants
  `/Applications/OpenTTD.app/Contents/MacOS/openttd`.
- **Load the registries into neuro-san.** Never started `ns run`.
- **Authorize connectors.** The `engineering` plugin's eight MCP servers (Asana, Atlassian,
  Datadog, GitHub, Linear, Notion, PagerDuty, Slack) are pending OAuth.
- **Delete files, at first.** The mount refused `unlink` until permission was granted — which is
  why `scratchpad.py` truncates rather than deletes, and that turned out to be the more robust
  design anyway.

---

## One mistake to learn from

Asked to "delete the tests, example networks, things we don't need", I deleted 445 files by
deciding for myself what wasn't needed — including half of the Agent Network Designer feature whose
middleware was still live. All restored via git, then redone properly as a *reachability* analysis:
209 files, keeping `aaosa*`, `middleware/`, `servers/` and anything plausibly needed.

The lesson: unreferenced `.hocon` files are inert — the manifest decides what loads, so deleting
examples buys nothing at runtime. If a future session is asked to clean up, show the list first.
