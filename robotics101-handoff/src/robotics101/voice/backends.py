"""Character voice backends (M02.2, SDK in M04.1): ElevenLabs (production) -> Kokoro -> espeak-ng [+ fixture].

Every backend turns (character voice config, text) into a deterministic ``VoiceRequest`` whose SHA-256 is the
cache key; ``render`` writes the provider's raw audio. Raw output is cached by that key (``cache.py``), so a
rerun never re-synthesizes — and never re-bills ElevenLabs — for a line whose text/voice/model/settings are unchanged.

ElevenLabs (M04.1): the official ``elevenlabs`` Python SDK, ``text_to_speech.convert_with_timestamps`` (audio +
character alignment in one billed call) with ``eleven_v4`` by default. The API key comes from ``ELEVENLABS_API_KEY``;
if it is not exported, ``load_env`` loads the project's gitignored ``.env`` with python-dotenv (path overridable
with ``ROBOTICS101_DOTENV``; tests point it at a missing file). The key is read at call time only and is never
stored on objects, written to disk, logged, put in a cache key/metadata/manifest, or echoed in an error (errors
pass through ``redact``). The SDK client factory is injectable so tests never touch the network.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from robotics101.characters import PROJECT_ROOT

CACHE_FORMAT = 1
KEY_ENV = "ELEVENLABS_API_KEY"
DOTENV_ENV = "ROBOTICS101_DOTENV"
DEFAULT_DOTENV = PROJECT_ROOT / ".env"
EL_DEFAULT_MODEL = "eleven_v4"           # best-quality TTS model; supports /with-timestamps
EL_OUTPUT_FORMAT = "mp3_44100_192"       # Creator+ plans
EL_SEED = 101                            # ElevenLabs best-effort determinism
# voice_settings each model family accepts (Eleven v4: stability + similarity_boost only; pace/emotion via text)
EL_V4_SETTINGS = ("stability", "similarity_boost")
EL_ALL_SETTINGS = ("stability", "similarity_boost", "style", "use_speaker_boost", "speed")
EL_RETRY_STATUS = (429, 500, 502, 503, 504)
KOKORO_DIR_ENV = "ROBOTICS101_KOKORO_DIR"
DEFAULT_KOKORO_DIR = PROJECT_ROOT / "models" / "kokoro"
KOKORO_MODEL, KOKORO_VOICES = "kokoro-v1.0.onnx", "voices-v1.0.bin"


def load_env() -> bool:
    """Load the project ``.env`` (never overriding an exported variable). Returns True if the key is now set."""
    if not os.environ.get(KEY_ENV):
        path = Path(os.environ.get(DOTENV_ENV) or DEFAULT_DOTENV)
        if path.is_file():
            try:
                from dotenv import load_dotenv
            except ImportError:            # pragma: no cover - dependency of the project
                return False
            load_dotenv(path, override=False)
    return bool(os.environ.get(KEY_ENV))


def el_settings_for(model_id: str) -> tuple[str, ...]:
    return EL_V4_SETTINGS if str(model_id).startswith("eleven_v4") else EL_ALL_SETTINGS


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

ClientFactory = Callable[[], Any]


def _sdk_client() -> Any:
    """Official SDK client. The key is passed from the environment at call time and not kept anywhere else."""
    from elevenlabs import ElevenLabs
    return ElevenLabs(api_key=os.environ[KEY_ENV])


def _status(e: Exception) -> int | None:
    code = getattr(e, "status_code", None)
    return int(code) if isinstance(code, int) else None


def words_from_alignment(al: dict | None) -> list[dict]:
    """Character alignment -> words [{text, start_s, end_s}] (audio tags like ``[laughs]`` are skipped)."""
    if not al:
        return []
    chars = al.get("characters") or []
    st, en = al.get("character_start_times_seconds") or [], al.get("character_end_times_seconds") or []
    words, cur, t0, t1, tag = [], "", None, None, 0
    for ch, a, b in zip(chars, st, en):
        if ch == "[":
            tag += 1
        if tag or ch.isspace():
            if cur:
                words.append({"text": cur, "start_s": round(t0, 3), "end_s": round(t1, 3)})
            cur, t0 = "", None
            if ch == "]" and tag:
                tag -= 1
            continue
        if t0 is None:
            t0 = a
        cur, t1 = cur + ch, b
    if cur:
        words.append({"text": cur, "start_s": round(t0, 3), "end_s": round(t1, 3)})
    return words


@dataclass
class ElevenLabsBackend(Backend):
    name: str = "elevenlabs"
    label: str = "ElevenLabs TTS (production voice)"
    is_production: bool = True
    billable: bool = True
    client_factory: ClientFactory | None = field(default=None, repr=False)   # None = official SDK (per call)
    timeout_s: float = 120.0
    retries: int = 3

    def available(self) -> tuple[bool, str]:
        if not load_env():
            return False, f"{KEY_ENV} is not set (environment or project .env)"
        return True, "API key present (environment or project .env)"

    def request(self, voice: dict, text: str) -> VoiceRequest:
        cfg = self.config(voice)
        model = cfg.get("modelId") or EL_DEFAULT_MODEL
        s = cfg.get("settings") or {}
        settings = {k: s[k] for k in el_settings_for(model) if k in s}
        return VoiceRequest(self.name, {"voiceId": cfg["voiceId"], "modelId": model, "settings": settings,
                                        "outputFormat": EL_OUTPUT_FORMAT, "seed": EL_SEED, "timestamps": True},
                            text, ext="mp3")

    def _client(self) -> Any:
        if not load_env():
            raise VoiceError(f"{KEY_ENV} is not set; no ElevenLabs call was made")
        return (self.client_factory or _sdk_client)()

    def _call(self, what: str, fn: Callable[[Any], Any]) -> Any:
        client = self._client()
        last = ""
        for attempt in range(self.retries):
            try:
                return fn(client)
            except Exception as e:                                       # noqa: BLE001 - SDK/httpx errors
                code = _status(e)
                body = getattr(e, "body", None)
                last = f"HTTP {code}: {str(body)[:300]}" if code else f"{type(e).__name__}: {str(e)[:300]}"
                if code is not None and code not in EL_RETRY_STATUS:
                    break
            time.sleep(min(8.0, 1.5 * 2 ** attempt))
        raise VoiceError(redact(f"ElevenLabs {what} failed: {last}"))

    def render(self, req: VoiceRequest, out_path: Path) -> dict:
        """One billed call: audio (written to ``out_path``) + character alignment (returned for the cache)."""
        from elevenlabs import VoiceSettings
        p = req.params

        def go(c):
            return c.text_to_speech.convert_with_timestamps(
                p["voiceId"], text=req.text, model_id=p["modelId"], output_format=p["outputFormat"],
                voice_settings=VoiceSettings(**p["settings"]) if p["settings"] else None, seed=p["seed"],
                request_options={"timeout_in_seconds": int(self.timeout_s), "max_retries": 0})
        resp = self._call("text-to-speech/with-timestamps", go)
        audio = base64.b64decode(getattr(resp, "audio_base_64", None) or getattr(resp, "audio_base64", "") or "")
        if len(audio) < 256:
            raise VoiceError(f"ElevenLabs returned {len(audio)} bytes of audio for {req.chars} chars")
        Path(out_path).write_bytes(audio)
        al = getattr(resp, "alignment", None)
        al = al.model_dump() if hasattr(al, "model_dump") else al
        return {"alignment": al} if al else {}

    # -- non-speech account calls (no character credits)
    def list_voices(self) -> list[dict]:
        r = self._call("voices", lambda c: c.voices.get_all())
        return [{"voiceId": v.voice_id, "name": v.name, "category": v.category, "labels": dict(v.labels or {}),
                 "previewUrl": getattr(v, "preview_url", None)} for v in r.voices]

    def subscription(self) -> dict:
        s = self._call("user/subscription", lambda c: c.user.subscription.get())
        d = s.model_dump() if hasattr(s, "model_dump") else dict(s)
        keep = ("tier", "status", "character_count", "character_limit", "next_character_count_reset_unix")
        out = {k: d.get(k) for k in keep}
        if out["character_limit"] is not None and out["character_count"] is not None:
            out["remaining"] = int(out["character_limit"]) - int(out["character_count"])
        return out

    def models(self) -> list[dict]:
        ms = self._call("models", lambda c: c.models.list())
        out = []
        for m in ms:
            d = m.model_dump() if hasattr(m, "model_dump") else dict(m)
            if d.get("can_do_text_to_speech"):
                out.append({"modelId": d.get("model_id"), "name": d.get("name"),
                            "costMultiplier": (d.get("model_rates") or {}).get("character_cost_multiplier")})
        return out


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


TRIM_THRESHOLD_DBFS, TRIM_KEEP_S = -45.0, 0.03


def leading_trim_s(wav: Path) -> float:
    """Seconds the edge-silence trim removes from the start of ``wav`` (ffmpeg silenceremove keeps
    ``TRIM_KEEP_S`` of the silence), so provider word timings can be shifted onto the trimmed line audio."""
    import array
    with wave.open(str(wav), "rb") as r:
        rate, a = r.getframerate(), array.array("h", r.readframes(r.getnframes()))
    lim = 32768 * 10 ** (TRIM_THRESHOLD_DBFS / 20)
    first = next((i for i, x in enumerate(a) if abs(x) > lim), 0)
    return max(0.0, first / rate - TRIM_KEEP_S)


def decode_to_wav(src: Path, dst: Path, fx: list[str], rate: int = 48_000) -> float:
    """Raw provider audio -> 48 kHz mono s16 WAV: optional sox fx, edge-silence trim, -3 dBFS peak normalise.
    Returns the (approximate) seconds trimmed from the start."""
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
        lead = leading_trim_s(mid)
        trim = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03,"
                "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,areverse")
        tmp = Path(td) / "trim.wav"
        run = subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(mid), "-af", trim, "-ac", "1", "-ar", str(rate),
                              "-c:a", "pcm_s16le", str(tmp)], capture_output=True, text=True, check=False)
        if run.returncode != 0:
            raise VoiceError(f"ffmpeg trim failed: {run.stderr.strip()[:300]}")
        _peak_normalise(tmp, Path(dst), target_dbfs=-3.0)
        return round(lead, 4)


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
