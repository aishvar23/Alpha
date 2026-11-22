"""Compose the episode: per-scene narration mix + video clip -> ``clips/<sceneId>.mp4`` -> ``final.mp4``.

Timeline model (A/V sync by construction)
-----------------------------------------
* Each scene's length is its clip's **actual frame count** N (render-scenes guarantees N is within one
  frame of ``timing.json``'s ``scene_duration_s``; anything else is a ComposeError).
* Its audio is built sample-exactly to N × 48000/30 samples: the narration WAV resampled/upmixed to
  48 kHz stereo, loudness-normalised (EBU R128 integrated loudness measured on that same stereo
  signal -> linear ``volume`` gain to -16 LUFS, then a brick-wall ``alimiter`` at -1.5 dBFS so the
  gain can never clip), delayed by the scene's lead-in (``narration_start_s - scene_start_s``) and
  padded with silence; 5 ms fades at both ends avoid clicks at the hard cuts. (Two-pass ``loudnorm``
  was tried first: with hot espeak peaks it falls back to dynamic mode and, in this chain under
  FFmpeg 7.1, emitted silence — the QA silent-audio gate caught it.)
* ``clips/<sceneId>.mp4`` = the scene video (stream copy) + that audio as AAC — a reviewable unit.
* ``final.mp4`` = the clips' video joined with the ``concat`` filter and re-encoded once
  (H.264 High, yuv420p, CFR 30 fps, +faststart), muxed with the losslessly concatenated per-scene
  PCM mixes encoded once as AAC 48 kHz stereo 192 kb/s. Video and audio therefore have the same
  length (to within AAC frame padding, < 22 ms) and scene boundaries fall on frame boundaries.
* ``captions.srt`` is regenerated on the same frame-quantised timeline (identical to ``narrate``'s
  when scene durations are whole frames).

Transitions are hard cuts (no crossfades), so the ``timing.json`` timeline needs no adjustment.
"""

from __future__ import annotations

import json
import shutil
import time
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path

from robotics101.animation.render import Profile
from robotics101.animation.timing import target_frames
from robotics101.media import (
    LIMIT_DBFS,
    TARGET_LUFS,
    MediaError,
    audio_levels,
    find_ffmpeg,
    gain_limiter_filter,
    loudness_gain_db,
    run,
    summarize,
)
from robotics101.narration.captions import build_srt, scene_cues

AUDIO_RATE = 48_000
AUDIO_CHANNELS = 2
AUDIO_BITRATE = "192k"
EDGE_FADE_S = 0.005
DEFAULT_CRF = 20
DEFAULT_PRESET = "medium"


class ComposeError(RuntimeError):
    pass


@dataclass
class SceneSegment:
    sceneId: str
    sequence: int
    template: str
    engine: str
    scheduled_duration_s: float      # timing.json scene_duration_s
    frames: int                      # actual frames in scenes/<sceneId>.mp4
    duration_s: float                # frames / fps (what the final uses)
    start_s: float                   # on the final timeline (frame-quantised)
    end_s: float
    narration_offset_s: float        # lead-in inside the scene
    narration_audio_s: float
    audio_samples: int
    loudness_input: dict = field(default_factory=dict)   # EBU R128 of the narration (stereo, before gain)
    gain_db: float | None = None                         # None = silent input, left as is
    scene_video: str = ""
    narration_wav: str = ""
    clip: str = ""


@dataclass
class ComposeResult:
    episodeId: str
    profile: dict
    fps: int
    total_frames: int
    total_duration_s: float
    scheduled_total_s: float
    final: str
    captions: str
    segments: list[SceneSegment]
    elapsed_s: float
    settings: dict

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------- commands (pure, testable)

def upmix_filter(rate: int = AUDIO_RATE) -> str:
    return f"aresample={rate},aformat=sample_fmts=fltp:channel_layouts=stereo"


