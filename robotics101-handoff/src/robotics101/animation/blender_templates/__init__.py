"""Deterministic headless-Blender scene templates (M01.4).

Each template is a standalone script run as
``blender --background --factory-startup --python-exit-code 1 --python <script> -- --params job.json ...``.
This ``__init__`` must not import ``bpy``: the host imports it to locate scripts and to run the same
motion plan (incl. ``collisionCheck``) before launching Blender, and the Blender script imports it
(under Blender's bundled Python 3.11) to build exactly the same plan. Keep it 3.11-compatible and
stdlib-only apart from pure ``robotics101`` modules.
"""

from __future__ import annotations

from dataclasses import dataclass
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


def plan_mobile_robot_avoidance(params: dict, duration_s: float, fps: int) -> AvoidancePlan:
    """Motion plan for the scene: nominal script, compressed only if the scene is too short.

    Raises ``CollisionError`` (collisionCheck, default on) or ``PathPlanningError``.
    """
    cfg, geom = AvoidanceConfig(), RobotGeometry()
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
