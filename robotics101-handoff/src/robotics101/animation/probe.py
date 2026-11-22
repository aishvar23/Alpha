"""ffprobe-based checks for rendered scene clips (reusable by the M01.5 QA report)."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path


class ProbeError(RuntimeError):
    pass


@dataclass
class VideoProbe:
    path: str
    codec: str
    width: int
    height: int
    fps: float
    duration_s: float
    frames: int
    has_audio: bool


@dataclass
class ClipCheck:
    probe: VideoProbe | None
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.probe is not None and not self.problems


def probe_video(path: Path, ffprobe: str | None = None) -> VideoProbe:
    """Probe ``path`` with ffprobe, counting decoded frames (so a corrupt file fails here)."""
    ffprobe = ffprobe or shutil.which("ffprobe")
    if not ffprobe:
        raise ProbeError("ffprobe not found on PATH (install ffmpeg, e.g. `apt-get install ffmpeg`)")
    cmd = [ffprobe, "-v", "error", "-count_frames", "-show_entries",
           "stream=codec_type,codec_name,width,height,avg_frame_rate,r_frame_rate,nb_read_frames:format=duration",
           "-of", "json", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed on {path}: {proc.stderr.strip() or proc.returncode}")
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ProbeError(f"{path} has no video stream")
    # r_frame_rate is the nominal stream rate; avg_frame_rate is derived from the (rounded)
    # container duration and drifts slightly (e.g. 30.02) for short clips.
    rate = video.get("r_frame_rate") or video.get("avg_frame_rate") or "0/1"
    fps = float(Fraction(rate)) if rate != "0/0" else 0.0
    frames = int(video.get("nb_read_frames") or 0)
    return VideoProbe(
        path=str(path), codec=video.get("codec_name", ""), width=int(video.get("width", 0)),
        height=int(video.get("height", 0)), fps=fps,
        duration_s=float(data.get("format", {}).get("duration") or 0.0), frames=frames,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
    )


def check_clip(path: Path, width: int, height: int, fps: int, duration_s: float,
               ffprobe: str | None = None) -> ClipCheck:
    """Resolution, frame rate, decodability and duration within one frame of ``duration_s``."""
    if not Path(path).is_file():
        return ClipCheck(None, [f"missing output {path}"])
    try:
        p = probe_video(path, ffprobe)
    except (ProbeError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        return ClipCheck(None, [str(e)])
    problems = []
    if (p.width, p.height) != (width, height):
        problems.append(f"resolution {p.width}x{p.height}, expected {width}x{height}")
    if abs(p.fps - fps) > 0.01:
        problems.append(f"frame rate {p.fps:.3f}, expected {fps}")
    if p.frames <= 0:
        problems.append("no decodable video frames")
    frame = 1.0 / fps
    decoded_s = p.frames / fps if fps else 0.0
    if abs(decoded_s - duration_s) > frame + 1e-6:
        problems.append(f"decoded duration {decoded_s:.3f}s ({p.frames} frames), expected {duration_s:.3f}s "
                        f"(±1 frame)")
    if abs(p.duration_s - duration_s) > frame + 1e-6:
        problems.append(f"container duration {p.duration_s:.3f}s, expected {duration_s:.3f}s (±1 frame)")
    if p.has_audio:
        problems.append("scene clip unexpectedly contains audio (scenes are video-only)")
    return ClipCheck(p, problems)
