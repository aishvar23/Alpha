"""TTS provider interface and local providers.

Every result carries a human-readable `label` and `is_synthetic_placeholder` so that
downstream QA/review can never mistake placeholder or offline synthetic audio for
production narration.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

SAMPLE_RATE = 48_000
WORDS_PER_MINUTE = 150

ESPEAK_LABEL = "offline synthetic TTS (espeak-ng) — not production narration"
FIXTURE_LABEL = "FIXTURE placeholder audio — not narration"


class TtsError(RuntimeError):
    """Provider misconfigured, missing binary, or synthesis failed."""


@dataclass(frozen=True)
class NarrationResult:
    path: Path
    duration_s: float
    provider: str
    is_synthetic_placeholder: bool
    label: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["path"] = str(self.path)
        return d


class TtsProvider(Protocol):
    name: str

    def synthesize(self, text: str, out_wav: Path) -> NarrationResult: ...


def probe_duration(path: Path) -> float:
    """Audio duration in seconds via ffprobe; falls back to the `wave` header if ffprobe is absent."""
    if shutil.which("ffprobe"):
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, check=False,
        )
        if proc.returncode != 0:
            raise TtsError(f"ffprobe failed on {path}: {proc.stderr.strip()}")
        return float(json.loads(proc.stdout)["format"]["duration"])
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def estimate_speech_seconds(text: str, wpm: int = WORDS_PER_MINUTE) -> float:
    words = len(text.split())
    return round(max(1, words) * 60.0 / wpm, 3)


class FixtureProvider:
    """Deterministic placeholder: quiet 440 Hz beeps (one per word) for the estimated speech length.

    Pure Python; needs no external binaries. Clearly NOT narration.
    """

    name = "fixture"

    def synthesize(self, text: str, out_wav: Path) -> NarrationResult:
        out_wav = Path(out_wav)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        duration = estimate_speech_seconds(text)
        n = int(round(duration * SAMPLE_RATE))
        words = max(1, len(text.split()))
        beat = n / words  # one beep per word: 60% tone, 40% gap
        amp = int(0.1 * 32767)  # ~ -20 dBFS peak
        frames = bytearray()
        for i in range(n):
            on = (i % beat) < 0.6 * beat
            s = int(amp * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)) if on else 0
            frames += struct.pack("<h", s)
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(frames))
        return NarrationResult(out_wav, round(n / SAMPLE_RATE, 3), self.name, True, FIXTURE_LABEL)


class EspeakProvider:
    """Offline espeak-ng voice, resampled by ffmpeg to 48 kHz mono s16 WAV."""

    name = "espeak"

    def __init__(self, voice: str = "en-us", wpm: int = WORDS_PER_MINUTE):
        self.voice, self.wpm = voice, wpm

    @staticmethod
    def available() -> bool:
        return bool(shutil.which("espeak-ng") and shutil.which("ffmpeg"))

    def synthesize(self, text: str, out_wav: Path) -> NarrationResult:
        if not self.available():
            raise TtsError("espeak provider needs `espeak-ng` and `ffmpeg` on PATH "
                           "(apt install espeak-ng ffmpeg), or use --provider fixture")
        out_wav = Path(out_wav)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as td:
            raw = Path(td) / "raw.wav"
            # text via stdin: no shell, no argument injection
            p = subprocess.run(["espeak-ng", "-v", self.voice, "-s", str(self.wpm), "-w", str(raw)],
                               input=text, text=True, capture_output=True, check=False)
            if p.returncode != 0 or not raw.exists():
                raise TtsError(f"espeak-ng failed: {p.stderr.strip()}")
            p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-ar", str(SAMPLE_RATE),
                                "-ac", "1", "-c:a", "pcm_s16le", str(out_wav)],
                               capture_output=True, text=True, check=False)
            if p.returncode != 0:
                raise TtsError(f"ffmpeg resample failed: {p.stderr.strip()}")
        return NarrationResult(out_wav, round(probe_duration(out_wav), 3), self.name, True, ESPEAK_LABEL)


class ExternalProvider:
    """Hook for a future paid/cloud TTS. Intentionally makes no network calls in M01."""

    name = "external"
    REQUIRED_ENV = ("TTS_EXTERNAL_URL", "TTS_EXTERNAL_API_KEY")

    def __init__(self) -> None:
        missing = [k for k in self.REQUIRED_ENV if not os.environ.get(k)]
        if missing:
            raise TtsError(f"TTS_PROVIDER=external requires env {', '.join(missing)}; "
                           "use espeak or fixture for local runs")

    def synthesize(self, text: str, out_wav: Path) -> NarrationResult:
        raise TtsError("external TTS provider is a stub in M01 (no API calls are made); "
                       "use espeak or fixture")


PROVIDERS = {"espeak": EspeakProvider, "fixture": FixtureProvider, "external": ExternalProvider}
DEFAULT_PROVIDER = "espeak"


def get_provider(name: str | None = None) -> TtsProvider:
    """Explicit name > env TTS_PROVIDER > espeak."""
    name = (name or os.environ.get("TTS_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
    if name not in PROVIDERS:
        raise TtsError(f"unknown TTS provider {name!r}; choose one of {sorted(PROVIDERS)}")
    return PROVIDERS[name]()
