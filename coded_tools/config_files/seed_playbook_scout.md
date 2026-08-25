# Scout

Finds where the next corridor should go, and which sites will actually earn.

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

Where a corridor should go, and which sites earn.

### Always ask a finder

`find_bus_stop_spots`, `find_station_spot`, `find_dock_spots`, `find_airport_spots` and the rest
run a real dry run inside the game, under your company, with the parameters you gave. **A tile
they return is one the game has already agreed to. Guessing a tile is the single commonest wasted
step.** `[common]`

When a finder returns an **empty list**, that is the failure to handle: try another town or a
larger radius. An error is rarer than no result. `[common]`

### Air: go long, and check the catchment

The mode where the usual "closest pair first" advice is wrong. Aircraft are fast, expensive, and
ignore terrain entirely, so they earn on **long-haul** routes. Pick the longest pair you can
reach, not the nearest, and prefer the two largest towns: demand scales roughly with the product
of the populations over the distance. `[air]`

Air revenue rises with distance, which is the opposite sign to road, so a ranking that favours a
long leg is correct and should not be second-guessed towards short hops. `[ns-air]`

Measured: a single big plane on a 205-tile leg earned 74,986, while small planes shuttling
35-tile hops earned around 13,000 each. `[gameplay]`

**Rank towns by population and check the airport fits inside its own catchment.** A commuter
airport covers 4 tiles. An airport sited 16 to 28 tiles from the town centre earns almost
nothing: re-siting the airports alone took a quarter's income from 25 to 131,740. One run built a
metropolitan field 29 tiles from its intended town, it attached to a 348-person village instead,
and the run scored 118 against 173. `[gameplay]` `[design]`

**Both endpoints must be real towns.** A long leg into a 348-person village returns big planes
almost empty and costs the same to fly as a leg into a city. Airport capability is not a reason
to pick a destination; population is. `[gameplay]`

Two airports in the **same town** earn nothing. Different towns, always. `[air]`

### Rail: pair the industries, not the towns

Pick a producer and a consumer, and use the **industry id, not the town id**, for a cargo route.
A station sited at a town near an industry does not serve the industry. `[rail]`

Rail station catchment is small. A 3-tile platform beside a town of 2,468 reported a supply of
**12 passengers**, against the hundreds an airport in the same town collects — so rail may not
want passengers at all. Its catchment is tiny while industry tonnage is large. `[gameplay]`
`[design]`

### Water and road, for when those modes are written

Docks sited by town are frequently on **unconnected water**. On two maps in a row, no pair of
docks built for the largest towns shared a body of water at all. Before buying ships, confirm a
vessel can actually reach the far dock. `[gameplay]`

Towns already have roads, so most of a road corridor exists — one measured route needed 6 tiles
built out of 25, which makes buses the fastest way to a positive balance early. **One pair
saturates**: past three or four buses a route has nothing left to carry, so growth is more town
pairs, not more buses. `[gameplay]`

---

### Learned rules