def scene_audio_filter(gain_db: float | None, offset_samples: int, total_samples: int, rate: int = AUDIO_RATE) -> str:
    """Narration -> 48 kHz stereo, gain + limiter, delayed by ``offset_samples``, exactly ``total_samples`` long."""
    dur = total_samples / rate
    chain = [
        upmix_filter(rate),
        gain_limiter_filter(gain_db),
        f"adelay={offset_samples}S:all=1",
        f"apad=whole_len={total_samples}",
        f"atrim=end_sample={total_samples}",
        "asetpts=PTS-STARTPTS",
        f"afade=t=in:st=0:d={EDGE_FADE_S}",
        f"afade=t=out:st={max(0.0, dur - EDGE_FADE_S):.6f}:d={EDGE_FADE_S}",
        "aformat=sample_fmts=s16:channel_layouts=stereo",
    ]
    return ",".join(chain)


def clip_mux_command(ffmpeg: str, video: Path, audio_wav: Path, out: Path) -> list[str]:
    return [ffmpeg, "-y", "-hide_banner", "-v", "error", "-i", str(video), "-i", str(audio_wav),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
            "-map_metadata", "-1", "-movflags", "+faststart", str(out)]


def final_encode_command(ffmpeg: str, clips: list[Path], episode_wav: Path, out: Path, profile: Profile,
                         total_frames: int, crf: int = DEFAULT_CRF, preset: str = DEFAULT_PRESET,
                         title: str = "") -> list[str]:
    n = len(clips)
    parts = [f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]" for i in range(n)]
    parts.append("".join(f"[v{i}]" for i in range(n)) +
                 f"concat=n={n}:v=1:a=0,fps={profile.fps},"
                 f"scale={profile.width}:{profile.height}:flags=lanczos,setsar=1,format=yuv420p[v]")
    cmd = [ffmpeg, "-y", "-hide_banner", "-v", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-i", str(episode_wav),
            "-filter_complex", ";".join(parts),
            "-map", "[v]", "-map", f"{n}:a:0",
            "-c:v", "libx264", "-profile:v", "high", "-preset", preset, "-crf", str(crf), "-tune", "animation",
            "-pix_fmt", "yuv420p", "-r", str(profile.fps), "-fps_mode", "cfr",
            "-g", str(2 * profile.fps), "-frames:v", str(total_frames),
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", str(AUDIO_RATE), "-ac", str(AUDIO_CHANNELS),
            "-map_metadata", "-1", "-metadata", f"title={title}",
            "-movflags", "+faststart", str(out)]
    return cmd


# ---------------------------------------------------------------- helpers

def concat_wavs(parts: list[Path], out: Path) -> int:
    """Sample-exact PCM concatenation (all parts must share rate/channels/width). Returns total samples."""
    params = None
    total = 0
    with wave.open(str(out), "wb") as w:
        for p in parts:
            with wave.open(str(p), "rb") as r:
                pr = (r.getnchannels(), r.getsampwidth(), r.getframerate())
                if params is None:
                    params = pr
                    w.setnchannels(pr[0])
                    w.setsampwidth(pr[1])
                    w.setframerate(pr[2])
                elif pr != params:
                    raise ComposeError(f"{p}: audio format {pr} differs from {params}")
                n = r.getnframes()
                w.writeframes(r.readframes(n))
                total += n
    return total


def wav_samples(path: Path) -> int:
    with wave.open(str(path), "rb") as r:
        return r.getnframes()


