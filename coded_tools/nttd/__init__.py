"""Coded tools for the nttd networks: the OpenTTD long-horizon planning benchmark.

Two layers live here, and the split is the point.

**The game layer** talks to the nttd engine over HTTP and nothing else. It never imports the
`nttd` package: the engine is a separate process reached at `NTTD_API_URL`, which is what lets
this studio run against an engine on another machine, at another version, or not at all.

**The knowledge layer** is why this exists rather than nttd-workbench. A benchmark run is one
session, and a session teaches things that die with it unless something writes them down. The
playbooks, the trials and the outcome ledger are that record: a hypothesis is logged at the
start of a session, judged at the end of it, and a confirmed one is promoted into the playbook
the next session reads first.

The two layers do not know about each other. A tool that plays the game never reads a playbook,
and a tool that curates knowledge never spends a game day.
"""
