"""'Robot-cam' cutaway (M02.5, owner direction): the M01 headless-Blender obstacle scene, restyled to the
cartoon palette with ink outlines, used as an insert in the cartoon rematch scene for the sensing/stop moment.

Same motion plan, collision check, sensor readout truncation and stop threshold (the episode's 0.5 m) as M01;
only colours/outlines and the HUD title change. Rendered once per bundle to ``<out>/robotcam/<id>.mp4``.
"""

from __future__ import annotations

from pathlib import Path

from robotics101.animation.blender_templates import JOB_STOP_THRESHOLD_KEY
from robotics101.animation.render import PROFILES, RenderSetupError


def robotcam_job(duration_s: float, threshold_m: float, obstacle: str = "boxes", clip_id: str = "robotcam") -> dict:
    """Blender job for the cutaway; the threshold is the episode's (same value as the 2D staging and the rule)."""
    return {"sceneId": clip_id, "template": "mobile_robot_avoidance", "durationSeconds": float(duration_s),
            "params": {"robotAsset": "simple_mobile_robot_v1", "obstacle": "cube" if obstacle == "boxes" else obstacle,
                       "collisionCheck": True},
            "title": "ROBOT-CAM", "style": "cartoon", JOB_STOP_THRESHOLD_KEY: float(threshold_m)}


def render_robotcam(out_dir: Path, duration_s: float, threshold_m: float, obstacle: str = "boxes",
                    profile: str = "full", clip_id: str = "robotcam", timeout_s: float = 1800) -> Path:
    from robotics101.animation.blender_render import find_blender, render_blender_scene
    import shutil

    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not (ffmpeg and ffprobe):
        raise RenderSetupError("ffmpeg/ffprobe required for the robot-cam insert")
    blender = find_blender()
    out_dir = Path(out_dir) / "robotcam"
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)
    (out_dir / "scenes").mkdir(parents=True, exist_ok=True)
    job = robotcam_job(duration_s, threshold_m, obstacle, clip_id)
    res = render_blender_scene(blender, ffmpeg, ffprobe, job, out_dir, PROFILES[profile], timeout_s)
    if res.status != "rendered":
        raise RuntimeError(f"robot-cam render failed: {res.message} (log {res.log})")
    return out_dir / "scenes" / f"{clip_id}.mp4"