def _scene_plan(spec: dict, timing: dict, out_dir: Path, profile: Profile, ffprobe: str) -> list[SceneSegment]:
    if timing.get("episodeId") != spec.get("episodeId"):
        raise ComposeError(f"timing.json is for {timing.get('episodeId')!r}, spec is {spec.get('episodeId')!r}; "
                           "re-run narrate")
    by_id = {s["sceneId"]: s for s in timing.get("scenes", [])}
    segs: list[SceneSegment] = []
    t_frames = 0
    problems: list[str] = []
    for scene in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        sid = scene["sceneId"]
        st = by_id.get(sid)
        if st is None:
            problems.append(f"{sid}: missing from timing.json (re-run narrate)")
            continue
        video = out_dir / "scenes" / f"{sid}.mp4"
        wav = out_dir / "audio" / f"{sid}.wav"
        if not video.is_file():
            problems.append(f"{sid}: scene clip {video} missing (run render-scenes)")
            continue
        if not wav.is_file():
            problems.append(f"{sid}: narration {wav} missing (run narrate)")
            continue
        try:
            s = summarize(video, ffprobe)
        except MediaError as e:
            problems.append(f"{sid}: {e}")
            continue
        v = s.video
        if v is None:
            problems.append(f"{sid}: {video} has no video stream")
            continue
        if (v["width"], v["height"]) != (profile.width, profile.height):
            problems.append(f"{sid}: {v['width']}x{v['height']}, profile {profile.name} needs "
                            f"{profile.width}x{profile.height} (re-render scenes with --profile {profile.name})")
        if abs(v["fps"] - profile.fps) > 0.01:
            problems.append(f"{sid}: {v['fps']} fps, expected {profile.fps}")
        frames = v["frames"] or round((v["duration_s"] or s.duration_s) * profile.fps)
        sched = float(st["scene_duration_s"])
        expected = target_frames(sched, profile.fps)
        if abs(frames - expected) > 1:
            problems.append(f"{sid}: {frames} frames, timing.json needs {expected} ({sched}s); stale clip? "
                            "re-run render-scenes")
        offset = round(float(st["narration_start_s"]) - float(st["scene_start_s"]), 6)
        audio_s = float(st["audio_duration_s"])
        dur = frames / profile.fps
        if offset < 0 or offset + audio_s > dur + 1.0 / profile.fps:
            problems.append(f"{sid}: narration {offset:.3f}+{audio_s:.3f}s does not fit the {dur:.3f}s clip")
        segs.append(SceneSegment(
            sceneId=sid, sequence=scene["sequence"], template=scene["template"], engine=scene["engine"],
            scheduled_duration_s=sched, frames=frames, duration_s=round(dur, 6),
            start_s=round(t_frames / profile.fps, 6), end_s=round((t_frames + frames) / profile.fps, 6),
            narration_offset_s=offset, narration_audio_s=audio_s,
            audio_samples=frames * AUDIO_RATE // profile.fps,
            scene_video=str(video), narration_wav=str(wav),
            clip=str(out_dir / "clips" / f"{sid}.mp4")))
        t_frames += frames
    if problems:
        raise ComposeError("cannot compose:\n  - " + "\n  - ".join(problems))
    if AUDIO_RATE % profile.fps:
        raise ComposeError(f"{AUDIO_RATE} Hz is not a whole number of samples per frame at {profile.fps} fps")
    return segs


# ---------------------------------------------------------------- main entry

