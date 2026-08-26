"""The gates in `coded_tools/`, exercised.

The knowledge layer's whole value is that a model cannot write a confident wrong verdict into
the commons. That is enforced in code, not in prompts — so it is worth exactly one test file.

Every path in `paths.py` is RELATIVE (`state`), so `chdir` into a tmp dir is
all the isolation these need. No fixtures, no mocks, no monkeypatching of module constants.
"""

# Each test's name is its sentence — a docstring here would only restate it.
# pylint: disable=missing-function-docstring

from __future__ import annotations

import pathlib
import shutil

import pytest
from pyhocon import ConfigFactory

from coded_tools import claims
from coded_tools import paths
from coded_tools import seed_playbooks
from coded_tools.log_claim import LogClaim
from coded_tools.promote_claim import PromoteClaim
from coded_tools.read_claims import ReadClaims
from coded_tools.state_read import StateRead

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _in_tmp_state(tmp_path, monkeypatch):
    """Point the whole knowledge layer at a throwaway tree.

    The seeds are copied in because `prepare(fresh=True)` reads them from CONFIG_DIR, which is
    relative like everything else — without them seeding warns and leaves the playbooks empty.
    """
    monkeypatch.chdir(tmp_path)
    (tmp_path / paths.STATE_DIR).mkdir(parents=True, exist_ok=True)
    (tmp_path / paths.LOG_DIR).mkdir(parents=True, exist_ok=True)
    shutil.copytree(REPO_ROOT / paths.CONFIG_DIR, tmp_path / paths.CONFIG_DIR)


def _refused(reply) -> bool:
    """A gate refusal arrives as an ERROR string from some tools and a dict from others."""
    if isinstance(reply, str):
        return reply.startswith("ERROR:")
    return bool(
        reply.get("refused")
        or reply.get("problems")
        or reply.get("status") == "refused"
        or str(reply.get("action_taken", "")).startswith("skipped_")
    )


def _log(**over):
    """A claim write that passes every gate, unless a test breaks one on purpose."""
    args = {
        "domain": "scout",
        "claim": "Coastal sites out-earn inland ones on t1.",
        "status": "supported",
        "confidence": "low",
        "conditions": "t1, air, 256 flat, seed 1001",
        "evidence": "two coastal pairs beat every inland pair",
        "session_number": 1,
    }
    args.update(over)
    return LogClaim().invoke(args, {})


# --- Gate 1: a refutation must exhibit the condition being dismissed ------------------------


def test_refuted_without_despite_is_downgraded_not_written_as_refuted():
    reply = _log(status="refuted", re_test_when="a coastal pair is tried with a depot in range")
    assert reply.get("recorded_as") == "open", reply
    assert reply.get("the_gates_changed_this"), "a silent downgrade is the failure this prevents"
    assert claims.current()[reply["id"]].status == "open"


def test_downgraded_refutation_leaves_the_question_behind():
    _log(status="refuted", re_test_when="a coastal pair is tried with a depot in range")
    with open(paths.OPEN_QUESTIONS_PATH, encoding="utf-8") as handle:
        assert handle.read().strip(), "Gate 1 must record what it refused to let you conclude"


def test_refuted_with_despite_survives():
    reply = _log(
        status="refuted",
        refuted_despite="depot in range and cargo waiting, still zero income over 12 months",
        re_test_when="a larger aircraft is available",
    )
    assert reply.get("recorded_as") == "refuted", reply


# --- Gate 2: confidence is bought with varied conditions ------------------------------------


@pytest.mark.parametrize(
    "asked, varied, expected",
    [
        ("high", [], "low"),
        ("high", ["seed"], "med"),
        ("high", ["seed", "map size"], "high"),
        ("med", [], "low"),
        ("med", ["seed"], "med"),
    ],
)
def test_confidence_is_capped_by_how_much_was_varied(asked, varied, expected):
    reply = _log(
        confidence=asked,
        varied=varied,
        re_test_when="tier changes",  # required once anything lands at low
    )
    assert reply.get("confidence") == expected, reply


# --- Gate 3: inherited conditions that differ get flagged -----------------------------------


def test_claim_from_other_conditions_is_flagged_for_retest():
    _log(confidence="med", varied=["seed"], conditions="t1, air, 256 flat, seed 1001")
    reply = ReadClaims().invoke({"conditions_now": "t4, rail, 512 hilly, seed 2001"}, {})
    flagged = [c for c in reply["claims"] if c.get("re_test_before_relying")]
    assert flagged, "a claim established elsewhere must not be handed over as settled"


def test_matching_conditions_are_not_flagged():
    _log(confidence="med", varied=["seed"], conditions="t1, air, 256 flat, seed 1001")
    reply = ReadClaims().invoke({"conditions_now": "t1, air, 256 flat, seed 1001"}, {})
    assert not any(c.get("re_test_before_relying") for c in reply["claims"])


