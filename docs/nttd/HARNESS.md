# The nttd learning harness

The knowledge layer: what lets session N+1 start from what session N actually established. It
does not play the game, holds no session token, and cannot spend a game day.

---

## 1. The loop

Before a session the **planner** reads the commons, compiles a working plan, and raises two or
three **claims** — testable statements, each with the conditions it applies under. During the
session a **watcher** wakes at intervals and returns a verdict the runner can act on. After it,
the planner **revises** those claims against what the telemetry shows, and **promotes** the
supported ones into the playbook the next session's agents read first. A rule whose claim is later
refuted can be **demoted**.

Same shape as `Neuro-SAN-MAPs`, with one difference forced by the target: MAPs has an
`advance_episode` that resets the park; nttd has no such call, so a new world comes from re-running
`nttd benchmark` and the boundary tool here rolls knowledge only.

---

## 2. Files

### `coded_tools/`

| file | owns |
|---|---|
| `file_io.py` | every read/write/coercion, and the `"ERROR: …"`-string convention |
| `paths.py` | the three directories, six domains, the learned-rule marker |
| `session_number.py` | which session this is, read from disk |
| `name_map.py`, `state_read.py` | deny-by-default logical-name reader — the model never sees a path |
| `scratchpad.py` | a note one network leaves for its own next run |
| `seed_playbooks.py` | fresh-start reseeding, boundary snapshots |
| **`claims.py`** | the commons format **and the gates**, as enforceable functions |
| **`log_claim.py`** | raise or revise a claim, gates applied |
| **`read_claims.py`** | what stands, what conflicts, what is worth testing next |
| **`current_best_plan.py`** | the compiled strategy, with its confidence cap |
| `promote_trial.py` | the deterministic playbook editor (append-only + demotion) |
| `telemetry.py` | per-turn and per-session figures; the champion |
| `advance_session.py` | the session boundary |
| `write_session_plan.py` | the short plan every turn reads |
| `config_files/seed_playbook_*.md` | six playbooks, every line cited |

### `registries/`

`nttd_common.hocon` (caps, models, sly_data allow-lists), `nttd_planner.hocon`,
`nttd_watcher.hocon`, `manifest.hocon`. Wired by the root `.env`:

```bash
AGENT_MANIFEST_FILE=registries/manifest.hocon
AGENT_TOOL_PATH=coded_tools
```

That `.env` line is **required**: `neuro_san_studio/commands/project_environment.py` otherwise
defaults to `registries/manifest.hocon`, which serves the upstream examples instead of ours.

---

## 3. Three directories

```
coded_tools/config_files/   the SEEDS    survive a fresh start
state/         the WORKING copies + the commons
logs/nttd/                      the TELEMETRY
```

The **seeds** are baseline plus every rule promoted so far — the memory that crosses runs. The
**working playbooks** are reset from the seeds on a fresh start and left alone on a resume; without
that asymmetry a crash three hours in would either lose every promotion made in the session, or
carry forward a playbook edited by a session that never finished and was never judged.

The **commons** (`state/claims.md`) is never truncated, on a fresh start or otherwise.

---

## 4. A claim

```
---
ID: s3_1
REV: 3
DOMAIN: scout
ORIGIN: planner
CLAIM: One long air trunk delivers more cargo than two short corridors below 200k cash.
STATUS: supported
CONFIDENCE: low
CONDITIONS: t1-256-flat seed1001 stepped air session3
EVIDENCE: cargo 4,100 by day 200 vs champion 3,050 at same day
VARIED: —
RE-TEST WHEN: cash ceiling above 200k, or map hilly rather than flat
```

**Three statuses**: `open`, `supported`, `refuted`. Not five — "we didn't test it" and "it needs
another session" are the same state, and giving them separate names invites filing an untested idea
as a soft failure.

**Append-only, current view computed.** A status change appends a *new revision* for the same id.
So `s3_1` supported in session 3 and refuted in session 5 has both blocks; folding decides the
headline and the history stays underneath. Nothing is overwritten because nothing is *overwritable*.

---

## 5. The gates, and where each is enforced

| gate | rule | where |
|---|---|---|
| **1** | `refuted` requires `REFUTED_DESPITE` — an observation where the doubted condition *was* satisfied and the effect still didn't occur. Without it: downgraded to `open`, condition written to `open_questions.md`. | `claims.gate()` |
| **2** | `CONFIDENCE` is bought with `VARIED`. `high` needs 2 varied conditions, `med` needs 1. Repeats with a condition held fixed are one test run twice. | `claims.gate()` |
| **3** | Every claim returns its `CONDITIONS`; any whose conditions differ from the ones in force is flagged `re_test_before_relying`. | `read_claims` |
| **4** | Open and low-confidence claims come back as `worth_probing`, with the open questions. | `read_claims` |
| — | `RE-TEST WHEN` mandatory on anything refuted or low. A negative with no way back is policy, not knowledge. | `claims.gate()` |
| — | `always` / `never` / `dead`, and any claim telling a future agent to stop testing, are rejected. | `claims.check_wording()` |

