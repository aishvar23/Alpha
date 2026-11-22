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
    spec = json.loads(CARTOON.read_text(encoding="utf-8"))
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
            pres = S.presence(sc, t)
            assert min(pres.values()) >= 0.8, (sc.sid, t, pres)


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
    assert sc["cartoon_servo_highfive"].facts == {"missAngle": 30.0, "endAngle": 60.0}
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
