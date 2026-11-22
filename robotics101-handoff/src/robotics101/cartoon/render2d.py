"""Frame renderer for cartoon clips (M02.4): ``frame_fn(t) -> [Mobject]`` -> Cairo frames -> H.264 via ffmpeg.

Every frame is built from scratch from the timeline time ``t = i / fps`` (no accumulated animation state), so
frames can be rendered in parallel chunks and any frame can be reproduced exactly. Chunks are encoded to
separate MP4s (same codec settings) and concatenated losslessly with the concat demuxer.
"""

from __future__ import annotations

import multiprocessing as mp
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import numpy as np
from manim import Camera, Mobject, tempconfig

FrameFn = Callable[[float], list[Mobject]]
FRAME_W = 14.222222222222221
FRAME_H = 8.0


def _config(width: int, height: int, background: str) -> dict:
    return {"pixel_width": width, "pixel_height": height, "frame_width": FRAME_W, "frame_height": FRAME_H,
            "background_color": background, "disable_caching": True}


def frame_rgb(mobjects: list[Mobject], width: int, height: int, background: str) -> np.ndarray:
    with tempconfig(_config(width, height, background)):
        cam = Camera(background_color=background)
        cam.capture_mobjects(mobjects)
        return np.asarray(cam.get_image().convert("RGB"))


_FRAME_FN: FrameFn | None = None      # set before forking workers (closures can't be pickled)


def _encode_chunk(args) -> str:
    i0, i1, fps, width, height, background, out, crf = args
    frame_fn = _FRAME_FN
    ffmpeg = shutil.which("ffmpeg")
    cmd = [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-profile:v", "high",
           "-pix_fmt", "yuv420p", "-threads", "2", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    with tempconfig(_config(width, height, background)):
        cam = Camera(background_color=background)
        for i in range(i0, i1):
            cam.reset()
            cam.capture_mobjects(frame_fn(i / fps))
            try:
                proc.stdin.write(np.asarray(cam.get_image().convert("RGB")).tobytes())
            except BrokenPipeError:
                break
    proc.stdin.close()
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg chunk {i0}-{i1} failed: {err[:400]}")
    return str(out)


def render_clip(frame_fn: FrameFn, n_frames: int, out_mp4: Path, *, fps: int = 30, width: int = 1920,
                height: int = 1080, background: str = "#FFE8C2", workers: int | None = None, crf: int = 18,
                audio_wav: Path | None = None) -> Path:
    """Render ``n_frames`` frames to ``out_mp4`` (H.264 High yuv420p; AAC 48 kHz stereo when ``audio_wav``)."""
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(workers or max(1, (os.cpu_count() or 2) // 2), n_frames // 30 or 1))
    bounds = [round(n_frames * k / workers) for k in range(workers + 1)]
    with tempfile.TemporaryDirectory() as td:
        global _FRAME_FN
        _FRAME_FN = frame_fn
        jobs = [(bounds[k], bounds[k + 1], fps, width, height, background, Path(td) / f"c{k:03d}.mp4", crf)
                for k in range(workers) if bounds[k + 1] > bounds[k]]
        if len(jobs) == 1:
            parts = [_encode_chunk(jobs[0])]
        else:
            with mp.get_context("fork").Pool(len(jobs)) as pool:
                parts = pool.map(_encode_chunk, jobs)
        lst = Path(td) / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        video = Path(td) / "video.mp4"
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        str(video)], check=True)
        if audio_wav:
            n_samples = round(n_frames / fps * 48000)
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(audio_wav),
                            "-filter_complex", f"[1:a]aresample=48000,pan=stereo|c0=c0|c1=c0,apad=whole_len={n_samples},"
                            f"atrim=end_sample={n_samples}[a]", "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart", str(out_mp4)],
                           check=True)
        else:
            shutil.copyfile(video, out_mp4)
    return out_mp4
