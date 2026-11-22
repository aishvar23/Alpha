"""Host-side scene renderer: runs each Manim template in a subprocess and verifies the output.

Only validated scene parameters are passed to the template, as a JSON job file referenced by
the ``ROBOTICS101_SCENE_JOB`` environment variable. The template class is chosen from the fixed
``SCENE_CLASSES`` allowlist; nothing from the spec is ever executed as code.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from robotics101.animation.manim_templates import ENTRY_FILE, JOB_ENV, SCENE_CLASSES
from robotics101.animation.probe import check_clip
from robotics101.animation.timing import target_frames


@dataclass(frozen=True)
class Profile:
    name: str
    width: int
    height: int
    fps: int


PROFILES = {
    "preview": Profile("preview", 854, 480, 30),
    "full": Profile("full", 1920, 1080, 30),
}

MANIM_PREREQS = (
    "Manim Community is required to render 2D scenes. Prerequisites:\n"
    "  - Python 3.12 venv with manim (tested with 0.22.1):  uv pip install --python .venv/bin/python 'manim==0.22.1'\n"
    "  - system libs for manim/pango/cairo (Debian/Ubuntu): apt-get install libcairo2-dev libpango1.0-dev pkg-config\n"
    "  - ffmpeg + ffprobe on PATH:                           apt-get install ffmpeg\n"
    "  - LaTeX is NOT needed (templates use Text only).\n"
    "Set MANIM_BIN to override the manim executable path."
)


class RenderSetupError(RuntimeError):
    pass


@dataclass
class SceneResult:
    sceneId: str
    template: str
    status: str                 # rendered | failed | skipped
    message: str = ""
    output: str | None = None
    log: str | None = None
    duration_target_s: float | None = None
    probe: dict | None = None
    elapsed_s: float = 0.0
    problems: list[str] = field(default_factory=list)


def find_manim() -> str:
    """Locate the manim executable: $MANIM_BIN, next to this Python, then PATH."""
    candidates = [os.environ.get("MANIM_BIN"), str(Path(sys.executable).parent / "manim"), shutil.which("manim")]
    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    raise RenderSetupError("manim executable not found.\n" + MANIM_PREREQS)


def check_prerequisites() -> tuple[str, str]:
    manim = find_manim()
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not shutil.which("ffmpeg"):
        raise RenderSetupError("ffmpeg/ffprobe not found on PATH.\n" + MANIM_PREREQS)
    return manim, ffprobe


def build_job(spec: dict, scene: dict, duration_s: float) -> dict:
    """The only data handed to a template process (validated parameters + timing)."""
    return {
        "episodeId": spec["episodeId"],
        "episodeTitle": spec.get("title", ""),
        "episodeNumber": spec.get("episodeNumber"),
        "sceneId": scene["sceneId"],
        "title": scene["title"],
        "template": scene["template"],
        "params": scene.get("parameters", {}),
        "durationSeconds": duration_s,
    }


def _render_one(manim: str, ffprobe: str, job: dict, out_dir: Path, profile: Profile, timeout_s: float) -> SceneResult:
    sid, template = job["sceneId"], job["template"]
    scenes_dir, logs_dir = out_dir / "scenes", out_dir / "logs"
    work = (out_dir / ".manim" / sid).resolve()  # absolute: manim runs with cwd=work
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    job_path = work / "job.json"
    job_path.write_text(json.dumps(job, indent=2, ensure_ascii=False), encoding="utf-8")
    log_path = logs_dir / f"{sid}.log"
    final = scenes_dir / f"{sid}.mp4"
    result = SceneResult(sid, template, "failed", log=str(log_path), duration_target_s=job["durationSeconds"])

    cmd = [manim, "render", str(ENTRY_FILE), SCENE_CLASSES[template],
           "--resolution", f"{profile.width},{profile.height}", "--fps", str(profile.fps),
           "--format", "mp4", "--media_dir", str(work / "media"),
           "--disable_caching", "--progress_bar", "none", "-v", "WARNING"]
    env = {**os.environ, JOB_ENV: str(job_path.resolve())}
    t0 = time.monotonic()
    with open(log_path, "w", encoding="utf-8") as log:
        log.write(f"$ {' '.join(cmd)}\n# {JOB_ENV}={job_path}\n\n")
        log.flush()
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, env=env, cwd=work,
                                  timeout=timeout_s)
        except subprocess.TimeoutExpired:
            result.message = f"manim timed out after {timeout_s:.0f}s"
            result.elapsed_s = time.monotonic() - t0
            return result
    result.elapsed_s = time.monotonic() - t0
    if proc.returncode != 0:
        result.message = f"manim exited with {proc.returncode}"
        return result

    # manim 0.22 rejects -o when the entry file defines several scenes, so the clip is <ClassName>.mp4
    produced = sorted((work / "media" / "videos").rglob(f"{SCENE_CLASSES[template]}.mp4"))
    produced = [p for p in produced if "partial_movie_files" not in p.parts]
    if not produced:
        result.message = "manim succeeded but no output mp4 was found"
        return result
    final.unlink(missing_ok=True)
    shutil.move(str(produced[0]), final)
    shutil.rmtree(work, ignore_errors=True)

    # Expected length is the frame-quantised schedule, which is within half a frame of the target.
    expected = target_frames(job["durationSeconds"], profile.fps) / profile.fps
    check = check_clip(final, profile.width, profile.height, profile.fps, expected, ffprobe)
    result.output = str(final)
    if check.probe:
        result.probe = {k: getattr(check.probe, k) for k in ("codec", "width", "height", "fps", "duration_s", "frames")}
    if not check.ok:
        result.problems = check.problems
        result.message = "output failed probe checks"
        return result
    if abs(expected - job["durationSeconds"]) > 1.0 / profile.fps:
        result.problems = [f"scheduled {job['durationSeconds']}s cannot be met within 1 frame"]
        result.message = "duration mismatch"
        return result
    result.status = "rendered"
    result.message = f"{check.probe.width}x{check.probe.height}@{check.probe.fps:g} {check.probe.duration_s:.3f}s"
    return result


def render_scenes(spec: dict, durations: dict[str, float], out_dir: Path, profile: Profile,
                  only: set[str] | None = None, workers: int = 4, timeout_s: float = 900.0,
                  on_result=None) -> list[SceneResult]:
    """Render every manim scene (or the ``only`` subset). Blender scenes are skipped (M01.4)."""
    out_dir = Path(out_dir)
    manim, ffprobe = check_prerequisites()
    (out_dir / "scenes").mkdir(parents=True, exist_ok=True)
    (out_dir / "logs").mkdir(parents=True, exist_ok=True)

    results: list[SceneResult] = []
    jobs = []
    for scene in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        sid = scene["sceneId"]
        if only and sid not in only:
            continue
        if scene["engine"] != "manim":
            results.append(SceneResult(sid, scene["template"], "skipped",
                                       f"engine={scene['engine']} is rendered in M01.4 (Blender), not by render-scenes"))
            continue
        if scene["template"] not in SCENE_CLASSES:
            results.append(SceneResult(sid, scene["template"], "failed", "no Manim implementation for template"))
            continue
        jobs.append(build_job(spec, scene, durations[sid]))

    for r in results:
        if on_result:
            on_result(r)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(jobs) or 1))) as pool:
        futures = [pool.submit(_render_one, manim, ffprobe, job, out_dir, profile, timeout_s) for job in jobs]
        for f in futures:
            r = f.result()
            if on_result:
                on_result(r)
            results.append(r)
    results.sort(key=lambda r: r.sceneId)
    try:
        (out_dir / ".manim").rmdir()  # only removed when empty; failed scenes keep their work dir
    except OSError:
        pass
    return results
