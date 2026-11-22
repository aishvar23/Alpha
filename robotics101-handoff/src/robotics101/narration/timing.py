"""Per-scene narration step: synthesize audio, derive scene timing, write timing.json + captions.srt."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from robotics101.narration.captions import build_srt, scene_cues
from robotics101.narration.providers import NarrationResult, TtsProvider

LEAD_IN_S = 0.5
TAIL_S = 0.5
MIN_SPEECH_COVERAGE = 0.60
SHORT_VOICE_FLAG = ("voice content too short; holds fill gap — not acceptable educational pacing")
PLACEHOLDER_FLAG = "synthetic/placeholder audio — not production narration"


@dataclass
class SceneTiming:
    sceneId: str
    sequence: int
    audio_path: str
    audio_duration_s: float
    target_duration_s: float
    scene_start_s: float
    scene_end_s: float
    scene_duration_s: float
    narration_start_s: float
    narration_end_s: float
    hold_s: float
    speech_coverage: float
    provider: str
    provider_label: str
    is_synthetic_placeholder: bool
    qa_flags: list[str] = field(default_factory=list)


def _r(x: float) -> float:
    return round(x, 3)


def compute_scene_timing(scene: dict, result: NarrationResult, start_s: float,
                         lead_in: float = LEAD_IN_S, tail: float = TAIL_S) -> SceneTiming:
    """scene_duration = max(target, audio + lead_in + tail); narration starts after lead-in; rest is hold."""
    audio = result.duration_s
    target = float(scene["durationTargetSeconds"])
    duration = _r(max(target, audio + lead_in + tail))
    n_start = _r(start_s + lead_in)
    n_end = _r(n_start + audio)
    coverage = _r(audio / duration) if duration else 0.0
    flags = []
    if coverage < MIN_SPEECH_COVERAGE:
        flags.append(SHORT_VOICE_FLAG)
    if result.is_synthetic_placeholder:
        flags.append(f"{PLACEHOLDER_FLAG}: {result.label}")
    return SceneTiming(
        sceneId=scene["sceneId"], sequence=scene["sequence"], audio_path=str(result.path),
        audio_duration_s=_r(audio), target_duration_s=target,
        scene_start_s=_r(start_s), scene_end_s=_r(start_s + duration), scene_duration_s=duration,
        narration_start_s=n_start, narration_end_s=n_end,
        hold_s=_r(duration - lead_in - audio), speech_coverage=coverage,
        provider=result.provider, provider_label=result.label,
        is_synthetic_placeholder=result.is_synthetic_placeholder, qa_flags=flags,
    )


def build_timeline(scenes: list[dict], results: dict[str, NarrationResult]) -> list[SceneTiming]:
    timings, t = [], 0.0
    for scene in sorted(scenes, key=lambda s: s["sequence"]):
        st = compute_scene_timing(scene, results[scene["sceneId"]], t)
        timings.append(st)
        t = st.scene_end_s
    return timings


def narrate_episode(spec: dict, out_dir: Path, provider: TtsProvider) -> dict:
    """Synthesize every scene, write audio/<sceneId>.wav, timing.json and captions.srt. Returns timing doc."""
    out_dir = Path(out_dir)
    audio_dir = out_dir / "audio"
    results = {
        s["sceneId"]: provider.synthesize(s["narration"], audio_dir / f"{s['sceneId']}.wav")
        for s in spec["scenes"]
    }
    timings = build_timeline(spec["scenes"], results)
    narration = {s["sceneId"]: s["narration"] for s in spec["scenes"]}

    cues = []
    for st in timings:
        cues += scene_cues(narration[st.sceneId], st.narration_start_s, st.narration_end_s)
    (out_dir / "captions.srt").write_text(build_srt(cues), encoding="utf-8")

    total = timings[-1].scene_end_s if timings else 0.0
    speech = sum(t.audio_duration_s for t in timings)
    doc = {
        "episodeId": spec["episodeId"],
        "provider": provider.name,
        "providerLabels": sorted({t.provider_label for t in timings}),
        "leadInSeconds": LEAD_IN_S,
        "tailSeconds": TAIL_S,
        "totalDurationSeconds": total,
        "totalSpeechSeconds": _r(speech),
        "speechCoverage": _r(speech / total) if total else 0.0,
        "scenesFlagged": [t.sceneId for t in timings if SHORT_VOICE_FLAG in t.qa_flags],
        "scenes": [asdict(t) for t in timings],
    }
    (out_dir / "timing.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc
