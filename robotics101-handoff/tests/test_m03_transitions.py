"""M03.2: scene transitions + concept title cards — expansion defaults, engine overlays, mix swishes, QA."""

import json
from pathlib import Path

import numpy as np
import pytest

from robotics101.cartoon.episode import AUTO_CYCLE, CONCEPT_CUE, INTRO_TEMPLATE, expand_episode
from robotics101.characters import load_registry
from robotics101.qa import QaReport
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


def _spec():
    return json.loads(CARTOON.read_text(encoding="utf-8"))


def test_every_scene_after_the_first_gets_a_transition_by_default():
    e = expand_episode(_spec(), load_registry())
    assert "transitionIn" not in e["scenes"][0]
    styles = [s["transitionIn"] for s in e["scenes"][1:]]
    assert all(st in ("wipe", "iris", "slide", "character") for st in styles)
    assert e["scenes"][1]["template"] == INTRO_TEMPLATE and styles[0] == "iris"
    assert styles[1:5] == list(AUTO_CYCLE)
    assert validate_episode(e).ok and expand_episode(e, load_registry()) == e


def test_transition_overrides_and_explicit_cut():
    s = _spec()
    s["transitions"] = {"default": "slide"}
    s["scenes"][3]["transitionIn"] = "cut"
    e = expand_episode(s, load_registry())
    by = {x["sceneId"]: x["transitionIn"] for x in e["scenes"][1:]}
    assert by[s["scenes"][3]["sceneId"]] == "cut"
    assert {v for k, v in by.items() if k != s["scenes"][3]["sceneId"]} == {"slide"}


def test_concept_markers_insert_one_sting_before_the_marked_beat():
    src = _spec()
    e = expand_episode(src, load_registry())
    for a, b in zip(src["scenes"], [x for x in e["scenes"] if x.get("generated") != "intro"]):
        cs = a.get("concepts") or []
        stings = [i for i, x in enumerate(b["beats"]) if x["type"] == "music" and x["cue"] == CONCEPT_CUE]
        assert len(stings) == len(cs)
        for c, i in zip(sorted(cs, key=lambda c: c.get("beforeBeat", 0)), stings):
            assert b["beats"][i + 1] == a["beats"][c.get("beforeBeat", 0)]
    assert sum(len(s.get("concepts") or []) for s in src["scenes"]) == 5


@pytest.mark.parametrize("mut,needle", [
    (lambda s: s["scenes"][2]["concepts"].append(dict(s["scenes"][1]["concepts"][0])), "introduced twice"),
    (lambda s: s["scenes"][2]["concepts"][0].update(beforeBeat=999), "beyond the scene"),
])
def test_concept_marker_validation(mut, needle):
    s = _spec()
    mut(s)
    assert any(needle in str(i) for i in validate_episode(s).errors)


def test_transition_full_cover_is_identical_on_both_sides():
    from robotics101.cartoon import props as PR
    from robotics101.cartoon.render2d import frame_rgb
    for style in ("wipe", "iris", "slide", "character"):
        a = frame_rgb([PR.transition(style, 1.0, entering=False)], 192, 108, "#FFE8C2").astype(int)
        b = frame_rgb([PR.transition(style, 0.0, entering=True)], 192, 108, "#FFE8C2").astype(int)
        half = frame_rgb([PR.transition(style, 0.5, entering=False)], 192, 108, "#FFE8C2").astype(int)
        assert np.abs(a - b).mean() < 2.0, style
        assert np.abs(a - half).mean() > 5.0, style                    # it animates
        assert len(PR.transition(style, 1.0, entering=True)) == 0      # fully revealed at the end


def test_mix_places_a_swish_on_every_transition():
    from robotics101.cartoon.audio import transition_swishes
    e = expand_episode(_spec(), load_registry())
    timing = {"scenes": [{"sceneId": s["sceneId"], "scene_duration_s": 10.0} for s in e["scenes"]]}
    ts = transition_swishes(timing, e)
    assert ts == [round(10.0 * i - 0.4, 4) for i in range(1, len(e["scenes"]))]


def _fake_frames(monkeypatch, across, arrive):
    from robotics101.cartoon import vision

    def fa(video, idx, w=0, h=0):
        idx = sorted(idx)
        base = np.zeros((10, 10), np.uint8)
        out = {}
        # idx = [b-1-k, b-1, b, b+k+2]
        out[idx[0]] = base + arrive
        out[idx[1]] = base
        out[idx[2]] = base + across
        out[idx[3]] = base + 40
        return out
    monkeypatch.setattr(vision, "frames_at", fa)


@pytest.mark.parametrize("across,arrive,ok", [(0, 40, True), (30, 40, False), (0, 2, False)])
def test_qa_no_hard_cuts(monkeypatch, tmp_path, across, arrive, ok):
    from robotics101.cartoon.qa import check_transitions
    _fake_frames(monkeypatch, across, arrive)
    e = expand_episode(_spec(), load_registry())
    timing = {"scenes": [{"sceneId": s["sceneId"], "scene_duration_s": 10.0} for s in e["scenes"]]}
    rep = QaReport("ep", "full", str(tmp_path))
    check_transitions(rep, tmp_path, e, timing, 0.4)
    assert ("transitions.no_hard_cuts" in {c.id for c in rep.failures}) is not ok


def test_qa_missing_transition_is_a_hard_cut(monkeypatch, tmp_path):
    from robotics101.cartoon.qa import check_transitions
    _fake_frames(monkeypatch, 0, 40)
    e = expand_episode(_spec(), load_registry())
    e["scenes"][4].pop("transitionIn")
    timing = {"scenes": [{"sceneId": s["sceneId"], "scene_duration_s": 10.0} for s in e["scenes"]]}
    rep = QaReport("ep", "full", str(tmp_path))
    check_transitions(rep, tmp_path, e, timing, 0.4)
    assert "transitions.no_hard_cuts" in {c.id for c in rep.failures}


def test_qa_every_concept_needs_a_card(monkeypatch, tmp_path):
    from robotics101.cartoon import vision
    from robotics101.cartoon.qa import check_concepts
    monkeypatch.setattr(vision, "frames_at", lambda v, idx, w=0, h=0: {i: np.full((4, 4), 60 * k, np.uint8)
                                                                        for k, i in enumerate(sorted(idx))})
    e = expand_episode(_spec(), load_registry())
    timing = {"scenes": [{"sceneId": s["sceneId"], "scene_duration_s": 30.0} for s in e["scenes"]]}
    by = {}
    for s in e["scenes"]:
        by[s["sceneId"]] = {"facts": {"conceptCards": [{"id": c["id"], "title": c["title"], "start": 0.4, "end": 3.2,
                                                        "teachStart": 3.4} for c in s.get("concepts") or []]}}
    rep = QaReport("ep", "full", str(tmp_path))
    check_concepts(rep, tmp_path, e, by, timing)
    assert not rep.failures
    by["scene-004"]["facts"]["conceptCards"] = []
    rep2 = QaReport("ep", "full", str(tmp_path))
    check_concepts(rep2, tmp_path, e, by, timing)
    assert "concepts.cards" in {c.id for c in rep2.failures}
