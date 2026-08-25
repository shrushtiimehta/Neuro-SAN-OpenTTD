# Current best plan

The compiled working strategy. Revised by append: the newest block below is current, the older
ones are kept so a reader can see what the plan used to be and whether changing it helped.

**This does not override the claims.** Every recommendation names the claim ids it rests on, and
its confidence cannot exceed that of the claim ruling out its biggest untested upside. When this
and a claim disagree, the claim wins and this needs revising.

<!-- REVISIONS BELOW, NEWEST FIRST -->

## Revision 1 — 2026-08-25T23:23:01+00:00

**First run with no baseline: bank one confirmed-working long-haul air corridor fast, then widen with a second town pair rather than more planes on the first.**

Confidence: low. Rests on: s1_1, s1_2, s1_3.

This is the first session on the benchmark. There is no champion, no prior claim, and nothing to beat — the job is to bank a legitimate baseline with figures a later session can compare against, not to win.

ORDER OF WORK
1. Read the position report first and take the run length FROM IT. Do not assume 366 days; every "by day N" target below is expressed against the reported remaining days.
2. Scout both endpoints before building either. Rank towns by population, pick the longest leg between two large towns, and use find_airport_spots for each — a returned tile is one the game already agreed to. An empty list means try another town or a wider radius, rather than a guessed tile.
3. Build BOTH airports in ONE commit. Smallest airport type that serves the need. Then get_hangars for the hangar tile; the hangar is not derivable from the airport tile by arithmetic.
4. Next commit: buy the aircraft, matched to the SMALLER of the two fields, and issue orders with no full-load flags. Call start_vehicle exactly once — it is a toggle.
5. Confirm what landed: which town each airport actually attached to, and its tile distance to that town centre. Log those figures whether they look good or bad; s1_2 cannot be judged without them.
6. Give the route ~100 game days before any verdict on it. Avoid selling or re-pointing early. Avoid idling too: once the first route is confirmed running and healthy, start scouting the SECOND town pair rather than stepping with no actions.
7. Growth is a second corridor rather than a fifth plane on the first. Add aircraft to an existing leg only when cargo is visibly piling at a station.
8. Stop buying when too few days remain for a vehicle to return its price. Keep a cash floor near 40,000; the run that bottomed at 7,707 nearly went bankrupt, and bankruptcy scores nothing.

MONEY
Borrow only the shortfall for a build that will earn, rather than to hold cash. Loan above 250,000 forfeits SCORE_LOAN outright, and drawing a loan does not raise company_value because it is subtracted straight back.

WHAT TO LEAVE ALONE THIS SESSION
Rail, water, and the three score components a one-year run cannot win (MIN_PROFIT, MIN_INCOME, LOAN-past-250k). Treat money as a poor score route: it is 50 points and needs ten million.

MEASUREMENTS THIS RUN MUST BRING BACK
Day the first route was confirmed complete; day of first non-zero cargo delivered; per-airport tile distance to intended town centre and population attached; cargo per flight; and the banked cargo total rather than the quarterly counter, which resets on 1 January.

Biggest untested upside: Rail on flat terrain (s1_3). The case for air over rail rests entirely on runs from other maps whose terrain is not recorded as flat, and the specific documented rail killers — tunnel-cannot-build-on-water, unequal bridge heads — are terrain failures that a flat 256 map should not generate. Rail moves industry tonnage where an airport catchment collects passengers, so if the corridor completes at all the cargo ceiling could be materially higher. This plan declines that test only because a first session with no baseline should bank a working number first; it is the first thing to spend a session on once one exists. (see s1_3)



