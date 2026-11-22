"""Voice a cartoon episode (M02.2): per-line audio -> beat timeline -> per-scene dialogue stems, SRT, timing.json.

Timeline rules (scene-relative seconds; deterministic, from audio durations + fixed beat costs):
* a scene starts with ``LEAD_IN_S``; each ``line`` occupies its audio duration, followed by a gap
  (``GAP_SAME_S`` if the next line has the same speaker, ``GAP_SWITCH_S`` otherwise); actions attached to a line
  play during it.
* ``action`` beats take ``seconds`` or ``ACTION_SECONDS[action]``; ``sfx`` beats ``SFX_ADVANCE_S``;
  ``music`` cues ``MUSIC_ADVANCE_S[cue]``; ``pause`` its seconds.
* scene duration = end of the last beat + ``TAIL_S``, rounded *up* to a whole 30 fps frame.
Scene durations are therefore driven by the dialogue, not by ``durationTargetSeconds`` (reported vs target).
"""

from __future__ import annotations

import array
import json
import math
import os
import textwrap
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from robotics101.characters import Registry
from robotics101.narration.captions import MAX_LINE, MAX_LINES, build_srt, split_cue_texts, wrap_cue
from robotics101.voice.backends import Backend, VoiceError, VoiceRequest, decode_to_wav
from robotics101.voice.cache import VoiceCache

TIMING_SCHEMA = "robotics101.timing/2"
RATE = 48_000
FPS = 30
LEAD_IN_S, TAIL_S = 0.4, 0.8
GAP_SAME_S, GAP_SWITCH_S = 0.25, 0.35
SFX_ADVANCE_S = 0.45
ACTION_DEFAULT_S = 0.9
ACTION_SECONDS = {"zoom": 1.2, "bonk": 0.7, "dizzy": 1.4, "fall": 1.0, "land": 0.8, "fly_to": 1.2, "skid": 1.0,
                  "drive": 1.5, "stop": 0.5, "turn": 1.0, "resume": 1.0, "spin": 1.2, "enter": 1.0, "exit": 1.0,
                  "beep_dance": 1.6, "highfive": 0.8, "flinch": 0.5, "ping": 0.8, "hop": 0.6, "yawn": 1.2}
MUSIC_ADVANCE_S = {"theme_intro": 2.0, "title_sting": 2.5, "idea_sting": 1.2, "chant_beat": 0.0,
                   "victory_sting": 2.0, "outro": 3.0}
BUDGET_ENV = "ROBOTICS101_ELEVENLABS_MAX_CHARS"
DEFAULT_BUDGET_CHARS = 8000          # per run, uncached characters only (one episode ~ 3.5-6k)


@dataclass
class LinePlan:
    sceneId: str
    index: int              # beat index inside the scene
    speaker: str
    text: str
    request: VoiceRequest
    fx: list[str]
    cached: bool = False


@dataclass
class SceneVoice:
    sceneId: str
    sequence: int
    target_duration_s: float
    scene_start_s: float
    scene_end_s: float
    scene_duration_s: float
    speech_s: float
    speech_coverage: float
    dialogue_wav: str
    beats: list[dict] = field(default_factory=list)


def _r(x: float) -> float:
    return round(x, 3)


def ceil_frame(seconds: float) -> float:
    return round(math.ceil(round(seconds * FPS, 6)) / FPS, 6)


def plan_lines(spec: dict, registry: Registry, backend: Backend, cache: VoiceCache) -> list[LinePlan]:
    plans = []
    for scene in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        for i, b in enumerate(scene.get("beats", [])):
            if b.get("type") != "line":
                continue
            ch = registry.get(b["speaker"])
            if ch is None or not ch.speaks or not ch.voice:
                raise VoiceError(f"{scene['sceneId']} beat {i}: {b['speaker']!r} has no voice")
            req = backend.request(ch.voice, " ".join(b["text"].split()))
            plans.append(LinePlan(scene["sceneId"], i, ch.id, b["text"], req, backend.fx(ch.voice),
                                  cached=cache.has(req)))
    return plans


