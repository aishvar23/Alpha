"""M01.5: composer, QA gates and SHA-256 manifest on tiny synthetic inputs (ffmpeg colour clips + tones)."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from robotics101.animation.render import Profile
from robotics101.compose import ComposeError, compose_episode, final_encode_command
from robotics101.compose.composer import concat_wavs, scene_audio_filter
from robotics101.manifest import attach_qa, build_manifest, verify_manifest, write_manifest
from robotics101.media import (
    gain_limiter_filter,
    is_faststart,
    loudness_gain_db,
    mp4_top_level_atoms,
    summarize,
)
from robotics101.narration.captions import parse_srt, validate_srt
from robotics101.qa import FAIL, render_markdown, run_qa, write_qa_report

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")

TINY = Profile("tiny", 160, 90, 30)
# (sceneId, colour, scene seconds, tone seconds, tone Hz)
SCENES = [("scene-a", "red", 2.0, 1.0, 440), ("scene-b", "blue", 1.5, 0.6, 660)]
LEAD_IN = 0.5


def _ff(*args):
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-v", "error", *args], check=True)


def make_bundle(root: Path, *, silent: bool = False, size: str = "160x90") -> tuple[dict, dict]:
    """scenes/<id>.mp4 (colour, video only), audio/<id>.wav (mono 48k tone), episode.json, timing.json."""
    (root / "scenes").mkdir(parents=True)
    (root / "audio").mkdir()
    spec = {"episodeId": "ep-900", "title": "Synthetic test episode", "scenes": []}
    timing = {"episodeId": "ep-900", "provider": "fixture", "providerLabels": ["FIXTURE placeholder audio — not narration"],
              "scenes": []}
    t = 0.0
    for seq, (sid, colour, dur, tone, hz) in enumerate(SCENES, 1):
        _ff("-f", "lavfi", "-i", f"color=c={colour}:s={size}:r=30:d={dur}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-frames:v", str(round(dur * 30)), str(root / "scenes" / f"{sid}.mp4"))
        src = f"anullsrc=r=48000:cl=mono:d={tone}" if silent else f"sine=f={hz}:r=48000:d={tone},volume=0.5"
        _ff("-f", "lavfi", "-i", src, "-c:a", "pcm_s16le", "-ac", "1", str(root / "audio" / f"{sid}.wav"))
        spec["scenes"].append({"sceneId": sid, "sequence": seq, "template": "robot_intro", "engine": "manim",
                               "narration": f"Tone number {seq} for the composer test."})
        timing["scenes"].append({
            "sceneId": sid, "sequence": seq, "audio_duration_s": tone, "scene_start_s": t, "scene_end_s": t + dur,
            "scene_duration_s": dur, "narration_start_s": t + LEAD_IN, "narration_end_s": t + LEAD_IN + tone,
            "speech_coverage": round(tone / dur, 3), "provider": "fixture", "is_synthetic_placeholder": True})
        t += dur
    (root / "episode.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "timing.json").write_text(json.dumps(timing), encoding="utf-8")
    return spec, timing


def composed(root: Path, **kw) -> tuple[dict, dict]:
    spec, timing = make_bundle(root, **kw)
    compose_episode(spec, timing, root, TINY, preset="veryfast", log=lambda *_: None)  # ultrafast = Main profile
    m = build_manifest(root, spec, TINY.name, timing, run_id="run-test", tool_versions={"ffmpeg": "test"})
    write_manifest(root, m)
    return spec, m


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    root = tmp_path_factory.mktemp("bundle")
    if HAVE_FFMPEG:
        composed(root)
    return root


# ---------------------------------------------------------------- pure

def test_final_encode_command_settings(tmp_path):
    cmd = final_encode_command("ffmpeg", [tmp_path / "a.mp4", tmp_path / "b.mp4"], tmp_path / "e.wav",
                               tmp_path / "f.mp4", Profile("full", 1920, 1080, 30), 9000)
    s, pairs = " ".join(cmd), set(zip(cmd, cmd[1:]))
    assert "concat=n=2:v=1:a=0" in s and "scale=1920:1080" in s and "format=yuv420p" in s
    for flag, val in [("-c:v", "libx264"), ("-profile:v", "high"), ("-pix_fmt", "yuv420p"), ("-r", "30"),
                      ("-fps_mode", "cfr"), ("-c:a", "aac"), ("-b:a", "192k"), ("-ar", "48000"), ("-ac", "2"),
                      ("-movflags", "+faststart"), ("-frames:v", "9000"), ("-map", "2:a:0")]:
        assert (flag, val) in pairs, flag


def test_scene_audio_filter_is_sample_exact_and_limited():
    f = scene_audio_filter(5.2, 24000, 96000)
    assert "volume=+5.20dB" in f and "alimiter" in f and "level=0" in f
    assert "adelay=24000S" in f and "apad=whole_len=96000" in f and "atrim=end_sample=96000" in f
    assert f.endswith("aformat=sample_fmts=s16:channel_layouts=stereo")
    assert "volume=" not in gain_limiter_filter(None)


def test_loudness_gain():
    assert loudness_gain_db(-21.3) == pytest.approx(5.3)
    assert loudness_gain_db(-70.0) is None and loudness_gain_db(None) is None


# ---------------------------------------------------------------- compose

@needs_ffmpeg
def test_compose_durations_streams_and_sync(bundle):
    total_frames = sum(round(d * 30) for _, _, d, _, _ in SCENES)      # 60 + 45
    for sid, _, dur, _, _ in SCENES:
        c = summarize(bundle / "clips" / f"{sid}.mp4", count_frames=True)
        assert c.video["frames"] == round(dur * 30) and c.audio["sample_rate"] == 48000 and c.audio["channels"] == 2
    s = summarize(bundle / "final.mp4", count_frames=True)
    v, a = s.video, s.audio
    assert (v["codec"], v["profile"], v["pix_fmt"], v["width"], v["height"]) == ("h264", "High", "yuv420p", 160, 90)
    assert v["fps"] == 30 and v["frames"] == total_frames
    assert (a["codec"], a["sample_rate"], a["channels"]) == ("aac", 48000, 2)
    assert abs(a["duration_s"] - total_frames / 30) <= 0.03          # < one AAC frame of padding
    assert is_faststart(bundle / "final.mp4")
    comp = json.loads((bundle / "compose.json").read_text())
    assert comp["total_frames"] == total_frames and [g["start_s"] for g in comp["segments"]] == [0.0, 2.0]
    assert not (bundle / ".compose").exists()


@needs_ffmpeg
def test_compose_places_narration_at_lead_in(bundle):
    """Tone onsets in final.mp4 land at scene start + 0.5 s (0.5 s and 2.5 s) within 10 ms."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(bundle / "final.mp4"), "-af",
                        "silencedetect=n=-40dB:d=0.2", "-f", "null", "-"], capture_output=True, text=True)
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", p.stderr)]
    assert ends[:2] == pytest.approx([0.5, 2.5], abs=0.01)


