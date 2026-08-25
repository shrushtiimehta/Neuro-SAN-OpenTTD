"""The failure signatures, and the contract between what the runner writes and diagnose reads.

The traps in `nttd/docs/gameplay_guide.md` section 4 all produce a run that looks busy from the
inside and scores nothing. Each check here asserts both directions: that a signature fires on the
shape it is for, and that it stays quiet on the shape it is not for. A detector that cries wolf
gets ignored, which costs more than not having it.
"""

# Each test's name is its sentence — a docstring here would only restate it.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import pathlib
import shutil

import pytest

from apps.nttd.runner import _tally
from apps.nttd.runner import _turn_row
from coded_tools.nttd import diagnose
from coded_tools.nttd import paths
from coded_tools.nttd import seed_playbooks
from coded_tools.nttd import session_number
from coded_tools.nttd import telemetry

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _session(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / paths.LOG_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / paths.CONFIG_DIR, tmp_path / paths.CONFIG_DIR)
    seed_playbooks.prepare(fresh=True)
    return session_number.open_next()


def _row(turn, **over):
    """A healthy turn, unless a test spoils one field of it."""
    row = {
        "turn": turn,
        "company_value": 50_000,
        "stations": 4,
        "vehicles": 6,
        "cargo_delivered": 900,
        "problems": 0,
        "problem_kinds": {},
        "refusals": {},
    }
    row.update(over)
    return row


def _fired(rows):
    return {found["signature"] for found in diagnose.run(rows)}


# --- company value at the engine's floor -------------------------------------------------------


def test_company_value_of_exactly_one_is_reported():
    assert "company_value_at_floor" in _fired([_row(1), _row(2, company_value=1)])


def test_a_merely_low_company_value_is_not_the_floor():
    assert "company_value_at_floor" not in _fired([_row(1, company_value=2)])


# --- built, but delivering nothing --------------------------------------------------------------


def test_stations_built_and_nothing_delivered_is_reported_once_sustained():
    rows = [_row(t, cargo_delivered=0) for t in range(1, diagnose.SUSTAINED_TURNS + 1)]
    assert "built_but_delivering_nothing" in _fired(rows)


def test_one_quiet_turn_is_not_a_broken_route():
    rows = [_row(t, cargo_delivered=0) for t in range(1, diagnose.SUSTAINED_TURNS)]
    assert "built_but_delivering_nothing" not in _fired(rows), "a new route has not run yet"


def test_delivering_cargo_clears_it():
    rows = [_row(t, cargo_delivered=0) for t in range(1, diagnose.SUSTAINED_TURNS + 1)]
    rows.append(_row(9))
    assert "built_but_delivering_nothing" not in _fired(rows)


# --- the fleet-wide stall (the double `start_vehicle` shape) --------------------------------------


def test_a_problem_on_every_vehicle_reads_as_fleet_wide():
    rows = [_row(1, vehicles=6, problems=6, problem_kinds={"vehicle is not moving": 6})]
    found = _fired(rows)
    assert "fleet_wide_stall" in found


def test_a_couple_of_bad_vehicles_is_not_a_fleet_wide_stall():
    assert "fleet_wide_stall" not in _fired([_row(1, vehicles=6, problems=2)])


def test_no_vehicles_at_all_is_not_a_stall():
    assert "fleet_wide_stall" not in _fired([_row(1, vehicles=0, problems=0)])


# --- one call refused over and over ---------------------------------------------------------------


def test_an_action_refused_repeatedly_is_reported_with_its_count():
    rows = [_row(1, refusals={"connect_rail": 16, "buy_vehicle": 1})]
    found = diagnose.run(rows)
    hit = next(f for f in found if f["signature"] == "repeated_refusals")
    assert hit["refused_by_action"] == {"connect_rail": 16}, "one-off failures are not the story"
    assert "connect_rail" in hit["what_the_engine_is_saying"]


def test_ordinary_trial_and_error_is_not_a_repeated_refusal():
    assert "repeated_refusals" not in _fired([_row(1, refusals={"connect_rail": 1, "build": 2})])


# --- the tool ---------------------------------------------------------------------------------------


def test_a_healthy_run_reports_nothing_and_says_so(_session):
    telemetry.record_turn({**_row(1), "session_number": _session})
    reply = diagnose.Diagnose().invoke({"session_number": _session}, {})
    assert reply["signatures"] == [] and reply["note"]


def test_a_broken_run_reports_and_refuses_to_prescribe(_session):
    telemetry.record_turn({**_row(1, company_value=1), "session_number": _session})
    reply = diagnose.Diagnose().invoke({"session_number": _session}, {})
    assert reply["signatures"], reply
    assert "not instructions" in reply["how_to_read_this"], (
        "the response to a signature is a claim to test, not something this tool decides"
    )


def test_no_turns_yet_is_not_an_error(_session):
    reply = diagnose.Diagnose().invoke({"session_number": _session}, {})
    assert reply["status"] == "ok" and reply["turns"] == 0


# --- the contract between the runner's writer and this reader ---------------------------------------


def test_the_runner_writes_the_shape_diagnose_reads():
    """The two halves are in different packages; only this asserts they agree."""
    sly = {
        "refusals": [
            {"action": "connect_rail", "error": "ERR_PRECONDITION_FAILED"},
            {"action": "connect_rail", "error": "ERR_LAND_SLOPED"},
            {"action": "connect_rail", "error": "ERR_PRECONDITION_FAILED"},
            {"action": "connect_rail", "error": "ERR_PRECONDITION_FAILED"},
            {"action": "buy_vehicle", "error": "ERR_PRECONDITION_FAILED"},
        ]
    }
    pos = {
        "money": {"company_value": 1},
        "built": {"stations": 3, "vehicles": 4},
        "earning": {"cargo_delivered_total": 0},
        "problems": [{"problem": "vehicle is not moving"}] * 4,
    }
    row = _turn_row("sess", 1, 7, {"game_date": 100}, pos, 1.5, sly)

    assert row["refusals"] == {"connect_rail": 4, "buy_vehicle": 1}
    assert row["problem_kinds"] == {"vehicle is not moving": 4}

    fired = _fired([row, row, row])
    assert fired == {
        "company_value_at_floor",
        "built_but_delivering_nothing",
        "fleet_wide_stall",
        "repeated_refusals",
    }, fired


def test_tally_survives_a_ledger_of_junk():
    assert _tally([None, "nonsense", {"action": "a"}, {}], "action") == {"a": 1, "?": 1}
