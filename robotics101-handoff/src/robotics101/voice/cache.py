"""Content-addressed cache of raw provider audio (M02.2) + ElevenLabs usage ledger (no secrets).

Layout (directory ``tts-cache/`` at the project root, gitignored; override with ``ROBOTICS101_TTS_CACHE``):
``<key[:2]>/<key>.<ext>`` raw audio, ``<key[:2]>/<key>.json`` metadata (provider, params, text, chars, time),
``<key[:2]>/<key>.alignment.json`` provider character alignment when the backend returns one (ElevenLabs
with-timestamps, M04.1; stored with the audio so a cached line still has word timings without re-billing),
``elevenlabs-ledger.jsonl`` one line per billed request (key, voiceId, modelId, chars, time).
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from robotics101.characters import PROJECT_ROOT
from robotics101.voice.backends import Backend, VoiceRequest

CACHE_ENV = "ROBOTICS101_TTS_CACHE"
DEFAULT_CACHE_DIR = PROJECT_ROOT / "tts-cache"
LEDGER = "elevenlabs-ledger.jsonl"


def cache_dir() -> Path:
    return Path(os.environ.get(CACHE_ENV) or DEFAULT_CACHE_DIR)


class VoiceCache:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or cache_dir())

    def path(self, req: VoiceRequest) -> Path:
        return self.root / req.key[:2] / f"{req.key}.{req.ext}"

    def alignment_path(self, req: VoiceRequest) -> Path:
        return self.root / req.key[:2] / f"{req.key}.alignment.json"

    def alignment(self, req: VoiceRequest) -> dict | None:
        p = self.alignment_path(req)
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None

    def has(self, req: VoiceRequest) -> bool:
        p = self.path(req)
        return p.is_file() and p.stat().st_size > 0

    def get_or_render(self, backend: Backend, req: VoiceRequest) -> tuple[Path, bool]:
        """Return (raw audio path, was_cached). Writes atomically so an interrupted call never poisons the cache."""
        p = self.path(req)
        if self.has(req):
            return p, True
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f"{req.key}.part.{req.ext}")
        extra = backend.render(req, tmp)
        os.replace(tmp, p)
        if isinstance(extra, dict) and extra.get("alignment"):
            self.alignment_path(req).write_text(json.dumps(extra["alignment"], ensure_ascii=False) + "\n",
                                                encoding="utf-8")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        meta = {"key": req.key, "provider": req.provider, "params": req.params, "text": req.text,
                "chars": req.chars, "createdAt": now, "bytes": p.stat().st_size}
        p.with_suffix(".json").write_text(json.dumps(meta, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        if backend.billable:
            with (self.root / LEDGER).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time": now, "key": req.key, "voiceId": req.params.get("voiceId"),
                                    "modelId": req.params.get("modelId"), "chars": req.chars}) + "\n")
        return p, False

    def ledger_chars(self) -> int:
        f = self.root / LEDGER
        if not f.is_file():
            return 0
        return sum(int(json.loads(l).get("chars", 0)) for l in f.read_text(encoding="utf-8").splitlines() if l)

    def copy_out(self, req: VoiceRequest, dst: Path) -> None:
        shutil.copyfile(self.path(req), dst)