@needs_ffmpeg
def test_compose_captions_on_final_timeline(bundle):
    cues = parse_srt((bundle / "captions.srt").read_text())
    assert cues and not validate_srt(cues, bounds_ms=(0, 3500))
    assert cues[0].start_ms == 500 and any(c.start_ms == 2500 for c in cues)


@needs_ffmpeg
def test_compose_rejects_wrong_resolution_and_stale_clip(tmp_path):
    spec, timing = make_bundle(tmp_path / "res", size="320x180")
    with pytest.raises(ComposeError, match="320x180"):
        compose_episode(spec, timing, tmp_path / "res", TINY, log=lambda *_: None)
    spec, timing = make_bundle(tmp_path / "stale")
    timing["scenes"][0]["scene_duration_s"] = 3.0
    with pytest.raises(ComposeError, match="stale clip"):
        compose_episode(spec, timing, tmp_path / "stale", TINY, log=lambda *_: None)
    (tmp_path / "stale" / "scenes" / "scene-b.mp4").unlink()
    with pytest.raises(ComposeError, match="scene-b"):
        compose_episode(spec, timing, tmp_path / "stale", TINY, log=lambda *_: None)


def test_concat_wavs_rejects_mixed_formats(tmp_path):
    import wave
    for name, rate in (("a.wav", 48000), ("b.wav", 44100)):
        with wave.open(str(tmp_path / name), "wb") as w:
            w.setnchannels(2), w.setsampwidth(2), w.setframerate(rate)
            w.writeframes(b"\0" * 400)
    with pytest.raises(ComposeError):
        concat_wavs([tmp_path / "a.wav", tmp_path / "b.wav"], tmp_path / "o.wav")


@needs_ffmpeg
def test_faststart_detection(tmp_path):
    out = tmp_path / "slow.mp4"
    _ff("-f", "lavfi", "-i", "color=c=black:s=64x64:r=30:d=0.2", "-c:v", "libx264", str(out))
    atoms = mp4_top_level_atoms(out)
    assert atoms.index("mdat") < atoms.index("moov") and not is_faststart(out)


# ---------------------------------------------------------------- QA

def _status(rep, check_id):
    return next(c.status for c in rep.checks if c.id == check_id)


@needs_ffmpeg
def test_qa_good_bundle_passes_media_gates(bundle):
    rep = run_qa(bundle, TINY)
    failed = {c.id for c in rep.failures}
    assert failed == {"final.duration_range"}            # 3.5 s is (correctly) outside the 270–420 s window
    for cid in ("final.decodable", "final.video_codec", "final.resolution", "final.fps", "final.audio_codec",
                "final.audio_not_silent", "final.no_clipping", "final.av_sync", "final.duration_matches_scenes",
                "captions.valid", "manifest.hashes", "scene.scene-a.clip_duration", "scene.scene-b.narration_audible"):
        assert _status(rep, cid) == "pass", cid
    warned = {c.id for c in rep.warnings}
    assert {"tts.production_voice", "profile.publishable", "scene.scene-a.voice_coverage"} <= warned
    assert rep.status == FAIL
    md = render_markdown(rep.to_dict())
    assert "| scene-a | robot_intro | manim |" in md and "Status: FAIL" in md


@needs_ffmpeg
def test_qa_wrong_resolution_fails(bundle):
    rep = run_qa(bundle, Profile("tiny", 320, 180, 30))
    assert rep.status == FAIL and _status(rep, "final.resolution") == "fail"


@needs_ffmpeg
def test_qa_silent_audio_fails(tmp_path):
    composed(tmp_path, silent=True)
    rep = run_qa(tmp_path, TINY)
    assert rep.status == FAIL
    assert _status(rep, "final.audio_not_silent") == "fail"
    assert _status(rep, "scene.scene-a.narration_audible") == "fail"


@needs_ffmpeg
def test_qa_missing_clip_and_captions_fail(tmp_path):
    composed(tmp_path)
    (tmp_path / "clips" / "scene-b.mp4").unlink()
    (tmp_path / "captions.srt").write_text("1\n00:00:02,000 --> 00:00:01,000\nbackwards\n")
    rep = run_qa(tmp_path, TINY)
    assert _status(rep, "scene.scene-b.clip_present") == "fail"
    assert _status(rep, "captions.valid") == "fail"
    assert _status(rep, "manifest.hashes") == "fail"


# ---------------------------------------------------------------- manifest

@needs_ffmpeg
def test_manifest_contents(bundle):
    m = json.loads((bundle / "manifest.json").read_text())
    roles = {a["role"] for a in m["artifacts"]}
    assert {"spec", "timing", "narration_audio", "scene_video", "scene_clip", "final_video", "captions",
            "compose_report"} <= roles
    final = next(a for a in m["artifacts"] if a["role"] == "final_video")
    assert m["finalVideoSha256"] == final["sha256"] and len(final["sha256"]) == 64
    assert m["publish"] == {"status": "not_published", "requiresApprovalOfSha256": final["sha256"]}
    assert final["media"]["video"]["codec"] == "h264" and m["tts"]["isSyntheticPlaceholder"] is True
    assert all(not Path(a["path"]).is_absolute() for a in m["artifacts"])
    assert verify_manifest(bundle) == []


@needs_ffmpeg
def test_manifest_detects_one_byte_change(tmp_path):
    composed(tmp_path)
    assert verify_manifest(tmp_path) == []
    final = tmp_path / "final.mp4"
    data = bytearray(final.read_bytes())
    data[len(data) // 2] ^= 0x01
    final.write_bytes(bytes(data))
    problems = verify_manifest(tmp_path)
    assert any("final.mp4: sha256" in p for p in problems)
    rep = run_qa(tmp_path, TINY)
    assert _status(rep, "manifest.hashes") == "fail" and rep.status == FAIL


@needs_ffmpeg
def test_manifest_rejects_tampered_publish_and_escaping_paths(bundle):
    m = json.loads((bundle / "manifest.json").read_text())
    m["publish"] = {"status": "published", "requiresApprovalOfSha256": "0" * 64}
    m["artifacts"].append({"path": "../outside.txt", "role": "captions", "bytes": 1, "sha256": "x"})
    problems = verify_manifest(bundle, m)
    assert any("escapes" in p for p in problems)
    assert any("requiresApprovalOfSha256" in p for p in problems)
    assert any("not_published" in p for p in problems)


@needs_ffmpeg
def test_qa_reports_sealed_into_manifest(tmp_path):
    spec, m = composed(tmp_path)
    doc, paths = write_qa_report(tmp_path, run_qa(tmp_path, TINY))
    write_manifest(tmp_path, attach_qa(m, tmp_path, doc["status"], paths))
    m2 = json.loads((tmp_path / "manifest.json").read_text())
    assert m2["qa"]["status"] == doc["status"] and set(m2["qa"]["reports"]) == {"qa_report.json", "qa_report.md"}
    assert verify_manifest(tmp_path, skip_roles=frozenset()) == []   # reports hash-match too
    assert (tmp_path / "qa_report.md").read_text().startswith("# QA report")
