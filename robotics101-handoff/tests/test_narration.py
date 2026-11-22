import json
import re
import subprocess
import wave

import pytest
from conftest import SAMPLE

from robotics101.cli import EXIT_INPUT, EXIT_OK, main
from robotics101.narration import (
    ESPEAK_LABEL,
    FIXTURE_LABEL,
    EspeakProvider,
    FixtureProvider,
    NarrationResult,
    TtsError,
    get_provider,
)
from robotics101.narration.captions import (
    MAX_LINE,
    format_ts,
    parse_srt,
    parse_ts,
    scene_cues,
    split_cue_texts,
    validate_srt,
)
from robotics101.narration.timing import SHORT_VOICE_FLAG, build_timeline, compute_scene_timing

needs_espeak = pytest.mark.skipif(not EspeakProvider.available(), reason="espeak-ng/ffmpeg not installed")


def _mean_volume_db(path) -> float:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True, check=True)
    return float(re.search(r"mean_volume:\s*(-?[\d.]+) dB", p.stderr).group(1))


# --- providers -------------------------------------------------------------

def test_fixture_provider_deterministic(tmp_path):
    text = " ".join(["word"] * 25)  # 25 words @150 wpm = 10 s
    a = FixtureProvider().synthesize(text, tmp_path / "a.wav")
    b = FixtureProvider().synthesize(text, tmp_path / "b.wav")
    assert a.duration_s == b.duration_s == 10.0
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()
    assert a.is_synthetic_placeholder and a.label == FIXTURE_LABEL and "not narration" in a.label
    with wave.open(str(tmp_path / "a.wav")) as w:
        assert (w.getframerate(), w.getsampwidth(), w.getnchannels()) == (48000, 2, 1)


def test_get_provider_env_and_errors(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "fixture")
    assert get_provider().name == "fixture"
    assert get_provider("espeak").name == "espeak"  # explicit beats env
    with pytest.raises(TtsError, match="unknown TTS provider"):
        get_provider("nope")
    monkeypatch.delenv("TTS_EXTERNAL_URL", raising=False)
    monkeypatch.delenv("TTS_EXTERNAL_API_KEY", raising=False)
    with pytest.raises(TtsError, match="requires env"):
        get_provider("external")


def test_external_provider_never_calls_out(monkeypatch, tmp_path):
    monkeypatch.setenv("TTS_EXTERNAL_URL", "https://example.invalid")
    monkeypatch.setenv("TTS_EXTERNAL_API_KEY", "x")
    with pytest.raises(TtsError, match="stub"):
        get_provider("external").synthesize("hi", tmp_path / "x.wav")


@needs_espeak
def test_espeak_provider_real_audio(tmp_path):
    r = EspeakProvider().synthesize("A robot senses, decides, and acts.", tmp_path / "e.wav")
    assert r.label == ESPEAK_LABEL and r.is_synthetic_placeholder
    assert 1.0 < r.duration_s < 10.0
    with wave.open(str(r.path)) as w:
        assert (w.getframerate(), w.getsampwidth()) == (48000, 2)
    assert _mean_volume_db(r.path) > -60.0


# --- timing ----------------------------------------------------------------

def _res(d, placeholder=True):
    return NarrationResult("x.wav", d, "fixture", placeholder, FIXTURE_LABEL)


def test_timing_uses_target_when_audio_short():
    t = compute_scene_timing({"sceneId": "s", "sequence": 1, "durationTargetSeconds": 30}, _res(10.0), 5.0)
    assert t.scene_duration_s == 30.0 and t.scene_start_s == 5.0 and t.scene_end_s == 35.0
    assert t.narration_start_s == 5.5 and t.narration_end_s == 15.5
    assert t.hold_s == 19.5
    assert SHORT_VOICE_FLAG in t.qa_flags  # 10/30 < 60%


def test_timing_extends_when_audio_long():
    t = compute_scene_timing({"sceneId": "s", "sequence": 1, "durationTargetSeconds": 10}, _res(12.0), 0.0)
    assert t.scene_duration_s == 13.0 and t.hold_s == 0.5
    assert SHORT_VOICE_FLAG not in t.qa_flags


def test_timeline_contiguous(spec):
    results = {s["sceneId"]: _res(8.0) for s in spec["scenes"]}
    tl = build_timeline(spec["scenes"], results)
    assert tl[0].scene_start_s == 0.0
    for a, b in zip(tl, tl[1:]):
        assert a.scene_end_s == b.scene_start_s
    assert tl[-1].scene_end_s == sum(s["durationTargetSeconds"] for s in spec["scenes"])


# --- captions --------------------------------------------------------------

def test_timestamp_format_roundtrip():
    assert format_ts(0) == "00:00:00,000"
    assert format_ts(3_723_045) == "01:02:03,045"
    assert parse_ts("01:02:03,045") == 3_723_045
    with pytest.raises(ValueError):
        parse_ts("1:02:03.045")


def test_split_respects_line_limits():
    long = ("This is a deliberately long sentence, with several clauses, that keeps going well past the "
            "eighty-four character cue limit; it must be split into readable caption chunks.")
    texts = split_cue_texts("Short one. " + long)
    assert texts[0] == "Short one."
    assert len(texts) >= 3
    assert " ".join(texts) == "Short one. " + long


def test_scene_cues_within_window_and_proportional():
    cues = scene_cues("Hi. This sentence is much longer than the first.", 10.0, 20.0)
    assert cues[0][0] == 10_000 and cues[-1][1] == 20_000
    assert (cues[0][1] - cues[0][0]) < (cues[1][1] - cues[1][0])


def test_parse_validate_detects_overlap():
    bad = "1\n00:00:01,000 --> 00:00:03,000\nA\n\n2\n00:00:02,000 --> 00:00:04,000\nB\n"
    assert any("overlaps" in p for p in validate_srt(parse_srt(bad)))


# --- end-to-end (fixture: no external binaries required except ffprobe if present) ---

def test_narrate_cli_fixture(tmp_path, capsys):
    out = tmp_path / "ep"
    assert main(["narrate", str(SAMPLE), "--out", str(out), "--provider", "fixture"]) == EXIT_OK
    doc = json.loads((out / "timing.json").read_text())
    scenes = doc["scenes"]
    assert len(scenes) == 7 and all((out / "audio" / f"{s['sceneId']}.wav").exists() for s in scenes)
    assert doc["providerLabels"] == [FIXTURE_LABEL]
    assert len(doc["scenesFlagged"]) == 7  # sample narration is intentionally short

    cues = parse_srt((out / "captions.srt").read_text())
    assert validate_srt(cues, bounds_ms=(0, round(doc["totalDurationSeconds"] * 1000))) == []
    assert all(len(line) <= MAX_LINE for c in cues for line in c.text.splitlines())
    for s in scenes:  # each scene's cues sit inside its narration window
        lo, hi = round(s["narration_start_s"] * 1000), round(s["narration_end_s"] * 1000)
        inside = [c for c in cues if lo <= c.start_ms < hi]
        assert inside and all(c.end_ms <= hi for c in inside)
    assert "FIXTURE placeholder" in capsys.readouterr().out


def test_narrate_cli_rejects_invalid_spec(tmp_path, spec):
    spec["scenes"][0]["template"] = "nope"
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(spec))
    assert main(["narrate", str(p), "--out", str(tmp_path / "o"), "--provider", "fixture"]) == 1
    assert not (tmp_path / "o").exists()


def test_narrate_cli_external_unconfigured(tmp_path, monkeypatch):
    monkeypatch.delenv("TTS_EXTERNAL_URL", raising=False)
    assert main(["narrate", str(SAMPLE), "--out", str(tmp_path / "o"), "--provider", "external"]) == EXIT_INPUT


@needs_espeak
def test_narrate_cli_espeak_nonsilent(tmp_path):
    out = tmp_path / "ep"
    assert main(["narrate", str(SAMPLE), "--out", str(out), "--provider", "espeak"]) == EXIT_OK
    wavs = sorted((out / "audio").glob("*.wav"))
    assert len(wavs) == 7
    assert all(_mean_volume_db(w) > -60.0 for w in wavs)