# --- Gate 4: what is still open comes back as worth probing ---------------------------------


def test_open_and_low_confidence_claims_resurface():
    _log(status="open", confidence="low", re_test_when="a depot is in range")
    reply = ReadClaims().invoke({}, {})
    assert reply.get("worth_probing"), "an untested idea nobody resurfaces is an idea lost"


# --- wording: a finding may not be frozen into policy ---------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Rail is always better than air on hilly maps.",
        "Never build across water.",
        "The inland corridor is dead.",
        "Coastal sites earn more, so stop testing inland ones.",
    ],
)
def test_policy_phrasing_is_refused(text):
    reply = _log(claim=text)
    assert _refused(reply), f"accepted policy phrasing: {text!r}"


def test_retest_trigger_is_mandatory_on_a_weak_claim():
    reply = _log(confidence="low", re_test_when="")
    assert _refused(reply), "a low claim with no way back is policy"


# --- the ledger is append-only --------------------------------------------------------------


def test_conflicting_revisions_both_survive_and_latest_wins():
    first = _log(confidence="med", varied=["seed"])
    claim_id = first["id"]
    _log(
        id=claim_id,
        status="refuted",
        refuted_despite="tried coastal with depot in range, no income",
        re_test_when="a larger aircraft is available",
        session_number=2,
    )
    revisions = claims.fold(claims.read_all())[claim_id]
    assert len(revisions) == 2, "a status change must append, never overwrite"
    assert {r.status for r in revisions} == {"supported", "refuted"}
    assert claims.current()[claim_id].status == "refuted", "the fold takes the latest"


# --- playbooks are append-only ---------------------------------------------------------------


def test_replace_line_is_refused():
    seed_playbooks.prepare(fresh=True)
    reply = PromoteClaim().invoke(
        {"domain": "scout", "edit_type": "replace_line", "new_text": "anything", "session_number": 1},
        {},
    )
    assert str(reply).startswith("ERROR:") and "replace_line" in str(reply), reply


def test_the_handwritten_baseline_cannot_be_removed():
    seed_playbooks.prepare(fresh=True)
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        body = handle.read()
    # The playbooks are prose, not bullet lists. Take the longest hand-authored line so
    # `find_text` is unambiguous — a short one matches several lines and the promoter refuses it
    # as ambiguous before the learned-tag guard is ever reached.
    baseline = max(
        (
            line.strip()
            for line in body.split(paths.LEARNED_HEADER)[0].splitlines()
            if len(line.strip()) > 40 and not line.startswith("#") and not paths.is_learned(line)
        ),
        key=len,
    )
    assert body.count(baseline) == 1
    reply = PromoteClaim().invoke({"domain": "scout", "edit_type": "remove_line", "find_text": baseline}, {})
    assert _refused(reply), f"only (learned sN) lines are demotable, got: {reply!r}"
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert baseline in handle.read(), "the baseline survived the attempt"


# --- promotion lands where the reader will look ---------------------------------------------


def test_a_promoted_rule_lands_under_the_learned_heading_and_is_tagged():
    seed_playbooks.prepare(fresh=True)
    rule = "Coastal pairs beat inland on t1 when a depot is in range."
    PromoteClaim().invoke({"domain": "scout", "edit_type": "add_line", "new_text": rule, "session_number": 7}, {})
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        body = handle.read()
    tail = body.rpartition(paths.LEARNED_HEADER)[2]
    assert rule in tail, "a promoted rule must land under the learned heading, not in the baseline"
    assert paths.is_learned(tail[tail.index(rule) :]), "and must carry its (learned sN) tag"


@pytest.mark.parametrize("section", list(paths.SECTIONS))
def test_every_seed_has_exactly_one_learned_heading(section):
    """Five seeds once shipped a second, dangling `### Learned rules — <section>` heading.

    Harmless to the promoter, which anchors on the exact bare line — but a model reading its
    playbook saw two identically-named sections, one permanently empty.
    """
    with open(REPO_ROOT / paths.seed(section), encoding="utf-8") as handle:
        headings = [ln for ln in handle.read().splitlines() if ln.startswith(paths.LEARNED_HEADER)]
    assert headings == [paths.LEARNED_HEADER], headings


@pytest.mark.parametrize("section", list(paths.SECTIONS))
def test_promotion_works_for_every_section(section):
    """A seed whose anchor does not resolve fails as `section_missing`, silently, at run time."""
    seed_playbooks.prepare(fresh=True)
    rule = f"A rule for {section}."
    PromoteClaim().invoke({"domain": section, "edit_type": "add_line", "new_text": rule, "session_number": 3}, {})
    with open(paths.playbook(section), encoding="utf-8") as handle:
        assert rule in handle.read().rpartition(paths.LEARNED_HEADER)[2]


