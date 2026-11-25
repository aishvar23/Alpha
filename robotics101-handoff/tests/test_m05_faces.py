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
        for o in r["offFrame"]:                 # M05.8: and every overlay stays inside the action-safe area
            hits.append(f"{tmg['sceneId']}: {o['what']} leaves the safe area by {o['maxExcess']} from {o['first']}s")
    assert hits == [], hits


# ---------------------------------------------------------------- M05.8: title / end cards never cover a face

def _v6_end_card(sc):
    """Reproduce v6's scene-008 end card: the starburst popped straight onto the stage at the outro cue."""
    from robotics101.cartoon import props as PR
    from robotics101.cartoon import scenes as S
    outro = sc.beat("music", "cue", "outro")
    sc.screen = [f for f in sc.screen if getattr(f, "__name__", "") not in ("clean", "card")]
    sc.screen.append(lambda t, m: [PR.title_card(min(0.8, S._u(t, outro["start_s"], outro["start_s"] + 3.0)),
                                                 subtitle="See you next time!")] if t >= outro["start_s"] else [])
    return sc


def test_face_coverage_uses_the_card_outline():
    import numpy as np
    from robotics101.cartoon.scenes import face_coverage
    from robotics101.cartoon.layout import FRAME_X, FRAME_Y
    sq = [np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]])]   # world square around the centre
    cx = lambda x: (x + FRAME_X) / (2 * FRAME_X)                            # noqa: E731
    cy = lambda y: (FRAME_Y - y) / (2 * FRAME_Y)                            # noqa: E731
    assert face_coverage([cx(-0.5), cy(0.5), cx(0.5), cy(-0.5)], sq) == 1.0              # fully under
    assert face_coverage([cx(3.0), cy(0.5), cx(4.0), cy(-0.5)], sq) == 0.0               # clear
    assert 0.2 < face_coverage([cx(0.0), cy(0.5), cx(2.0), cy(-0.5)], sq) < 0.8          # half under


def test_v6_scene008_end_card_is_flagged_and_the_default_clears_the_stage(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-008", monkeypatch)
    rec = sc.facts["stageCards"][0]
    outro = sc.beat("music", "cue", "outro")
    last = max(b["end_s"] for b in sc.lines() if b["start_s"] < outro["start_s"])
    # the clear starts after the last line, lasts CARD_CLEAR_S, and the card only pops on the cleared stage
    assert rec["clearFrom"] >= last - 1e-6 and abs(rec["clearAt"] - rec["clearFrom"] - S.CARD_CLEAR_S) < 1e-6
    assert rec["cardAt"] >= rec["clearAt"] - 1e-6 and rec["cardAt"] >= outro["start_s"]
    fixed = S.card_faces_report(sc, step=0.25)
    assert fixed["samples"] > 5 and fixed["offenders"] == []
    v6 = S.card_faces_report(_v6_end_card(_scene(voiced, "scene-008", monkeypatch)), step=0.25)
    who = {o["character"]: o for o in v6["offenders"]}
    assert "maya" in who and who["maya"]["kind"] == "partial"     # her face peeks out from behind the burst
    assert "bolt" in who


def test_stage_card_clear_fully_hides_the_set_before_the_card(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-008", monkeypatch)
    rec = sc.facts["stageCards"][0]
    mobs, _, over = S.frame_layers(sc, rec["cardAt"] + 0.05)
    clears = [m for m in over if getattr(m, "clears_stage", False)]
    cards = [m for m in over if getattr(m, "covers_stage", False)]
    assert clears and clears[0].clear_alpha == 1.0 and cards
    assert over.index(clears[0]) < over.index(cards[0])          # card drawn on top of the clean set
    _, _, before = S.frame_layers(sc, rec["clearFrom"] - 0.05)
    assert not any(getattr(m, "clears_stage", False) or getattr(m, "covers_stage", False) for m in before)
    _, _, mid = S.frame_layers(sc, (rec["clearFrom"] + rec["clearAt"]) / 2)
    assert not any(getattr(m, "covers_stage", False) and (m.has_points() or m.submobjects) for m in mid)


def test_qa_title_card_faces():
    from robotics101.cartoon.qa import check_title_card_faces

    def run(by):
        rep = QaReport("ep", "full", "x")
        check_title_card_faces(rep, by)
        return {c.id: c for c in rep.checks}["layout.title_card_faces"]

    ok = {"facesClear": {"cardFaces": {"samples": 15, "offenders": []}}}
    assert run({"scene-008": ok}).status == "pass"
    bad = {"facesClear": {"cardFaces": {"samples": 15, "offenders": [
        {"character": "maya", "what": "cartoon_recap_chant:<lambda>", "first": 30.25, "n": 14,
         "maxCoverage": 0.42, "kind": "partial"}]}}}
    c = run({"scene-002": ok, "scene-008": bad})
    assert c.status == "fail" and "maya" in c.message and "partial" in c.message
    assert run({"scene-002": ok, "scene-003": {"facesClear": {}}}).status == "fail"   # unmeasured scene
    assert run({"scene-003": {"facesClear": {}}}).status == "warn"                     # pre-v7 bundle