def budget_chars() -> int:
    try:
        return int(os.environ.get(BUDGET_ENV) or DEFAULT_BUDGET_CHARS)
    except ValueError as e:
        raise VoiceError(f"{BUDGET_ENV} must be an integer") from e


def cost_summary(plans: list[LinePlan], backend: Backend) -> dict:
    uncached = [p for p in plans if not p.cached]
    return {"provider": backend.name, "lines": len(plans), "cachedLines": len(plans) - len(uncached),
            "charsTotal": sum(p.request.chars for p in plans),
            "billableChars": sum(p.request.chars for p in uncached) if backend.billable else 0}


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def _place(stem: array.array, wav: Path, at_sample: int) -> None:
    with wave.open(str(wav), "rb") as w:
        if w.getframerate() != RATE or w.getnchannels() != 1:
            raise VoiceError(f"{wav} is not 48 kHz mono")
        a = array.array("h", w.readframes(w.getnframes()))
    end = min(len(stem), at_sample + len(a))
    for k in range(at_sample, end):
        stem[k] = max(-32768, min(32767, stem[k] + a[k - at_sample]))


def _write_wav(path: Path, samples: array.array) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.tobytes())


def voice_episode(spec: dict, registry: Registry, out_dir: Path, backend: Backend,
                  cache: VoiceCache | None = None, *, log=print, skipped: list[str] | None = None) -> dict:
    """Synthesize (or reuse) every line, build the timeline, write stems + captions + timing.json."""
    out_dir = Path(out_dir)
    cache = cache or VoiceCache()
    plans = plan_lines(spec, registry, backend, cache)
    cost = cost_summary(plans, backend)
    if backend.billable:
        unapproved = sorted({p.speaker for p in plans
                             if not (registry.get(p.speaker).voice.get(backend.name) or {}).get("approved")})
        if unapproved:
            raise VoiceError(f"{backend.name} voices for {unapproved} are not owner-approved yet: run "
                             "`robotics101 voices samples` (short sample lines only), get the owner's approval, then "
                             "set voice.elevenlabs.approved=true in characters/registry.json. Nothing was synthesized.")
        limit = budget_chars()
        if cost["billableChars"] > limit:
            raise VoiceError(f"{backend.name}: {cost['billableChars']} uncached characters exceed the per-run budget "
                             f"{limit} ({BUDGET_ENV}); nothing was synthesized")
    log(f"voice: {backend.name} — {cost['lines']} lines, {cost['cachedLines']} cached, "
        f"{cost['charsTotal']} chars ({cost['billableChars']} billable)")

    lines_dir = out_dir / "voice" / "lines"
    lines_dir.mkdir(parents=True, exist_ok=True)
    line_wavs: dict[tuple[str, int], tuple[Path, LinePlan]] = {}
    for n, p in enumerate(plans, 1):
        raw, was_cached = cache.get_or_render(backend, p.request)
        dst = lines_dir / f"{p.sceneId}-{p.index:02d}-{p.speaker}.wav"
        decode_to_wav(raw, dst, p.fx)
        line_wavs[(p.sceneId, p.index)] = (dst, p)
        if not was_cached:
            log(f"  [{n}/{len(plans)}] synthesized {p.sceneId}#{p.index} {p.speaker} ({p.request.chars} chars)")

    scenes_out, cues, t0 = [], [], 0.0
    names = {cid: c.displayName for cid, c in registry.characters.items()}
    for scene in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        sid, t, beats_out = scene["sceneId"], LEAD_IN_S, []
        beats = scene.get("beats", [])
        line_idx = [i for i, b in enumerate(beats) if b["type"] == "line"]
        speech = 0.0
        for i, b in enumerate(beats):
            kind, entry = b["type"], {"index": i, "type": b["type"]}
            if kind == "line":
                wav, p = line_wavs[(sid, i)]
                dur = _wav_seconds(wav)
                nxt = next((j for j in line_idx if j > i), None)
                gap = GAP_SAME_S if nxt is not None and beats[nxt]["speaker"] == b["speaker"] else GAP_SWITCH_S
                entry.update(speaker=b["speaker"], text=b["text"], emotion=b.get("emotion"), action=b.get("action"),
                             target=b.get("target"), wav=str(wav.relative_to(out_dir)), cacheKey=p.request.key,
                             start_s=_r(t), end_s=_r(t + dur), audio_s=_r(dur))
                speech += dur
                t += dur + gap
            elif kind == "action":
                d = float(b.get("seconds") or ACTION_SECONDS.get(b["do"].split(":")[0], ACTION_DEFAULT_S))
                entry.update(who=b["who"], do=b["do"], emotion=b.get("emotion"), start_s=_r(t), end_s=_r(t + d))
                t += d
            elif kind == "sfx":
                entry.update(id=b["id"], who=b.get("who"), start_s=_r(t), end_s=_r(t + SFX_ADVANCE_S))
                t += SFX_ADVANCE_S
            elif kind == "music":
                d = MUSIC_ADVANCE_S.get(b["cue"], 0.0)
                entry.update(cue=b["cue"], start_s=_r(t), end_s=_r(t + d))
                t += d
            elif kind == "pause":
                entry.update(start_s=_r(t), end_s=_r(t + float(b["seconds"])))
                t += float(b["seconds"])
            beats_out.append(entry)
        last_end = max([e["end_s"] for e in beats_out] + [LEAD_IN_S])
        duration = ceil_frame(last_end + TAIL_S)
        n_samples = round(duration * RATE)
        stem = array.array("h", bytes(2 * n_samples))
        for e in beats_out:
            if e["type"] == "line":
                _place(stem, out_dir / e["wav"], round(e["start_s"] * RATE))
                name = names.get(e["speaker"], e["speaker"])
                label = f"{name}: {' '.join(e['text'].split())}"
                # one cue per line when it fits 2x42; otherwise sentence/clause chunks (speaker on the first)
                texts = [label] if len(textwrap.wrap(label, MAX_LINE)) <= MAX_LINES else split_cue_texts(label)
                total = sum(len(x) for x in texts)
                a_ms, b_ms, acc = round((t0 + e["start_s"]) * 1000), round((t0 + e["end_s"]) * 1000), 0
                prev = a_ms
                for x in texts:
                    acc += len(x)
                    edge = a_ms + round((b_ms - a_ms) * acc / total)
                    cues.append((prev, edge, wrap_cue(x)))
                    prev = edge
        stem_path = out_dir / "voice" / "scenes" / f"{sid}.wav"
        _write_wav(stem_path, stem)
        scenes_out.append(SceneVoice(sid, scene["sequence"], float(scene["durationTargetSeconds"]), _r(t0),
                                     _r(t0 + duration), duration, _r(speech),
                                     _r(speech / duration) if duration else 0.0,
                                     str(stem_path.relative_to(out_dir)), beats_out))
        t0 = round(t0 + duration, 6)

    (out_dir / "captions.srt").write_text(build_srt(cues), encoding="utf-8")
    total = scenes_out[-1].scene_end_s if scenes_out else 0.0
    speech_total = sum(s.speech_s for s in scenes_out)
    voices = {cid: {"provider": backend.name, **{k: v for k, v in (registry.get(cid).voice.get(backend.name) or {})
                                                 .items() if k in ("voiceId", "voiceName", "modelId", "voice")}}
              for cid in sorted({p.speaker for p in plans})}
    doc = {
        "schemaVersion": TIMING_SCHEMA, "episodeId": spec["episodeId"], "fps": FPS, "sampleRate": RATE,
        "provider": backend.name, "providerLabel": backend.label, "isProductionVoice": backend.is_production,
        "fallbacksSkipped": skipped or [], "voices": voices, "registrySha256": registry.sha256,
        "cost": cost, "totalDurationSeconds": _r(total), "totalSpeechSeconds": _r(speech_total),
        "speechCoverage": _r(speech_total / total) if total else 0.0,
        "constants": {"leadIn": LEAD_IN_S, "tail": TAIL_S, "gapSame": GAP_SAME_S, "gapSwitch": GAP_SWITCH_S,
                      "sfxAdvance": SFX_ADVANCE_S},
        "scenes": [asdict(s) for s in scenes_out],
    }
    (out_dir / "timing.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc
