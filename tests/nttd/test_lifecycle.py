"""The session lifecycle: the plan cap, the scratchpad, telemetry, and the state readers.

These modules were at 0% coverage. Everything here was first run as a throwaway probe; this is
that probe kept, because the plan cap in particular is a headline gate of the design — a plan may
not be more confident than the least-tested claim it rests on — and nothing exercised it.
"""

# Each test's name is its sentence — a docstring here would only restate it.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import pathlib
import shutil

import pytest

from coded_tools.nttd import paths
from coded_tools.nttd import seed_playbooks
from coded_tools.nttd import session_number
from coded_tools.nttd import telemetry
from coded_tools.nttd.advance_session import AdvanceSession
from coded_tools.nttd.current_best_plan import WriteCurrentBestPlan
from coded_tools.nttd.log_claim import LogClaim
from coded_tools.nttd.scratchpad import Scratchpad
from coded_tools.nttd.state_read import StateRead
from coded_tools.nttd.write_session_plan import WriteSessionPlan

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# Long enough to clear the tools' own "that is too short to be a plan" guard.
PLAN = (
    "Open with two coastal town pairs, buses first because the roads already exist. "
    "Consolidate once three routes are earning. Leave the inland corridor alone until a "
    "depot is within range of it, and do not buy a fourth bus on a saturated pair."
)


@pytest.fixture(autouse=True)
def _session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / paths.LOG_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / paths.CONFIG_DIR, tmp_path / paths.CONFIG_DIR)
    seed_playbooks.prepare(fresh=True)
    return session_number.open_next()


def _claim(session, confidence, status="supported", varied=("seed", "map size")):
    reply = LogClaim().invoke(
        {
            "domain": "scout",
            "claim": f"Coastal pairs out-earn inland at {confidence}.",
            "status": status,
            "confidence": confidence,
            "varied": list(varied),
            "conditions": "t1, air, 256 flat",
            "evidence": "two pairs beat every inland pair",
            "re_test_when": "tier changes",
            "session_number": session,
        },
        {},
    )
    return reply["id"]


def _plan(session, **over):
    args = {
        "headline": "Coastal first.",
        "plan": PLAN,
        "confidence": "high",
        "biggest_untested_upside": "a third coastal pair",
        "session_number": session,
    }
    args.update(over)
    return WriteCurrentBestPlan().invoke(args, {})


# --- the plan cap ----------------------------------------------------------------------------


def test_a_plan_resting_on_a_high_claim_keeps_its_confidence(_session):
    high = _claim(_session, "high")
    assert _plan(_session, rests_on=[high], upside_claim_id=high)["confidence"] == "high"


def test_a_plan_cannot_be_more_confident_than_the_claim_it_rests_on(_session):
    low = _claim(_session, "low", varied=())
    reply = _plan(_session, rests_on=[low], upside_claim_id=low)
    assert reply["confidence"] == "low"
    assert reply.get("the_cap_applied")


def test_an_open_claim_caps_a_plan_to_low_whatever_its_stated_confidence(_session):
    still_open = _claim(_session, "med", status="open", varied=("seed",))
    reply = _plan(_session, rests_on=[still_open], upside_claim_id=still_open)
    assert reply["confidence"] == "low", "an untested assumption is not a med-confidence one"


def test_with_no_upside_named_the_weakest_cited_claim_sets_the_ceiling(_session):
    high, low = _claim(_session, "high"), _claim(_session, "low", varied=())
    reply = _plan(_session, rests_on=[high, low])
    assert reply["confidence"] == "low", "one well-established claim cannot carry a weak one"


def test_a_plan_cannot_rest_on_a_claim_that_is_not_in_the_commons(_session):
    reply = _plan(_session, rests_on=["s9_99"])
    assert reply.get("status") == "refused", reply


# --- the scratchpad is read-once --------------------------------------------------------------


