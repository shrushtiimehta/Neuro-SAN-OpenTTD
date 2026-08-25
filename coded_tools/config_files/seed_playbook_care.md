# Care

Keeps what exists earning, and knows when a vehicle cannot be saved.

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

Keeping what exists earning, and knowing when it cannot be saved.

### Judge on how long, not on the state

`at_station` for a vehicle loading at a station and `in_depot` for one in its hangar are both
**normal**. Treating any non-empty idle reason as a problem made a working fleet read as a wall of
faults, told the strategist to repair before expanding, and would eventually have sold working
aircraft. `[design]`

Use the engine's own problems list rather than deriving one. It never reads the idle reason, and it
allows for a vehicle still settling. `[design]`

No vehicle is stuck until it has had time to fly or drive its route out and back — a window worked
out from the leg and the vehicle's speed, so a long corridor gets a longer grace than a short one
and neither gets a fixed day number. `[ns-air]`

Refuse any verdict harsher than "watching" early in a run: one measured run had
`cargo_delivered_total` at exactly 0 until day 73. `[design]`

### How to see the three silent failures

| symptom | cause | how to see it |
|---|---|---|
| Every vehicle parked beside its depot | `start_vehicle` called twice; the second call stopped it | the fleet table shows every row "not moving" |
| A vehicle in the far corner of the map | it is lost, and says so | `lost` on the vehicle |
| Stations full, nothing delivered | the depot cannot reach the line | trace from the depot, not between platforms |

`[gameplay]`

Two more worth knowing: a cargo total reading 0 at the end of a run is the game's quarterly
counter resetting on 1 January, the day a 366-day run ends — score against the banked total, never
the quarter. And a company value of exactly 1 is the floor, not a bug. `[gameplay]`

A crash removes a vehicle from the observation and reports nothing. The only way to notice one is
to have kept the previous list of vehicle ids and compare. `[design]`

### Repointing

Clear a vehicle's orders before re-issuing them. Appending left one aircraft with four zig-zagging
orders. Resolve the route from the record of what was built, not from the last route in a list: a
repair tool that re-ordered every broken vehicle onto the LAST route's stations regardless of which
route it flies is a measured defect. **Never repair a vehicle onto a route it does not fly.**
`[design]` `[ns-air]`

Use the service-only depot call, not the plain send-to-depot: the latter parks the vehicle and
needs a follow-up start. `[design]`

### Retiring

Selling a working vehicle is the expensive mistake. A retirement requires a stuck verdict, a
committed repoint, and time for that repoint to have failed. `[ns-air]`

**Send to a depot and sell on a LATER turn, once it has arrived** — the two cannot be done in one
step. One measured disposal batched them together and the sale was refused every time and
resubmitted forever; the round trip took 32 game days with three `ERR_VEHICLE_NOT_IN_DEPOT`
refusals, and buying during the wait bottomed cash at 7,707. Treat expected proceeds as unavailable
while the vehicle is still in flight. `[design]`

A vehicle that is not earning is money already spent, and repairing it beats replacing it.
`[ns-air]`

---

### Learned rules
