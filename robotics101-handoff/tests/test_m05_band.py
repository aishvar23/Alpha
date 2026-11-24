"""M05.2: the bottom caption band is reserved — layout keeps characters / teaching visuals / readouts out of it."""

import json
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("manim")

from robotics101.cartoon import props as PR  # noqa: E402
from robotics101.cartoon.layout import BAND_TOP_Y, CAPTION_BAND, band_overlap, norm_box  # noqa: E402
from robotics101.cartoon.rigs import Pose, build  # noqa: E402
from robotics101.qa import QaReport  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _bottom(m):
    return m.get_bottom()[1]


def test_band_geometry():
    assert CAPTION_BAND == pytest.approx(0.18) and BAND_TOP_Y == pytest.approx(-2.56)
    assert band_overlap(norm_box(-1, -2.5, 1, 0)) == 0
    assert band_overlap(norm_box(-1, -3.0, 1, 0)) == pytest.approx(0.44 / 8, abs=1e-3)


def test_floor_rulers_and_labels_sit_above_the_band():
    for r in (PR.ruler(-3.0, 4.0, highlight=1.2), PR.ruler_rev(4.0, 3.0, danger=0.5)):
        assert _bottom(r) > BAND_TOP_Y + 0.05


@pytest.mark.parametrize("u", [0.02, 0.06, 0.1, 0.14, 0.5, 0.9])
def test_concept_card_content_clears_the_band_even_at_its_overshoot(u):
    g = PR.concept_card("What is a robot?", "It can sense, think and act", "robot", u, 1.0)
    if len(g):
        assert _bottom(g[1]) > BAND_TOP_Y and g[1].get_top()[1] < 4.0


@pytest.mark.parametrize("cid", ["bolt", "maya", "nib"])
@pytest.mark.parametrize("lean", [-0.3, -0.12, 0.12, 0.3, 1.2])
def test_rigs_rock_on_the_ground_instead_of_sinking_below_it(cid, lean):
    expr = {"bolt": "happy", "maya": "happy", "nib": "happy"}[cid]
    g = build(cid, Pose(expression=expr, lean=lean))
    assert _bottom(g) >= -1e-6


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


def test_band_report_measures_real_geometry_and_names_the_offender(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-004", monkeypatch)            # the floor ruler scene
    r = S.band_report(sc, step=1.0)
    assert r["samples"] > 10 and r["offenders"] == []
    sc.front.append(lambda t, m: [PR.readout([("distance: 1.20 m", "#7CFFCB")], PR.P(0, -3.2))])
    r = S.band_report(sc, step=1.0)
    assert r["offenders"] and "cartoon_sensor_ping:<lambda>" in r["offenders"][0]["what"]
    assert r["maxIntrusion"] > 0.03


def test_decorations_may_run_under_the_band(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-002", monkeypatch)
    star = PR.title_card(0.5)                                  # burst backdrop reaches the bottom edge
    assert _bottom(star) < BAND_TOP_Y
    sc.screen.append(lambda t, m: [PR.title_card(0.5)])
    assert S.band_report(sc, step=2.0)["offenders"] == []


def _qa(by):
    from robotics101.cartoon.qa import check_caption_band
    rep = QaReport("ep", "full", "x")
    check_caption_band(rep, by)
    return rep.checks[0]


def test_qa_caption_band():
    ok = {"captionBand": {"samples": 40, "maxIntrusion": 0.001, "offenders": []}}
    assert _qa({"s1": ok}).status == "pass"
    bad = {"captionBand": {"samples": 40, "maxIntrusion": 0.05, "offenders": [
        {"what": "cartoon_sensor_ping:ruler", "maxIntrusion": 0.05, "first": 3.0, "n": 12}]}}
    c = _qa({"s1": ok, "s2": bad})
    assert c.status == "fail" and "cartoon_sensor_ping:ruler" in c.message
    assert _qa({"s1": ok, "s3": {}}).status == "fail"                      # an unmeasured scene
    assert _qa({"s3": {}}).status == "warn"                                # pre-M05.2 bundle
