# Session 1 plan

Written 2026-08-25T23:23:13+00:00. Mode: air.

## The plan

FIRST RUN — no champion, no established claims. Goal is a banked, legitimate baseline with figures, not a heroic score.

1. Read the position report and take the run length from it. Do not assume the calendar.
2. Scout: rank towns by population, pick the LONGEST leg between two large towns. Air revenue rises with distance, so a long leg is correct — do not second-guess it toward a short hop. Use find_airport_spots for both ends; a returned tile is one the game already agreed to. Empty list -> another town or a wider radius.
3. ONE commit builds BOTH airports. Smallest type that serves. Then get_hangars for the hangar tile — do not derive it by arithmetic.
4. NEXT commit buys the aircraft (matched to the SMALLER field — big planes crash at small airports with no refusal), issues orders with NO full-load flags, and calls start_vehicle exactly ONCE. It is a toggle; a second call parks the plane.
5. Confirm what landed: which town each airport attached to, its tile distance to that town centre, and the population attached.
6. Let it run ~100 days before judging. Cargo may read 0 for a long while — one measured run sat at 0 until day 73. Do not sell, do not re-point on an early reading.
7. While it runs, scout the SECOND town pair. Growth is another corridor, not more planes on the first. Add a plane only where cargo is visibly piling up.
8. Cash floor ~40,000. Borrow only a shortfall for something that will earn; keep loan at or under 250,000.

BRING BACK THESE NUMBERS (the claims cannot be judged without them):
- day the first route was confirmed complete (tests s1_1)
- day of first non-zero cargo delivered (tests s1_1)
- per airport: tile distance to intended town centre, population attached, cargo per flight (tests s1_2)
- banked cargo total, not the quarterly counter.

A build returning success is not a working route. Confirm a vehicle can get end to end before buying one.

## What is different from the last session

Nothing — this is session 1. No baseline exists, so the playbooks are being played as written and every number this run produces becomes the first point of comparison.

## How to read this

This is the plan for the whole session. Follow it unless the position makes it plainly wrong, and if it does, say so rather than quietly playing something else. The trials in force carry the specifics of what is being tested.
