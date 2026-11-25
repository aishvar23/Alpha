"""Dialogue QA (M02.2): checks on a voiced cartoon bundle (``timing.json`` v2 + line WAVs + captions)."""

from __future__ import annotations

import array
import json
import math
import os
import wave
from pathlib import Path

from robotics101.narration.captions import parse_srt, validate_srt
from robotics101.voice.backends import KEY_ENV

MIN_LINE_S = 0.25
WPS_HARD = (0.8, 7.0)     # outside: truncated / garbled / stuck TTS
WPS_SOFT = (1.2, 5.0)     # outside: rushed or dragging delivery (lines of >= 4 words)
MIN_SCENE_COVERAGE = 0.40
TOTAL_RANGE_S = (270.0, 420.0)          # default only; see validation.episode_duration_range (ADR-034)
SCENE_TARGET_TOLERANCE = 0.40
SILENT_DBFS = -45.0
SECRET_SCAN_SUFFIXES = {".json", ".srt", ".md", ".txt", ".log", ".jsonl"}


def _rms_dbfs(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        a = array.array("h", w.readframes(w.getnframes()))
    if not a:
        return -120.0
    rms = math.sqrt(sum(x * x for x in a) / len(a))
    return 20 * math.log10(rms / 32768) if rms else -120.0


def secret_leaks(roots: list[Path]) -> list[str]:
    """Files under ``roots`` that contain the ElevenLabs key value (only checked when the key is set)."""
    key = os.environ.get(KEY_ENV)
    if not key or len(key) < 8:
        return []
    hits = []
    for root in roots:
        if not Path(root).exists():
            continue
        for p in Path(root).rglob("*"):
            if p.is_file() and (p.suffix in SECRET_SCAN_SUFFIXES or p.suffix == ""):
                try:
                    if key in p.read_text(encoding="utf-8", errors="ignore"):
                        hits.append(str(p))
                except OSError:
                    pass
    return hits


def check_dialogue(rep, out_dir: Path, extra_secret_roots: list[Path] | None = None) -> dict | None:
    """Append dialogue checks to a ``robotics101.qa.QaReport``. Returns the timing doc (or None)."""
    out_dir = Path(out_dir)
    try:
        doc = json.loads((out_dir / "timing.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rep.hard("dialogue.timing", False, "timing.json (v2) missing or unreadable — run `robotics101 voice`")
        return None
    if not rep.hard("dialogue.timing", doc.get("schemaVersion") == "robotics101.timing/2",
                    f"timing.json schema {doc.get('schemaVersion')}"):
        return doc

    providers = set()
    bad_lines, word_rate, pace, silent = [], [], [], []
    for s in doc["scenes"]:
        prev_end = 0.0
        for b in s["beats"]:
            if b["type"] != "line":
                continue
            wav = out_dir / b["wav"]
            providers.add(doc["provider"])
            if not wav.is_file() or b["audio_s"] < MIN_LINE_S:
                bad_lines.append(f"{s['sceneId']}#{b['index']}")
                continue
            if _rms_dbfs(wav) < SILENT_DBFS:
                silent.append(f"{s['sceneId']}#{b['index']}")
            words = len(b["text"].split())
            wps = words / b["audio_s"]
            if doc["provider"] != "fixture":
                if wps > WPS_HARD[1] or (words >= 4 and wps < WPS_HARD[0]):
                    word_rate.append(f"{s['sceneId']}#{b['index']} {wps:.1f} w/s")
                elif words >= 4 and not (WPS_SOFT[0] <= wps <= WPS_SOFT[1]):
                    pace.append(f"{s['sceneId']}#{b['index']} {wps:.1f} w/s")
            if b["start_s"] < prev_end - 1e-6:
                bad_lines.append(f"{s['sceneId']}#{b['index']} overlaps previous line")
            prev_end = b["end_s"]
        stem = out_dir / s["dialogue_wav"]
        ok_len = stem.is_file() and abs(_wav_len(stem) - s["scene_duration_s"]) < 1 / 48000 * 2
        rep.hard(f"dialogue.stem.{s['sceneId']}", ok_len,
                 f"{s['sceneId']} dialogue stem {'matches' if ok_len else 'does not match'} scene duration "
                 f"{s['scene_duration_s']:.3f}s")
        rep.soft(f"dialogue.coverage.{s['sceneId']}", s["speech_coverage"] >= MIN_SCENE_COVERAGE,
                 f"{s['sceneId']} speech {s['speech_s']:.1f}s of {s['scene_duration_s']:.1f}s "
                 f"({s['speech_coverage']:.0%}; min {MIN_SCENE_COVERAGE:.0%})", s["speech_coverage"])
        dev = abs(s["scene_duration_s"] - s["target_duration_s"]) / s["target_duration_s"]
        rep.soft(f"dialogue.pacing.{s['sceneId']}", dev <= SCENE_TARGET_TOLERANCE,
                 f"{s['sceneId']} {s['scene_duration_s']:.1f}s vs target {s['target_duration_s']:.0f}s "
                 f"({dev:.0%} off; tolerance {SCENE_TARGET_TOLERANCE:.0%})")
    rep.hard("dialogue.lines", not bad_lines, "every line has audio, none overlap" if not bad_lines
             else f"missing/short/overlapping lines: {bad_lines[:8]}", bad_lines)
    rep.hard("dialogue.audible", not silent, "no silent line audio" if not silent else f"silent lines: {silent[:8]}")
    rep.hard("dialogue.word_rate", not word_rate, "speech rate plausible for every line" if not word_rate
             else f"implausible speech rate (truncated/garbled TTS?): {word_rate[:8]}", word_rate)
    rep.soft("dialogue.delivery_pace", not pace, "delivery pace natural for every line" if not pace
             else f"rushed/dragging lines: {pace[:8]}", pace)
    from robotics101.validation import episode_duration_range_for
    lo, hi = episode_duration_range_for(out_dir)                    # ADR-034
    total = doc["totalDurationSeconds"]
    rep.soft("dialogue.total_duration", lo <= total <= hi, f"episode {total:.1f}s (target {lo:.0f}-{hi:.0f}s)", total)
    rep.soft("dialogue.production_voice", bool(doc.get("isProductionVoice")),
             f"voice: {doc.get('providerLabel')}" + ("" if doc.get("isProductionVoice") else
                                                     " — production voice (ElevenLabs) not used ("
                                                     + ("; ".join(doc.get("fallbacksSkipped") or [])
                                                        or "backend chosen explicitly") + ")"))
    try:
        cues = parse_srt((out_dir / "captions.srt").read_text(encoding="utf-8"))
        problems = validate_srt(cues, bounds_ms=(0, round(total * 1000)))
    except (OSError, ValueError) as e:
        cues, problems = [], [str(e)]
    rep.hard("dialogue.captions", not problems and bool(cues),
             f"{len(cues)} speaker-labelled cues valid" if not problems else f"captions: {problems[:5]}")
    leaks = secret_leaks([out_dir, *(extra_secret_roots or [])])
    rep.hard("security.no_api_key", not leaks, "ElevenLabs key not present in any artifact" if not leaks
             else f"API KEY FOUND IN: {leaks[:5]}")
    return doc


def _wav_len(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()