**The gates adjust where the honest write is obvious, and refuse only where it isn't.** A `refuted`
with no exhibited observation *is* an `open`, so it's filed as one and the caller is told why —
refusing outright would discard the observation that was actually made.

Verified behaviour:

```
refuted, no REFUTED_DESPITE   → filed as open + open_questions entry
refuted, with it              → allowed
high, 0 varied                → downgraded to low, then refused for missing RE-TEST WHEN
high, 2 varied                → allowed
"Rail never pays…"            → refused (forbidden word)
"…so stop testing water"      → refused (stop-testing phrasing)
low, no RE-TEST WHEN          → refused
```

---

## 6. Promotion, demotion, and append-only playbooks

`promote_trial` does two things: `add_line` appends a rule under a playbook's learned-rules
heading, and `remove_line` demotes one.

**There is no `replace_line`.** A swap destroys the record it replaces, and a destroyed record can't
be re-examined when later evidence contradicts the reason for the swap. Two conflicting rules are
both kept; only a refutation removes one.

**The baseline can't be deleted.** Only lines tagged `(learned sN)` are removable — the worst a
model can do by asking is a no-op. That guarantee is why demotion can be handed to a model at all.

Every edit mirrors into the seed, since the working copy is reset from the seed at the next fresh
start.

---

## 7. The current best plan

`state/current_best_plan.md`, revised by append, newest block first.

It is deliberately **not** a master document — that's why it's a separate file rather than a
playbook section. A plan that overrode the claims would let a confident summary outrank the evidence
it was compiled from, and the summary is the part nobody re-checks. So:

- every revision must **name the claim ids** it rests on; one that cites none is refused
- its **confidence is capped** by the claim bearing on its biggest untested upside. A plan cannot be
  more certain than its least-tested assumption, and that's exactly where over-confidence enters —
  not in the gated claims, but in the summary that quietly rounds them up.

---

## 8. Telemetry

The runner writes one JSONL row per turn (`logs/nttd/run.sNNN.jsonl`) and one per finished session
(`sessions.jsonl`). Ranking is `company_value`, tie-broken by `total_cargo` — what the nttd
leaderboard ranks on, both straight from the game.

`SessionTelemetry` compares against the best session **at the same game day**, never its final
figures. A run 90 days in isn't behind a completed one; it's 90 days in, and a watcher told
otherwise aborts a run that's doing fine.

The rating comes back as `"not computed yet"` when the game answers `-1` — OpenTTD needs a full
quarter before it computes one, and reading `-1` as a score makes a healthy young company look
catastrophic.

Written by the runner rather than read from nttd's `result.parquet`: parquet would mean installing
the engine into this studio, and it means telemetry exists for a session abandoned halfway, which is
the session a planner most wants to see.

---

## 9. Bugs the functional tests caught

Worth recording; none were obvious.

1. **Read-and-clear silently degraded to read-and-keep.** The scratchpad deleted its file with
   `os.remove`, which failed `EPERM` on a restricted mount — so the note would be served every run
   forever, exactly the stale-advice problem read-and-clear prevents. Now truncates: both empty the
   pad, but truncating needs only the permission that just wrote the file.
2. **A rule promoted twice could never be demoted.** The seed mirror deduplicated; the working copy
   didn't. Two identical lines made `remove_line`'s unique-match requirement answer
   `skipped_ambiguous` forever.
3. **A documentation line was demotable.** The playbook header explains the convention and so
   contains the literal `(learned sN)`; a substring marker test called it a promoted rule. The
   marker is now a regex requiring digits.
4. **The Gate-1 open-question append never fired.** The condition was
   `args.get("refuted_despite") == ""`, but an absent key gives `None` — and a caller who omits the
   field entirely is precisely the one whose refutation was downgraded. Now tests falsiness.
5. **The newest plan revision landed at the bottom.** The insert anchored on header *prose* that
   differed by one word, so every revision fell through to the append branch and the oldest plan was
   presented as current. Now anchored on an HTML-comment sentinel.
6. **`session_number` bound in HOCON** would have made every session after the third record as the
   third — colliding claim ids and merging turn logs. Now read from `state/session_number.json`.
7. **A cascading gate gave an opaque refusal.** `high` with no varied conditions was downgraded to
   `low`, which then demanded `RE-TEST WHEN`; the caller saw only the second half and would re-send
   `high`. Downgrades are now reported on the refusal path too.

---

## 10. What's verified, and what isn't

