"""M02.6: cartoon scene engine — staging from timing.json beats, presence, teaching facts, robot-cam splice math."""

import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("manim")
pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")

from robotics101.cartoon import scenes as S  # noqa: E402
from robotics101.characters import load_registry  # noqa: E402
from robotics101.voice import VoiceCache, voice_episode  # noqa: E402
from robotics101.voice import backends as B  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    d = tmp_path_factory.mktemp("voice")
    from robotics101.cartoon.episode import expand_episode
    spec = expand_episode(json.loads(CARTOON.read_text(encoding="utf-8")), load_registry())   # M03 defaults
    timing = voice_episode(spec, load_registry(), d, B.FixtureBackend(), VoiceCache(d / "cache"), log=lambda m: None)
    return spec, timing, d


@pytest.fixture(autouse=True)
def _fast_lipsync(monkeypatch):
    from robotics101.cartoon import lipsync
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))


def _scenes(voiced, robotcam=None):
    spec, timing, d = voiced
    by = {s["sceneId"]: s for s in spec["scenes"]}
    return [S.build_scene(by[t["sceneId"]], t, d, robotcam) for t in timing["scenes"]]


def test_every_template_has_staging(voiced):
    spec, _, _ = voiced
    assert {s["template"] for s in spec["scenes"]} <= set(S.STAGING)


def test_cast_stays_on_screen(voiced):
    for sc in _scenes(voiced):
        for k in range(int(sc.duration * 2)):
            t = k * 0.5
            if sc.template == "cartoon_cold_open" and t < 3.6:        # Bolt zooms in from off-screen
                continue
            pres = {c: v for c, v in S.presence(sc, t).items() if t >= sc.enter_at.get(c, 0.0)}
            assert not pres or min(pres.values()) >= 0.8, (sc.sid, t, pres)


def test_lipsync_covers_every_line(voiced):
    for sc in _scenes(voiced):
        assert len(sc.lipsync_methods) == len(sc.lines())
        for b in sc.lines():
            p = sc.perf[b["speaker"]]
            mid = (b["start_s"] + b["end_s"]) / 2
            assert any(p.mouth.talking_at(mid + d) for d in (-0.3, 0, 0.3)), (sc.sid, b["index"])


def test_teaching_facts_match_spec(voiced):
    sc = {s.template: s for s in _scenes(voiced)}
    rule = sc["cartoon_rule_board"].facts
    assert rule["thresholdMeters"] == 0.5 and rule["stopReading"] < 0.5 and rule["readings"] == [1.5, 1.0, 0.6, 0.4]
    rem = sc["cartoon_obstacle_rematch"].facts
    assert rem["thresholdMeters"] == 0.5 and rem["stopReading"] == pytest.approx(0.49) and rem["stopDistance"] < 0.5
    ping = sc["cartoon_sensor_ping"].facts
    assert ping["rangeMeters"] == 3.0 and ping["nibMeters"] == 1.2
    sv = sc["cartoon_servo_highfive"].facts
    assert (sv["missAngle"], sv["endAngle"]) == (30.0, 60.0)
    assert "measures distance" in sc["cartoon_recap_chant"].facts["question"]


def test_rematch_robot_stops_on_the_ping_beat_without_touching_boxes(voiced):
    sc = next(s for s in _scenes(voiced) if s.template == "cartoon_obstacle_rematch")
    a = sc.facts["approach"]
    ping = sc.beat("action", "do", "ping")
    assert a.stop_t == pytest.approx(ping["end_s"], abs=0.1)
    from robotics101.cartoon import props as PR
    face = 5.4 - PR.BOX_W / 2
    bolt = sc.perf["bolt"]
    for k in range(int(sc.duration * 10)):
        t = k / 10
        x, _ = bolt.position_at(t)
        assert x + S.BOLT_FRONT * S.SCALES["bolt"] <= face + 1e-6, t