def compose_episode(spec: dict, timing: dict, out_dir: Path, profile: Profile, *,
                    crf: int = DEFAULT_CRF, preset: str = DEFAULT_PRESET, log=print) -> ComposeResult:
    """Build clips/<sceneId>.mp4, final.mp4, captions.srt and compose.json in ``out_dir``."""
    t0 = time.monotonic()
    out_dir = Path(out_dir)
    ffmpeg, ffprobe = find_ffmpeg()
    segs = _scene_plan(spec, timing, out_dir, profile, ffprobe)

    work = out_dir / ".compose"
    clips_dir = out_dir / "clips"
    for d in (work, clips_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    final = out_dir / "final.mp4"
    final.unlink(missing_ok=True)

    mixes = []
    try:
        for seg in segs:
            measured = audio_levels(Path(seg.narration_wav), ffmpeg, prefilter=upmix_filter())
            seg.loudness_input = {"integrated_lufs": measured.integrated_lufs,
                                  "true_peak_dbfs": measured.true_peak_dbfs, "max_volume_db": measured.max_volume_db}
            seg.gain_db = loudness_gain_db(measured.integrated_lufs)
            mix = work / f"{seg.sceneId}.wav"
            af = scene_audio_filter(seg.gain_db, round(seg.narration_offset_s * AUDIO_RATE), seg.audio_samples)
            run([ffmpeg, "-y", "-hide_banner", "-v", "error", "-i", seg.narration_wav, "-af", af,
                 "-c:a", "pcm_s16le", "-ar", str(AUDIO_RATE), str(mix)], what=f"ffmpeg audio mix {seg.sceneId}")
            got = wav_samples(mix)
            if got != seg.audio_samples:
                raise ComposeError(f"{seg.sceneId}: mixed audio has {got} samples, expected {seg.audio_samples}")
            mixes.append(mix)
            run(clip_mux_command(ffmpeg, Path(seg.scene_video), mix, Path(seg.clip)),
                what=f"ffmpeg clip mux {seg.sceneId}")
            log(f"  [clip] {seg.sceneId}: {seg.frames} frames ({seg.duration_s:.3f}s), narration at "
                f"+{seg.narration_offset_s:.2f}s, narration {measured.integrated_lufs} LUFS"
                + (f", gain {seg.gain_db:+.2f} dB" if seg.gain_db is not None else " (silent: no gain)"))

        episode_wav = work / "episode.wav"
        total_samples = concat_wavs(mixes, episode_wav)
        total_frames = sum(s.frames for s in segs)
        if total_samples != total_frames * AUDIO_RATE // profile.fps:
            raise ComposeError(f"episode audio {total_samples} samples != video {total_frames} frames")
        cmd = final_encode_command(ffmpeg, [Path(s.clip) for s in segs], episode_wav, final, profile,
                                   total_frames, crf, preset, title=spec.get("title", ""))
        t_enc = time.monotonic()
        log(f"  [final] encoding {total_frames} frames ({total_frames / profile.fps:.2f}s) "
            f"{profile.width}x{profile.height} H.264 High crf {crf} {preset} + AAC {AUDIO_BITRATE} ...")
        run(cmd, timeout=3600, what="ffmpeg final encode")
        log(f"  [final] {final} ({time.monotonic() - t_enc:.1f}s)")
    except MediaError as e:
        raise ComposeError(str(e)) from e

    # captions on the frame-quantised final timeline
    narration = {s["sceneId"]: s.get("narration", "") for s in spec["scenes"]}
    cues = []
    for seg in segs:
        a = seg.start_s + seg.narration_offset_s
        cues += scene_cues(narration[seg.sceneId], a, a + seg.narration_audio_s)
    captions = out_dir / "captions.srt"
    captions.write_text(build_srt(cues), encoding="utf-8")

    shutil.rmtree(work, ignore_errors=True)
    result = ComposeResult(
        episodeId=spec["episodeId"], profile=asdict(profile), fps=profile.fps, total_frames=total_frames,
        total_duration_s=round(total_frames / profile.fps, 6),
        scheduled_total_s=round(sum(s.scheduled_duration_s for s in segs), 6),
        final=str(final), captions=str(captions), segments=segs, elapsed_s=round(time.monotonic() - t0, 2),
        settings={"video": {"codec": "libx264", "profile": "high", "pix_fmt": "yuv420p", "crf": crf,
                            "preset": preset, "tune": "animation", "gop": 2 * profile.fps, "fps_mode": "cfr"},
                  "audio": {"codec": "aac", "bitrate": AUDIO_BITRATE, "sample_rate": AUDIO_RATE,
                            "channels": AUDIO_CHANNELS,
                            "loudness": f"per-scene EBU R128 gain to {TARGET_LUFS} LUFS + alimiter {LIMIT_DBFS} dBFS",
                            "edge_fade_s": EDGE_FADE_S},
                  "transitions": "hard cuts", "movflags": "+faststart"},
    )
    (out_dir / "compose.json").write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    return result
