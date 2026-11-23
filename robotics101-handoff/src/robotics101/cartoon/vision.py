"""Pixel-level checks on rendered video (M03): low-resolution grey frames decoded with ffmpeg.

Used by cartoon QA for transitions (no hard cuts), concept cards, burned-in subtitles and static-hold detection.
Frames are numpy ``uint8`` arrays of shape (h, w); differences are mean absolute grey-level differences (0..255).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Iterator

import numpy as np

FPS = 30
W, H = 192, 108


def frame_at(video: Path, n: int, w: int = W, h: int = H, fps: int = FPS) -> np.ndarray:
    t = max(0.0, (n - 0.25) / fps)
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", str(video), "-frames:v", "1",
                        "-vf", f"scale={w}:{h}:flags=area", "-pix_fmt", "gray", "-f", "rawvideo", "-"],
                       capture_output=True, check=True)
    if len(p.stdout) < w * h:
        raise ValueError(f"no frame {n} in {video}")
    return np.frombuffer(p.stdout[: w * h], np.uint8).reshape(h, w)


def frame_rgb_at(video: Path, n: int, fps: int = FPS) -> np.ndarray:
    """Full-resolution RGB frame ``n`` (h, w, 3)."""
    t = max(0.0, (n - 0.25) / fps)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=p=0", str(video)], capture_output=True, text=True, check=True)
    w, h = (int(x) for x in probe.stdout.strip().split(",")[:2])
    p = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", str(video), "-frames:v", "1",
                        "-pix_fmt", "rgb24", "-f", "rawvideo", "-"], capture_output=True, check=True)
    if len(p.stdout) < w * h * 3:
        raise ValueError(f"no frame {n} in {video}")
    return np.frombuffer(p.stdout[: w * h * 3], np.uint8).reshape(h, w, 3)


def frames_at(video: Path, indices, w: int = W, h: int = H) -> dict[int, np.ndarray]:
    return {int(n): frame_at(video, int(n), w, h) for n in sorted(set(indices))}


def diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a.astype(np.int16) - b.astype(np.int16))))


def stream_gray(video: Path, w: int = W, h: int = H, fps: int | None = None) -> Iterator[np.ndarray]:
    """Every frame (or ``fps`` resampled) of ``video`` as small grey arrays, streamed."""
    vf = f"scale={w}:{h}:flags=area" + (f",fps={fps}" if fps else "")
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vf", vf, "-pix_fmt", "gray", "-f", "rawvideo",
                          "-"], stdout=subprocess.PIPE)
    try:
        size = w * h
        while True:
            buf = p.stdout.read(size)
            if len(buf) < size:
                break
            yield np.frombuffer(buf, np.uint8).reshape(h, w)
    finally:
        p.stdout.close()
        p.wait()


__all__ = ["diff", "frame_at", "frame_rgb_at", "frames_at", "stream_gray"]