def test_robotcam_cutaway_is_synced_to_the_stop(voiced, tmp_path):
    cam = {"clip": tmp_path / "rc.mp4", "stop_s": 3.7, "stop_reading": 0.47}
    sc = next(s for s in _scenes(voiced, cam) if s.template == "cartoon_obstacle_rematch")
    (c,) = sc.cutaways
    a = sc.facts["approach"]
    assert c["start"] < a.stop_t < c["end"]
    assert c["clip_offset"] + (a.stop_t - c["start"]) == pytest.approx(3.7, abs=1 / 30)   # clip stop == 2D stop
    assert sc.facts["stopReading"] == pytest.approx(0.47)                                   # same number on screen


def test_sfx_lettering_tracks_anchored_sfx(voiced):
    sc = _scenes(voiced)[0]
    bonk = sc.beat("sfx", "id", "bonk")
    zoom = sc.beat("action", "do", "zoom")
    assert bonk["start_s"] == zoom["end_s"]
    f = S.frame_fn(sc)
    assert len(f(bonk["start_s"] + 0.2)) > len(f(bonk["start_s"] - 0.2))


def test_frames_render_for_every_scene(voiced):
    from robotics101.cartoon.render2d import frame_rgb
    for sc in _scenes(voiced):
        for t in (0.0, sc.duration / 2, sc.duration - 0.05):
            img = frame_rgb(S.frame_fn(sc)(t), 192, 108, "#FFE8C2")
            assert img.shape == (108, 192, 3) and img.std() > 5


def test_generated_intro_stages_every_main_character(voiced):
    sc = next(s for s in _scenes(voiced) if s.template == "cartoon_character_intro")
    intro = sc.facts["introduced"]
    assert [x["name"] for x in intro] == ["Bolt", "Maya", "Nib"]
    for x in intro:
        cid = x["id"]
        assert x["plate"][1] - x["plate"][0] >= 1.5 and x["name"] in x["line"]
        assert S.presence(sc, max(0.0, sc.enter_at[cid] - 1.2))[cid] < 0.8      # enters from off-stage
        assert S.presence(sc, sc.enter_at[cid] + 0.1)[cid] >= 0.8
    assert len(S.frame_fn(sc)(intro[0]["plate"][0] + 1.0)) > 3


def test_concept_cards_and_transitions_are_staged(voiced):
    spec, timing, d = voiced
    by = {s["sceneId"]: s for s in spec["scenes"]}
    order = [t["sceneId"] for t in timing["scenes"]]
    cards = 0
    for i, t in enumerate(timing["scenes"]):
        nxt = by[order[i + 1]].get("transitionIn") if i + 1 < len(order) else None
        sc = S.build_scene(by[t["sceneId"]], t, d, None, trans_out=nxt)
        assert sc.trans_in == by[t["sceneId"]].get("transitionIn")
        assert bool(S.transition_overlay(sc, (sc.n_frames - 1) / 30)) == bool(nxt)       # last frame covered
        if sc.trans_in:
            assert S.transition_overlay(sc, 0.0)                                       # first frame covered
            assert not S.transition_overlay(sc, 1.0)
        for c in sc.concepts:
            cards += 1
            assert c["end"] - c["start"] >= 2.0 and c["end"] <= c["teachStart"] + 0.05
    assert cards == sum(len(s.get("concepts") or []) for s in spec["scenes"]) == 5


def test_nobody_is_ever_static(voiced):
    """M03.3: every on-stage character keeps moving (pose-track static run ≤ 1 s) in every scene."""
    from robotics101.cartoon.liveliness import MAX_STATIC_S, scene_liveliness
    for sc in _scenes(voiced, {"clip": Path("x.mp4"), "stop_s": 5.0, "stop_reading": 0.49}):
        live = scene_liveliness(sc, S.presence, S.HEIGHT, S.SCALES)
        assert set(live) == {c for c in sc.perf if c in sc.cast}
        for cid, v in live.items():
            assert v["frames"] > 0 and v["longestStaticS"] <= MAX_STATIC_S, (sc.sid, cid, v)
