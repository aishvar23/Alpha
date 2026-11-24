"""M05.7: overlays, cards, HUD and SFX text never cover a character's head or face."""

import json
from pathlib import Path

import pytest

pytest.importorskip("manim")

from robotics101.cartoon.layout import FACE_OVERLAP_TOL, boxes_collide, norm_box  # noqa: E402
from robotics101.qa import QaReport  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def test_boxes_collide_respects_the_slack():
    a = [0.2, 0.2, 0.5, 0.5]
    assert boxes_collide(a, [0.4, 0.4, 0.8, 0.8])
    assert not boxes_collide(a, [0.5 + FACE_OVERLAP_TOL, 0.2, 0.9, 0.5])
    assert not boxes_collide(a, [0.8, 0.8, 0.9, 0.9])


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    d = tmp_path_factory.mktemp("voice")
    spec = expand_episode(json.loads((ROOT / "examples" / "episode-001-cartoon.json").read_text()), load_registry())
    timing = voice_episode(spec, load_registry(), d, B.FixtureBackend(), VoiceCache(d / "cache"), log=lambda m: None)
    return spec, timing, d


def _scene(voiced, sid, monkeypatch):
    from robotics101.cartoon import lipsync
    from robotics101.cartoon import scenes as S
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))
    spec, timing, d = voiced
    by = {s["sceneId"]: s for s in spec["scenes"]}
    t = next(x for x in timing["scenes"] if x["sceneId"] == sid)
    return S.build_scene(by[sid], t, d)


def test_face_box_covers_maya_head_not_her_feet():
    from robotics101.cartoon.rigs import Pose, build
    from robotics101.cartoon.scenes import face_box
    from robotics101.cartoon.sets import GROUND
    import numpy as np
    g = build("maya", Pose()).scale(0.8, about_point=np.zeros(3))
    g.shift(np.array([0.0, GROUND, 0]))
    fb = face_box("maya", g)
    # normalised y grows downward; the face sits in the upper half of the frame, not in the caption band
    assert fb[3] < 0.75 and fb[1] < fb[3]
    # feet are well below the face box
    feet_y = g.get_bottom()[1]
    # world y of face bottom: invert norm_box roughly
    from robotics101.cartoon.layout import FRAME_H, FRAME_Y
    face_bottom_world = FRAME_Y - fb[3] * FRAME_H
    assert face_bottom_world > feet_y + 1.0


def test_faces_report_flags_a_card_on_maya_face(voiced, monkeypatch):
    from robotics101.cartoon import props as PR
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-003", monkeypatch)
    r = S.faces_report(sc, step=1.0)
    assert r["samples"] > 5 and r["offenders"] == []
    # a card parked on Maya's pre-charge stand (left, head ~ y=1) must be flagged
    sc.front.append(lambda t, m: [PR.checklist(["structure", "sensors"], [1, 1]).move_to(PR.P(-4.4, 1.0))])
    r = S.faces_report(sc, step=1.0)
    assert r["offenders"] and any(o["character"] == "maya" for o in r["offenders"])


def test_checkup_charge_keeps_faces_clear_of_the_card_and_bzzt(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-003", monkeypatch)
    r = S.faces_report(sc, step=0.25)
    assert r["samples"] > 20 and r["offenders"] == []


def test_qa_faces_clear():
    from robotics101.cartoon.qa import check_faces_clear

    def run(by):
        rep = QaReport("ep", "full", "x")
        check_faces_clear(rep, by)
        return {c.id: c for c in rep.checks}["layout.faces_clear"]

    ok = {"facesClear": {"samples": 40, "offenders": []}}
    assert run({"s1": ok}).status == "pass"
    bad = {"facesClear": {"samples": 40, "offenders": [
        {"character": "maya", "what": "cartoon_robot_checkup:<lambda>", "first": 37.5, "n": 8}]}}
    c = run({"s1": ok, "s2": bad})
    assert c.status == "fail" and "maya" in c.message
    assert run({"s1": ok, "s3": {}}).status == "fail"          # an unmeasured scene
    assert run({"s3": {}}).status == "warn"                    # pre-M05.7 bundle


def test_every_fixture_scene_keeps_faces_clear(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    spec, timing, _d = voiced
    by = {s["sceneId"]: s for s in spec["scenes"]}
    hits = []
    for tmg in timing["scenes"]:
        sc = _scene(voiced, tmg["sceneId"], monkeypatch)
        r = S.faces_report(sc, step=0.25)
        for o in r["offenders"]:
            hits.append(f"{tmg['sceneId']}: {o['what']} covers {o['character']} from {o['first']}s ({o['n']} samples)")
    assert hits == [], hits
