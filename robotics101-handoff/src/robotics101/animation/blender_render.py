"""Host side of the headless-Blender scenes (M01.4).

For each ``engine=blender`` scene: plan the motion and run ``collisionCheck`` on the host (fails
fast, no Blender launched), render the motion frames to PNG with ``blender --background
--factory-startup`` split across a few Blender processes, then encode to H.264 with ffmpeg,
cloning the last frame for the static hold so the clip is exactly ``round(duration × fps)``
frames. The clip gets the same ffprobe checks as the Manim scenes.

As with Manim, the template script is chosen from a fixed allowlist and only validated parameters
+ duration reach it, as a JSON job file. Nothing from the spec is executed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from robotics101.animation.blender_templates import TEMPLATE_SCRIPTS, plan_mobile_robot_avoidance
from robotics101.animation.render import Profile, RenderSetupError, SceneResult, verify_clip
from robotics101.kinematics import CollisionError, PathPlanningError

MIN_BLENDER = (4, 2)
BLENDER_ENGINE_ENV = "ROBOTICS101_BLENDER_ENGINE"   # workbench (default) | eevee
BLENDER_PROCS_ENV = "ROBOTICS101_BLENDER_PROCS"     # parallel Blender processes per scene

BLENDER_PREREQS = (
    "Blender is required to render engine=blender scenes (scene-006 mobile_robot_avoidance). Prerequisites:\n"
    f"  - Blender >= {MIN_BLENDER[0]}.{MIN_BLENDER[1]} (tested with 4.3.2), runnable headless:  blender --background --version\n"
    "      Debian/Ubuntu: apt-get install blender   or download from https://www.blender.org/download/\n"
    "  - no GPU needed (Workbench engine, software OpenGL); no add-ons or downloaded assets are used\n"
    "  - ffmpeg + ffprobe on PATH:  apt-get install ffmpeg\n"
    "Set BLENDER_BIN to override the blender executable path."
)

# Workbench anti-aliasing per profile (render time is dominated by AA samples).
WORKBENCH_AA = {"preview": "5", "full": "8"}


def blender_version(binary: str) -> tuple[int, int] | None:
    try:
        proc = subprocess.run([binary, "--background", "--factory-startup", "--version"],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Blender (\d+)\.(\d+)", proc.stdout)
    return (int(m.group(1)), int(m.group(2))) if m else None


def find_blender() -> str:
    """Locate a usable blender: $BLENDER_BIN, then PATH; checks it runs headless and its version."""
    candidates = [os.environ.get("BLENDER_BIN"), shutil.which("blender")]
    binary = next((c for c in candidates if c and Path(c).is_file() and os.access(c, os.X_OK)), None)
    if binary is None:
        raise RenderSetupError("blender executable not found.\n" + BLENDER_PREREQS)
    version = blender_version(binary)
    if version is None:
        raise RenderSetupError(f"{binary} did not run headless (`--background --version` failed).\n" + BLENDER_PREREQS)
    if version < MIN_BLENDER:
        raise RenderSetupError(f"{binary} is Blender {version[0]}.{version[1]}, too old.\n" + BLENDER_PREREQS)
    return binary


# Measured peak RSS of one Workbench Blender process (Blender 4.3.2, software GL): ~760 MB at 1080p.
PROC_RSS_MB = {"preview": 500, "full": 800}


def available_memory_mb() -> int | None:
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def default_procs(profile_name: str = "full") -> int:
    """$ROBOTICS101_BLENDER_PROCS, else min(4, CPUs/2), capped so the processes fit in ~75% of free RAM."""
    env = os.environ.get(BLENDER_PROCS_ENV)
    if env:
        return max(1, int(env))
    procs = max(1, min(4, (os.cpu_count() or 2) // 2))
    avail = available_memory_mb()
    if avail is not None:
        procs = max(1, min(procs, int(0.75 * avail) // PROC_RSS_MB.get(profile_name, 800)))
    return procs


def chunk_ranges(n: int, parts: int) -> list[tuple[int, int]]:
    """Split frames [0, n) into at most ``parts`` contiguous, non-empty [a, b) ranges."""
    parts = max(1, min(parts, n))
    base, extra = divmod(n, parts)
    out, a = [], 0
    for i in range(parts):
        b = a + base + (1 if i < extra else 0)
        out.append((a, b))
        a = b
    return out


def encode_command(ffmpeg: str, frames_dir: Path, fps: int, hold_frames: int, total_frames: int,
                   out_mp4: Path) -> list[str]:
    """PNG sequence -> H.264 yuv420p, last frame cloned ``hold_frames`` times, exactly ``total_frames``."""
    vf = f"tpad=stop_mode=clone:stop={hold_frames}" if hold_frames > 0 else "null"
    return [ffmpeg, "-y", "-v", "error", "-framerate", str(fps), "-start_number", "0",
            "-i", str(frames_dir / "%05d.png"), "-vf", vf, "-frames:v", str(total_frames),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-r", str(fps), "-movflags", "+faststart", "-an", str(out_mp4)]


def render_blender_scene(blender: str, ffmpeg: str, ffprobe: str, job: dict, out_dir: Path, profile: Profile,
                         timeout_s: float, procs: int | None = None) -> SceneResult:
    sid, template = job["sceneId"], job["template"]
    out_dir = Path(out_dir)
    log_path = out_dir / "logs" / f"{sid}.log"
    final = out_dir / "scenes" / f"{sid}.mp4"
    result = SceneResult(sid, template, "failed", log=str(log_path), duration_target_s=job["durationSeconds"])
    t0 = time.monotonic()

    # 1. plan + collisionCheck on the host (same pure code the Blender script runs)
    try:
        plan = plan_mobile_robot_avoidance(job["params"], job["durationSeconds"], profile.fps)
    except (CollisionError, PathPlanningError) as e:
        log_path.write_text(f"planning failed before launching Blender:\n{e}\n", encoding="utf-8")
        result.message = str(e)
        return result
    n = plan.path.motion_frames

    work = (out_dir / ".blender" / sid).resolve()
    if work.exists():
        shutil.rmtree(work)
    frames = work / "frames"
    frames.mkdir(parents=True)
    job_path = work / "job.json"
    job_path.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")

    engine = os.environ.get(BLENDER_ENGINE_ENV, "workbench")
    if engine not in ("workbench", "eevee"):
        result.message = f"{BLENDER_ENGINE_ENV} must be workbench or eevee, got {engine!r}"
        return result
    script = TEMPLATE_SCRIPTS[template]
    ranges = chunk_ranges(n, procs or default_procs(profile.name))
    base = [blender, "--background", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
            "--", "--params", str(job_path), "--out", str(frames), "--width", str(profile.width),
            "--height", str(profile.height), "--fps", str(profile.fps), "--engine", engine,
            "--aa", WORKBENCH_AA.get(profile.name, "8")]
    env = {**os.environ, "PYTHONNOUSERSITE": "1"}

    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"# {sid} {template}: {n} motion frames + {plan.hold_frames} hold frames = "
                  f"{plan.target_frames} @ {profile.fps}fps, engine {engine}, {len(ranges)} blender process(es)\n")
        log.write(f"# plan: stop at frame {plan.path.stop_frame}, reading {plan.path.stop_reading:.3f} m "
                  f"< threshold {plan.cfg.stop_threshold} m; collisionCheck "
                  f"{'passed' if plan.collision_checked else 'DISABLED'}\n")
        chunk_logs, running = [], []
        for i, (a, b) in enumerate(ranges):
            cmd = base + ["--frames", f"{a}:{b}"] + (["--summary", str(work / "plan.json")] if i == 0 else [])
            log.write(f"$ {' '.join(cmd)}\n")
            clog = open(work / f"blender-{i}.log", "w", encoding="utf-8")
            chunk_logs.append(clog)
            running.append(subprocess.Popen(cmd, stdout=clog, stderr=subprocess.STDOUT, cwd=work, env=env))
        log.flush()
        deadline = t0 + timeout_s
        failed_msg = None
        try:
            for p in running:
                rc = p.wait(timeout=max(1.0, deadline - time.monotonic()))
                if rc != 0 and failed_msg is None:
                    failed_msg = f"blender exited with {rc}"
        except subprocess.TimeoutExpired:
            failed_msg = f"blender timed out after {timeout_s:.0f}s"
        finally:
            for p in running:
                if p.poll() is None:
                    p.kill()
                    p.wait()
            for i, clog in enumerate(chunk_logs):
                clog.close()
                log.write(f"\n----- blender process {i} -----\n")
                log.write(Path(clog.name).read_text(encoding="utf-8", errors="replace"))
        render_s = time.monotonic() - t0
        log.write(f"\n# blender render wall time {render_s:.1f}s\n")
        if failed_msg:
            result.message, result.elapsed_s = failed_msg, render_s
            return result
        missing = [i for i in range(n) if not (frames / f"{i:05d}.png").is_file()]
        if missing:
            result.message = f"blender finished but {len(missing)} of {n} frames are missing (first {missing[0]})"
            result.elapsed_s = render_s
            return result

        # 2. encode + static hold
        final.unlink(missing_ok=True)
        cmd = encode_command(ffmpeg, frames, profile.fps, plan.hold_frames, plan.target_frames, final)
        log.write(f"$ {' '.join(cmd)}\n")
        log.flush()
        try:
            enc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                 timeout=max(30.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            result.message, result.elapsed_s = "ffmpeg encode timed out", time.monotonic() - t0
            return result
        result.elapsed_s = time.monotonic() - t0
        log.write(f"# total wall time {result.elapsed_s:.1f}s (render {render_s:.1f}s)\n")
    if enc.returncode != 0:
        result.message = f"ffmpeg exited with {enc.returncode}"
        return result
    shutil.rmtree(work, ignore_errors=True)
    return verify_clip(result, final, job["durationSeconds"], profile, ffprobe)
