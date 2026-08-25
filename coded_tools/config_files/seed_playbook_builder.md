# Builder

Turns a chosen corridor into something that actually carries, and confirms what landed.

This is strategy, not reference. What an action is called and what it takes is served live by the
engine at `GET /v1/public/actions`; a hand-written parameter list is the thing that goes stale, so
there is none here.

Confirmed trials are promoted under the learned-rules heading at the foot of this file, tagged with
the number of the session that confirmed them. Do not edit those lines by hand — the promotion tool
owns them, and it will only ever remove a line carrying that tag.

---

Turning a chosen corridor into something that actually carries.

### Air: build both airports before buying anything

1. Pick two large, distant towns.
2. `find_airport_spots` in each.
3. Build both airports, one **before** buying anything.
4. Ask `get_hangars` for the hangar tile. The build tells you the station it created but not
   where the hangar is, and the hangar is the depot an aircraft is bought into.
5. Buy the aircraft, give it orders between the two airports.

The split between building and buying is real, not superstition: **the airport must exist before
its hangar can be found.**

The hangar tile is not derivable from the airport tile. Four consecutive `buy_vehicle` calls at
the airport coordinates failed with `ERR_UNKNOWN` and no diagnostic. Resolve it from
`get_hangars`, never by arithmetic.

Stage both airports so they cost ONE game day together rather than one each.

**Start with the smallest airport type** that serves the need: a smaller footprint fits where
nothing else does, and on a crowded or hilly map the difference between a route and no route is
usually whether the airport fitted.

After the commit, confirm what landed — check the airport attached to the town that was intended.

### Air: the refusal to expect

A town will refuse a further station once it already has several, reporting too many stations in
that town. The fix is **another town, not another tile**: retrying nearby in the same town will
keep failing.

### Rail: the order of work, and it is not the obvious one

1. Pick a producer and a consumer by **industry id**.
2. `find_station_spot` for each end. It returns candidate spots, each with the platform
   **orientations that would actually work**.
3. Build both stations, passing the `direction` the finder reported. Leaving it to default is the
   classic silent failure: the station builds on the wrong axis and the pathfinder cannot join
   it.

   **Build exactly one platform, three tiles long, and say so explicitly.** The finder dry-runs a
   one-by-three station, so that is the footprint the game agreed to. The build defaults to a
   larger one, which needs ground the finder never checked, and the result is a refusal for ground
   being occupied at a tile the finder just called clear. A first live run failed exactly here.
4. **Lay the track between the built stations.** Use `connect_rail`, giving it the station
   platform tiles as the hint parameters at each end — that is what makes the route join up to
   your platforms rather than merely reach them.
5. **Then** the depot. `find_rail_depot_spot` looks for a tile adjacent to existing rail, so
   before track exists it correctly returns nothing. Asking earlier is not an error to work
   around; it is the wrong order.
6. Buy the train and give it orders.

### Rail: where the depot goes

A depot built beside a platform joins that station's **stub** of track, not the main line.
Measured at three towns, every such depot reached 5 to 8 tiles of a 71-tile line. **Put the depot
against the middle of the corridor instead**, and trace from the depot rather than between
platforms.

### Rail: water crossings

A corridor that crosses water fails as `ERR_TUNNEL_CANNOT_BUILD_ON_WATER`: the connection reaches
for a tunnel where the crossing needs a bridge, and the bridge heads must be at equal height.
This defeated five of six routes on one map.

### Rail: laying track yourself

`build_path` takes the tiles you chose and works out how each piece must sit, including the
three-tile context rail needs. Use it for a route of your own design; use `connect_rail` when you
would rather the pathfinder chose. `build_rail_track` lays a single piece in a chosen orientation
and is the only way to express a siding, a junction stub or a passing loop.

`connect_rail` and `connect_road` must be alone in a step: they lay a whole corridor, can
partially fail on a single tile, and the refusal names that tile. Batching them with anything else
makes the report ambiguous about which action the coordinate belongs to.

### Rail: signals

Signals are what let more than one train share a line. A single train on a simple out-and-back
route does not need them; add them when a second train joins. One unsignalled line cannot take two
trains.

---

### Learned rules
