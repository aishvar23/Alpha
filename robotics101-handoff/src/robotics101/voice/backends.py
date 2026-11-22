"""Character voice backends (M02.2): ElevenLabs (production) -> Kokoro (local) -> espeak-ng (local) [+ fixture].

Every backend turns (character voice config, text) into a deterministic ``VoiceRequest`` whose SHA-256 is the
cache key; ``render`` writes the provider's raw audio. Raw output is cached by that key (``cache.py``), so a
rerun never re-synthesizes — and never re-bills ElevenLabs — for a line whose text/voice/settings are unchanged.

ElevenLabs security rules: the API key is read from ``ELEVENLABS_API_KEY`` at call time only. It is never
stored on objects, written to disk, logged, put in a cache key/metadata/manifest, or echoed in an error
(errors are passed through ``redact``). Only stdlib ``urllib`` is used; the transport is injectable for tests.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from robotics101.characters import PROJECT_ROOT

CACHE_FORMAT = 1
KEY_ENV = "ELEVENLABS_API_KEY"
API_BASE = "https://api.elevenlabs.io"
EL_OUTPUT_FORMAT = "mp3_44100_128"
EL_SEED = 101                       # ElevenLabs best-effort determinism
KOKORO_DIR_ENV = "ROBOTICS101_KOKORO_DIR"
DEFAULT_KOKORO_DIR = PROJECT_ROOT / "models" / "kokoro"
KOKORO_MODEL, KOKORO_VOICES = "kokoro-v1.0.onnx", "voices-v1.0.bin"


class VoiceError(RuntimeError):
    """Backend unavailable/misconfigured, budget exceeded, or synthesis failed."""


def redact(text: str) -> str:
    key = os.environ.get(KEY_ENV)
    text = str(text)
    if key and len(key) >= 4:
        text = text.replace(key, "[REDACTED]")
    return text


@dataclass(frozen=True)
class VoiceRequest:
    provider: str
    params: dict
    text: str
    ext: str = "wav"                 # raw file extension produced by the backend

    @property
    def key(self) -> str:
        blob = json.dumps({"format": CACHE_FORMAT, "provider": self.provider, "params": self.params,
                           "text": self.text}, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class Backend:
    name: str = ""
    label: str = ""
    is_production: bool = False
    billable: bool = False

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def config(self, voice: dict) -> dict:
        cfg = voice.get(self.name)
        if not isinstance(cfg, dict):
            raise VoiceError(f"character voice has no {self.name!r} config")
        return cfg

    def fx(self, voice: dict) -> list[str]:
        cfg = voice.get(self.name) or {}
        return list(cfg["fx"]) if "fx" in cfg else list(voice.get("fx") or [])

    def request(self, voice: dict, text: str) -> VoiceRequest:
        raise NotImplementedError

    def render(self, req: VoiceRequest, out_path: Path) -> None:
        raise NotImplementedError


# ------------------------------------------------------------------------------------------ ElevenLabs

Transport = Callable[[urllib.request.Request, float], bytes]


def _urllib_transport(req: urllib.request.Request, timeout: float) -> bytes:
    with urllib.request.urlopen(req, timeout=timeout) as resp:      # noqa: S310 (fixed https host)
        return resp.read()


@dataclass
class ElevenLabsBackend(Backend):
    name: str = "elevenlabs"
    label: str = "ElevenLabs TTS (production voice)"
    is_production: bool = True
    billable: bool = True
    transport: Transport | None = field(default=None, repr=False)   # None = stdlib urllib (looked up per call)
    timeout_s: float = 60.0
    retries: int = 3

    def available(self) -> tuple[bool, str]:
        if not os.environ.get(KEY_ENV):
            return False, f"{KEY_ENV} is not set"
        return True, "API key present in environment"

    def request(self, voice: dict, text: str) -> VoiceRequest:
        cfg = self.config(voice)
        s = cfg.get("settings") or {}
        settings = {k: s[k] for k in ("stability", "similarity_boost", "style", "use_speaker_boost", "speed")
                    if k in s}
        return VoiceRequest(self.name, {"voiceId": cfg["voiceId"], "modelId": cfg["modelId"],
                                        "settings": settings, "outputFormat": EL_OUTPUT_FORMAT, "seed": EL_SEED},
                            text, ext="mp3")

    def _call(self, method: str, path: str, body: dict | None = None, accept: str = "application/json") -> bytes:
        key = os.environ.get(KEY_ENV)
        if not key:
            raise VoiceError(f"{KEY_ENV} is not set; no ElevenLabs call was made")
        data = json.dumps(body).encode("utf-8") if body is not None else None
        last = ""
        for attempt in range(self.retries):
            req = urllib.request.Request(API_BASE + path, data=data, method=method,
                                         headers={"xi-api-key": key, "Accept": accept,
                                                  "Content-Type": "application/json"})
            try:
                return (self.transport or _urllib_transport)(req, self.timeout_s)
            except urllib.error.HTTPError as e:
                try:
                    detail = e.read()[:300].decode("utf-8", "replace")
                except Exception:                                      # noqa: BLE001
                    detail = ""
                last = f"HTTP {e.code}: {detail}"
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = f"{type(e).__name__}: {e}"
            time.sleep(min(8.0, 1.5 * 2 ** attempt))
        raise VoiceError(redact(f"ElevenLabs {method} {path.split('?')[0]} failed: {last}"))

    def render(self, req: VoiceRequest, out_path: Path) -> None:
        p = req.params
        body = {"text": req.text, "model_id": p["modelId"], "voice_settings": p["settings"], "seed": p["seed"]}
        audio = self._call("POST", f"/v1/text-to-speech/{p['voiceId']}?output_format={p['outputFormat']}",
                           body, accept="audio/mpeg")
        if len(audio) < 256:
            raise VoiceError(f"ElevenLabs returned {len(audio)} bytes of audio for {req.chars} chars")
        Path(out_path).write_bytes(audio)

    def list_voices(self) -> list[dict]:
        """GET /v1/voices (free: no character credits)."""
        doc = json.loads(self._call("GET", "/v1/voices"))
        return [{"voiceId": v.get("voice_id"), "name": v.get("name"), "category": v.get("category"),
                 "labels": v.get("labels") or {}, "previewUrl": v.get("preview_url")}
                for v in doc.get("voices", [])]


# ------------------------------------------------------------------------------------------ Kokoro

_KOKORO_CACHE: dict[str, object] = {}


def kokoro_dir() -> Path:
    return Path(os.environ.get(KOKORO_DIR_ENV) or DEFAULT_KOKORO_DIR)


@dataclass
class KokoroBackend(Backend):
    name: str = "kokoro"
    label: str = "Kokoro-82M local TTS (Apache-2.0) — offline fallback, not the production voice"

    def available(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
            import soundfile  # noqa: F401
        except ImportError:
            return False, "python packages kokoro-onnx + soundfile not installed (pip install '.[kokoro]')"
        d = kokoro_dir()
        missing = [n for n in (KOKORO_MODEL, KOKORO_VOICES) if not (d / n).is_file()]
        if missing:
            return False, f"Kokoro model files missing in {d}: {missing} (see README: Kokoro fallback)"
        return True, f"model in {d}"

    def request(self, voice: dict, text: str) -> VoiceRequest:
        cfg = self.config(voice)
        d = kokoro_dir()
        sizes = {n: (d / n).stat().st_size if (d / n).is_file() else None for n in (KOKORO_MODEL, KOKORO_VOICES)}
        return VoiceRequest(self.name, {"voice": cfg["voice"], "speed": cfg.get("speed", 1.0), "lang": "en-us",
                                        "model": KOKORO_MODEL, "modelBytes": sizes}, text)

    def render(self, req: VoiceRequest, out_path: Path) -> None:
        ok, why = self.available()
        if not ok:
            raise VoiceError(f"kokoro unavailable: {why}")
        import soundfile as sf
        from kokoro_onnx import Kokoro

        d = str(kokoro_dir())
        if d not in _KOKORO_CACHE:
            _KOKORO_CACHE[d] = Kokoro(str(kokoro_dir() / KOKORO_MODEL), str(kokoro_dir() / KOKORO_VOICES))
        samples, sr = _KOKORO_CACHE[d].create(req.text, voice=req.params["voice"], speed=req.params["speed"],
                                              lang=req.params["lang"])
        sf.write(str(out_path), samples, sr, format="WAV", subtype="PCM_16")


# ------------------------------------------------------------------------------------------ espeak / fixture

@dataclass
class EspeakBackend(Backend):
    name: str = "espeak"
    label: str = "espeak-ng offline synthetic voice — placeholder, not the production voice"

    def available(self) -> tuple[bool, str]:
        return (True, "espeak-ng on PATH") if shutil.which("espeak-ng") else (False, "espeak-ng not on PATH")

    def request(self, voice: dict, text: str) -> VoiceRequest:
        cfg = self.config(voice)
        return VoiceRequest(self.name, {"voice": cfg["voice"], "pitch": cfg.get("pitch", 50),
                                        "speed": cfg.get("speed", 160)}, text)

    def render(self, req: VoiceRequest, out_path: Path) -> None:
        p = req.params
        proc = subprocess.run(["espeak-ng", "-v", p["voice"], "-p", str(p["pitch"]), "-s", str(p["speed"]),
                               "-w", str(out_path)], input=req.text, text=True, capture_output=True, check=False)
        if proc.returncode != 0 or not Path(out_path).is_file():
            raise VoiceError(f"espeak-ng failed: {proc.stderr.strip()}")


@dataclass
class FixtureBackend(Backend):
    """Deterministic test tone: one short beep per word at a character-specific pitch (no binaries)."""

    name: str = "fixture"
    label: str = "FIXTURE placeholder tones — not speech"

    def available(self) -> tuple[bool, str]:
        return True, "built in"

    def config(self, voice: dict) -> dict:
        return voice.get("espeak") or {}

    def request(self, voice: dict, text: str) -> VoiceRequest:
        return VoiceRequest(self.name, {"pitch": self.config(voice).get("pitch", 50)}, text)

    def render(self, req: VoiceRequest, out_path: Path) -> None:
        rate, words = 24_000, max(1, len(req.text.split()))
        per_word = int(0.36 * rate)
        freq = 200 + 4 * float(req.params["pitch"])
        frames = bytearray()
        for i in range(words * per_word):
            on = (i % per_word) < 0.7 * per_word
            frames += struct.pack("<h", int(9000 * math.sin(2 * math.pi * freq * i / rate)) if on else 0)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))


BACKENDS: dict[str, type[Backend]] = {"elevenlabs": ElevenLabsBackend, "kokoro": KokoroBackend,
                                      "espeak": EspeakBackend, "fixture": FixtureBackend}
AUTO_ORDER = ("elevenlabs", "kokoro", "espeak")


def select_backend(choice: str | None = "auto") -> tuple[Backend, list[str]]:
    """``auto``: ElevenLabs if the key is set, else Kokoro, else espeak. Returns (backend, reasons for skips)."""
    choice = (choice or "auto").strip().lower()
    if choice != "auto":
        if choice not in BACKENDS:
            raise VoiceError(f"unknown voice backend {choice!r}; choose auto or one of {sorted(BACKENDS)}")
        b = BACKENDS[choice]()
        ok, why = b.available()
        if not ok:
            raise VoiceError(f"voice backend {choice} unavailable: {why}")
        return b, []
    skipped = []
    for name in AUTO_ORDER:
        b = BACKENDS[name]()
        ok, why = b.available()
        if ok:
            return b, skipped
        skipped.append(f"{name}: {why}")
    raise VoiceError("no voice backend available: " + "; ".join(skipped))


def decode_to_wav(src: Path, dst: Path, fx: list[str], rate: int = 48_000) -> None:
    """Raw provider audio -> 48 kHz mono s16 WAV: optional sox fx, edge-silence trim, -3 dBFS peak normalise."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VoiceError("ffmpeg is required to decode voice audio")
    with tempfile.TemporaryDirectory() as td:
        mid = Path(td) / "mid.wav"
        run = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(src), "-ac", "1", "-ar", str(rate),
                              "-c:a", "pcm_s16le", str(mid)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            raise VoiceError(f"ffmpeg decode failed for {src.name}: {run.stderr.strip()[:300]}")
        if fx:
            sox = shutil.which("sox")
            if not sox:
                raise VoiceError("sox is required for character voice fx (apt install sox)")
            fxd = Path(td) / "fx.wav"
            run = subprocess.run([sox, "-R", "-D", str(mid), str(fxd), *fx, "rate", str(rate)], capture_output=True,
                                 text=True, check=False)
            if run.returncode != 0:
                raise VoiceError(f"sox fx {fx} failed: {run.stderr.strip()[:300]}")
            mid = fxd
        trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
                "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
        tmp = Path(td) / "trim.wav"
        run = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(mid), "-af", trim, "-ac", "1", "-ar", str(rate),
                              "-c:a", "pcm_s16le", str(tmp)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            raise VoiceError(f"ffmpeg trim failed: {run.stderr.strip()[:300]}")
        _peak_normalise(tmp, Path(dst), target_dbfs=-3.0)


def _peak_normalise(src: Path, dst: Path, target_dbfs: float) -> None:
    import array

    with wave.open(str(src), "rb") as r:
        params, raw = r.getparams(), r.readframes(r.getnframes())
    a = array.array("h", raw)
    peak = max((abs(x) for x in a), default=0)
    if peak:
        g = (32767 * 10 ** (target_dbfs / 20)) / peak
        a = array.array("h", (max(-32768, min(32767, int(round(x * g)))) for x in a))
    with wave.open(str(dst), "wb") as w:
        w.setparams(params)
        w.writeframes(a.tobytes())
