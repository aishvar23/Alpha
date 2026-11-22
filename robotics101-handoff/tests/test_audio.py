"""M02.7: generated music + SFX, loudness meter, ducking, deterministic mix, mix QA, licence manifest."""

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from robotics101.cartoon import MUSIC_CUES, SFX_IDS
from robotics101.cartoon import audio as A
from robotics101.qa import QaReport

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


@pytest.mark.parametrize("sid", sorted(SFX_IDS))
def test_every_sfx_is_synthesised_deterministically(sid):
    x, y = A.sfx(sid), A.sfx(sid)
    assert np.array_equal(x, y) and 0.05 < len(x) / A.RATE < 2.0
    assert np.max(np.abs(x)) == pytest.approx(1.0) and abs(x[-1]) < 1e-3          # normalised, no end click


@pytest.mark.parametrize("cue", sorted(MUSIC_CUES))
def test_every_music_cue_is_generated(cue):
    x = A.sting(cue)
    assert np.array_equal(x, A.sting(cue)) and 1.0 < len(x) / A.RATE < 4.0 and np.max(np.abs(x)) <= 0.9 + 1e-9


def test_bed_loop_is_seamless_and_seeded():
    a, b = A.bed_loop(3), A.bed_loop(4)
    assert len(a) == len(b) and not np.array_equal(a, b)
    assert abs(a[-1] - a[0]) < 0.05


def test_unknown_ids_rejected():
    with pytest.raises(ValueError):
        A.sfx("kaboom")
    with pytest.raises(ValueError):
        A.sting("dubstep")


@needs_ffmpeg
def test_lufs_matches_ffmpeg_ebur128(tmp_path):
    from robotics101.media import audio_levels
    rng = np.random.default_rng(1)
    t = np.arange(10 * A.RATE) / A.RATE
    x = 0.2 * np.sin(2 * np.pi * 440 * t) * (1 + 0.5 * np.sin(2 * np.pi * 0.3 * t)) + 0.02 * rng.standard_normal(len(t))
    p = A.write_wav(tmp_path / "x.wav", x)
    assert A.lufs(x) == pytest.approx(audio_levels(p).integrated_lufs, abs=0.3)


def test_duck_envelope():
    n = 4 * A.RATE
    g = A.duck_envelope(n, [(1.0, 2.0)])
    db = 20 * np.log10(g)
    assert db[int(0.5 * A.RATE)] == pytest.approx(0) and db[int(1.5 * A.RATE)] == pytest.approx(A.DUCK_DB)
    assert db[int(3.5 * A.RATE)] == pytest.approx(0)
    assert np.all(np.abs(np.diff(db)) < 1.0)                                         # ramps, no steps


def test_licence_manifest_lists_everything():
    lic = json.loads((ROOT / "assets" / "LICENSES.json").read_text())
    assert set(lic["generated"]["sfx"]) >= SFX_IDS and set(lic["generated"]["music"]) >= MUSIC_CUES
    assert {f["family"] for f in lic["fonts"]} >= {"Fredoka", "Luckiest Guy", "Bangers"}
    assert all(f["license"] in ("OFL-1.1", "Apache-2.0") for f in lic["fonts"])


@needs_ffmpeg
def test_mix_is_deterministic_and_passes_qa(tmp_path):
    from robotics101.characters import load_registry
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    spec = json.loads((ROOT / "examples" / "episode-001-cartoon.json").read_text())
    spec["scenes"] = spec["scenes"][:2]
    timing = voice_episode(spec, load_registry(), tmp_path / "v", B.FixtureBackend(), VoiceCache(tmp_path / "c"),
                           log=lambda m: None)
    sums = []
    for k in range(2):
        out = tmp_path / f"m{k}"
        A.mix_episode(timing, tmp_path / "v", out, log=lambda m: None)
        sums.append({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((out / "audio").rglob("*.wav"))})
    assert sums[0] == sums[1] and len(sums[0]) == 4
    rep = QaReport("t", "mix", str(tmp_path))
    res = A.check_mix(rep, tmp_path / "m0", timing, json.loads((ROOT / "assets" / "LICENSES.json").read_text()))
    failed = [c for c in rep.checks if not c.ok]
    assert not failed, failed
    assert res["samples"] == res["expectedSamples"]