# --- air and rail keep separate playbooks ---------------------------------------------------------


@pytest.mark.parametrize("mode, mine, theirs", [("air", "Air", "Rail"), ("rail", "Rail", "Air")])
def test_a_mode_is_seeded_only_its_own_sections(mode, mine, theirs):
    seed_playbooks.prepare(fresh=True, mode=mode)
    with open(paths.playbook("builder"), encoding="utf-8") as handle:
        body = handle.read()
    assert f"### {mine}:" in body
    assert f"### {theirs}:" not in body, "the other mode's rules are noise this one cannot act on"


def test_the_two_modes_get_separate_directories():
    seed_playbooks.prepare(fresh=True, mode="air")
    air = paths.playbook("scout")
    seed_playbooks.prepare(fresh=True, mode="rail")
    assert paths.playbook("scout") != air, "one file for both modes is how a rail rule reaches air"


def test_a_rule_learned_in_one_mode_does_not_reach_the_other():
    """`promote_claim` mirrors into the SHARED seed, so the tag is what keeps the modes apart."""
    seed_playbooks.prepare(fresh=True, mode="air")
    PromoteClaim().invoke(
        {
            "domain": "scout",
            "edit_type": "add_line",
            "new_text": "Coastal pairs beat inland on t1.",
            "session_number": 4,
        },
        {},
    )
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert "Coastal pairs beat inland" in handle.read()

    seed_playbooks.prepare(fresh=True, mode="rail")
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert "Coastal pairs beat inland" not in handle.read(), "an air session's finding is not rail doctrine"


def test_a_learned_line_names_the_mode_it_came_from():
    seed_playbooks.prepare(fresh=True, mode="rail")
    reply = PromoteClaim().invoke(
        {"domain": "fleet", "edit_type": "add_line", "new_text": "Two locomotives per corridor.", "session_number": 2},
        {},
    )
    assert paths.learned_mode(reply["line"]) == "rail", reply


def test_state_read_resolves_the_mode_placeholder():
    """The planner and watcher are one network each, serving both modes, so their binding
    cannot name a mode statically — `{mode}` is what lets one map resolve in either."""
    mapping = {"playbook_builder": "state/{mode}/playbook_builder.md"}
    for mode, mine, theirs in (("air", "Air", "Rail"), ("rail", "Rail", "Air")):
        seed_playbooks.prepare(fresh=True, mode=mode)
        reply = StateRead().invoke({"name": "playbook_builder", "name_map": mapping}, {})
        assert reply["file_path"] == f"state/{mode}/playbook_builder.md", reply
        assert f"### {mine}:" in reply["content"] and f"### {theirs}:" not in reply["content"]


# --- the baseline is authored; what the loop learns is state ---------------------------------------


def test_promotion_never_writes_into_the_hand_authored_baseline():
    seed_playbooks.prepare(fresh=True, mode="air")
    with open(paths.seed("scout"), encoding="utf-8") as handle:
        before = handle.read()
    PromoteClaim().invoke(
        {
            "domain": "scout",
            "edit_type": "add_line",
            "new_text": "Coastal pairs beat inland on t1.",
            "session_number": 4,
        },
        {},
    )
    with open(paths.seed("scout"), encoding="utf-8") as handle:
        assert handle.read() == before, "the seed is authored and cited; model output goes to state/learned/"
    with open(paths.learned("scout"), encoding="utf-8") as handle:
        assert "Coastal pairs beat inland" in handle.read()


def test_a_learned_rule_survives_fresh_but_stays_in_its_own_mode():
    seed_playbooks.prepare(fresh=True, mode="air")
    PromoteClaim().invoke(
        {
            "domain": "scout",
            "edit_type": "add_line",
            "new_text": "Coastal pairs beat inland on t1.",
            "session_number": 4,
        },
        {},
    )
    seed_playbooks.prepare(fresh=True, mode="air")
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert "Coastal pairs beat inland" in handle.read(), "--fresh must not lose what was earned"
    seed_playbooks.prepare(fresh=True, mode="rail")
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert "Coastal pairs beat inland" not in handle.read()


def test_a_demoted_rule_does_not_come_back_on_the_next_fresh():
    seed_playbooks.prepare(fresh=True, mode="air")
    rule = "Coastal pairs beat inland on t1."
    PromoteClaim().invoke({"domain": "scout", "edit_type": "add_line", "new_text": rule, "session_number": 4}, {})
    PromoteClaim().invoke({"domain": "scout", "edit_type": "remove_line", "find_text": rule}, {})
    seed_playbooks.prepare(fresh=True, mode="air")
    with open(paths.playbook("scout"), encoding="utf-8") as handle:
        assert rule not in handle.read(), "a demotion that the next reseed undoes is not a demotion"


