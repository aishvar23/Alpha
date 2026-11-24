"""M05.1: illustration-first layouts — `illustration` / `solo` shots as pipeline defaults, rendering, QA."""

import json
from pathlib import Path

import pytest

from robotics101.cartoon.episode import DEFAULT_SHOTS, expand_episode, plan_shots
from robotics101.cartoon.layout import ILLUSTRATION_MIN_AREA, SOLO_MIN_AREA, box_area, norm_box, band_overlap
from robotics101.characters import load_registry
from robotics101.qa import QaReport
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


def _spec():
    return json.loads(CARTOON.read_text(encoding="utf-8"))


def _by(e):
    return {s["sceneId"]: s for s in e["scenes"]}


def test_template_defaults_put_explanations_into_illustration_and_solo_shots():
    e = expand_episode(_spec(), load_registry())
    assert validate_episode(e).ok and expand_episode(e, load_registry()) == e        # valid + idempotent
    fam = _by(e)["scene-002"]["shots"]
    assert [s["layout"] for s in fam] == ["illustration"] and fam[0]["visual"] == "robot_families"
    b = _by(e)["scene-002"]["beats"]
    assert b[fam[0]["fromBeat"]] == {"type": "sfx", "id": "page_flip"}
    covered = [x["text"] for x in b[fam[0]["fromBeat"]:fam[0]["toBeat"] + 1] if x["type"] == "line"]
    assert any("vacuum" in t for t in covered) and any("rover" in t for t in covered)
    echo = _by(e)["scene-004"]["shots"]
    assert echo[0]["layout"] == "solo" and echo[0]["character"] == "maya" and echo[0]["visual"] == "echo_diagram"
    eb = _by(e)["scene-004"]["beats"]
    assert eb[echo[0]["fromBeat"]]["type"] == "line"           # starts on the first line (after the concept sting)
    assert "bounces" in eb[echo[0]["toBeat"]]["text"]
    assert all(x.get("explain") for x in eb[echo[0]["fromBeat"]:echo[0]["toBeat"] + 1] if x["type"] == "line")


def test_defaults_are_template_wide_not_episode_specific():
    beats = [{"type": "line", "speaker": "bolt", "text": "Hi"}, {"type": "sfx", "id": "page_flip"},
             {"type": "line", "speaker": "maya", "text": "A drone flies."},
             {"type": "line", "speaker": "maya", "text": "A robot dog walks."}, {"type": "sfx", "id": "sparkle"}]
    assert DEFAULT_SHOTS["cartoon_robot_family"](beats) == [
        {"layout": "illustration", "fromBeat": 1, "toBeat": 3, "visual": "robot_families"}]
    ping = [{"type": "line", "speaker": "bolt", "text": "Watch!"}, {"type": "sfx", "id": "ping"},
            {"type": "sfx", "id": "echo"}, {"type": "line", "speaker": "maya", "text": "Echo!"}]
    assert DEFAULT_SHOTS["cartoon_sensor_ping"](ping)[0]["character"] == "bolt"


def test_authored_explain_line_gets_a_generic_solo_and_authored_shots_win():
    sc = {"template": "cartoon_servo_highfive", "concepts": [{"id": "x", "title": "Servo", "icon": "servo"}],
          "beats": [{"type": "line", "speaker": "maya", "text": "A servo turns to an angle.", "explain": True},
                    {"type": "line", "speaker": "bolt", "text": "Cool!"}]}
    plan_shots(sc)
    assert sc["shots"] == [{"layout": "solo", "fromBeat": 0, "toBeat": 0, "visual": "concept_servo",
                            "character": "maya", "generated": True}]
    sc2 = {"template": "cartoon_robot_family", "shots": [], "beats": [{"type": "sfx", "id": "page_flip"},
                                                                       {"type": "line", "speaker": "m", "text": "x"}]}
    plan_shots(sc2)
    assert "shots" not in sc2                                    # authored "no shots" is respected


@pytest.mark.parametrize("mut,needle", [
    (lambda s: s["scenes"][1].__setitem__("shots", [{"layout": "solo", "fromBeat": 0, "toBeat": 99,
                                                    "character": "maya"}]), "outside the scene"),
    (lambda s: s["scenes"][1].__setitem__("shots", [{"layout": "solo", "fromBeat": 0, "toBeat": 1}]), "needs its one"),
    (lambda s: s["scenes"][1].__setitem__("shots", [{"layout": "illustration", "fromBeat": 0, "toBeat": 1,
                                                    "visual": "nope"}]), "unknown shot visual"),
])
def test_shot_validation(mut, needle):
    s = _spec()
    mut(s)
    assert any(needle in str(i) for i in validate_episode(s).errors)


def test_layout_boxes_respect_area_rules_and_the_caption_band():
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX, SOLO_BOX
    assert box_area(norm_box(*ILLUSTRATION_BOX)) >= ILLUSTRATION_MIN_AREA
    assert box_area(norm_box(*SOLO_BOX)) >= SOLO_MIN_AREA
    assert band_overlap(norm_box(*ILLUSTRATION_BOX)) == 0 and band_overlap(norm_box(*SOLO_BOX)) == 0


