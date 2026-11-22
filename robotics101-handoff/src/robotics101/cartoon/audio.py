"""Music, sound effects and the episode mix (M02.7) — all generated in code, deterministic.

* Music: a small numpy synth (marimba-ish plucks, bass, kick/clap/shaker) in C major at 112 BPM. One looping bed
  per scene (melody seeded by the scene sequence) plus the six cues of ``MUSIC_CUES`` as stings.
* SFX: every id in ``SFX_IDS`` is synthesised (sweeps, noise bursts, bells, boings); nothing is sampled.
* Mix (48 kHz stereo): dialogue stems placed on the episode timeline and normalised to -16 LUFS; music at
  ``MUSIC_LUFS`` and ducked by ``DUCK_DB`` under every voiced line with a deterministic envelope computed from the
  timeline (not a sidechain); SFX at fixed per-id levels; then one make-up trim to -16 LUFS integrated and a
  brick-wall limiter at -1.5 dBFS (ffmpeg ``alimiter``). Stems and the mix are written as 16-bit WAV.

Everything is a pure function of timing.json + the dialogue stems, so re-running produces byte-identical WAVs.
"""

from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np

from robotics101.cartoon import MUSIC_CUES, SFX_IDS

RATE = 48_000
FPS = 30
BPM = 112
BEAT = 60.0 / BPM
DIALOGUE_LUFS = -16.0
MUSIC_LUFS = -27.0           # bed + stings before ducking (≈ 11 LU under dialogue)
DUCK_DB = -12.0              # extra attenuation of music while anyone speaks
DUCK_ATTACK_S, DUCK_RELEASE_S, DUCK_PRE_S, DUCK_HOLD_S = 0.08, 0.35, 0.10, 0.15
TARGET_LUFS = -16.0
LIMIT_DBFS = -1.5
STING_GAIN_DB = 6.0          # stings sit above the bed (they play in dialogue gaps)
SFX_PEAK_DBFS = -12.0
SFX_GAIN_DB = {"motor": -6, "charge": -4, "chalk": -6, "page_flip": -4, "sparkle": -5, "stars": -6, "echo": -5,
               "nib_whistle": -3, "zoom": -2, "whoosh": -3}

# C major scale degrees -> MIDI; chords for I-V-vi-IV
CHORDS = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
BASS = [36, 43, 45, 41]


def midi_hz(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _t(n: int) -> np.ndarray:
    return np.arange(n) / RATE


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = _t(n)
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / max(decay, 1e-4))


def _rng(key: str) -> np.random.Generator:
    import hashlib
    return np.random.default_rng(int(hashlib.sha256(key.encode()).hexdigest()[:12], 16))


# ------------------------------------------------------------------------------------------ instruments

def marimba(m: float, dur: float = 0.6, vel: float = 1.0) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    f = midi_hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 4 * f * t) * np.exp(-t / 0.05)
    return (vel * x * _env(n, 0.004, 0.28)).astype(np.float64)


def bell(m: float, dur: float = 1.0, vel: float = 1.0) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    f = midi_hz(m)
    x = sum(a * np.sin(2 * np.pi * f * r * t) for r, a in ((1, 1), (2.76, 0.4), (5.4, 0.2), (8.93, 0.1)))
    return vel * x * _env(n, 0.002, 0.45)


def bass(m: float, dur: float = 0.5, vel: float = 1.0) -> np.ndarray:
    n = int(dur * RATE)
    t = _t(n)
    f = midi_hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return vel * x * _env(n, 0.006, 0.35)


def kick(vel: float = 1.0) -> np.ndarray:
    n = int(0.3 * RATE)
    t = _t(n)
    f = 50 + 90 * np.exp(-t / 0.04)
    return vel * np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.001, 0.12)


