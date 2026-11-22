"""Shared FFmpeg/ffprobe helpers for the composer, QA and manifest (M01.5).

Everything here shells out to local ``ffmpeg``/``ffprobe`` binaries only; no network.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

FFMPEG_PREREQS = "ffmpeg + ffprobe are required on PATH (tested with 7.1; Debian/Ubuntu: apt-get install ffmpeg)."


class MediaError(RuntimeError):
    pass


def find_ffmpeg() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise MediaError("ffmpeg/ffprobe not found. " + FFMPEG_PREREQS)
    return ffmpeg, ffprobe


MIN_FFMPEG = (5, 1)  # -fps_mode, alimiter latency=


def ffmpeg_version(ffmpeg: str) -> tuple[int, int] | None:
    try:
        out = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else None


def check_ffmpeg() -> tuple[str, str]:
    """find_ffmpeg + minimum version (unparseable versions, e.g. git builds, are accepted)."""
    ffmpeg, ffprobe = find_ffmpeg()
    v = ffmpeg_version(ffmpeg)
    if v is not None and v < MIN_FFMPEG:
        raise MediaError(f"{ffmpeg} is FFmpeg {v[0]}.{v[1]}; need >= {MIN_FFMPEG[0]}.{MIN_FFMPEG[1]}. " + FFMPEG_PREREQS)
    return ffmpeg, ffprobe


def run(cmd: list[str], timeout: float = 1800.0, what: str = "ffmpeg") -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise MediaError(f"{what} timed out after {timeout:.0f}s: {' '.join(cmd)}") from e
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise MediaError(f"{what} failed (exit {proc.returncode}): {' '.join(cmd)}\n{tail}")
    return proc


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------- ffprobe

def ffprobe_json(path: Path, ffprobe: str | None = None, count_frames: bool = False) -> dict:
    ffprobe = ffprobe or find_ffmpeg()[1]
    cmd = [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json"]
    if count_frames:
        cmd.append("-count_frames")
    cmd.append(str(path))
    proc = run(cmd, timeout=300, what="ffprobe")
    return json.loads(proc.stdout or "{}")


def _rate(s: str | None) -> float:
    if not s or s in ("0/0", "N/A"):
        return 0.0
    return float(Fraction(s))


def _f(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class MediaSummary:
    format: str
    duration_s: float
    bit_rate: int | None
    video: dict | None      # codec, profile, pix_fmt, width, height, fps, avg_fps, duration_s, frames
    audio: dict | None      # codec, sample_rate, channels, channel_layout, duration_s, bit_rate

    def to_dict(self) -> dict:
        return {"format": self.format, "duration_s": self.duration_s, "bit_rate": self.bit_rate,
                "video": self.video, "audio": self.audio}


def summarize(path: Path, ffprobe: str | None = None, count_frames: bool = False) -> MediaSummary:
    """Compact stream summary. ``count_frames`` decodes the video (slow but proves decodability)."""
    data = ffprobe_json(path, ffprobe, count_frames)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    video = audio = None
    if v is not None:
        frames = v.get("nb_read_frames") if count_frames else v.get("nb_frames")
        video = {
            "codec": v.get("codec_name"), "profile": v.get("profile"), "pix_fmt": v.get("pix_fmt"),
            "width": int(v.get("width", 0)), "height": int(v.get("height", 0)),
            "fps": round(_rate(v.get("r_frame_rate")), 6), "avg_fps": round(_rate(v.get("avg_frame_rate")), 6),
            "duration_s": _f(v.get("duration")), "frames": int(frames) if str(frames or "").isdigit() else None,
        }
    if a is not None:
        audio = {
            "codec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate", 0) or 0),
            "channels": int(a.get("channels", 0) or 0), "channel_layout": a.get("channel_layout"),
            "duration_s": _f(a.get("duration")), "bit_rate": int(a["bit_rate"]) if str(a.get("bit_rate", "")).isdigit() else None,
        }
    br = fmt.get("bit_rate")
    return MediaSummary(format=fmt.get("format_name", ""), duration_s=_f(fmt.get("duration")) or 0.0,
                        bit_rate=int(br) if str(br or "").isdigit() else None, video=video, audio=audio)


# ---------------------------------------------------------------- loudness / levels

TARGET_LUFS = -16.0
LIMIT_DBFS = -1.5
SILENCE_LUFS = -70.0   # EBU R128 absolute gate: anything at/below is treated as silence


def loudness_gain_db(integrated_lufs: float | None, target: float = TARGET_LUFS) -> float | None:
    """Linear make-up gain to reach ``target`` LUFS, or None for silent/unmeasurable input."""
    if integrated_lufs is None or integrated_lufs <= SILENCE_LUFS:
        return None
    return round(target - integrated_lufs, 2)


def gain_limiter_filter(gain_db: float | None, limit_dbfs: float = LIMIT_DBFS) -> str:
    """``volume`` (measured gain) + brick-wall ``alimiter`` (no auto-levelling, latency-compensated)."""
    limit = 10 ** (limit_dbfs / 20)
    vol = f"volume={gain_db:+.2f}dB," if gain_db is not None else ""
    return f"{vol}alimiter=limit={limit:.6f}:attack=5:release=50:level=0:latency=1"


@dataclass
class Levels:
    mean_volume_db: float | None
    max_volume_db: float | None
    integrated_lufs: float | None = None
    true_peak_dbfs: float | None = None
    loudness_range_lu: float | None = None

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _last_float(pattern: str, text: str) -> float | None:
    found = re.findall(pattern, text)
    if not found:
        return None
    try:
        return float(found[-1])
    except ValueError:
        return None  # e.g. "-inf"


def audio_levels(path: Path, ffmpeg: str | None = None, ebur128: bool = True, prefilter: str | None = None) -> Levels:
    """volumedetect (mean/max dBFS) and optionally EBU R128 integrated loudness + true peak, one decode pass.

    ``prefilter`` runs before the meters (e.g. the composer's resample/upmix, so the measurement matches
    the signal that gets the gain)."""
    ffmpeg = ffmpeg or find_ffmpeg()[0]
    af = "ebur128=peak=true:framelog=quiet,volumedetect" if ebur128 else "volumedetect"
    if prefilter:
        af = f"{prefilter},{af}"
    proc = run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", af, "-f", "null", "-"],
               timeout=600, what="ffmpeg volumedetect")
    err = proc.stderr
    lv = Levels(_last_float(r"mean_volume:\s*(-?[\d.]+|-inf) dB", err), _last_float(r"max_volume:\s*(-?[\d.]+|-inf) dB", err))
    if ebur128:
        summary = err[err.rfind("Summary:"):] if "Summary:" in err else ""
        lv.integrated_lufs = _last_float(r"I:\s*(-?[\d.]+) LUFS", summary)
        lv.loudness_range_lu = _last_float(r"LRA:\s*(-?[\d.]+) LU\b", summary)
        lv.true_peak_dbfs = _last_float(r"Peak:\s*(-?[\d.]+|-inf) dBFS", summary)
    return lv


# ---------------------------------------------------------------- MP4 structure

def mp4_top_level_atoms(path: Path, limit: int = 64) -> list[str]:
    """Top-level box types in file order (enough to confirm +faststart: moov before mdat)."""
    atoms: list[str] = []
    size_total = Path(path).stat().st_size
    with open(path, "rb") as f:
        pos = 0
        while pos < size_total and len(atoms) < limit:
            f.seek(pos)
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            size, typ = struct.unpack(">I4s", hdr)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = size_total - pos
            atoms.append(typ.decode("latin-1"))
            if size < 8:
                break
            pos += size
    return atoms


def is_faststart(path: Path) -> bool:
    atoms = mp4_top_level_atoms(path)
    return "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat")


# ---------------------------------------------------------------- tool versions

def _first_line(cmd: list[str]) -> str | None:
    exe = shutil.which(cmd[0]) if not Path(cmd[0]).is_absolute() else cmd[0]
    if not exe:
        return None
    try:
        p = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (p.stdout or p.stderr).strip().splitlines()
    return out[0].strip() if out else None


def tool_versions() -> dict:
    """Versions of every tool that can touch the bundle (None = not installed)."""
    try:
        from importlib.metadata import PackageNotFoundError, version
        try:
            manim = version("manim")
        except PackageNotFoundError:
            manim = None
    except ImportError:  # pragma: no cover
        manim = None
    from robotics101 import __version__
    import os
    blender_bin = os.environ.get("BLENDER_BIN") or shutil.which("blender")
    blender = None
    if blender_bin:
        line = _first_line([blender_bin, "--background", "--factory-startup", "--version"])
        blender = line
    return {
        "robotics101": __version__,
        "python": sys.version.split()[0],
        "manim": manim,
        "blender": blender,
        "ffmpeg": _first_line(["ffmpeg", "-version"]),
        "ffprobe": _first_line(["ffprobe", "-version"]),
        "espeak-ng": _first_line(["espeak-ng", "--version"]),
    }
