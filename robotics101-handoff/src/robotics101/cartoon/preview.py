"""M05.8 single-scene previews: ``robotics101 render <spec> --out <run> --scene <id> [--scene <id>] --preview``.

Renders only the chosen scenes at 854x480 and writes, per scene, ``<run>/scenes/<id>-preview.mp4`` — the scene
video with its slice of the episode mix (cached voices only) and the burned-in subtitles — plus
``<run>/scenes/<id>-preview.json`` (scene QA incl. ``sync.visual_narration`` / ``sync.visual_topic``, the content
hash used by the scene lock, and the clip's decoded-frame MD5). Paid synthesis is refused outright: a preview never
spends credits (any uncached line is an error).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from robotics101.media import run, sha256_file

PREVIEW_SIZE = (854, 480)
FPS = 30


class PreviewError(RuntimeError):
    pass


def _load(p: Path):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def scene_offsets(timing: dict) -> dict[str, tuple[float, float]]:
    """Episode (start, duration) of each scene on the composed timeline (frame-rounded like compose_final)."""
    out, frames = {}, 0
    for s in timing["scenes"]:
        n = round(s["scene_duration_s"] * FPS)
        out[s["sceneId"]] = (frames / FPS, n / FPS)
        frames += n
    return out


def frames_md5(mp4: Path) -> str | None:
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(mp4), "-map", "0:v:0", "-f", "md5", "-"],
                           capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired):
        return None
    line = (r.stdout or "").strip()
    return line.split("=", 1)[1] if line.startswith("MD5=") else None


def cut_preview(out_dir: Path, sid: str, start: float, dur: float, burn: bool) -> Path:
    from robotics101.cartoon.subtitles import burn_filter
    out_dir = Path(out_dir)
    dst = out_dir / "scenes" / f"{sid}-preview.mp4"
    vf = f"setpts=PTS-STARTPTS+{start:.6f}/TB," + (f"{burn_filter(out_dir)}," if burn else "") + \
        "setpts=PTS-STARTPTS,format=yuv420p"
    run(["ffmpeg", "-y", "-hide_banner", "-v", "error", "-i", str(out_dir / "scenes" / f"{sid}.mp4"),
         "-ss", f"{start:.6f}", "-t", f"{dur:.6f}", "-i", str(out_dir / "audio" / "mix.wav"),
         "-filter_complex", f"[0:v:0]{vf}[v]", "-map", "[v]", "-map", "1:a:0",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "24", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2", "-frames:v", str(round(dur * FPS)),
         "-movflags", "+faststart", str(dst)], timeout=1800, what=f"ffmpeg preview {sid}")
    return dst


def scene_qa(out_dir: Path, scene_ids: list[str]) -> dict:
    """The QA checks that apply to single rendered scenes (layout, faces, sync, presence) — not the episode-level
    ones (duration, final mix, manifest)."""
    from robotics101.cartoon import qa as Q
    from robotics101.cartoon.sync import check_sync
    from robotics101.qa import QaReport
    out_dir = Path(out_dir)
    spec, timing, sj = (_load(out_dir / n) for n in ("episode.json", "timing.json", "scenes.json"))
    by = {s["sceneId"]: s for s in (sj or {}).get("scenes", []) if s["sceneId"] in scene_ids}
    sub_spec = {**spec, "scenes": [s for s in spec["scenes"] if s["sceneId"] in scene_ids]}
    sub_timing = {**timing, "scenes": [s for s in timing["scenes"] if s["sceneId"] in scene_ids]}
    rep = QaReport(spec.get("episodeId"), "preview-scene", str(out_dir))
    for sid in scene_ids:
        r = by.get(sid) or {}
        pres = r.get("minPresence", {})
        rep.hard(f"scene.{sid}.presence", bool(pres) and min(pres.values()) >= Q.PRESENCE_MIN,
                 f"min on-screen fraction {pres} (≥ {Q.PRESENCE_MIN})", pres)
    rows = check_sync(rep, sub_spec, sub_timing, by, out_dir, only=scene_ids)
    for fn in ("check_shots", "check_one_example_per_frame"):
        getattr(Q, fn)(rep, sub_spec, sub_timing, by)
    Q.check_clutter(rep, sub_spec, by)
    Q.check_faces_clear(rep, by)
    Q.check_caption_band(rep, by)
    half = float((sj or {}).get("transitionHalfSeconds", 0.4))
    for sid in scene_ids:                            # still-picture checks on the scene video itself
        one = {**timing, "scenes": [s for s in timing["scenes"] if s["sceneId"] == sid]}
        res = Q.hold_runs(out_dir / "scenes" / f"{sid}.mp4", one, by, half)
        ff, regs = res["fullFrame"], res["regions"]
        rep.hard(f"video.no_long_holds.{sid}", ff["longestHoldS"] <= Q.HOLD_MAX_S,
                 f"longest near-still stretch {ff['longestHoldS']:.2f} s at {ff['at']} s (≤ {Q.HOLD_MAX_S} s)",
                 ff["longestHoldS"])
        bad = {k: v for k, v in regs.items() if v["longestHoldS"] > Q.HOLD_MAX_S}
        rep.hard(f"illustrations.animated.{sid}", not bad,
                 f"{len(regs)} illustration region(s); static: {bad or 'none'}",
                 {k: v["longestHoldS"] for k, v in regs.items()})
    d = rep.to_dict()
    d["syncRows"] = rows
    return d


def render_scene_previews(episode: Path, out_dir: Path, scene_ids: list[str], tts: str = "auto",
                          approvals_path: Path | None = None, log=print) -> dict:
    from robotics101.cartoon import approvals as A
    from robotics101.cartoon.audio import mix_episode
    from robotics101.cartoon.episode import expand_episode
    from robotics101.cartoon.pipeline import CartoonPipelineError, pick_backend
    from robotics101.cartoon.scenes import render_cartoon_scenes
    from robotics101.cartoon.subtitles import write_subtitles
    from robotics101.characters import load_registry
    from robotics101.validation import validate_episode, validate_file
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice.dialogue import cost_summary, plan_lines

    episode, out_dir = Path(episode), Path(out_dir)
    rep = validate_file(episode)
    if not rep.ok:
        raise CartoonPipelineError(f"{episode} is invalid ({len(rep.errors)} error(s))", 1)
    registry = load_registry()
    spec_bytes = episode.read_bytes()
    spec = expand_episode(json.loads(spec_bytes), registry)
    if not validate_episode(spec).ok:
        raise CartoonPipelineError("expanded spec is invalid", 1)
    known = [s["sceneId"] for s in spec["scenes"]]
    bad = [s for s in scene_ids if s not in known]
    if bad:
        raise CartoonPipelineError(f"unknown scene id(s) {bad}; known: {known}", 1)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "episode.source.json").write_bytes(spec_bytes)
    (out_dir / "episode.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    backend, skipped = pick_backend(tts, registry)
    cache = VoiceCache()
    cost = cost_summary(plan_lines(spec, registry, backend, cache), backend)
    if cost["billableChars"]:
        raise PreviewError(f"preview uses cached audio only: {cost['lines'] - cost['cachedLines']} line(s), "
                           f"{cost['billableChars']} billable chars are not cached. Nothing was synthesized.")
    timing = voice_episode(spec, registry, out_dir, backend, cache, skipped=skipped, log=log)
    log(f"[preview] voice: {cost['cachedLines']}/{cost['lines']} cached, 0 billable")
    old = _load(out_dir / "scenes.json")
    render_cartoon_scenes(out_dir / "episode.json", out_dir, out_dir, *PREVIEW_SIZE, only=scene_ids, log=log)
    new = _load(out_dir / "scenes.json")
    if old and new:                                  # keep earlier previews' render reports in the run
        keep = {s["sceneId"]: s for s in old.get("scenes", [])}
        keep.update({s["sceneId"]: s for s in new["scenes"]})
        new["scenes"] = [keep[t["sceneId"]] for t in timing["scenes"] if t["sceneId"] in keep]
        (out_dir / "scenes.json").write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
    mix_episode(timing, out_dir, out_dir, log=lambda m: None, spec=spec)
    sdoc = write_subtitles(out_dir, timing, registry, spec, _load(out_dir / "scenes.json"))
    offs = scene_offsets(timing)
    hashes = A.bundle_scene_hashes(out_dir, scene_ids)
    apath = Path(approvals_path) if approvals_path else A.default_path(spec["episodeId"])
    results = {}
    for sid in scene_ids:
        start, dur = offs[sid]
        clip = cut_preview(out_dir, sid, start, dur, bool(sdoc.get("burnIn")))
        qa = scene_qa(out_dir, [sid])
        md5 = frames_md5(clip)
        carried = A.carry_over(apath, sid, hashes[sid], md5)
        rec = {"sceneId": sid, "clip": str(clip), "episodeStart": round(start, 3), "duration": round(dur, 3),
               "size": list(PREVIEW_SIZE), "voice": {"provider": timing.get("provider"), "billableChars": 0,
                                                       "cachedLines": cost["cachedLines"]},
               "hashes": hashes[sid], "previewSha256": sha256_file(clip), "previewFramesMd5": md5,
               "approvalCarriedOver": carried, "qa": {"status": qa["status"], "checks": qa["checks"]},
               "syncRows": qa["syncRows"]}
        (out_dir / "scenes" / f"{sid}-preview.json").write_text(json.dumps(rec, indent=2, ensure_ascii=False) + "\n",
                                                               encoding="utf-8")
        log(f"[preview] {sid}: {clip} ({dur:.2f}s from {start:.2f}s), QA {qa['status']}")
        results[sid] = rec
    return results


def approve_from_preview(out_dir: Path, scene_id: str, by: str = "owner", approvals_path: Path | None = None,
                         note: str | None = None) -> dict:
    """Lock a scene from its preview record (the hash it was reviewed at)."""
    from robotics101.cartoon import approvals as A
    out_dir = Path(out_dir)
    rec = _load(out_dir / "scenes" / f"{scene_id}-preview.json")
    if not rec:
        raise PreviewError(f"no preview for {scene_id} in {out_dir} (render it with --scene {scene_id} --preview)")
    cur = A.bundle_scene_hashes(out_dir, [scene_id]).get(scene_id)
    if cur != rec["hashes"]:
        raise PreviewError(f"{scene_id} changed since its preview was rendered; re-render the preview first")
    spec = _load(out_dir / "episode.json")
    apath = Path(approvals_path) if approvals_path else A.default_path(spec["episodeId"])
    return A.approve(apath, spec["episodeId"], scene_id, rec["hashes"], frames_md5=rec.get("previewFramesMd5"),
                     preview_sha256=rec.get("previewSha256"), by=by, note=note)


__all__ = ["PREVIEW_SIZE", "PreviewError", "approve_from_preview", "cut_preview", "frames_md5",
           "render_scene_previews", "scene_offsets", "scene_qa"]
