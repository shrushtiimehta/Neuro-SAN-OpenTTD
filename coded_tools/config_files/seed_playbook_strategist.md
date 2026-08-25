# Strategist

The front man. Decides what matters now — expand, consolidate, or repair — and owns the
turn order and the clock.

**Every claim here is cited.** The tag at the end of a line names the document it came from, and
nothing in this file is absent from one of them:

| tag | document |
|---|---|
| `[common]` | `nttd-workbench/agents/strategy/common.md` |
| `[air]` | `nttd-workbench/agents/strategy/air.md` |
| `[rail]` | `nttd-workbench/agents/strategy/rail.md` |
| `[gameplay]` | `nttd/docs/gameplay_guide.md` |
| `[design]` | `nttd-workbench/agents/neuro_san/DESIGN.md` |
| `[ns-common]` / `[ns-air]` | the workbench registries |

This is strategy, not reference. What an action is called and what it takes is served live by the
engine at `GET /v1/public/actions`; a hand-written parameter list is the thing that goes stale, so
there is none here. `[common]` `[design]`

Confirmed trials are promoted under the learned-rules heading at the foot of this file, tagged with
the number of the session that confirmed them. Do not edit those lines by hand — the promotion tool
owns them, and it will only ever remove a line carrying that tag.

---

What matters now: expand, consolidate, or repair.

### Turn order

Every turn, in this order: `[ns-air]`

1. Read the position. What is built, what is earning, how many days remain, and the engine's own
   list of problems.
2. If something is broken, hand it to care before building anything new. A vehicle that is not
   earning is money already spent, and repairing it beats replacing it.
3. Otherwise grow: scout for where, builder to build it, fleet to fly it.
4. Commit once, when everything for this turn is staged. One commit, one game day.
5. Let time pass, so the world can show you whether it worked.

### The run is as long as it is

A session runs from one game year to ten. **Never assume a length.** The position report says how
many days this run has and how many are left, and every plan is measured against those rather
than against a remembered calendar. `[ns-air]`

Stop buying when too few days remain for a vehicle to pay for itself: a vehicle bought with sixty
days to go is cash converted into a depreciating asset. `[ns-air]`

### Which mode wins, and by how much

Measured across one-year runs on random seeds, **air and mixed air-and-road networks scored
several times what rail and water managed**, and the rail attempts that failed did not fail by a
little — they delivered nothing at all. `[gameplay]`

The reason is not the vehicles. Aircraft need no infrastructure between their endpoints, so the
only decisions that matter are ones the game answers well. Rail and water depend on a junction
between a depot and a line, and that junction is the thing hardest to confirm before committing
money to it. `[gameplay]`

### How long to wait

Judging when to act, and how long to let the world run before looking again, is part of what the
benchmark measures. It belongs to the route rather than the calendar: `[design]` `[ns-air]`

- about **10 days** to see a vehicle leave its depot and get under way
- about **30 days** to see a route start earning at all — one measured run had
  `cargo_delivered_total` at exactly 0 until day 73
- about **90 days** to see whether a route pays, which is the only horizon on which a decision to
  sell or re-point is worth making

Give an air route around a hundred game-days before judging it; give a rail route several hundred.
`[air]` `[rail]`

But a step with no actions at all is a step wasted: if your route is running and healthy, start
the next one rather than waiting. `[rail]`

### Write down what you decide

A turn that cannot remember its own plan re-invents one. Record what you commit to and why. Every
worker agent is rebuilt from scratch each turn — only the strategist's history survives — so
anything a worker must not forget lives in a tool that enforces it, not in prose it may skip.
`[design]` `[ns-air]`

---

### Learned rules
