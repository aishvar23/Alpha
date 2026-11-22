"""Thumbnail (M01.6): one representative frame of ``final.mp4`` + the episode title -> ``thumbnail.png``.

1280x720 PNG (YouTube's recommended size, well under its 2 MB limit). The frame is taken from the 3D
demo scene when there is one (≈10 s in, around the "obstacle detected" beat), else from the middle of
the video. The title is drawn with ffmpeg ``drawtext`` on a dark band; if no font file can be found the
band is drawn without text (the thumbnail is still valid, just untitled). Pure ffmpeg, no extra deps.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from robotics101.media import MediaError, run

THUMB_W, THUMB_H = 1280, 720
THUMB_NAME = "thumbnail.png"
FONT_CANDIDATES = ("Inter:bold", "DejaVu Sans:bold", "sans-serif:bold")


def pick_thumbnail_time(spec: dict, segments: list[dict]) -> float:
    """Seconds into final.mp4: first blender scene start + min(10 s, half its length), else the middle."""
    engines = {s["sceneId"]: s.get("engine") for s in spec.get("scenes", [])}
    for seg in segments:
        if engines.get(seg["sceneId"]) == "blender":
            return round(seg["start_s"] + min(10.0, (seg["end_s"] - seg["start_s"]) / 2), 3)
    if not segments:
        return 0.0
    return round((segments[0]["start_s"] + segments[-1]["end_s"]) / 2, 3)


def find_font_file() -> str | None:
    fc = shutil.which("fc-match")
    if not fc:
        return None
    for pattern in FONT_CANDIDATES:
        try:
            out = subprocess.run([fc, "-f", "%{file}", pattern], capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        if out and Path(out).is_file():
            return out
    return None


def _escape_drawtext(s: str) -> str:
    # drawtext text= value inside a single-quoted filter argument
    return s.replace("\\", "\\\\").replace("'", "\u2019").replace(":", "\\:").replace("%", "\\%")


def thumbnail_filter(title: str, font_file: str | None, w: int = THUMB_W, h: int = THUMB_H) -> str:
    band_h = int(h * 0.22)
    vf = [f"scale={w}:{h}:force_original_aspect_ratio=decrease", f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0f1724",
          f"drawbox=x=0:y={h - band_h}:w={w}:h={band_h}:color=0x0f1724@0.88:t=fill"]
    if font_file:
        ff = font_file.replace("\\", "/").replace(":", "\\:").replace("'", "")
        vf.append(f"drawtext=fontfile='{ff}':text='{_escape_drawtext(title)}':fontcolor=white:fontsize={int(h * 0.075)}"
                  f":x=(w-text_w)/2:y={h - band_h}+({band_h}-text_h)/2")
    return ",".join(vf)


def make_thumbnail(final: Path, out_png: Path, title: str, at_s: float, ffmpeg: str = "ffmpeg") -> Path:
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(final), "-frames:v", "1",
           "-vf", thumbnail_filter(title, find_font_file()), str(out_png)]
    run(cmd, timeout=120, what="ffmpeg thumbnail")
    if not out_png.is_file() or out_png.stat().st_size == 0:
        raise MediaError(f"thumbnail not written: {out_png}")
    return out_png


def thumbnail_title(spec: dict) -> str:
    n = spec.get("episodeNumber")
    t = spec.get("title") or spec.get("episodeId", "")
    return f"Ep. {n}: {t}" if n else t


__all__ = ["THUMB_H", "THUMB_NAME", "THUMB_W", "make_thumbnail", "pick_thumbnail_time", "thumbnail_filter",
           "thumbnail_title"]