def noise_burst(key: str, dur: float, decay: float, hp: float = 0.0, vel: float = 1.0) -> np.ndarray:
    n = int(dur * RATE)
    x = _rng(key).standard_normal(n)
    if hp > 0:                                    # crude high-pass: first difference blended
        x = np.concatenate([[0], np.diff(x)]) * hp + x * (1 - hp)
    return vel * x * _env(n, 0.001, decay)


def clap_hit(vel: float = 1.0) -> np.ndarray:
    return noise_burst("clap", 0.2, 0.05, hp=0.7, vel=vel * 0.6)


def shaker(vel: float = 1.0) -> np.ndarray:
    return noise_burst("shaker", 0.08, 0.02, hp=1.0, vel=vel * 0.25)


def _add(buf: np.ndarray, x: np.ndarray, at: float) -> None:
    i = int(round(at * RATE))
    if i >= len(buf) or i + len(x) <= 0:
        return
    if i < 0:
        x, i = x[-i:], 0
    j = min(len(buf), i + len(x))
    buf[i:j] += x[: j - i]


# ------------------------------------------------------------------------------------------ music

def bed_loop(seed: int, bars: int = 8) -> np.ndarray:
    """Looping kid-friendly groove (mono): marimba melody over I-V-vi-IV, bass, kick/clap/shaker."""
    rng = _rng(f"bed-{seed}")
    bar = 4 * BEAT
    buf = np.zeros(int(bars * bar * RATE) + RATE)
    for b in range(bars):
        c = b % 4
        t0 = b * bar
        for k in range(4):                                     # bass on 1 and 3, kick on 1/3, clap on 2/4
            if k in (0, 2):
                _add(buf, bass(BASS[c] + (12 if k == 2 and b % 2 else 0), 0.45, 0.55), t0 + k * BEAT)
                _add(buf, kick(0.5), t0 + k * BEAT)
            else:
                _add(buf, clap_hit(0.35), t0 + k * BEAT)
        for k in range(8):
            _add(buf, shaker(0.6 if k % 2 else 0.35), t0 + k * BEAT / 2)
        for k in range(8):                                     # melody: chord tones, some rests
            if rng.random() < 0.3:
                continue
            note = CHORDS[c][rng.integers(0, 3)] + 12
            _add(buf, marimba(note, 0.5, 0.45 + 0.2 * rng.random()), t0 + k * BEAT / 2)
        _add(buf, marimba(CHORDS[c][0], 1.2, 0.25), t0)   # soft chord root
    n = int(bars * bar * RATE)
    loop = buf[:n].copy()
    loop[: len(buf) - n] += buf[n:]                            # wrap tails so the loop is seamless
    return 0.9 * loop / (np.max(np.abs(loop)) or 1.0)