def test_every_seed_keeps_the_learned_heading_it_is_spliced_at():
    """The heading is load-bearing, not decoration.

    `prepare()` splices earned rules under it when composing the working copy, and
    `promote_claim` appends under it during a session. A seed without it silently produces a
    playbook that can never carry anything the loop learned.
    """
    for section in paths.SECTIONS:
        with open(REPO_ROOT / paths.seed(section), encoding="utf-8") as handle:
            body = handle.read()
        assert paths.LEARNED_HEADER + "\n" in body, f"{section} seed lost its splice point"


# --- each agent is BOUND to its own playbook, not merely asked to read it -------------------------


def _reader_maps(registry: str) -> dict[str, dict[str, str]]:
    """{tool name: its name_map} for every per-job playbook reader in a generated player."""
    # basedir is the repo root: the registry includes nttd_common.hocon, and the autouse
    # fixture has moved cwd to a tmp dir where that include cannot resolve.
    config = ConfigFactory.parse_string((REPO_ROOT / registry).read_text(encoding="utf-8"), basedir=str(REPO_ROOT))
    return {
        tool["name"]: dict((tool.get("args", None) or {}).get("name_map", None) or {})
        for tool in config.get("tools", None) or []
        if str(tool.get("name", "")).startswith("read_playbook_")
    }


@pytest.mark.parametrize("registry", ["registries/nttd_air_player.hocon", "registries/nttd_rail_player.hocon"])
def test_a_worker_cannot_address_another_workers_playbook(registry):
    maps = _reader_maps(registry)
    assert len(maps) == 5, f"one reader per job, got {sorted(maps)}"
    for job in ("scout", "builder", "fleet", "care"):
        addressable = set(maps[f"read_playbook_{job}"])
        assert addressable == {"playbook_common", f"playbook_{job}"}, (
            f"{job} can address {sorted(addressable)}; the split is a binding, not a request"
        )


@pytest.mark.parametrize("registry", ["registries/nttd_air_player.hocon", "registries/nttd_rail_player.hocon"])
def test_only_the_front_man_reads_the_session_plan(registry):
    maps = _reader_maps(registry)
    assert "session_plan" in maps["read_playbook_strategist"]
    for job in ("scout", "builder", "fleet", "care"):
        assert "session_plan" not in maps[f"read_playbook_{job}"]


def test_an_unaddressable_playbook_is_refused_by_name():
    """The deny-by-default map is what makes the binding real at call time."""
    scout_map = {
        "playbook_common": "state/{mode}/playbook_common.md",
        "playbook_scout": "state/{mode}/playbook_scout.md",
    }
    reply = StateRead().invoke({"name": "playbook_builder", "name_map": scout_map}, {})
    assert str(reply).startswith("ERROR: unknown_name"), reply


# --- the session boundaries are two agents with different powers ------------------------------------


def _registry(name: str):
    return ConfigFactory.parse_string(
        (REPO_ROOT / "registries" / f"{name}.hocon").read_text(encoding="utf-8"), basedir=str(REPO_ROOT)
    )


def test_the_opener_cannot_promote_or_close_a_session():
    """Capability, not convenience: an opener able to promote or advance could close a session
    it never watched, and the split would be cosmetic."""
    tools = {t.get("name") for t in _registry("nttd_opener")["tools"]}
    assert "promote_claim" not in tools
    assert "advance_session" not in tools
    assert {"write_session_plan", "log_claim", "read_claims"} <= tools


def test_the_closer_cannot_rewrite_the_session_plan_it_is_judging():
    tools = {t.get("name") for t in _registry("nttd_closer")["tools"]}
    assert "write_session_plan" not in tools, "the plan is what the session is judged against"
    assert {"promote_claim", "advance_session", "session_telemetry"} <= tools


@pytest.mark.parametrize("network", ["nttd_opener", "nttd_closer", "nttd_watcher"])
def test_diagnose_is_named_in_the_procedure_of_every_agent_it_is_bound_to(network):
    """A tool bound but never mentioned is a tool that never gets called."""
    config = _registry(network)
    tools = {t.get("name") for t in config["tools"]}
    assert "diagnose" in tools
    instructions = " ".join(str(t.get("instructions", "")) for t in config["tools"] if not t.get("class", None))
    assert "diagnose" in instructions, f"{network} binds diagnose and never tells the agent to use it"


def test_no_prompt_names_a_status_that_does_not_exist():
    """`inconclusive` and `not_applied` were in the curator conduct long after the schema dropped
    them; a curator following that instruction got a refusal from log_claim."""
    for name in ("nttd_common", "nttd_opener", "nttd_closer", "nttd_watcher"):
        body = (REPO_ROOT / "registries" / f"{name}.hocon").read_text(encoding="utf-8")
        for gone in ("inconclusive", "not_applied", "carried_over", "falsified"):
            assert gone not in body, f"{name} still names the dead status '{gone}'"