def _qa(spec, shots_by_scene, timing):
    from robotics101.cartoon.qa import check_shots
    rep = QaReport("ep", "full", "x")
    by = {sid: {"facts": {"shots": sh}} for sid, sh in shots_by_scene.items()}
    check_shots(rep, spec, timing, by)
    return {c.id: c for c in rep.checks}["layout.illustration_first"]


def _mini():
    spec = {"scenes": [{"sceneId": "s1", "beats": [{"type": "line", "speaker": "maya", "text": "x", "explain": True},
                                                  {"type": "line", "speaker": "bolt", "text": "y"}]}]}
    timing = {"scenes": [{"sceneId": "s1", "beats": [{"index": 0, "start_s": 1.0, "end_s": 3.0},
                                                    {"index": 1, "start_s": 3.5, "end_s": 4.0}]}]}
    return spec, timing


def test_qa_explanatory_line_must_be_inside_a_shot():
    spec, timing = _mini()
    good = {"layout": "solo", "visual": "v", "areaShare": 0.45, "characters": [{"id": "maya", "area": 0.1}],
            "start": 0.9, "end": 3.2}
    assert _qa(spec, {"s1": [good]}, timing).ok
    assert not _qa(spec, {"s1": [{**good, "end": 2.0}]}, timing).ok                 # line spills out
    assert not _qa(spec, {"s1": []}, timing).ok


@pytest.mark.parametrize("patch", [
    {"areaShare": 0.2},                                                                  # visual too small
    {"characters": []},                                                                  # solo without its character
    {"characters": [{"id": "maya", "area": 0.1}, {"id": "bolt", "area": 0.1}]},          # solo with two
    {"layout": "illustration", "areaShare": 0.5},                                        # < 55% for illustration
    {"layout": "illustration", "areaShare": 0.7, "characters": [{"id": "maya", "area": 0.2}]},   # corner too big
])
def test_qa_shot_area_and_character_rules(patch):
    spec, timing = _mini()
    good = {"layout": "solo", "visual": "v", "areaShare": 0.45, "characters": [{"id": "maya", "area": 0.1}],
            "start": 0.9, "end": 3.2}
    assert not _qa(spec, {"s1": [{**good, **patch}]}, timing).ok


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    pytest.importorskip("manim")
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    d = tmp_path_factory.mktemp("voice")
    spec = expand_episode(_spec(), load_registry())
    timing = voice_episode(spec, load_registry(), d, B.FixtureBackend(), VoiceCache(d / "cache"), log=lambda m: None)
    return spec, timing, d


def _scene(voiced, sid, monkeypatch):
    from robotics101.cartoon import lipsync
    from robotics101.cartoon import scenes as S
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))
    spec, timing, d = voiced
    by = _by(spec)
    t = next(x for x in timing["scenes"] if x["sceneId"] == sid)
    return S.build_scene(by[sid], t, d), t


def test_engine_solo_shot_shows_only_the_explainer(voiced, monkeypatch):
    import numpy as np
    from robotics101.cartoon import scenes as S
    from robotics101.cartoon.render2d import frame_rgb
    sc, t = _scene(voiced, "scene-004", monkeypatch)
    [sh] = sc.shots
    assert sh["layout"] == "solo" and [c["id"] for c in sh["characters"]] == ["maya"]
    assert sh["areaShare"] >= SOLO_MIN_AREA
    mid = (sh["start"] + sh["end"]) / 2
    img = frame_rgb(S.frame_fn(sc)(mid), 320, 180, "#FFE8C2").astype(int)
    # the stage (garage wall #FFE8C2, Bolt's body) is covered: the backdrop colour fills the frame corners
    for y, x in ((3, 3), (3, 316), (176, 3), (176, 316)):
        assert np.abs(img[y, x, :3] - np.array([0xE9, 0xF7, 0xFF])).sum() < 40
    # hidden stage characters don't count for liveliness while the shot covers them
    from robotics101.cartoon.liveliness import scene_liveliness
    live = scene_liveliness(sc, S.presence, S.HEIGHT, S.SCALES)
    full = round(sc.duration * 30)
    assert live["bolt"]["frames"] < live["maya"]["frames"] < full


def test_engine_family_illustration_is_full_screen_with_animated_tiles(voiced, monkeypatch):
    sc, t = _scene(voiced, "scene-002", monkeypatch)
    [sh] = sc.shots
    assert sh["layout"] == "illustration" and sh["characters"] == [] and sh["areaShare"] >= ILLUSTRATION_MIN_AREA
    tiles = [i for i in sc.illustrations if i["id"].startswith("shot-family-")]
    assert {i["kind"] for i in tiles} == {"vacuum", "arm", "rover"}
    assert all(sh["start"] <= i["start"] < i["end"] <= sh["end"] for i in tiles)
