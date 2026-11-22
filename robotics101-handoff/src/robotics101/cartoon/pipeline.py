"""Cartoon episode pipeline (M02.8): validate -> voice -> render scenes -> mix -> compose -> thumbnail ->
manifest (+ character registry fingerprint and drawing version) -> QA -> sealed bundle.

Bundle layout (``<out>/``): episode.json, timing.json, captions.srt, voice/…, voice_qa.json, scenes/*.mp4,
scenes.json, robotcam/…, audio/{mix.wav,mix.json,stems/*.wav}, licenses.json, final.mp4, compose.json,
thumbnail.png, manifest.json, qa_report.{json,md}. ``robotics101 publish --dry-run`` works on it unchanged.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from robotics101.manifest import SCHEMA_VERSION, artifact_entry, new_run_id, write_manifest
from robotics101.media import check_ffmpeg, run, sha256_file, tool_versions

ROOT = Path(__file__).resolve().parents[3]
LICENSES = ROOT / "assets" / "LICENSES.json"
FPS = 30
CRF, PRESET, AUDIO_BITRATE = 20, "medium", "192k"
STALE = ("final.mp4", "compose.json", "manifest.json", "qa_report.json", "qa_report.md", "publish_plan.json",
         "thumbnail.png", "licenses.json", "scenes.json")


class CartoonPipelineError(RuntimeError):
    def __init__(self, msg: str, code: int = 4):
        super().__init__(msg)
        self.code = code


def compose_final(out_dir: Path, timing: dict, title: str, log=print) -> dict:
    """Concatenate scene videos (one re-encode) + the mixed audio -> final.mp4; writes compose.json."""
    out_dir = Path(out_dir)
    segs, t, frames = [], 0.0, 0
    for s in timing["scenes"]:
        n = round(s["scene_duration_s"] * FPS)
        segs.append({"sceneId": s["sceneId"], "start_s": round(t, 6), "end_s": round(t + n / FPS, 6), "frames": n})
        t += n / FPS
        frames += n
    clips = [out_dir / "scenes" / f"{g['sceneId']}.mp4" for g in segs]
    k = len(clips)
    parts = [f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]" for i in range(k)]
    parts.append("".join(f"[v{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0,fps={FPS},setsar=1,format=yuv420p[v]")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-v", "error"]
    for c in clips:
        cmd += ["-i", str(c)]
    cmd += ["-i", str(out_dir / "audio" / "mix.wav"), "-filter_complex", ";".join(parts),
            "-map", "[v]", "-map", f"{k}:a:0",
            "-c:v", "libx264", "-profile:v", "high", "-preset", PRESET, "-crf", str(CRF), "-tune", "animation",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-fps_mode", "cfr", "-g", str(2 * FPS), "-frames:v", str(frames),
            "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "48000", "-ac", "2",
            "-map_metadata", "-1", "-metadata", f"title={title}", "-movflags", "+faststart",
            str(out_dir / "final.mp4")]
    run(cmd, timeout=3600, what="ffmpeg final encode")
    doc = {"schemaVersion": "robotics101.compose/cartoon-1", "fps": FPS, "total_frames": frames,
           "total_duration_s": round(frames / FPS, 6), "segments": segs, "video": {"codec": "h264", "crf": CRF},
           "audio": {"source": "audio/mix.wav", "codec": "aac", "bitrate": AUDIO_BITRATE}}
    (out_dir / "compose.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    log(f"  final.mp4: {frames} frames = {frames / FPS:.3f}s")
    return doc


def collect_artifacts(out_dir: Path, timing: dict) -> list[tuple[str, str, str | None]]:
    items = [("episode.json", "spec", None), ("timing.json", "timing", None), ("captions.srt", "captions", None)]
    for s in timing["scenes"]:
        items.append((s["dialogue_wav"], "dialogue_stem", s["sceneId"]))
        for b in s["beats"]:
            if b["type"] == "line":
                items.append((b["wav"], "voice_line", s["sceneId"]))
    for s in timing["scenes"]:
        items.append((f"scenes/{s['sceneId']}.mp4", "scene_video", s["sceneId"]))
    out_dir = Path(out_dir)
    for p in sorted((out_dir / "robotcam" / "scenes").glob("*.mp4")):
        items.append((str(p.relative_to(out_dir)), "robotcam_clip", None))
    items += [("scenes.json", "render_report", None), ("voice_qa.json", "voice_qa", None),
              ("audio/stems/dialogue.wav", "audio_stem", None), ("audio/stems/music.wav", "audio_stem", None),
              ("audio/stems/sfx.wav", "audio_stem", None), ("audio/mix.wav", "audio_mix", None),
              ("audio/mix.json", "mix_report", None), ("licenses.json", "licenses", None),
              ("final.mp4", "final_video", None), ("compose.json", "compose_report", None),
              ("thumbnail.png", "thumbnail", None)]
    return items


def build_cartoon_manifest(out_dir: Path, spec: dict, timing: dict, registry, run_id: str, profile: str) -> dict:
    from robotics101.cartoon.rigs import RIG_VERSION
    out_dir = Path(out_dir)
    items = collect_artifacts(out_dir, timing)
    missing = [rel for rel, _, _ in items if not (out_dir / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"cannot build manifest, missing artifacts: {missing[:8]}")
    arts = [artifact_entry(out_dir, rel, role, sid, probe=role in ("final_video", "scene_video", "audio_mix"))
            for rel, role, sid in items]
    final = next(a for a in arts if a["role"] == "final_video")
    spec_e = next(a for a in arts if a["role"] == "spec")
    return {
        "schemaVersion": SCHEMA_VERSION, "engine": "cartoon", "episodeId": spec["episodeId"], "title": spec.get("title"),
        "runId": run_id, "createdAt": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .isoformat(timespec="seconds"), "profile": profile,
        "specSha256": spec_e["sha256"], "finalVideoSha256": final["sha256"],
        "finalVideo": {"path": final["path"], "bytes": final["bytes"], "media": final.get("media")},
        "characterRegistry": {"path": "characters/registry.json", "sha256": registry.sha256,
                              "rigVersion": registry.rig_version, "drawingVersion": RIG_VERSION,
                              "characters": sorted(registry.characters)},
        "tts": {"provider": timing.get("provider"), "labels": [timing.get("providerLabel")],
                "isProductionVoice": bool(timing.get("isProductionVoice")),
                "isSyntheticPlaceholder": not timing.get("isProductionVoice"),
                "voices": timing.get("voices")},
        "audience": {"madeForKids": (spec.get("publishing") or {}).get("madeForKids")},
        "toolVersions": tool_versions(),
        "publish": {"status": "not_published", "requiresApprovalOfSha256": final["sha256"]},
        "qa": None, "artifacts": arts,
    }


def unapproved_elevenlabs(registry) -> list[str]:
    return sorted(c.id for c in registry.characters.values()
                  if c.speaks and not ((c.voice or {}).get("elevenlabs") or {}).get("approved"))


def pick_backend(tts: str, registry):
    """Like ``select_backend`` but full-episode ElevenLabs voicing needs every speaking character's voice to be
    approved in the registry (after `voices samples`). ``auto`` then falls back to Kokoro/espeak; an explicit
    ``elevenlabs`` request is refused (no credits spent)."""
    from robotics101.voice import select_backend
    backend, skipped = select_backend(tts)
    if backend.name == "elevenlabs" and unapproved_elevenlabs(registry):
        why = f"elevenlabs: voices not approved yet for {unapproved_elevenlabs(registry)} (run `voices samples`)"
        if (tts or "auto") != "auto":
            raise CartoonPipelineError(why, 2)
        for name in ("kokoro", "espeak"):
            try:
                b, _ = select_backend(name)
                return b, skipped + [why]
            except Exception as e:  # noqa: BLE001 - try the next fallback
                why = f"{why}; {name}: {e}"
        raise CartoonPipelineError(f"no usable voice backend: {why}", 2)
    return backend, skipped


def render_cartoon_episode(episode: Path, out_dir: Path, tts: str = "auto", size: str = "1920x1080",
                           log=print) -> dict:
    from robotics101.cartoon.audio import mix_episode
    from robotics101.cartoon.scenes import render_cartoon_scenes
    from robotics101.cartoon.thumbnail import make_cartoon_thumbnail
    from robotics101.characters import load_registry
    from robotics101.qa import QaReport
    from robotics101.validation import validate_file
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice.qa import check_dialogue

    t_all, stages = time.monotonic(), {}
    episode, out_dir = Path(episode), Path(out_dir)
    w, h = (int(x) for x in size.lower().split("x"))
    profile = "full" if (w, h) == (1920, 1080) else "preview"
    t0 = time.monotonic()
    rep = validate_file(episode)
    for issue in rep.issues:
        log(f"  {issue}")
    if not rep.ok:
        raise CartoonPipelineError(f"{episode} is invalid ({len(rep.errors)} error(s))", 1)
    spec_bytes = episode.read_bytes()
    spec = json.loads(spec_bytes)
    check_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in STALE:
        (out_dir / name).unlink(missing_ok=True)
    (out_dir / "episode.json").write_bytes(spec_bytes)
    run_id = new_run_id()
    registry = load_registry()
    stages["validate"] = round(time.monotonic() - t0, 2)
    log(f"[1/7] validate: {spec['episodeId']} ok; run {run_id}")

    t0 = time.monotonic()
    backend, skipped = pick_backend(tts, registry)
    timing = voice_episode(spec, registry, out_dir, backend, VoiceCache(), skipped=skipped, log=log)
    vq = QaReport(spec["episodeId"], "voice", str(out_dir))
    check_dialogue(vq, out_dir)
    (out_dir / "voice_qa.json").write_text(json.dumps(vq.to_dict(), indent=2, ensure_ascii=False) + "\n",
                                           encoding="utf-8")
    stages["voice"] = round(time.monotonic() - t0, 2)
    log(f"[2/7] voice ({timing['provider']}): {timing['totalDurationSeconds']}s, dialogue QA {vq.status}")

    t0 = time.monotonic()
    render_cartoon_scenes(episode, out_dir, out_dir, w, h, log=log)
    stages["render_scenes"] = round(time.monotonic() - t0, 2)
    log(f"[3/7] scenes rendered [{stages['render_scenes']}s]")

    t0 = time.monotonic()
    mix_episode(timing, out_dir, out_dir, log=log)
    shutil.copyfile(LICENSES, out_dir / "licenses.json")
    stages["mix"] = round(time.monotonic() - t0, 2)
    log(f"[4/7] mix [{stages['mix']}s]")

    t0 = time.monotonic()
    compose_final(out_dir, timing, spec.get("title", ""), log=log)
    make_cartoon_thumbnail(out_dir / "thumbnail.png", spec.get("title", ""))
    stages["compose"] = round(time.monotonic() - t0, 2)
    log(f"[5/7] compose + thumbnail [{stages['compose']}s]")

    t0 = time.monotonic()
    manifest = build_cartoon_manifest(out_dir, spec, timing, registry, run_id, profile)
    write_manifest(out_dir, manifest)
    stages["manifest"] = round(time.monotonic() - t0, 2)
    log(f"[6/7] manifest: {len(manifest['artifacts'])} artifacts, final {manifest['finalVideoSha256']}")

    t0 = time.monotonic()
    doc = qa_and_seal_cartoon(out_dir, profile, manifest)
    stages["qa"] = round(time.monotonic() - t0, 2)
    stages["total"] = round(time.monotonic() - t_all, 2)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    manifest["stageSeconds"] = stages
    write_manifest(out_dir, manifest)
    log(f"[7/7] QA: {doc['status']} ({doc['summary']['hardFailures']} hard failure(s), "
        f"{doc['summary']['warnings']} warning(s)) [{stages['qa']}s]")
    return {"status": doc["status"], "manifest": manifest, "qa": doc}


def qa_and_seal_cartoon(out_dir: Path, profile: str, manifest: dict | None = None) -> dict:
    from robotics101.cartoon.qa import run_cartoon_qa
    from robotics101.manifest import attach_qa, load_manifest
    from robotics101.qa import write_qa_report
    rep = run_cartoon_qa(out_dir, profile)
    doc, paths = write_qa_report(out_dir, rep)
    manifest = manifest or load_manifest(out_dir)
    write_manifest(out_dir, attach_qa(manifest, out_dir, doc["status"], paths))
    return doc


__all__ = ["CartoonPipelineError", "compose_final", "render_cartoon_episode", "sha256_file"]