def test_a_note_is_visible_exactly_once(_session):
    del _session
    Scratchpad().invoke({"pad": "player", "note": "depot at 12,40"}, {})
    first = Scratchpad().invoke({"pad": "player"}, {})
    second = Scratchpad().invoke({"pad": "player"}, {})
    assert first["note"] == "depot at 12,40" and first["note_found"]
    assert not second["note_found"], "reading clears it, so advice cannot rot into stale advice"


def test_pads_cannot_read_each_other(_session):
    del _session
    Scratchpad().invoke({"pad": "player", "note": "player only"}, {})
    assert not Scratchpad().invoke({"pad": "watcher"}, {})["note_found"]


# --- telemetry -------------------------------------------------------------------------------


def test_the_champion_is_the_best_session_and_keeps_its_number(_session):
    for value, number in ((50_000, 1), (90_000, 2), (70_000, 3)):
        telemetry.record_session(
            {
                "session": f"s{number}",
                "session_number": number,
                "turns": 10,
                "company_value": value,
                "total_cargo": 100,
            }
        )
    best = telemetry.champion()
    assert best["company_value"] == 90_000
    assert telemetry.headline(best)["session_number"] == 2, "the headline must keep the number"


def test_turn_rows_are_filed_under_their_own_session(_session):
    del _session
    telemetry.record_turn({"session": "a", "session_number": 1, "turn": 1, "company_value": 10})
    telemetry.record_turn({"session": "a", "session_number": 2, "turn": 1, "company_value": 20})
    assert len(telemetry.turn_rows(1)) == 1 and len(telemetry.turn_rows(2)) == 1


# --- the state readers -------------------------------------------------------------------------


def test_state_read_serves_a_mapped_file_and_refuses_an_unmapped_one(_session):
    del _session
    mapping = {"playbook_scout": paths.playbook("scout")}
    ok = StateRead().invoke({"name": "playbook_scout", "name_map": mapping}, {})
    assert ok["status"] == "ok" and "Scout" in ok["content"]
    denied = StateRead().invoke({"name": "/etc/passwd", "name_map": mapping}, {})
    assert not (isinstance(denied, dict) and denied.get("status") == "ok"), denied


# --- the session boundary -----------------------------------------------------------------------


def test_the_session_plan_is_written_and_a_stub_is_refused(_session):
    reply = WriteSessionPlan().invoke(
        {"plan": PLAN, "mode": "air", "what_changed_from_last_session": "first session", "session_number": _session},
        {},
    )
    assert not str(reply).startswith("ERROR:"), reply
    with open(paths.SESSION_PLAN_PATH, encoding="utf-8") as handle:
        assert "coastal" in handle.read().lower()
    stub = WriteSessionPlan().invoke({"plan": "go", "mode": "air", "session_number": _session}, {})
    assert str(stub).startswith("ERROR:"), "every turn reads this; a stub is worse than nothing"


def test_closing_a_session_snapshots_the_playbooks_and_names_what_is_still_open(_session):
    still_open = _claim(_session, "med", status="open", varied=("seed",))
    telemetry.record_session(
        {"session": "a", "session_number": _session, "turns": 10, "company_value": 90_000, "total_cargo": 100}
    )
    report = AdvanceSession().invoke({"session_number": _session}, {})
    assert isinstance(report, dict), report  # invoke() may return an ERROR string
    assert report["status"] == "ok"
    assert pathlib.Path(report["playbook_snapshot"]).exists(), "the close must leave a snapshot"
    assert still_open in report["claims_still_open"]
    assert report["warning"], "an open claim carrying over must be said out loud"
    # `or {}` rather than an assert: the champion is Optional in the tool's own return, and
    # pylint reads that, so this keeps the check honest without fighting the inference.
    assert (report["champion"] or {}).get("company_value") == 90_000


def test_closing_with_no_finished_session_says_there_is_no_baseline(_session):
    report = AdvanceSession().invoke({"session_number": _session}, {})
    assert isinstance(report, dict), report
    assert report["champion"] is None and report["note"]
