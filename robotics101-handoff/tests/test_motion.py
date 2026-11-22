"""M02.4: motion (performers, actions, blinks, easing), lip sync (Rhubarb + RMS fallback), 2D clip renderer."""

import json
import shutil
import subprocess
import wave
from array import array
from pathlib import Path

import pytest

pytest.importorskip("manim")

from robotics101.cartoon import lipsync  # noqa: E402
from robotics101.cartoon.lipsync import MouthCue, MouthTrack, lipsync_agreement, line_cues, rms_cues  # noqa: E402
from robotics101.cartoon.motion import ACTIONS, Performer, action_fn, blink_schedule, ease_in_out  # noqa: E402
from robotics101.characters import load_registry  # noqa: E402


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOTICS101_TTS_CACHE", str(tmp_path / "cache"))


def _tone_wav(path: Path, segments: list[tuple[float, bool]], rate: int = 48000) -> Path:
    import math
    a = array("h")
    for dur, on in segments:
        for i in range(int(dur * rate)):
            a.append(int(12000 * math.sin(2 * math.pi * 220 * i / rate)) if on else 0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(a.tobytes())
    return path


def test_every_registry_action_has_motion():
    reg = load_registry()
    missing = sorted({a for c in reg.characters.values() for a in c.actions} - set(ACTIONS))
    assert missing == [], f"actions without a motion: {missing}"
    assert action_fn("arm_to:60") is ACTIONS["arm_to"]


@pytest.mark.parametrize("name", sorted(ACTIONS))
def test_actions_are_bounded_and_settle(name):
    for k in range(0, 101):
        o = action_fn(name)(k / 100, None)
        assert 0.5 <= o.get("squash", 1.0) <= 1.5
        assert abs(o.get("lean", 0.0)) <= 1.3 and -0.5 <= o.get("dy", 0.0) <= 1.0
        assert -20 <= o.get("arm_l", 20) <= 200 and -20 <= o.get("arm_r", 20) <= 200
    if name in ("hop", "cheer", "highfive"):
        assert abs(action_fn(name)(1.0, None).get("dy", 0.0)) < 1e-9          # lands back on the ground


def test_performer_is_deterministic_and_turn_persists():
    def make():
        p = Performer("bolt", x=-3).move(0, 1, x=2).act(1, 1.6, "turn").act(2, 3, "hop").feel(2, "proud")
        return p.finalize(5)
    a, b = make(), make()
    for t in (0, 0.5, 1.0, 1.3, 2.4, 4.9):
        assert a.state(t) == b.state(t)
    assert a.state(0).x == -3 and a.state(1.0).x == 2 and a.state(0.5).x == pytest.approx(-0.5)
    assert a.state(0.9).pose.facing == 1 and a.state(1.7).pose.facing == -1 and a.state(4.0).pose.facing == -1
    assert a.state(2.5).y > 0.3 and a.state(2.5).pose.expression == "proud"
    assert ease_in_out(0) == 0 and ease_in_out(1) == 1


def test_blinks_deterministic_spaced_and_per_character():
    b1, b2 = blink_schedule("maya", 60), blink_schedule("maya", 60)
    assert b1 == b2 and b1 != blink_schedule("bolt", 60)
    assert 10 <= len(b1) <= 30 and all(y - x >= 0.3 for x, y in zip(b1, b1[1:]))
    p = Performer("maya", x=0).finalize(60)
    t = p.blinks[0]
    assert p.state(t + 0.07).pose.blink == pytest.approx(1.0) and p.state(t + 0.5).pose.blink == 0


def test_mouth_track_and_talk():
    tr = MouthTrack()
    tr.add_line(2.0, [MouthCue(0.0, 0.2, "B"), MouthCue(0.2, 0.5, "D"), MouthCue(0.5, 0.6, "X")])
    assert [tr.shape_at(t) for t in (1.9, 2.1, 2.3, 2.55, 3.0)] == ["X", "B", "D", "X", "X"]
    p = Performer("maya", x=0)
    p.mouth = tr
    assert p.finalize(5).state(2.3).pose.mouth == "D" and p.state(4).pose.mouth == "X"


def test_rms_fallback_cues_follow_loudness(tmp_path):
    wav = _tone_wav(tmp_path / "t.wav", [(0.5, False), (1.0, True), (0.5, False)])
    cues = rms_cues(wav)
    tr = MouthTrack()
    tr.add_line(0, cues)
    assert tr.shape_at(0.2) == "X" and tr.shape_at(1.0) not in ("X", "A") and tr.shape_at(1.8) == "X"
    assert lipsync_agreement(tr, wav, 0) > 0.95


def test_line_cues_cached_and_method_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(lipsync, "find_rhubarb", lambda: None)
    wav = _tone_wav(tmp_path / "t.wav", [(0.3, False), (0.6, True)])
    c1, m1 = line_cues(wav, "Hi there")
    c2, m2 = line_cues(wav, "Hi there")
    assert m1 == m2 == "rms" and c1 == c2 and list((tmp_path / "cache" / "lipsync").glob("*.json"))


@pytest.mark.skipif(not (lipsync.find_rhubarb() and shutil.which("espeak-ng")), reason="needs rhubarb + espeak-ng")
def test_rhubarb_on_real_speech_is_deterministic_and_in_sync(tmp_path):
    raw = tmp_path / "raw.wav"
    text = "Bolt, that is not a wall. It is a pile of boxes!"
    subprocess.run(["espeak-ng", "-w", str(raw), text], check=True)
    a, m = line_cues(raw, text)
    b = lipsync.rhubarb_cues(raw, text, lipsync.find_rhubarb())
    assert m == "rhubarb" and a == b and len({c.shape for c in a}) >= 4
    tr = MouthTrack()
    tr.add_line(1.0, a)
    assert lipsync_agreement(tr, raw, 1.0) > 0.75


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_render_clip_frames_audio_and_parallel_determinism(tmp_path):
    from robotics101.cartoon.render2d import render_clip
    from robotics101.cartoon.rigs import build

    perf = Performer("bolt", x=-2).move(0, 1.0, x=2).act(0.2, 1.0, "hop").finalize(1.0)

    def frame(t):
        st = perf.state(t)
        return [build("bolt", st.pose).scale(0.6).shift([st.x, -2 + st.y, 0])]
    wav = _tone_wav(tmp_path / "a.wav", [(0.4, True), (0.2, False)])
    one = render_clip(frame, 30, tmp_path / "one.mp4", width=320, height=180, workers=1, audio_wav=wav)
    two = render_clip(frame, 30, tmp_path / "two.mp4", width=320, height=180, workers=2)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json",
                                       str(one)], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert v["nb_read_frames"] == "30" and v["width"] == 320 and v["profile"] == "High"
    assert a["sample_rate"] == "48000" and a["channels"] == 2 and float(a["duration"]) == pytest.approx(1.0, abs=0.03)

    def frames(p):
        return subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                              capture_output=True, check=True).stdout
    fa, fb = frames(one), frames(two)
    assert len(fa) == len(fb) == 30 * 320 * 180 * 3
    import numpy as np
    d = np.abs(np.frombuffer(fa, np.uint8).astype(int) - np.frombuffer(fb, np.uint8).astype(int))
    assert d.mean() < 1.0            # chunked parallel render == single-process render (codec noise only)
