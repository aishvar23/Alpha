"""M02.1: character registry, episode schema v1.1 (dialogue beats), teaching-fact and kid-safe lints."""

import copy
import json
from pathlib import Path

import pytest

from robotics101.cartoon.lint import fact_problems, kidsafe_problems, spoken_quantities
from robotics101.characters import load_registry, registry_problems
from robotics101.templates.registry import get_template
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


@pytest.fixture
def cartoon() -> dict:
    return json.loads(CARTOON.read_text(encoding="utf-8"))


def _errors(spec):
    return [str(i) for i in validate_episode(spec).errors]


def _first(spec, pred):
    for s in spec["scenes"]:
        for b in s["beats"]:
            if pred(b):
                return b
    raise AssertionError("beat not found")


def test_registry_loads_cast_with_voices_and_hash():
    reg = load_registry()
    assert set(reg.characters) == {"bolt", "maya", "nib"}
    assert len(reg.sha256) == 64 and reg.rig_version >= 1
    assert reg.get("bolt").speaks and reg.get("maya").speaks and not reg.get("nib").speaks
    for cid in ("bolt", "maya"):
        v = reg.get(cid).voice
        assert v["elevenlabs"]["modelId"] and v["kokoro"]["voice"] and v["espeak"]["voice"]
    assert reg.get("nib").voice is None


def test_registry_problems_detect_bad_entries():
    doc = json.loads((ROOT / "characters" / "registry.json").read_text())
    assert registry_problems(doc) == []
    bad = copy.deepcopy(doc)
    bad["characters"]["bolt"]["voice"]["elevenlabs"]["api_key"] = "x"
    del bad["characters"]["maya"]["voice"]["espeak"]
    bad["characters"]["nib"]["voice"] = {"espeak": {}}
    bad["characters"]["bolt"]["palette"]["body"] = "teal"
    probs = " | ".join(registry_problems(bad))
    assert "credentials" in probs and "espeak: required" in probs and "must be null" in probs and "palette" in probs


def test_registry_file_has_no_secrets():
    text = (ROOT / "characters" / "registry.json").read_text().lower()
    assert "api_key" not in text and "xi-api-key" not in text and "sk_" not in text


def test_cartoon_episode_valid_strict_and_v1_0_still_valid(cartoon, spec):
    rep = validate_episode(cartoon)
    assert rep.ok and not rep.warnings, [str(i) for i in rep.issues]
    assert validate_episode(spec).ok          # M01 contract fixture unchanged
    assert cartoon["publishing"]["madeForKids"] is True


def test_cartoon_script_shape(cartoon):
    lines = [b for s in cartoon["scenes"] for b in s["beats"] if b["type"] == "line"]
    words = sum(len(b["text"].split()) for b in lines)
    assert 550 <= words <= 750
    assert {b["speaker"] for b in lines} == {"bolt", "maya"}
    assert sum(s["durationTargetSeconds"] for s in cartoon["scenes"]) == 300
    assert all(s["engine"] == "cartoon" for s in cartoon["scenes"])
    thr = {s["parameters"].get("thresholdMeters") for s in cartoon["scenes"]} - {None}
    assert thr == {0.5}


@pytest.mark.parametrize("mutate, expect", [
    (lambda s: _first(s, lambda b: b["type"] == "line").update(speaker="zed"), "not in the episode cast"),
    (lambda s: _first(s, lambda b: b["type"] == "line").update(speaker="nib"), "does not speak"),
    (lambda s: _first(s, lambda b: b["type"] == "line").update(emotion="angry"), "is not an expression"),
    (lambda s: _first(s, lambda b: b["type"] == "line").update(action="backflip"), "is not an action"),
    (lambda s: _first(s, lambda b: b["type"] == "sfx").update(id="explosion"), "unknown sfx"),
    (lambda s: _first(s, lambda b: b["type"] == "music").update(cue="rock_anthem"), "unknown music cue"),
    (lambda s: s["characters"].append("zed"), "unknown character"),
    (lambda s: s.update(set="moon"), "unknown set"),
    (lambda s: _first(s, lambda b: b.get("text", "").startswith("Ping! Nib is")).update(
        text="Ping! Nib is 1.3 meters away!"), "teaching fact"),
    (lambda s: s["scenes"][6]["parameters"].update(thresholdMeters=0.6), "same in every scene"),
    (lambda s: s["scenes"][4]["parameters"].update(readings=[1.5, 1.0, 0.6]), "end below"),
    (lambda s: s["scenes"][4]["beats"].__setitem__(slice(None), [{"type": "pause", "seconds": 1}]), "at least one dialogue line"),
    (lambda s: _first(s, lambda b: b["type"] == "line").update(text="Shut up, you dumb box!"), "kid-safe"),
    (lambda s: s["scenes"][0].update(narration="old style"), "schema"),
])
def test_cartoon_validation_errors(cartoon, mutate, expect):
    s = copy.deepcopy(cartoon)
    mutate(s)
    errs = _errors(s)
    assert any(expect in e for e in errs), errs


def test_kidsafe_is_warning_when_not_made_for_kids(cartoon):
    s = copy.deepcopy(cartoon)
    s["publishing"]["madeForKids"] = False
    _first(s, lambda b: b["type"] == "line").update(text="That was a dumb idea.")
    rep = validate_episode(s)
    assert rep.ok and any("kid-safe" in str(w) for w in rep.warnings)


def test_spoken_quantities():
    q = lambda t: [(v, k) for v, k, _ in spoken_quantities(t)]
    assert q("Nib is 1.2 meters away") == [(1.2, "m")]
    assert q("less than half a meter") == [(0.5, "m")]
    assert q("up to three meters, at sixty degrees") == [(3.0, "m"), (60.0, "deg")]
    assert q("zero point four meters") == [(0.4, "m")]
    assert q("50 cm and 30°") == [(0.5, "m"), (30.0, "deg")]
    assert q("Is 0.6 less than 0.5?") == []          # unit-less comparisons are not checked


def test_lints_clean_on_example(cartoon):
    assert fact_problems(cartoon) == [] and kidsafe_problems(cartoon) == []


def test_cartoon_templates_registered():
    for name in ("cartoon_cold_open", "cartoon_robot_family", "cartoon_robot_checkup", "cartoon_sensor_ping",
                 "cartoon_rule_board", "cartoon_servo_highfive", "cartoon_obstacle_rematch", "cartoon_recap_chant"):
        assert get_template("cartoon", name) is not None
    assert get_template("cartoon", "cartoon_rule_board").validate_params({"thresholdMeters": 0.5, "readings": [1.0, 2.0]})


@pytest.mark.parametrize("cmd", ["narrate", "render-scenes"])   # `render` runs the cartoon pipeline (M02.8)
def test_m01_pipeline_refuses_cartoon_spec_cleanly(cmd, tmp_path):
    from robotics101.cli import main
    assert main([cmd, str(CARTOON), "--out", str(tmp_path / "o")]) == 3
