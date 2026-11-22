"""Lip sync (M02.4): mouth-shape cues per dialogue line via Rhubarb Lip Sync, with an RMS fallback.

Rhubarb Lip Sync (MIT, https://github.com/DanielSWolf/rhubarb-lip-sync) turns a WAV (+ the known dialogue text)
into timed mouth shapes A–H/X. We run its *phonetic* recogniser (≈5x faster than PocketSphinx, deterministic).
Binary: ``$RHUBARB_BIN`` or ``tools/rhubarb/rhubarb`` (gitignored; see README). Without it, ``rms_cues`` derives
open/closed shapes from loudness per frame so characters still lip-flap (lower quality, flagged in QA).
Results are cached in ``tts-cache/lipsync/`` keyed by the SHA-256 of the audio + text + method.
"""

from __future__ import annotations

import array
import hashlib
import json
import math
import os
import shutil
import subprocess
import tempfile
import wave
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from robotics101.characters import PROJECT_ROOT
from robotics101.voice.cache import cache_dir

RHUBARB_ENV = "RHUBARB_BIN"
DEFAULT_RHUBARB = PROJECT_ROOT / "tools" / "rhubarb" / "rhubarb"
METHOD_VERSION = 1
SHAPES = set("ABCDEFGHX")


@dataclass(frozen=True)
class MouthCue:
    start: float
    end: float
    shape: str


def find_rhubarb() -> str | None:
    for c in (os.environ.get(RHUBARB_ENV), str(DEFAULT_RHUBARB), shutil.which("rhubarb")):
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rms_cues(wav: Path, fps: int = 30) -> list[MouthCue]:
    """Fallback: per-frame RMS -> X (silence) / A / B / C / D by loudness relative to the line's peak frame."""
    with wave.open(str(wav), "rb") as w:
        rate, n = w.getframerate(), w.getnframes()
        a = array.array("h", w.readframes(n))
    hop = max(1, rate // fps)
    levels = []
    for i in range(0, len(a), hop):
        seg = a[i:i + hop]
        levels.append(math.sqrt(sum(x * x for x in seg) / len(seg)) if seg else 0.0)
    peak = max(levels, default=0.0) or 1.0
    cues: list[MouthCue] = []
    for i, lv in enumerate(levels):
        r = lv / peak
        shape = "X" if r < 0.06 else "A" if r < 0.15 else "B" if r < 0.35 else "C" if r < 0.65 else "D"
        t0, t1 = round(i / fps, 3), round((i + 1) / fps, 3)
        if cues and cues[-1].shape == shape:
            cues[-1] = MouthCue(cues[-1].start, t1, shape)
        else:
            cues.append(MouthCue(t0, t1, shape))
    return cues


def rhubarb_cues(wav: Path, text: str, binary: str) -> list[MouthCue]:
    with tempfile.TemporaryDirectory() as td:
        dlg = Path(td) / "dialog.txt"
        dlg.write_text(text, encoding="utf-8")
        p = subprocess.run([binary, "-q", "-f", "json", "-r", "phonetic", "--extendedShapes", "GHX", "-d", str(dlg),
                            str(wav)], capture_output=True, text=True, check=False, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"rhubarb failed ({p.returncode}): {p.stderr.strip()[:300]}")
    doc = json.loads(p.stdout)
    return [MouthCue(float(c["start"]), float(c["end"]), c["value"]) for c in doc["mouthCues"]
            if c["value"] in SHAPES]


def line_cues(wav: Path, text: str, *, prefer_rhubarb: bool = True) -> tuple[list[MouthCue], str]:
    """Cues for one line WAV (cached). Returns (cues, method) with method 'rhubarb' or 'rms'."""
    binary = find_rhubarb() if prefer_rhubarb else None
    method = "rhubarb" if binary else "rms"
    key = hashlib.sha256(json.dumps([METHOD_VERSION, method, _sha(wav), " ".join(text.split())]).encode()).hexdigest()
    cache = cache_dir() / "lipsync" / f"{key}.json"
    if cache.is_file():
        doc = json.loads(cache.read_text(encoding="utf-8"))
        return [MouthCue(*c) for c in doc["cues"]], doc["method"]
    cues = rhubarb_cues(wav, text, binary) if binary else rms_cues(wav)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"method": method, "cues": [[c.start, c.end, c.shape] for c in cues]}),
                     encoding="utf-8")
    return cues, method


class MouthTrack:
    """Mouth shape of one character over the episode/scene timeline (X when not talking)."""

    def __init__(self) -> None:
        self._starts: list[float] = []
        self._cues: list[MouthCue] = []

    def add_line(self, offset: float, cues: list[MouthCue]) -> None:
        for c in cues:
            self._cues.append(MouthCue(round(offset + c.start, 4), round(offset + c.end, 4), c.shape))
        self._cues.sort(key=lambda c: c.start)
        self._starts = [c.start for c in self._cues]

    def shape_at(self, t: float) -> str:
        i = bisect_right(self._starts, t) - 1
        if i >= 0 and self._cues[i].start <= t < self._cues[i].end:
            return self._cues[i].shape
        return "X"

    def talking_at(self, t: float) -> bool:
        return self.shape_at(t) != "X"

    @property
    def cues(self) -> list[MouthCue]:
        return list(self._cues)


def voiced_frames(wav: Path, fps: int = 30, rel_threshold: float = 0.2) -> list[bool]:
    """Per video frame: is the line audibly voiced (RMS >= rel_threshold x the line's loudest frame)?"""
    with wave.open(str(wav), "rb") as w:
        rate = w.getframerate()
        a = array.array("h", w.readframes(w.getnframes()))
    hop = rate / fps
    levels = []
    for i in range(int(len(a) / hop)):
        seg = a[int(i * hop):int((i + 1) * hop)]
        levels.append(math.sqrt(sum(x * x for x in seg) / len(seg)) if seg else 0.0)
    peak = max(levels, default=0.0) or 1.0
    return [lv / peak >= rel_threshold for lv in levels]


def lipsync_agreement(track: "MouthTrack", wav: Path, offset: float, fps: int = 30) -> float:
    """Share of voiced frames of a line during which the mouth is open (not X/A). ~1.0 = good sync."""
    voiced = voiced_frames(wav, fps)
    hits = total = 0
    for i, v in enumerate(voiced):
        if v:
            total += 1
            hits += track.shape_at(offset + (i + 0.5) / fps) not in ("X", "A")
    return hits / total if total else 1.0
