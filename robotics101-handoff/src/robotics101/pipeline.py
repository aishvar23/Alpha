"""End-to-end local render (M01.5): validate -> narrate -> render-scenes -> compose -> manifest -> QA.

Re-running regenerates every artifact. Stale outputs that a failed run could leave behind looking
valid (final.mp4, clips/, compose.json, manifest.json, qa_report.*) are deleted up front. Nothing
here uploads or publishes; the manifest records ``publish.status = "not_published"``.
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from robotics101.animation.render import PROFILES, RenderSetupError, render_scenes
from robotics101.animation.timing import resolve_scene_durations
from robotics101.compose import ComposeError, compose_episode
from robotics101.manifest import attach_qa, build_manifest, new_run_id, write_manifest
from robotics101.media import MediaError, check_ffmpeg, tool_versions
from robotics101.narration import TtsError, get_provider, narrate_episode
from robotics101.qa import FAIL, run_qa, write_qa_report
from robotics101.validation import validate_file

STALE_OUTPUTS = ("final.mp4", "compose.json", "manifest.json", "qa_report.json", "qa_report.md", "episode.json")


class PipelineError(RuntimeError):
    def __init__(self, message: str, exit_code: int):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class RenderOutcome:
    status: str
    out_dir: Path
    run_id: str
    final_sha256: str | None
    stage_seconds: dict = field(default_factory=dict)
    qa: dict | None = None


def clear_stale(out_dir: Path) -> None:
    for name in STALE_OUTPUTS:
        (out_dir / name).unlink(missing_ok=True)
    shutil.rmtree(out_dir / "clips", ignore_errors=True)
    shutil.rmtree(out_dir / ".compose", ignore_errors=True)


def qa_and_seal(out_dir: Path, profile: str, manifest: dict | None = None, log=print) -> tuple[dict, dict]:
    """Run QA, write qa_report.{json,md}, then hash the reports into manifest.json."""
    from robotics101.manifest import load_manifest
    rep = run_qa(out_dir, profile)
    doc, report_paths = write_qa_report(out_dir, rep)
    if manifest is None:
        try:
            manifest = load_manifest(out_dir)
        except (OSError, json.JSONDecodeError):
            manifest = None
    if manifest is not None:
        write_manifest(out_dir, attach_qa(manifest, out_dir, doc["status"], report_paths))
    return doc, manifest or {}


def render_episode(episode: Path, out_dir: Path, profile_name: str = "preview", tts: str | None = None,
                   workers: int = 4, timeout_s: float = 900.0, log=print) -> RenderOutcome:
    """Raises PipelineError(exit_code) for invalid spec (1), input/prereq errors (2), render/compose failures (4)."""
    t_all = time.monotonic()
    stages: dict[str, float] = {}
    episode, out_dir = Path(episode), Path(out_dir)
    profile = PROFILES[profile_name]

    def stage(name, t0):
        stages[name] = round(time.monotonic() - t0, 2)

    # 1. validate
    t0 = time.monotonic()
    try:
        report = validate_file(episode)
    except (OSError, json.JSONDecodeError) as e:
        raise PipelineError(f"cannot read {episode}: {e}", 2) from e
    for issue in report.issues:
        log(f"  {issue}")
    if not report.ok:
        raise PipelineError(f"{episode} is invalid ({len(report.errors)} error(s))", 1)
    spec_bytes = episode.read_bytes()
    spec = json.loads(spec_bytes)
    try:
        provider = get_provider(tts)
        check_ffmpeg()
    except (TtsError, MediaError) as e:
        raise PipelineError(str(e), 2) from e
    out_dir.mkdir(parents=True, exist_ok=True)
    clear_stale(out_dir)
    (out_dir / "episode.json").write_bytes(spec_bytes)  # exact copy -> specSha256 == hash of the input file
    run_id = new_run_id()
    stage("validate", t0)
    log(f"[1/6] validate: {spec['episodeId']} ok ({len(report.warnings)} warning(s)); run {run_id}")

    # 2. narrate
    t0 = time.monotonic()
    try:
        timing = narrate_episode(spec, out_dir, provider)
    except TtsError as e:
        raise PipelineError(f"narration failed: {e}", 2) from e
    stage("narrate", t0)
    log(f"[2/6] narrate ({provider.name}): total {timing['totalDurationSeconds']:.2f}s, speech "
        f"{timing['totalSpeechSeconds']:.2f}s ({timing['speechCoverage']:.0%}) [{stages['narrate']}s]")

    # 3. render scenes
    t0 = time.monotonic()
    durations, _ = resolve_scene_durations(spec, out_dir / "timing.json")
    log(f"[3/6] render-scenes: profile {profile.name} {profile.width}x{profile.height}@{profile.fps} ...")

    def on_result(r):
        tag = {"rendered": "ok  ", "skipped": "skip", "failed": "FAIL"}[r.status]
        log(f"  [{tag}] {r.sceneId} {r.template}: {r.message} ({r.elapsed_s:.1f}s)")
        for p in r.problems:
            log(f"         - {p}")

    try:
        results = render_scenes(spec, durations, out_dir, profile, workers=workers, timeout_s=timeout_s,
                                on_result=on_result)
    except RenderSetupError as e:
        raise PipelineError(str(e), 2) from e
    from dataclasses import asdict
    (out_dir / "scenes" / "render-report.json").write_text(json.dumps({
        "episodeId": spec["episodeId"], "profile": asdict(profile), "durationSource": "timing.json",
        "scenes": [asdict(r) for r in results]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [r.sceneId for r in results if r.status != "rendered"]
    stage("render_scenes", t0)
    if failed:
        raise PipelineError(f"scene(s) failed to render: {failed} (logs in {out_dir / 'logs'})", 4)
    log(f"  {len(results)} scenes rendered [{stages['render_scenes']}s]")

    # 4. compose
    t0 = time.monotonic()
    log("[4/6] compose: clips + final.mp4 + captions.srt")
    try:
        comp = compose_episode(spec, timing, out_dir, profile, log=log)
    except ComposeError as e:
        raise PipelineError(f"compose failed: {e}", 4) from e
    stage("compose", t0)
    log(f"  final {comp.total_frames} frames = {comp.total_duration_s:.3f}s [{stages['compose']}s]")

    # 5. manifest (everything except the QA reports, which QA writes next)
    t0 = time.monotonic()
    try:
        manifest = build_manifest(out_dir, spec, profile.name, timing, run_id=run_id, tool_versions=tool_versions())
    except (FileNotFoundError, MediaError) as e:
        raise PipelineError(f"manifest failed: {e}", 4) from e
    write_manifest(out_dir, manifest)
    stage("manifest", t0)
    log(f"[5/6] manifest: {len(manifest['artifacts'])} artifacts, finalVideoSha256 {manifest['finalVideoSha256']}")

    # 6. QA, then seal the reports into the manifest
    t0 = time.monotonic()
    stages["total_before_qa"] = round(time.monotonic() - t_all, 2)
    manifest["stageSeconds"] = stages
    doc, manifest = qa_and_seal(out_dir, profile.name, manifest, log=log)
    stage("qa", t0)
    stages["total"] = round(time.monotonic() - t_all, 2)
    manifest["stageSeconds"] = stages
    write_manifest(out_dir, manifest)
    log(f"[6/6] QA: {doc['status']} ({doc['summary']['hardFailures']} hard failure(s), "
        f"{doc['summary']['warnings']} warning(s)) [{stages['qa']}s]")
    return RenderOutcome(doc["status"], out_dir, run_id, manifest.get("finalVideoSha256"), stages, doc)


def qa_bundle(out_dir: Path, profile_name: str | None = None) -> dict:
    """Re-run QA on an existing bundle and re-seal the QA report hashes into manifest.json."""
    from robotics101.qa import detect_profile
    profile_name = profile_name or detect_profile(out_dir) or "full"
    doc, _ = qa_and_seal(Path(out_dir), profile_name)
    return doc


__all__ = ["FAIL", "PipelineError", "RenderOutcome", "qa_bundle", "render_episode"]