**Verified in the sandbox:** the full loop end to end; all four gates firing and refusing correctly;
the ledger append-only with conflicting revisions both retained; the plan cap applying; newest-first
ordering across two sessions; every `.hocon` parsing; all 17 registry `class` references resolving.

**Not verified, and I can't:** anything touching the game. My shell is isolated Linux; nttd is
macOS-only and wants `/Applications/OpenTTD.app/Contents/MacOS/openttd`. The neuro-san server has
also never loaded these registries — the HOCON is valid and structurally sound but unproven against
neuro-san itself.

---

## 10. logs/ versus state/

**The test is whether the next session needs it.**

`logs/nttd/` is transient: server stdout, engine stdout, the agents' thinking. Read it while
something is going wrong, delete it afterwards, and nothing breaks. `rm -rf logs/` is always safe.

`state/` is maintained. The playbooks, the claims ledger, the compiled plan — and now
`state/telemetry/`, which holds the per-turn rows, the finished-session rows the champion is
computed from, and the per-turn record of what the agents were holding.

The telemetry used to live under `logs/`, which was wrong, and the code said so: the comment on
`SESSION_LOG_PATH` read "never archived, because a champion that vanished when logs were rotated
is a champion the next run cannot aim at". A file that must not be rotated is not a log.

Not kept, because nttd already keeps it better: per-turn world snapshots. The engine writes
`snapshots.parquet` (one row per game day) and `tiles.parquet` (the full map) into
`nttd/logs/sessions/<id>/`, alongside `result.parquet`, `spend.parquet` and `actions.parquet`.
What is NOT in any of those is what the agents built up — `sites` is the map as the scout
surveyed it, `decisions` is what the strategist chose and why — so that is what
`state/telemetry/agents.sNNN.jsonl` records.

---

## 10a. Where the seed playbooks came from

Nothing in `coded_tools/config_files/seed_playbook_*.md` was invented. Every line was taken from
one of:

- `nttd-workbench/agents/strategy/{common,air,rail}.md`
- `nttd/docs/gameplay_guide.md`
- `nttd-workbench/agents/neuro_san/DESIGN.md`
- the workbench registries

The seeds used to carry a per-line `[gameplay]`-style tag and a table mapping the tags to those
paths. Both were removed: the agents cannot open any of those files — none is in a `name_map` —
so a citation was a pointer to something unreachable, costing about 1,050 tokens every time a
playbook was read. The provenance is recorded here instead, and the tagged version is in git
history before that commit.

**Keep the property, not the tags.** A new seed line should still be traceable to one of the
documents above, or marked as a claim to be tested.

---

## 11. What's missing

Updated 2026-08-25. Items 2 to 5 of the original list were written mid-build and have since
landed; what remains is the part that needs a real game.

1. **The smoke test.** Nothing has run against a real session. This is the whole remaining risk:
   every item below is verified only as far as a test without an engine can reach.

   ```bash
   cd nttd             && uv sync && uv run python -m scripts.verify_environment
   cd ../nttd-workbench && uv sync --extra neuro-san      # .env written; add the key
   ./apps/run_all.sh --tier t1 --mode air
   ```

2. **`apps/runner.py` is at 0% coverage.** It exists and is complete — turn stamp, spend
   reporting, stream retry, the watcher at intervals, the abort guardrail on `doomed`, telemetry,
   the planner at both boundaries — but it needs a live engine, so no unit test reaches it. It is
   the largest untested piece in the repo and what the smoke test exercises first.

Done since: the player networks are generated by `scripts/nttd/sync_player_registries.py` and the
game-layer tools are referenced in place; `apps/run_all.sh` brings up engine, studio and
runner and threads the session id and token; and `coded_tools/diagnose.py` computes the
documented failure signatures — company value at the engine's floor, stations built that deliver
nothing, a fleet-wide stall, and one action refused repeatedly. It is bound into the watcher
(mid-session, while there are turns left to matter) and the planner (at the boundary, where a
detection becomes a claim). It detects and names; it deliberately does not prescribe, because what
a signature means for play is a claim to be tested, not a rule to hard-code.

---

## 12. Two things to watch

**Python 3.14** in all three venvs. nttd wants ≥3.13 and the studio ≥3.10, so nominally fine — but
your MAPs repo pins 3.12 so one env satisfies everything, and the langchain/neuro-san stack is barely
road-tested on 3.14. First suspect for odd import errors. Here you don't need a shared env: the
harness needs only `httpx`, which the studio venv already has.

**The knowledge networks hold no game credentials.** Not an oversight — the watcher and planner read
files and telemetry, never the game, so a network that cannot address the session cannot accidentally
spend a game day thinking about one. If you later want the watcher reading live state, that's a
deliberate change with a real cost.
