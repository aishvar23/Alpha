"""Deterministic headless-Blender scene templates (M01.4).

Each template is a standalone script run as
``blender --background --factory-startup --python-exit-code 1 --python <script> -- --params job.json ...``.
This ``__init__`` must not import ``bpy``: the host imports it to locate scripts and to run the same
motion plan (incl. ``collisionCheck``) before launching Blender, and the Blender script imports it
(under Blender's bundled Python 3.11) to build exactly the same plan. Keep it 3.11-compatible and
stdlib-only apart from pure ``robotics101`` modules.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from pathlib import Path

from robotics101.animation.timing import animation_speed, target_frames
from robotics101.kinematics import (
    AvoidanceConfig,
    AvoidancePath,
    PathPlanningError,
    RobotGeometry,
    assert_collision_free,
    generate_avoidance_path,
)

TEMPLATE_DIR = Path(__file__).resolve().parent

# template name -> script file (fixed allowlist; spec content never selects a path)
TEMPLATE_SCRIPTS: dict[str, Path] = {
    "mobile_robot_avoidance": TEMPLATE_DIR / "mobile_robot_avoidance.py",
}


DEFAULT_STOP_THRESHOLD_M = 0.5
JOB_STOP_THRESHOLD_KEY = "stopThresholdMeters"


def episode_stop_threshold(spec: dict) -> float:
    """The stop threshold the episode teaches: the first ``sense_think_act`` scene's ``thresholdMeters``
    (by sequence), else ``DEFAULT_STOP_THRESHOLD_M``. Keeps the 3D demo consistent with the 2D rule."""
    for scene in sorted(spec.get("scenes", []), key=lambda s: s.get("sequence", 0)):
        if scene.get("template") == "sense_think_act":
            t = (scene.get("parameters") or {}).get("thresholdMeters")
            if isinstance(t, (int, float)) and not isinstance(t, bool) and t > 0:
                return float(t)
    return DEFAULT_STOP_THRESHOLD_M


def format_reading_m(reading_m: float) -> str:
    """HUD sensor readout, truncated (not rounded) to the centimetre so a reading just below the
    threshold never displays as equal to it (0.498 m -> "0.49 m", not "0.50 m" next to "< 0.5 m")."""
    return f"{math.floor(reading_m * 100 + 1e-9) / 100:.2f} m"


def format_threshold_m(threshold_m: float) -> str:
    """Threshold as written in the 2D sense_think_act scene (0.5 -> "0.5 m")."""
    return f"{threshold_m:g} m"


@dataclass
class AvoidancePlan:
    cfg: AvoidanceConfig
    geom: RobotGeometry
    path: AvoidancePath
    target_frames: int          # total clip frames (motion + hold)
    collision_checked: bool

    @property
    def hold_frames(self) -> int:
        return self.target_frames - self.path.motion_frames


def plan_mobile_robot_avoidance(params: dict, duration_s: float, fps: int,
                                stop_threshold: float | None = None) -> AvoidancePlan:
    """Motion plan for the scene: nominal script, compressed only if the scene is too short.

    ``stop_threshold`` (m) is the episode's taught rule (see ``episode_stop_threshold``); default 0.5 m.
    Raises ``CollisionError`` (collisionCheck, default on) or ``PathPlanningError`` (e.g. a threshold
    beyond the 1.5 m sensor range).
    """
    thr = DEFAULT_STOP_THRESHOLD_M if stop_threshold is None else float(stop_threshold)
    cfg, geom = replace(AvoidanceConfig(), stop_threshold=thr), RobotGeometry()
    cfg.validate()
    total = target_frames(duration_s, fps)
    nominal = generate_avoidance_path(cfg, geom, fps, 1.0)
    speed = animation_speed(duration_s, nominal.motion_frames / fps)
    path = nominal if speed >= 1.0 else generate_avoidance_path(cfg, geom, fps, speed)
    if path.motion_frames > total:
        raise PathPlanningError(f"scene too short: motion needs {path.motion_frames} frames, "
                                f"clip has {total} ({duration_s}s @ {fps}fps)")
    check = params.get("collisionCheck", True)
    if check:
        assert_collision_free(path, geom, cfg)
    return AvoidancePlan(cfg, geom, path, total, bool(check))
