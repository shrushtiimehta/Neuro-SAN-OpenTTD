# Fleet

Chooses vehicles, buys them, and gets them moving.

This is strategy, not reference. What an action is called and what it takes is served live by the
engine at `GET /v1/public/actions`; a hand-written parameter list is the thing that goes stale, so
there is none here.

Supported claims are promoted under the learned-rules heading at the foot of this file, tagged with
the session that confirmed them and the mode it was played in. Everything above that heading was
written by a person; everything below it was earned by a session and can be taken back. Do not edit
the tagged lines by hand — the promotion tool owns them, and it will only ever remove a line
carrying that tag.

---

What to buy, how many, and getting it moving.

### Read what the game will actually sell

Never name an engine yourself. `get_engines` carries a price per engine and the ids the running
game assigns, gated by year. Note that `get_engines(vehicle_type="air")` has returned TRAIN
engines with `success: true`, so the vehicle type has to be the literal the manifest names.

Score an engine by capacity times income per unit at this distance times speed, minus running cost
over the days remaining — not by capacity over running cost, and not by maximum capacity.

### Air: match the plane to the airport

**Large aircraft crash at small airports**, with no warning and no refusal. Where the good towns
only take commuter fields, fly small planes; where they take large or international fields, big
planes carry four times the load on the same leg. The smaller of a route's two fields decides what
may fly.

A purchase too late to return its price is worse than no purchase.

### Buying and dispatching are separate commits

A vehicle id only exists once its purchase has been committed, so orders and starts belong in the
next step rather than the same one.

Cloning is cheaper when a route already flies: a clone copies the orders, but **it arrives
stopped**, so it still needs starting. A clone without an explicit depot is built at the
original's current tile.

### `start_vehicle` is a TOGGLE

Calling it on a moving vehicle stops it. One measured trap: every vehicle parked beside its depot,
because `start_vehicle` was called twice and the second call stopped it. The fleet table shows
every row "not moving". Call it exactly once.

### Order flags

Leave the flags off for the orders on a new route. A station only starts producing cargo once a
vehicle has visited it, so a train told to wait for a full load sits in an empty station forever
and the route never starts. Never use full-load flags on a new route.

### Rail: a locomotive on its own carries nothing

**Buying a vehicle gives you an engine.** To haul anything you need wagons coupled to it, which is
what `build_train` is for. A rail route built end to end with a bare locomotive looks complete,
runs, and earns zero.

Rail type has to match the locomotive, and a company should build and buy in one rail technology.

### How many

Cargo piling up at a station means too few vehicles; vehicles arriving empty mean too many, or the
wrong destination. For road, one pair saturates past three or four buses, so growth is
more town pairs. For rail, one unsignalled line cannot take two trains, so growth is a
second corridor.

### Keep a cash floor

A batch should not spend the balance to nothing. The best air run's floor was 38,441 and it
survived; a run that bottomed at 7,707 nearly went bankrupt, which ends the run and scores nothing.

---

### Learned rules
