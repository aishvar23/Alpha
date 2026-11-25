"""Automated QA for an episode bundle (M01.5) -> ``qa_report.json`` + ``qa_report.md``.

Hard checks (any failure -> status FAIL, non-zero exit) follow the gates in docs/SECURITY_AND_QA.md:
video (decodable, H.264 High yuv420p, resolution, 30 fps CFR), audio (AAC 48 kHz stereo, present, not
silent, no peak clipping), total duration inside the episode length window (default 270–420 s, ADR-034) and equal to the scene timeline, A/V stream
lengths, captions (present, monotonic, inside the video), every scene/clip present with the right
duration, and manifest hashes. Soft warnings: synthetic/fixture TTS, voice coverage < 60 % per scene,
preview profile, loudness off target, missing +faststart.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from robotics101.animation.render import PROFILES, Profile
from robotics101.animation.timing import target_frames
from robotics101.manifest import MANIFEST_NAME, verify_manifest
from robotics101.media import MediaError, audio_levels, find_ffmpeg, is_faststart, summarize
from robotics101.narration.captions import parse_srt, validate_srt
from robotics101.narration.timing import MIN_SPEECH_COVERAGE

DURATION_RANGE_S = (270.0, 420.0)       # default only; see validation.episode_duration_range (ADR-034)
SILENT_MEAN_DB = -60.0          # whole programme mean below this = silent
SILENT_SCENE_MAX_DB = -50.0     # a narrated clip whose peak is below this = silent narration
CLIP_MAX_DB = -0.1              # max_volume must stay below (no peak clipping)
AV_TOLERANCE_S = 0.1
LOUDNESS_TARGET_LUFS, LOUDNESS_TOLERANCE_LU = -16.0, 2.0

PASS, PASS_WITH_WARNINGS, FAIL = "PASS", "PASS_WITH_WARNINGS", "FAIL"


@dataclass
class Check:
    id: str
    severity: str          # hard | soft
    ok: bool
    message: str
    value: object = None

    @property
    def status(self) -> str:
        return "pass" if self.ok else ("fail" if self.severity == "hard" else "warn")

    def to_dict(self) -> dict:
        return {"id": self.id, "severity": self.severity, "status": self.status, "message": self.message,
                "value": self.value}


@dataclass
class QaReport:
    episodeId: str | None
    profile: str
    out_dir: str
    checks: list[Check] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    final: dict = field(default_factory=dict)

    def hard(self, id: str, ok: bool, message: str, value=None) -> bool:
        self.checks.append(Check(id, "hard", bool(ok), message, value))
        return bool(ok)

    def soft(self, id: str, ok: bool, message: str, value=None) -> bool:
        self.checks.append(Check(id, "soft", bool(ok), message, value))
        return bool(ok)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if c.status == "fail"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    @property
    def status(self) -> str:
        return FAIL if self.failures else (PASS_WITH_WARNINGS if self.warnings else PASS)

    def to_dict(self) -> dict:
        return {
            "status": self.status, "episodeId": self.episodeId, "profile": self.profile,
            "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": {"hardFailures": len(self.failures), "warnings": len(self.warnings),
                        "checks": len(self.checks)},
            "final": self.final, "scenes": self.scenes,
            "failures": [c.to_dict() for c in self.failures],
            "warnings": [c.to_dict() for c in self.warnings],
            "checks": [c.to_dict() for c in self.checks],
        }


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def detect_profile(out_dir: Path) -> str | None:
    for name in (MANIFEST_NAME, "compose.json"):
        doc = _load_json(Path(out_dir) / name)
        if doc:
            prof = doc.get("profile")
            if isinstance(prof, dict):
                prof = prof.get("name")
            if prof in PROFILES:
                return prof
    return None


# ---------------------------------------------------------------- the checks

def _check_final(rep: QaReport, out_dir: Path, ffmpeg: str, ffprobe: str, profile, scheduled_total: float | None,
                 expected_frames: int | None) -> float | None:
    final = out_dir / "final.mp4"
    if not rep.hard("final.present", final.is_file(), f"{final.name} exists"):
        return None
    try:
        s = summarize(final, ffprobe, count_frames=True)
    except MediaError as e:
        rep.hard("final.decodable", False, f"ffprobe could not decode final.mp4: {e}")
        return None
    v, a = s.video, s.audio
    rep.final = {"path": "final.mp4", "bytes": final.stat().st_size, "probe": s.to_dict()}
    if not rep.hard("final.decodable", v is not None and (v.get("frames") or 0) > 0,
                    f"ffprobe decoded {v.get('frames') if v else 0} video frames", v.get("frames") if v else 0):
        return None
    rep.hard("final.video_codec", v["codec"] == "h264" and v["profile"] == "High" and v["pix_fmt"] == "yuv420p",
             f"video {v['codec']} {v['profile']} {v['pix_fmt']} (need h264 High yuv420p)",
             [v["codec"], v["profile"], v["pix_fmt"]])
    rep.hard("final.resolution", (v["width"], v["height"]) == (profile.width, profile.height),
             f"{v['width']}x{v['height']} (profile {profile.name}: {profile.width}x{profile.height})",
             f"{v['width']}x{v['height']}")
    rep.hard("final.fps", abs(v["fps"] - profile.fps) < 0.01 and abs(v["avg_fps"] - profile.fps) < 0.05,
             f"r_frame_rate {v['fps']:g}, avg_frame_rate {v['avg_fps']:g} (need constant {profile.fps})", v["fps"])
    video_s = v["frames"] / profile.fps
    if a is None:
        rep.hard("final.audio_present", False, "no audio track")
    else:
        rep.hard("final.audio_present", True, f"audio track {a['codec']} {a['sample_rate']} Hz {a['channels']} ch")
        rep.hard("final.audio_codec", a["codec"] == "aac" and a["sample_rate"] == 48000 and a["channels"] == 2,
                 f"audio {a['codec']} {a['sample_rate']} Hz {a['channels']} ch (need aac 48000 Hz stereo)",
                 [a["codec"], a["sample_rate"], a["channels"]])
        a_s = a["duration_s"] or s.duration_s
        rep.hard("final.av_sync", abs(a_s - video_s) <= AV_TOLERANCE_S,
                 f"audio {a_s:.3f}s vs video {video_s:.3f}s (|Δ| ≤ {AV_TOLERANCE_S}s)", round(a_s - video_s, 4))
        try:
            lv = audio_levels(final, ffmpeg)
        except MediaError as e:
            rep.hard("final.audio_levels", False, f"volumedetect failed: {e}")
            lv = None
        if lv:
            rep.final["levels"] = lv.to_dict()
            rep.hard("final.audio_not_silent", lv.mean_volume_db is not None and lv.mean_volume_db > SILENT_MEAN_DB,
                     f"mean volume {lv.mean_volume_db} dBFS (silent if ≤ {SILENT_MEAN_DB})", lv.mean_volume_db)
            rep.hard("final.no_clipping", lv.max_volume_db is not None and lv.max_volume_db < CLIP_MAX_DB,
                     f"max volume {lv.max_volume_db} dBFS (must be < {CLIP_MAX_DB})", lv.max_volume_db)
            if lv.integrated_lufs is not None:
                rep.soft("final.loudness", abs(lv.integrated_lufs - LOUDNESS_TARGET_LUFS) <= LOUDNESS_TOLERANCE_LU,
                         f"integrated {lv.integrated_lufs} LUFS, true peak {lv.true_peak_dbfs} dBFS "
                         f"(target {LOUDNESS_TARGET_LUFS}±{LOUDNESS_TOLERANCE_LU})", lv.integrated_lufs)
    from robotics101.validation import episode_duration_range_for
    lo, hi = episode_duration_range_for(out_dir)                    # ADR-034: configurable, default 270..420 s
    rep.hard("final.duration_range", lo <= video_s <= hi, f"total {video_s:.3f}s (must be {lo:g}–{hi:g}s)",
             round(video_s, 3))
    frame = 1.0 / profile.fps
    if scheduled_total is not None:
        rep.hard("final.duration_matches_scenes", abs(video_s - scheduled_total) <= 2 * frame + 1e-6,
                 f"final {video_s:.3f}s vs sum of scene durations {scheduled_total:.3f}s (±2 frames)",
                 round(video_s - scheduled_total, 4))
    if expected_frames is not None:
        rep.hard("final.frames_match_clips", v["frames"] == expected_frames,
                 f"{v['frames']} frames, clips total {expected_frames}", v["frames"])
    rep.soft("final.faststart", is_faststart(final), "moov atom before mdat (+faststart)")
    return video_s


def _check_captions(rep: QaReport, out_dir: Path, video_s: float | None) -> None:
    path = out_dir / "captions.srt"
    if not rep.hard("captions.present", path.is_file() and path.stat().st_size > 0, "captions.srt exists, non-empty"):
        return
    try:
        cues = parse_srt(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        rep.hard("captions.parse", False, f"captions.srt does not parse: {e}")
        return
    rep.hard("captions.parse", len(cues) > 0, f"{len(cues)} cues", len(cues))
    bounds = (0, int(round(video_s * 1000))) if video_s else None
    problems = validate_srt(cues, bounds_ms=bounds)
    rep.hard("captions.valid", not problems,
             "monotonic, non-overlapping, within video duration" if not problems else "; ".join(problems[:5]),
             problems[:20] or None)


def _check_scenes(rep: QaReport, out_dir: Path, ffmpeg: str, ffprobe: str, spec: dict | None, timing: dict | None,
                  compose: dict | None, profile) -> tuple[float | None, int | None]:
    if spec is None:
        rep.hard("scenes.spec", False, "episode.json missing/unreadable in bundle")
        return None, None
    t_by = {s["sceneId"]: s for s in (timing or {}).get("scenes", [])}
    c_by = {s["sceneId"]: s for s in (compose or {}).get("segments", [])}
    if not rep.hard("scenes.timing", timing is not None and all(s["sceneId"] in t_by for s in spec["scenes"]),
                    "timing.json covers every scene"):
        return None, None
    scheduled_total, total_frames = 0.0, 0
    frame = 1.0 / profile.fps
    for scene in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        sid = scene["sceneId"]
        st = t_by[sid]
        sched = float(st["scene_duration_s"])
        scheduled_total += sched
        row = {"sceneId": sid, "sequence": scene["sequence"], "template": scene["template"],
               "engine": scene["engine"], "duration_s": sched, "frames": None,
               "speech_s": st.get("audio_duration_s"), "speech_coverage": st.get("speech_coverage"),
               "clip_mean_db": None, "clip_max_db": None, "flags": []}
        rep.scenes.append(row)
        scene_mp4, clip = out_dir / "scenes" / f"{sid}.mp4", out_dir / "clips" / f"{sid}.mp4"
        rep.hard(f"scene.{sid}.video_present", scene_mp4.is_file(), f"scenes/{sid}.mp4 exists")
        if not rep.hard(f"scene.{sid}.clip_present", clip.is_file(), f"clips/{sid}.mp4 exists"):
            row["flags"].append("clip missing")
            continue
        try:
            cs = summarize(clip, ffprobe)
        except MediaError as e:
            rep.hard(f"scene.{sid}.clip_probe", False, str(e))
            row["flags"].append("clip unreadable")
            continue
        frames = (cs.video or {}).get("frames") or 0
        row["frames"] = frames
        total_frames += frames
        expected = target_frames(sched, profile.fps)
        c_frames = c_by.get(sid, {}).get("frames")
        ok = abs(frames - expected) <= 1 and (c_frames is None or c_frames == frames) and \
            abs(frames / profile.fps - sched) <= frame + 1e-6
        rep.hard(f"scene.{sid}.clip_duration", ok,
                 f"{frames} frames ({frames / profile.fps:.3f}s) vs scheduled {sched:.3f}s (±1 frame)", frames)
        if cs.audio is None:
            rep.hard(f"scene.{sid}.clip_audio", False, "clip has no audio track")
            row["flags"].append("no audio")
        else:
            try:
                lv = audio_levels(clip, ffmpeg, ebur128=False)
                row["clip_mean_db"], row["clip_max_db"] = lv.mean_volume_db, lv.max_volume_db
                narrated = bool(scene.get("narration", "").strip())
                if narrated:
                    loud = lv.max_volume_db is not None and lv.max_volume_db > SILENT_SCENE_MAX_DB
                    rep.hard(f"scene.{sid}.narration_audible", loud,
                             f"clip peak {lv.max_volume_db} dBFS (silent if ≤ {SILENT_SCENE_MAX_DB})", lv.max_volume_db)
                    if not loud:
                        row["flags"].append("SILENT narration")
            except MediaError as e:
                rep.hard(f"scene.{sid}.clip_audio", False, f"volumedetect failed: {e}")
        cov = st.get("speech_coverage")
        if cov is not None and not rep.soft(f"scene.{sid}.voice_coverage", cov >= MIN_SPEECH_COVERAGE,
                                            f"speech covers {cov:.0%} of the scene (< {MIN_SPEECH_COVERAGE:.0%}: "
                                            "holds fill gap — not acceptable educational pacing)", cov):
            row["flags"].append(f"voice {cov:.0%} < {MIN_SPEECH_COVERAGE:.0%}")
        if st.get("is_synthetic_placeholder"):
            row["flags"].append("synthetic TTS" if st.get("provider") == "espeak" else "FIXTURE audio")
    return round(scheduled_total, 6), total_frames


def run_qa(out_dir: Path, profile: str | Profile | None = None) -> QaReport:
    """Run every check on the bundle in ``out_dir`` (does not write files; see ``write_qa_report``).

    ``profile``: name in PROFILES (default: from manifest.json / compose.json, else "full") or a Profile."""
    out_dir = Path(out_dir)
    if not isinstance(profile, Profile):
        profile = PROFILES[profile or detect_profile(out_dir) or "full"]
    profile_name = profile.name
    spec = _load_json(out_dir / "episode.json")
    timing = _load_json(out_dir / "timing.json")
    compose = _load_json(out_dir / "compose.json")
    rep = QaReport(spec.get("episodeId") if spec else None, profile_name, str(out_dir))
    ffmpeg, ffprobe = find_ffmpeg()

    scheduled_total, clip_frames = _check_scenes(rep, out_dir, ffmpeg, ffprobe, spec, timing, compose, profile)
    video_s = _check_final(rep, out_dir, ffmpeg, ffprobe, profile, scheduled_total, clip_frames or None)
    _check_captions(rep, out_dir, video_s)

    mpath = out_dir / MANIFEST_NAME
    manifest = _load_json(mpath)
    if rep.hard("manifest.present", manifest is not None, f"{MANIFEST_NAME} exists and parses"):
        problems = verify_manifest(out_dir, manifest)
        rep.hard("manifest.hashes", not problems,
                 "every artifact matches its recorded SHA-256 and size" if not problems else "; ".join(problems[:5]),
                 problems[:50] or None)
        if manifest.get("finalVideoSha256"):
            rep.final["sha256"] = manifest["finalVideoSha256"]

    # soft: provenance / publishability
    if timing:
        labels = timing.get("providerLabels") or []
        synthetic = any(s.get("is_synthetic_placeholder") for s in timing.get("scenes", []))
        rep.soft("tts.production_voice", not synthetic,
                 f"TTS provider {timing.get('provider')!r}: {'; '.join(labels)}" +
                 (" — synthetic/fixture audio, not production narration"
                  if synthetic and "not production" not in "; ".join(labels) else ""),
                 timing.get("provider"))
    rep.soft("profile.publishable", profile_name == "full",
             f"profile {profile_name} ({profile.width}x{profile.height})" +
             (" is a low-res preview — not publishable" if profile_name != "full" else ""), profile_name)
    thumb = out_dir / "thumbnail.png"
    size = None
    if thumb.is_file():
        try:
            tv = summarize(thumb, ffprobe).video or {}
            size = (tv.get("width"), tv.get("height"))
        except MediaError:
            size = None
    rep.soft("thumbnail", size == (1280, 720),
             "thumbnail.png 1280x720" if size == (1280, 720) else
             (f"thumbnail.png is {size[0]}x{size[1]} (expected 1280x720)" if size else "thumbnail.png missing/unreadable"),
             list(size) if size else None)
    return rep


# ---------------------------------------------------------------- output

def render_markdown(doc: dict) -> str:
    f = doc.get("final", {})
    p = (f.get("probe") or {})
    v, a = p.get("video") or {}, p.get("audio") or {}
    lv = f.get("levels") or {}
    lines = [f"# QA report — {doc.get('episodeId')} ({doc.get('profile')})", "",
             f"**Status: {doc['status']}** — {doc['summary']['hardFailures']} hard failure(s), "
             f"{doc['summary']['warnings']} warning(s), {doc['summary']['checks']} checks. Generated {doc['createdAt']}.", ""]
    if f:
        lines += ["## Final video", "",
                  f"- File: `final.mp4` ({f.get('bytes', 0) / 1e6:.1f} MB), SHA-256 `{f.get('sha256', 'n/a')}`",
                  f"- Video: {v.get('codec')} {v.get('profile')} {v.get('pix_fmt')} {v.get('width')}x{v.get('height')} "
                  f"@ {v.get('fps')} fps, {v.get('frames')} frames",
                  f"- Audio: {a.get('codec')} {a.get('sample_rate')} Hz, {a.get('channels')} ch, "
                  f"{(a.get('bit_rate') or 0) // 1000} kb/s, {a.get('duration_s')} s",
                  f"- Duration: container {p.get('duration_s')} s",
                  f"- Levels: mean {lv.get('mean_volume_db')} dBFS, max {lv.get('max_volume_db')} dBFS, "
                  f"integrated {lv.get('integrated_lufs')} LUFS, true peak {lv.get('true_peak_dbfs')} dBFS", ""]
    if doc["failures"]:
        lines += ["## Hard failures", ""] + [f"- **{c['id']}**: {c['message']}" for c in doc["failures"]] + [""]
    if doc["warnings"]:
        lines += ["## Warnings", ""] + [f"- {c['id']}: {c['message']}" for c in doc["warnings"]] + [""]
    if doc["scenes"]:
        lines += ["## Scenes", "", "| # | Scene | Template | Engine | Duration (s) | Frames | Speech (s) | Coverage | "
                  "Clip max (dBFS) | Flags |", "|---|---|---|---|---|---|---|---|---|---|"]
        for s in doc["scenes"]:
            cov = s.get("speech_coverage")
            lines.append(f"| {s['sequence']} | {s['sceneId']} | {s['template']} | {s['engine']} | {s['duration_s']:.2f} | "
                         f"{s.get('frames')} | {s.get('speech_s')} | {f'{cov:.0%}' if cov is not None else '—'} | "
                         f"{s.get('clip_max_db')} | {', '.join(s['flags']) or '—'} |")
        lines.append("")
    lines += ["## All checks", "", "| Check | Severity | Result | Detail |", "|---|---|---|---|"]
    for c in doc["checks"]:
        lines.append(f"| {c['id']} | {c['severity']} | {c['status'].upper()} | {str(c['message']).replace('|', '/')} |")
    lines += ["", "Publishing: not published. Any release requires human approval bound to the final video SHA-256 "
              "(see `manifest.json` → `publish`).", ""]
    return "\n".join(lines)


def write_qa_report(out_dir: Path, rep: QaReport) -> tuple[dict, list[str]]:
    doc = rep.to_dict()
    out_dir = Path(out_dir)
    (out_dir / "qa_report.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "qa_report.md").write_text(render_markdown(doc), encoding="utf-8")
    return doc, ["qa_report.json", "qa_report.md"]


__all__ = ["FAIL", "PASS", "PASS_WITH_WARNINGS", "QaReport", "Check", "detect_profile", "render_markdown",
           "run_qa", "write_qa_report"]