def sting(cue: str) -> np.ndarray:
    """Music cues (mono)."""
    if cue not in MUSIC_CUES:
        raise ValueError(f"unknown music cue {cue!r}")
    if cue == "theme_intro":
        buf = np.zeros(int(2.4 * RATE))
        for i, m in enumerate([60, 64, 67, 72, 76, 79]):
            _add(buf, marimba(m, 0.6, 0.9), i * BEAT / 2)
        _add(buf, kick(0.8), 0)
        _add(buf, kick(0.8), 3 * BEAT / 2)
        for m in (60, 64, 67, 72):
            _add(buf, marimba(m, 1.0, 0.7), 6 * BEAT / 2)
        _add(buf, clap_hit(0.8), 6 * BEAT / 2)
    elif cue == "title_sting":
        buf = np.zeros(int(3.0 * RATE))
        n = int(0.9 * RATE)
        swell = noise_burst("swell", 0.9, 10.0, hp=1.0, vel=0.35) * np.linspace(0, 1, n) ** 2
        _add(buf, swell, 0)
        for m in (55, 59, 62):
            _add(buf, marimba(m + 12, 0.25, 0.7), 0.55)
        for m in (48, 60, 64, 67, 72, 76):
            _add(buf, bell(m, 2.0, 0.45), 0.9)
        _add(buf, kick(1.0), 0.9)
        _add(buf, clap_hit(1.0), 0.9)
    elif cue == "idea_sting":
        buf = np.zeros(int(1.6 * RATE))
        for i, m in enumerate([72, 76, 79, 84, 88]):
            _add(buf, bell(m, 0.9, 0.6), i * 0.07)
    elif cue == "chant_beat":
        buf = np.zeros(int(3.2 * RATE))
        for k in range(8):
            _add(buf, kick(0.9), k * BEAT / 1.0) if k % 2 == 0 else _add(buf, clap_hit(0.9), k * BEAT)
            _add(buf, shaker(0.8), k * BEAT + BEAT / 2)
        for k, m in enumerate([36, 36, 43, 43, 45, 45, 41, 43]):
            _add(buf, bass(m, 0.35, 0.7), k * BEAT)
    elif cue == "victory_sting":
        buf = np.zeros(int(2.4 * RATE))
        for i, m in enumerate([67, 67, 67, 72]):
            d = 0.12 if i < 3 else 1.2
            _add(buf, marimba(m, 0.4 if i < 3 else 1.4, 0.9), i * 0.14)
            _add(buf, marimba(m - 5, 0.4 if i < 3 else 1.4, 0.5), i * 0.14 + 0 * d)
        for m in (60, 64, 67, 72):
            _add(buf, bell(m, 1.6, 0.35), 0.42)
        _add(buf, kick(1.0), 0.42)
        _add(buf, clap_hit(1.0), 0.42)
    else:  # outro
        buf = np.zeros(int(3.6 * RATE))
        seq = [(72, 0), (71, 1), (67, 2), (69, 3), (65, 4), (67, 5), (64, 6), (60, 8)]
        for m, k in seq:
            _add(buf, marimba(m, 0.7 if k < 8 else 1.6, 0.8), k * BEAT / 2)
        for k, m in enumerate([48, 43, 45, 41, 48]):
            _add(buf, bass(m, 0.6, 0.7), k * BEAT)
        for m in (48, 60, 64, 67, 72):
            _add(buf, bell(m, 1.8, 0.3), 8 * BEAT / 2)
    return 0.9 * buf / (np.max(np.abs(buf)) or 1.0)


# ------------------------------------------------------------------------------------------ sfx

def _sweep(f0: float, f1: float, dur: float, curve: str = "exp") -> np.ndarray:
    n = int(dur * RATE)
    u = np.linspace(0, 1, n)
    f = f0 * (f1 / f0) ** u if curve == "exp" else f0 + (f1 - f0) * u
    return np.sin(2 * np.pi * np.cumsum(f) / RATE)


