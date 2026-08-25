# Common ground

Read by every agent. What holds whatever is being moved, and what the score measures.
Nothing mode-specific and nothing about one job belongs here.

This is strategy, not reference. What an action is called and what it takes is served live by the
engine at `GET /v1/public/actions`; a hand-written parameter list is the thing that goes stale, so
there is none here.

Confirmed trials are promoted under the learned-rules heading at the foot of this file, tagged with
the number of the session that confirmed them. Do not edit those lines by hand — the promotion tool
owns them, and it will only ever remove a line carrying that tag.

---

What holds whatever is being moved.

### The one rule that matters most

**Complete ONE working route before building anything else.** A working route is two stations in
different places, a connection between them, a depot, a vehicle, and orders. Anything less earns
nothing at all. Half-built infrastructure is not partial progress; it is cost with no revenue,
and it is the commonest way a run ends with a large map of track and no money.

If you have stations without vehicles, buy vehicles. Do not build more stations.

### What the score measures

The rating is OpenTTD's own `performance_rating`, nine capped components summing to 1000.
**Cargo delivered is 400 of those 1000 — 40% of the entire score, and nothing else comes close.**
Money is worth 50 points and needs ten million to collect them, so a run that moves freight badly
cannot be rescued by being rich.

Three components a one-year run cannot win, and should not be optimised for:

- `SCORE_MIN_PROFIT` (100 points) is always 0 — it only counts vehicles older than two years.
- `SCORE_MIN_INCOME` (50 points) needs every quarter profitable, and a company that spends its
  first quarter building has a negative one.
- `SCORE_LOAN` (50 points) is `250,000 - current_loan` clamped at zero, so borrowing past
  250,000 forfeits all 50.

A realistic ceiling for a single year is around 800, and hand-played runs on random seeds land
well under a quarter of that. Treat the rating as a scale you are near the bottom of.

`company_value` is assets minus loan plus cash, floored at 1. **Drawing a loan does not raise
company value**, because the loan is subtracted again — borrowing buys earning assets sooner, it
does not make the company look bigger. A company value of exactly 1 is not a bug; it is a company
that owes more than it owns.

### Revenue

Payment is for cargo **delivered**, and it falls the longer cargo sits in transit. So:

- Two stations in the **same town earn almost nothing**. Distance is what pays.
- A short busy route beats a long idle one.
- Cargo piling up at a station means too few vehicles. Vehicles arriving empty mean too many, or
  the wrong destination.

### Catchment, or zero revenue

A station only serves what is inside its catchment. A station placed near an industry but not
covering it looks identical to a working one and earns nothing.

### Planning is free; committing costs a day

A step advances the world by one day and a batch has no ceiling. Build a whole corridor in one
commit rather than one action at a time — a 366 day budget cannot be spent on paperwork. The best
hand-played air run spent 15 game days on an opening that needs 3.

### Never invent an identifier

Engine ids, coordinates, tiles and station ids all come from tools. One measured run submitted
`buy_vehicle` **35 times** with invented engine ids — 30, 40, 21, 60, 90 — all refused, when the
real aircraft ids in that era were 238 to 246.

If a tool refuses, read the reason: it is written for you, and repeating the call unchanged gets
the same answer. A refused action usually changes nothing, so the world looks identical either
way.

### Reading a build result

`connect_road`, `connect_rail` and `build_path` can partly succeed. They report a `status` of
`complete` or `partial` and a list of gaps, and **a partial route carries nothing: a gap means no
route at all.** Never test them as a boolean — check the status is complete and no gaps remain.

A build action returning success is NOT a working route. Nothing buys a vehicle until a tool has
confirmed a vehicle can actually get from one end to the other.

### Money

Borrow to build something that will earn, not to hold cash. Interest runs whether or not the
money is working. Do not borrow as a first move: check what the company has, work out what the
next build costs, and take only the shortfall.

### Patience

A new route takes time to earn. Leave running vehicles alone; do not judge a route on the step
after you built it, and never sell your whole fleet.

---

### Learned rules
