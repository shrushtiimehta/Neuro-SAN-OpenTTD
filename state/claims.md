# The commons: one claim per record, append-only
#
# Every write appends a block. A status change appends a NEW revision for the same id
# rather than editing the old one, so a claim supported in one session and refuted in a
# later one has both blocks and a reader can see the order they arrived in. The current
# standing of a claim is COMPUTED by folding this file, never stored.
#
# Fields: ID REV DOMAIN ORIGIN CLAIM STATUS CONFIDENCE CONDITIONS EVIDENCE VARIED
#         REFUTED_DESPITE 'RE-TEST WHEN' NOTE
---
ID: s1_1
REV: 1
DOMAIN: strategist
ORIGIN: planner
CLAIM: Completing one end-to-end air route (both airports built, hangar resolved from get_hangars, aircraft bought, orders issued, started) inside the first 10 game days produces a first cargo delivery before day 40.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, stepped mode, session 1, air mode, opening from zero infrastructure with starting cash and no prior route.
EVIDENCE: Untested here. Baseline prose reports a hand-played air opening consuming 15 game days for work it estimates needs 3, and one measured run with cargo_delivered_total at exactly 0 until day 73 — neither observation is from this scenario.
RE-TEST WHEN: Any session on a 256 flat map that records both the game day the first route was confirmed complete and the game day of first non-zero cargo_delivered_total.
NOTE: Record two figures explicitly: day-first-route-complete and day-of-first-delivery. Without both this claim cannot be judged, and a null result may mean the route was never confirmed complete rather than that tempo does not matter.
---
ID: s1_2
REV: 1
DOMAIN: scout
ORIGIN: planner
CLAIM: Cargo loaded per flight is governed primarily by the tile distance from each airport to its intended town centre, with airports sited inside the catchment radius loading multiples of what distant ones load.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, stepped mode, session 1, air mode, commuter-class airports on the two largest towns reachable.
EVIDENCE: Untested here. Baseline reports re-siting airports alone moving a quarter's income from 25 to 131,740, and a metropolitan field built 29 tiles from its intended town attaching to a 348-person village, scoring 118 against 173 — all on other maps, unknown terrain.
RE-TEST WHEN: Any session that records, per airport, the tile distance to the intended town centre, the population actually attached, and cargo carried per flight on that leg.
NOTE: A flat map may place airports closer to centres than a hilly one, which would compress the effect and make it look weak for a reason that has nothing to do with catchment. Log the distances even when they are small.
---
ID: s1_3
REV: 1
DOMAIN: builder
ORIGIN: planner
CLAIM: On a flat map a rail corridor can be completed with connect_rail reporting status complete and no gaps, because the documented rail failures are terrain failures (tunnel-on-water, unequal bridge heads) that flat ground does not produce.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, 256 flat terrain. Raised in session 1 but NOT scheduled for test this session, which plays air.
EVIDENCE: No test. The baseline's rail pessimism rests on runs where water crossings defeated five of six routes on one map, and on rail attempts that delivered nothing — the terrain of those maps is not recorded as flat, so the failure may be a property of the map rather than of rail.
RE-TEST WHEN: Once one air baseline is banked on this scenario, spend a session or a spare corridor on a single industry-to-industry rail route on flat ground and record connect_rail status, gaps, and cargo delivered.
NOTE: This is the session's biggest deliberate omission. Air is chosen on evidence gathered elsewhere; that evidence has never been checked on flat terrain, where rail's main documented killer is absent by construction.
---
ID: s1_1
REV: 2
DOMAIN: strategist
ORIGIN: planner
CLAIM: Completing one end-to-end air route (both airports built, hangar resolved from get_hangars, aircraft bought, orders issued, started) inside the first 10 game days produces a first cargo delivery before day 40.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, stepped mode, SESSION 2, air mode, opening from zero infrastructure with starting cash and no prior route. Re-raised because session 1 recorded 0 turns and 0 finished sessions, so this was never tested under any conditions.
EVIDENCE: No test exists. Telemetry for session 1 reports sessions=0, turns=0. The only figures behind this are from other maps: a hand-played air opening consuming 15 game days for work estimated at 3, and one measured run with cargo_delivered_total at exactly 0 until day 73.
RE-TEST WHEN: Any session on this 256 flat map that records BOTH the game day the first route was confirmed complete (connect status complete, no gaps) and the game day of first non-zero cargo_delivered_total.
NOTE: Two figures or this cannot be judged. A null result is ambiguous between "tempo does not matter" and "the route was never actually confirmed complete", so record the completion day even when the route is late. If the 10-day threshold is missed, still log the actual completion day and first-delivery day — the shape of the relationship is more useful than the pass/fail of the specific threshold, which was picked from prose rather than measurement.
---
ID: s1_2
REV: 2
DOMAIN: scout
ORIGIN: planner
CLAIM: Cargo loaded per flight is governed primarily by the tile distance from each airport to its intended town centre, with airports sited inside the catchment radius loading multiples of what distant ones load.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, stepped mode, SESSION 2, air mode, airports on the two largest towns reachable on the longest available leg. Re-raised: session 1 recorded 0 turns, so no distance or per-flight figure has ever been observed on this map.
EVIDENCE: No test exists on this scenario. Supporting figures come from other maps of unrecorded terrain: re-siting airports alone moving a quarter's income from 25 to 131,740, and a metropolitan field built 29 tiles from its intended town attaching to a 348-person village and scoring 118 against 173.
RE-TEST WHEN: Any session that records, per airport, the tile distance to the intended town centre, the population actually attached, and cargo carried per flight on that leg.
NOTE: A flat map may site airports closer to town centres than a hilly one, compressing the effect so it looks weak for a reason unrelated to catchment. Log the distances even when they are all small, and log the population actually attached alongside the population of the town that was intended — a mismatch between those two is the cheapest available signal that a field missed its catchment.
---
ID: s2_1
REV: 2
DOMAIN: fleet
ORIGIN: planner
CLAIM: On this map the airport class the two chosen towns will accept, rather than the aircraft budget, is what caps cargo per flight: where both ends accept a large or international field, cargo per flight is at least double what the same leg carries when the smaller end is limited to a commuter field.
STATUS: open
CONFIDENCE: low
CONDITIONS: t1_256_flat_1001_stepped, stepped mode, session 2, air mode, first long-haul corridor between the two largest towns reachable, opening from zero infrastructure.
EVIDENCE: Untested anywhere in this commons. The fleet playbook asserts without figures that large aircraft crash at small airports with no warning and no refusal, and that big planes carry four times the load on the same leg where fields permit them. No session has recorded an airport class alongside a cargo-per-flight figure, so the size of the effect here is unknown.
VARIED: Nothing yet — first raising.
RE-TEST WHEN: Any session recording, per corridor: the airport class accepted at each end, the aircraft class flown, and cargo per flight. Reopen immediately if a large aircraft is lost without a refusal being reported, since that would be the crash-at-small-field mechanism showing up as attrition rather than an error.
NOTE: Raised because it costs this session no extra actions: the figures needed are ones the plan already requires the run to bring back. It matters for sequencing rather than for this run alone — if class caps the load, then scouting should rank candidate town pairs by what field they will accept before ranking them by population or leg length, which would change step 2 of the plan. Do not let this become a reason to build a larger field than fits; the builder playbook's smallest-that-serves guidance is untested here too.
