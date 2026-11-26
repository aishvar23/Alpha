"""A4 (PLAN-authoring §5.6): visual-gap report, `visual_gap` placeholder, QA `authoring.visual_gaps`, publish
blocker and R3 refusal. Offline, no render of a full episode."""

import copy
import json
from pathlib import Path

import pytest

from robotics101.authoring import gaps as GP
from robotics101.authoring.schemas import ContractError
from robotics101.qa import QaReport

ROOT = Path(__file__).resolve().parents[1]
EP1 = ROOT / "examples" / "episode-001-cartoon.json"


@pytest.fixture()
def ep1():
    return json.loads(EP1.read_text())


@pytest.fixture()
def one_gap():
    return GP.gaps_doc([GP.make_gap(1, "scene-004", [3, 4], "An articulated gripper opening and closing on a ball",
                                    concept="grippers", suggested="body", closest="vignettes.arm")])


def test_gap_contract_and_placeholder_shot(one_gap):
    g = one_gap["gaps"][0]
    assert g["gapId"] == "gap-01" and g["severity"] == "blocker"
    sh = GP.placeholder_shot(g)
    assert sh == {"layout": "illustration", "fromBeat": 3, "toBeat": 4, "visual": "visual_gap",
                  "gap": {"gapId": "gap-01", "what": g["whatMustBeShown"]}}
    with pytest.raises(ContractError):
        GP.gaps_doc([{**g, "severity": "maybe"}])


def test_spec_with_placeholder_validates_and_expands(ep1, one_gap):
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    from robotics101.validation import validate_episode
    spec = GP.apply_placeholders(ep1, one_gap)
    assert validate_episode(spec).ok
    assert GP.gap_problems(spec, one_gap) == []
    exp = expand_episode(spec, load_registry())
    sc = next(s for s in exp["scenes"] if s["sceneId"] == "scene-004")
    assert any(sh.get("visual") == "visual_gap" for sh in sc["shots"])
    # a placeholder must carry its gap, and a gap only rides on visual_gap
    bad = copy.deepcopy(spec)
    next(s for s in bad["scenes"] if s["sceneId"] == "scene-004")["shots"][0].pop("gap")
    assert not validate_episode(bad).ok
    assert GP.gap_problems(spec, {"gaps": []})                     # unlisted placeholder


def test_placeholder_frame_golden_and_animated(tmp_path):
    from kit_golden import assert_golden, frame, moving
    from robotics101.cartoon.kit.placeholder import HEADLINE
    ctx = {"gapId": "gap-01", "what": "An articulated gripper opening and closing on a ball"}
    assert HEADLINE == "VISUAL COMING SOON"
    assert_golden(frame("visual_gap", ctx, 1.0), "visual_gap", tmp_path)
    assert moving("visual_gap", ctx, 1.0, 1.7) > 0.5                # never a frozen frame


def _sj(shots):
    return {"scenes": [{"sceneId": "scene-004", "facts": {"shots": shots}}]}


def test_qa_visual_gaps(tmp_path, one_gap):
    from robotics101.cartoon.qa import check_visual_gaps
    rep = QaReport("ep-001", "preview", str(tmp_path))
    check_visual_gaps(rep, tmp_path, _sj([{"layout": "stage", "visual": "concept_robot"}]))
    assert rep.status == "PASS"
    rep = QaReport("ep-001", "preview", str(tmp_path))
    shown = _sj([{"layout": "illustration", "visual": "visual_gap", "gap": {"gapId": "gap-01", "what": "x y z"}}])
    check_visual_gaps(rep, tmp_path, shown)                          # placeholder shown and not listed
    f = rep.failures[0]
    assert f.id == "authoring.visual_gaps" and "not listed" in f.message and "placeholder" in f.message
    (tmp_path / GP.GAPS_NAME).write_text(json.dumps(one_gap))
    rep = QaReport("ep-001", "preview", str(tmp_path))
    check_visual_gaps(rep, tmp_path, shown)                          # listed, but still shown -> still a failure
    assert rep.failures and "cannot be approved" in rep.failures[0].message
    (tmp_path / GP.GAPS_NAME).write_text("{\"gaps\": [{}]}")
    rep = QaReport("ep-001", "preview", str(tmp_path))
    check_visual_gaps(rep, tmp_path, _sj([]))
    assert rep.failures and "invalid" in rep.failures[0].message


def test_publish_blockers_and_r3(spec, tmp_path, one_gap):
    from test_publish import approve, make_bundle
    from robotics101.authoring.review import check_r3
    from robotics101.publish import build_publish_plan
    b = make_bundle(tmp_path / "b", spec)
    approve(b)
    assert check_r3(b)["status"] == "approved"
    assert not any("visual gap" in x or "VISUAL COMING SOON" in x for x in build_publish_plan(b)["blockers"])
    (b / GP.GAPS_NAME).write_text(json.dumps(one_gap))
    (b / "scenes.json").write_text(json.dumps(_sj([GP.placeholder_shot(one_gap["gaps"][0])])))
    blockers = build_publish_plan(b)["blockers"]
    assert any("1 blocker visual gap(s): gap-01 scene-004" in x for x in blockers)
    assert any("VISUAL COMING SOON" in x for x in blockers)
    assert check_r3(b)["status"] == "placeholder"


def test_cli_gaps(tmp_path, ep1, one_gap, capsys):
    from robotics101.cli import main
    gp = tmp_path / "visual_gaps.json"
    gp.write_text(json.dumps(one_gap))
    src = tmp_path / "ep.json"
    src.write_text(json.dumps(ep1))
    assert main(["authoring", "gaps", str(gp), "--spec", str(src)]) == 0
    out = tmp_path / "with.json"
    assert main(["authoring", "gaps", str(gp), "--spec", str(src), "--apply", str(out)]) == 0
    assert "gap-01 [blocker] scene-004" in capsys.readouterr().out
    assert GP.placeholders(json.loads(out.read_text()))


def test_layout_gate_uses_gap_ids(ep1, one_gap):
    from robotics101.authoring.gates import layout_problems
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    exp = expand_episode(GP.apply_placeholders(ep1, one_gap), load_registry())
    assert layout_problems(exp, one_gap, None) == []
    assert any("not listed" in p for p in layout_problems(exp, {"gaps": []}, None))
