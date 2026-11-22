"""Pure frame/duration helpers shared by the renderer (host side) and the Manim templates."""

from __future__ import annotations

import json
from pathlib import Path


def target_frames(duration_s: float, fps: int) -> int:
    """Number of frames a clip of ``duration_s`` must have (nearest frame, at least 1)."""
    if duration_s <= 0:
        raise ValueError(f"duration must be > 0, got {duration_s}")
    return max(1, round(duration_s * fps))


def frames_for(seconds: float, fps: int, minimum: int = 1) -> int:
    """Whole frames for an animation segment of ``seconds`` (never below ``minimum``)."""
    return max(minimum, round(seconds * fps))


def animation_speed(duration_s: float, nominal_s: float) -> float:
    """Time-scale factor for a template's scripted animations.

    Templates script ``nominal_s`` of animation. If the scene is long enough (nominal plus a
    short hold) they play at speed 1.0 and the remainder is a hold; for very short scenes
    (e.g. smoke tests) the script is compressed so at least 20% (max 1 s) remains as hold.
    """
    if nominal_s <= 0:
        raise ValueError("nominal animation time must be > 0")
    budget = duration_s - min(1.0, 0.2 * duration_s)
    return min(1.0, max(budget, 0.0) / nominal_s)


def resolve_scene_durations(spec: dict, timing_path: Path | None) -> tuple[dict[str, float], str]:
    """Return ({sceneId: seconds}, source) using timing.json if present, else durationTargetSeconds.

    A timing.json for a different episode, or one missing scenes, is an error (stale narration).
    """
    targets = {s["sceneId"]: float(s["durationTargetSeconds"]) for s in spec["scenes"]}
    if timing_path is None or not Path(timing_path).is_file():
        return targets, "durationTargetSeconds (no timing.json)"
    doc = json.loads(Path(timing_path).read_text(encoding="utf-8"))
    if doc.get("episodeId") != spec.get("episodeId"):
        raise ValueError(f"{timing_path} is for episode {doc.get('episodeId')!r}, "
                         f"not {spec.get('episodeId')!r}; re-run narrate")
    timed = {s["sceneId"]: float(s["scene_duration_s"]) for s in doc.get("scenes", [])}
    missing = sorted(targets.keys() - timed.keys())
    if missing:
        raise ValueError(f"{timing_path} lacks scenes {missing}; re-run narrate")
    return {sid: timed[sid] for sid in targets}, str(timing_path)