def sfx(sid: str) -> np.ndarray:
    """Synthesised sound effect (mono, peak-normalised)."""
    if sid not in SFX_IDS:
        raise ValueError(f"unknown sfx {sid!r}")
    if sid == "zoom":
        n = int(1.0 * RATE)
        x = _sweep(300, 1400, 1.0) * np.sin(np.linspace(0, np.pi, n)) + noise_burst("zoom", 1.0, 10, hp=1, vel=0.3) * \
            np.sin(np.linspace(0, np.pi, n))
    elif sid == "bonk":
        x = _sweep(420, 140, 0.45) * _env(int(0.45 * RATE), 0.001, 0.12) + noise_burst("bonk", 0.45, 0.02, vel=0.6)
    elif sid == "boing":
        n = int(0.6 * RATE)
        t = _t(n)
        f = 220 * (1 + 0.5 * np.sin(2 * np.pi * 9 * t) * np.exp(-t / 0.3))
        x = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.002, 0.3)
    elif sid in ("pop", "toaster_pop"):
        x = _sweep(900, 300, 0.12) * _env(int(0.12 * RATE), 0.001, 0.03) + noise_burst(sid, 0.12, 0.01, vel=0.5)
        if sid == "toaster_pop":
            y = np.zeros(int(0.5 * RATE))
            _add(y, x, 0)
            _add(y, bell(84, 0.4, 0.4), 0.08)
            x = y
    elif sid == "ping":
        x = np.sin(2 * np.pi * 2093 * _t(int(0.35 * RATE))) * _env(int(0.35 * RATE), 0.002, 0.08)
    elif sid == "echo":
        x = np.sin(2 * np.pi * 2093 * _t(int(0.45 * RATE))) * _env(int(0.45 * RATE), 0.01, 0.1) * 0.6
    elif sid == "charge":
        n = int(1.2 * RATE)
        x = _sweep(120, 900, 1.2) * np.sign(np.sin(2 * np.pi * 25 * _t(n))) * 0.5 * np.linspace(0.3, 1, n)
    elif sid == "skid":
        n = int(0.8 * RATE)
        x = (_sweep(1800, 1200, 0.8) * 0.5 + noise_burst("skid", 0.8, 10, hp=0.8, vel=0.5)) * np.linspace(1, 0, n) ** 0.7
    elif sid == "whoosh":
        n = int(0.6 * RATE)
        x = noise_burst("whoosh", 0.6, 10, hp=0.3) * np.sin(np.linspace(0, np.pi, n)) ** 2
    elif sid == "clap":
        x = clap_hit(1.0)
        y = np.zeros(int(0.35 * RATE))
        _add(y, x, 0)
        _add(y, clap_hit(0.5), 0.02)
        x = y
    elif sid == "motor":
        n = int(1.5 * RATE)
        t = _t(n)
        x = np.sign(np.sin(2 * np.pi * (70 + 30 * t) * t)) * 0.4 * np.minimum(1, t / 0.2) * np.minimum(1, (1.5 - t) / 0.3)
    elif sid == "nib_beep":
        y = np.zeros(int(0.5 * RATE))
        for i, f in enumerate((1760, 2349, 1976)):
            _add(y, np.sign(np.sin(2 * np.pi * f * _t(int(0.09 * RATE)))) * 0.4 * _env(int(0.09 * RATE), 0.002, 0.08),
                 i * 0.12)
        x = y
    elif sid == "nib_whistle":
        n = int(0.9 * RATE)
        t = _t(n)
        f = 1500 + 700 * np.sin(np.pi * t / 0.9) + 60 * np.sin(2 * np.pi * 7 * t)
        x = np.sin(2 * np.pi * np.cumsum(f) / RATE) * _env(n, 0.02, 0.6)
    elif sid == "ding":
        x = bell(88, 0.8, 1.0)
    elif sid == "chalk":
        y = np.zeros(int(0.9 * RATE))
        for i in range(5):
            _add(y, noise_burst(f"chalk{i}", 0.12, 0.05, hp=0.9, vel=0.6), i * 0.17)
        x = y
    elif sid == "sparkle":
        y = np.zeros(int(0.9 * RATE))
        for i, m in enumerate((84, 88, 91, 96, 100)):
            _add(y, bell(m, 0.5, 0.5), i * 0.06)
        x = y
    elif sid == "page_flip":
        n = int(0.4 * RATE)
        x = noise_burst("page", 0.4, 10, hp=0.6) * np.sin(np.linspace(0, np.pi, n)) ** 3
    elif sid == "stars":
        y = np.zeros(int(1.2 * RATE))
        for i, m in enumerate((96, 91, 96, 91, 96)):
            _add(y, bell(m, 0.3, 0.4), i * 0.2)
        x = y
    else:
        raise ValueError(sid)
    x = np.asarray(x, dtype=np.float64)
    fade = min(len(x), int(0.005 * RATE))
    x[-fade:] *= np.linspace(1, 0, fade)
    return x / (np.max(np.abs(x)) or 1.0)


# ------------------------------------------------------------------------------------------ wav io + loudness

def read_wav_mono(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == RATE and w.getsampwidth() == 2, path
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768
        if w.getnchannels() == 2:
            x = x.reshape(-1, 2).mean(axis=1)
    return x


def write_wav(path: Path, x: np.ndarray) -> Path:
    """Stereo (n, 2) or mono float -> 16-bit PCM (deterministic rounding, hard clip at full scale)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = np.clip(np.round(x * 32767), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return path


def lufs(x: np.ndarray) -> float:
    """ITU-R BS.1770-4 integrated loudness (K-weighting, 400 ms blocks, absolute + relative gating)."""
    from scipy.signal import lfilter
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    # K-weighting for 48 kHz (BS.1770 coefficients)
    b1, a1 = [1.53512485958697, -2.69169618940638, 1.19839281085285], [1.0, -1.69065929318241, 0.73248077421585]
    b2, a2 = [1.0, -2.0, 1.0], [1.0, -1.99004745483398, 0.99007225036621]
    y = lfilter(b2, a2, lfilter(b1, a1, x, axis=0), axis=0)
    blk, hop = int(0.4 * RATE), int(0.1 * RATE)
    if len(y) < blk:
        return -math.inf
    p = np.array([np.sum(np.mean(y[i:i + blk] ** 2, axis=0)) for i in range(0, len(y) - blk + 1, hop)])
    lk = -0.691 + 10 * np.log10(np.maximum(p, 1e-12))
    p = p[lk > -70]
    if not len(p):
        return -math.inf
    rel = -0.691 + 10 * np.log10(np.mean(p)) - 10
    gated = p[(-0.691 + 10 * np.log10(np.maximum(p, 1e-12))) > rel]
    return float(-0.691 + 10 * np.log10(np.mean(gated)))


def db(x: float) -> float:
    return 10 ** (x / 20)


# ------------------------------------------------------------------------------------------ mix

def duck_envelope(n: int, windows: list[tuple[float, float]]) -> np.ndarray:
    """Gain (linear) for music: 1 outside speech, DUCK_DB inside, with linear-in-dB attack/release ramps."""
    g_db = np.zeros(n)
    t = _t(n)
    for a, b in windows:
        a0, b0 = a - DUCK_PRE_S, b + DUCK_HOLD_S
        att = np.clip((t - (a0 - DUCK_ATTACK_S)) / DUCK_ATTACK_S, 0, 1)
        rel = np.clip(((b0 + DUCK_RELEASE_S) - t) / DUCK_RELEASE_S, 0, 1)
        g_db = np.minimum(g_db, DUCK_DB * np.minimum(att, rel))
    return 10 ** (g_db / 20)


def _limit(in_wav: Path, out_wav: Path, gain_db: float) -> None:
    import subprocess
    lim = 10 ** (LIMIT_DBFS / 20)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(in_wav), "-af",
                    f"volume={gain_db:+.3f}dB,alimiter=limit={lim:.6f}:attack=5:release=50:level=0:latency=1",
                    "-c:a", "pcm_s16le", "-ar", str(RATE), "-ac", "2", "-bitexact", str(out_wav)], check=True)


def mix_episode(timing: dict, voice_dir: Path, out_dir: Path, log=print) -> dict:
    voice_dir, out_dir = Path(voice_dir), Path(out_dir)
    scenes = timing["scenes"]
    total_frames = sum(round(s["scene_duration_s"] * FPS) for s in scenes)
    n = total_frames * RATE // FPS
    dia = np.zeros(n)
    mus = np.zeros(n)
    fx = np.zeros(n)
    speech: list[tuple[float, float]] = []
    events = []
    t_scene = 0.0
    for idx, s in enumerate(scenes):
        frames = round(s["scene_duration_s"] * FPS)
        dur = frames / FPS
        stem = read_wav_mono(voice_dir / s["dialogue_wav"])[: int(dur * RATE)]
        _add(dia, stem, t_scene)
        # music: bed for the scene (fades in/out), muted while a sting plays
        loop = bed_loop(s["sequence"])
        reps = int(math.ceil(dur * RATE / len(loop))) + 1
        bed = np.tile(loop, reps)[: int(dur * RATE)]
        fade = int(0.6 * RATE)
        bed[:fade] *= np.linspace(0, 1, fade)
        bed[-fade:] *= np.linspace(1, 0, fade)
        bed_gain = np.ones(len(bed))
        stings = []
        for b in s["beats"]:
            if b["type"] == "line":
                speech.append((t_scene + b["start_s"], t_scene + b["end_s"]))
            elif b["type"] == "music":
                x = sting(b["cue"])
                stings.append((b["start_s"], b["start_s"] + len(x) / RATE, b["cue"]))
                _add(mus, x * db(STING_GAIN_DB), t_scene + b["start_s"])
                events.append({"type": "music", "id": b["cue"], "t": round(t_scene + b["start_s"], 3)})
            elif b["type"] == "sfx":
                x = sfx(b["id"]) * db(SFX_PEAK_DBFS + SFX_GAIN_DB.get(b["id"], 0))
                _add(fx, x, t_scene + b["start_s"])
                events.append({"type": "sfx", "id": b["id"], "t": round(t_scene + b["start_s"], 3),
                               "anchor": b.get("anchorMode")})
        tt = _t(len(bed))
        for a, b_, cue in stings:                                     # bed dips out around stings
            if cue == "chant_beat":
                continue
            dip = np.clip(np.minimum((tt - (a - 0.3)) / 0.3, ((b_ + 0.5) - tt) / 0.5), 0, 1)
            bed_gain = np.minimum(bed_gain, 1 - dip)
        if s["sceneId"] == scenes[0]["sceneId"] and any(c == "theme_intro" for *_, c in stings):
            first = min(a for a, _, c in stings if c == "theme_intro")
            bed_gain[: int((first + 2.0) * RATE)] = np.minimum(bed_gain[: int((first + 2.0) * RATE)], 0)
        _add(mus, bed * bed_gain * 0.55, t_scene)
        t_scene += dur
    # levels
    d_l = lufs(dia)
    g_dia = DIALOGUE_LUFS - d_l
    dia *= db(g_dia)
    m_l = lufs(mus)
    mus *= db(MUSIC_LUFS - m_l)
    env = duck_envelope(n, speech)
    mus_d = mus * env
    pre = dia + mus_d + fx
    trim = TARGET_LUFS - lufs(pre)
    out = out_dir / "audio"
    stems = out / "stems"
    write_wav(stems / "dialogue.wav", dia)
    write_wav(stems / "music.wav", mus_d)
    write_wav(stems / "sfx.wav", fx)
    # the premix may exceed full scale before the limiter: write it at -6 dB and compensate in the limiter gain
    pre_path = write_wav(out / "premix.wav", pre * 0.5)
    _limit(pre_path, out / "mix.wav", trim + 6.0206)
    pre_path.unlink()
    report = {"rate": RATE, "samples": n, "frames": total_frames, "duration_s": round(n / RATE, 6),
              "dialogueLufsRaw": round(d_l, 2), "dialogueGainDb": round(g_dia, 2), "musicLufsPreDuck": MUSIC_LUFS,
              "duckDb": DUCK_DB, "trimDb": round(trim, 2), "limitDbfs": LIMIT_DBFS, "speechWindows": len(speech),
              "events": events, "stems": {k: f"audio/stems/{k}.wav" for k in ("dialogue", "music", "sfx")},
              "mix": "audio/mix.wav"}
    (out / "mix.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    log(f"  mix: dialogue {d_l:.1f} -> {DIALOGUE_LUFS} LUFS, music {MUSIC_LUFS} LUFS ducked {DUCK_DB} dB, trim {trim:+.2f} dB")
    return report


# ------------------------------------------------------------------------------------------ mix QA

def _rms_db(x: np.ndarray) -> float:
    return 20 * math.log10(max(1e-9, float(np.sqrt(np.mean(x ** 2))) if len(x) else 1e-9))


def longest_silence_s(x: np.ndarray, floor_db: float = -50.0, win_s: float = 0.1) -> float:
    w = int(win_s * RATE)
    k = len(x) // w
    r = np.sqrt(np.mean(x[: k * w].reshape(k, w) ** 2, axis=1))
    quiet = 20 * np.log10(np.maximum(r, 1e-9)) < floor_db
    best = run = 0
    for q in quiet:
        run = run + 1 if q else 0
        best = max(best, run)
    return best * win_s


def check_mix(rep, out_dir: Path, timing: dict, licenses: dict | None = None) -> dict:
    """Mix QA gates (hard unless noted) on ``<out>/audio``; adds checks to ``rep`` (a QaReport)."""
    from robotics101.media import audio_levels
    out_dir = Path(out_dir)
    a = out_dir / "audio"
    lv = audio_levels(a / "mix.wav")
    dl = audio_levels(a / "stems" / "dialogue.wav")
    mix = read_wav_mono(a / "mix.wav")
    dia = read_wav_mono(a / "stems" / "dialogue.wav")
    mus = read_wav_mono(a / "stems" / "music.wav")
    frames = sum(round(s["scene_duration_s"] * FPS) for s in timing["scenes"])
    ratios, t0 = [], 0.0
    for s in timing["scenes"]:
        for b in s["beats"]:
            if b["type"] == "line":
                i, j = int((t0 + b["start_s"]) * RATE), int((t0 + b["end_s"]) * RATE)
                ratios.append(_rms_db(dia[i:j]) - _rms_db(mus[i:j]))
        t0 += round(s["scene_duration_s"] * FPS) / FPS
    gap = longest_silence_s(mix)
    res = {"integratedLufs": lv.integrated_lufs, "truePeakDbfs": lv.true_peak_dbfs, "lra": lv.loudness_range_lu,
           "dialogueLufs": dl.integrated_lufs, "dialogueOverMusicDbMin": round(min(ratios), 1),
           "dialogueOverMusicDbMedian": round(float(np.median(ratios)), 1), "longestSilenceS": round(gap, 2),
           "samples": len(mix), "expectedSamples": frames * RATE // FPS}
    rep.hard("mix.loudness", lv.integrated_lufs is not None and abs(lv.integrated_lufs - TARGET_LUFS) <= 1.0,
             f"mix {lv.integrated_lufs} LUFS (target {TARGET_LUFS} ±1)")
    rep.hard("mix.true_peak", lv.true_peak_dbfs is not None and lv.true_peak_dbfs <= -1.0,
             f"true peak {lv.true_peak_dbfs} dBFS (≤ -1.0)")
    rep.hard("mix.dialogue_level", dl.integrated_lufs is not None and abs(dl.integrated_lufs - DIALOGUE_LUFS) <= 0.5,
             f"dialogue stem {dl.integrated_lufs} LUFS (target {DIALOGUE_LUFS} ±0.5)")
    rep.hard("mix.ducking", min(ratios) >= 10.0,
             f"dialogue over music during lines: min {min(ratios):.1f} dB, median {np.median(ratios):.1f} dB (≥ 10)")
    rep.hard("mix.silence", gap <= 2.5, f"longest near-silence {gap:.1f} s (≤ 2.5)")
    rep.hard("mix.length", len(mix) == frames * RATE // FPS, f"{len(mix)} samples = {frames} frames × 1600")
    if licenses is not None:
        used_sfx = {b["id"] for s in timing["scenes"] for b in s["beats"] if b["type"] == "sfx"}
        used_mus = {b["cue"] for s in timing["scenes"] for b in s["beats"] if b["type"] == "music"}
        gen = licenses.get("generated", {})
        missing = sorted((used_sfx - set(gen.get("sfx", []))) | (used_mus - set(gen.get("music", []))))
        rep.hard("assets.licenses", not missing, "every sfx / music cue is generated in code and listed in "
                 "assets/LICENSES.json" if not missing else f"unlisted assets: {missing}")
    return res
