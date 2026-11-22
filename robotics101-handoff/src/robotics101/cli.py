"""`robotics101` command-line entry point.

Exit codes: 0 ok (render/qa: QA PASS or PASS_WITH_WARNINGS), 1 validation failed, 2 usage/input error
(missing file, bad JSON, missing render prerequisites), 3 command not implemented yet, 4 a scene
render/probe or the composer failed, 5 QA status FAIL, 6 publish refused (bundle integrity, or any real
upload: only `publish --dry-run` exists and it never contacts YouTube).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from robotics101 import __version__
from robotics101.validation import validate_file

EXIT_OK, EXIT_INVALID, EXIT_INPUT, EXIT_NOT_IMPLEMENTED, EXIT_RENDER_FAILED, EXIT_QA_FAILED = 0, 1, 2, 3, 4, 5
EXIT_PUBLISH_REFUSED = 6


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        report = validate_file(args.episode)
    except OSError as e:
        print(f"error: cannot read {args.episode}: {e.strerror or e}", file=sys.stderr)
        return EXIT_INPUT
    except json.JSONDecodeError as e:
        print(f"error: {args.episode} is not valid JSON: {e}", file=sys.stderr)
        return EXIT_INPUT

    for issue in report.issues:
        print(issue, file=sys.stderr if issue.severity == "error" else sys.stdout)

    failed = not report.ok or (args.strict and report.warnings)
    status = "INVALID" if failed else "VALID"
    print(f"{status}: {args.episode} ({len(report.errors)} error(s), {len(report.warnings)} warning(s))")
    return EXIT_INVALID if failed else EXIT_OK


def _cmd_narrate(args: argparse.Namespace) -> int:
    from robotics101.narration import TtsError, get_provider, narrate_episode

    rc = _cmd_validate(argparse.Namespace(episode=args.episode, strict=False))
    if rc != EXIT_OK:
        return rc
    try:
        provider = get_provider(args.provider)
    except TtsError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    spec = json.loads(args.episode.read_text(encoding="utf-8"))
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        doc = narrate_episode(spec, args.out, provider)
    except TtsError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT

    print(f"narration provider: {provider.name} — {'; '.join(doc['providerLabels'])}")
    for s in doc["scenes"]:
        flag = "  [FLAG: voice too short]" if s["sceneId"] in doc["scenesFlagged"] else ""
        print(f"  {s['sceneId']}: audio {s['audio_duration_s']:6.2f}s  scene "
              f"{s['scene_start_s']:7.2f}-{s['scene_end_s']:7.2f}s  hold {s['hold_s']:6.2f}s{flag}")
    print(f"total {doc['totalDurationSeconds']:.2f}s, speech {doc['totalSpeechSeconds']:.2f}s "
          f"({doc['speechCoverage']:.0%}); {len(doc['scenesFlagged'])} scene(s) flagged")
    print(f"wrote {args.out / 'audio'}/*.wav, {args.out / 'timing.json'}, {args.out / 'captions.srt'}")
    return EXIT_OK


def _cmd_render_scenes(args: argparse.Namespace) -> int:
    from dataclasses import asdict

    from robotics101.animation.render import PROFILES, RenderSetupError, render_scenes
    from robotics101.animation.timing import resolve_scene_durations

    rc = _cmd_validate(argparse.Namespace(episode=args.episode, strict=False))
    if rc != EXIT_OK:
        return rc
    spec = json.loads(args.episode.read_text(encoding="utf-8"))
    known = {s["sceneId"] for s in spec["scenes"]}
    only = set(args.only or [])
    if only - known:
        print(f"error: --only names unknown scene(s): {sorted(only - known)}", file=sys.stderr)
        return EXIT_INPUT
    try:
        durations, source = resolve_scene_durations(spec, args.out / "timing.json")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    profile = PROFILES[args.profile]
    print(f"render-scenes: profile {profile.name} {profile.width}x{profile.height}@{profile.fps}fps, "
          f"durations from {source}, workers {args.workers}")

    def report(r):
        tag = {"rendered": "ok  ", "skipped": "skip", "failed": "FAIL"}[r.status]
        extra = f" ({r.elapsed_s:.1f}s)" if r.status != "skipped" else ""
        print(f"  [{tag}] {r.sceneId} {r.template}: {r.message}{extra}", flush=True)
        for p in r.problems:
            print(f"         - {p}")
        if r.status == "failed" and r.log:
            print(f"         log: {r.log}")

    try:
        results = render_scenes(spec, durations, args.out, profile, only=only or None,
                                workers=args.workers, timeout_s=args.timeout, on_result=report)
    except RenderSetupError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    report_path = args.out / "scenes" / "render-report.json"
    report_path.write_text(json.dumps({
        "episodeId": spec["episodeId"], "profile": asdict(profile), "durationSource": source,
        "scenes": [asdict(r) for r in results]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    failed = [r.sceneId for r in results if r.status == "failed"]
    n_ok = sum(r.status == "rendered" for r in results)
    print(f"{n_ok} rendered, {sum(r.status == 'skipped' for r in results)} skipped, {len(failed)} failed; "
          f"clips in {args.out / 'scenes'}, logs in {args.out / 'logs'}, report {report_path}")
    return EXIT_RENDER_FAILED if failed else EXIT_OK


def _print_qa(doc: dict, out: Path) -> None:
    for c in doc["failures"]:
        print(f"  FAIL {c['id']}: {c['message']}")
    for c in doc["warnings"]:
        print(f"  warn {c['id']}: {c['message']}")
    f = doc.get("final") or {}
    v = ((f.get("probe") or {}).get("video")) or {}
    a = ((f.get("probe") or {}).get("audio")) or {}
    if v:
        print(f"final.mp4: {v.get('codec')} {v.get('profile')} {v.get('pix_fmt')} {v.get('width')}x{v.get('height')} "
              f"@{v.get('fps'):g}fps {v.get('frames')} frames; audio {a.get('codec')} {a.get('sample_rate')} Hz "
              f"{a.get('channels')}ch; {(f.get('probe') or {}).get('duration_s')}s")
    if f.get("sha256"):
        print(f"finalVideoSha256: {f['sha256']}  (publish: not_published; approval must bind to this hash)")
    print(f"QA {doc['status']}: {out / 'qa_report.md'}, {out / 'qa_report.json'}, manifest {out / 'manifest.json'}")


def _cmd_render(args: argparse.Namespace) -> int:
    from robotics101.pipeline import FAIL, PipelineError, render_episode

    try:
        outcome = render_episode(args.episode, args.out, args.profile, args.tts, workers=args.workers,
                                 timeout_s=args.timeout, log=lambda m: print(m, flush=True))
    except PipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    _print_qa(outcome.qa, args.out)
    print(f"stage seconds: {outcome.stage_seconds}")
    return EXIT_QA_FAILED if outcome.status == FAIL else EXIT_OK


def _cmd_qa(args: argparse.Namespace) -> int:
    from robotics101.media import MediaError
    from robotics101.pipeline import FAIL, qa_bundle

    if not args.out_dir.is_dir():
        print(f"error: {args.out_dir} is not a directory", file=sys.stderr)
        return EXIT_INPUT
    try:
        doc = qa_bundle(args.out_dir, args.profile)
    except MediaError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    _print_qa(doc, args.out_dir)
    return EXIT_QA_FAILED if doc["status"] == FAIL else EXIT_OK


def _cmd_publish(args: argparse.Namespace) -> int:
    from robotics101.publish import PLAN_NAME, PublishRefused, dry_run, refuse_real_upload

    if not args.dry_run:
        print(f"REFUSED: {refuse_real_upload()}", file=sys.stderr)
        return EXIT_PUBLISH_REFUSED
    if not args.out_dir.is_dir():
        print(f"error: {args.out_dir} is not a directory", file=sys.stderr)
        return EXIT_INPUT
    try:
        plan = dry_run(args.out_dir)
    except PublishRefused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_PUBLISH_REFUSED
    sn, st = plan["snippet"], plan["status"]
    print("DRY RUN — no network calls, nothing uploaded (YouTube upload is not implemented; M06).")
    print(f"  video:     {plan['video']['file']} sha256 {plan['video']['sha256']} ({plan['video']['bytes']} bytes, "
          f"{plan['video']['durationSeconds']} s, {plan['video']['resolution']})")
    print(f"  title:     {sn['title']}")
    print(f"  privacy:   {st['privacyStatus']}  category {sn['categoryId']}  syntheticMedia {st['containsSyntheticMedia']}")
    print(f"  tags:      {', '.join(sn['tags'])}")
    print(f"  captions:  {(plan['captions'] or {}).get('file')}   thumbnail: {(plan['thumbnail'] or {}).get('file')}")
    print(f"  chapters:  {len(plan['chapters'])} (valid for YouTube: {plan['chaptersValidForYouTube']})")
    print(f"  approval:  {plan['approval']['status']} — {plan['approval']['message']}")
    print(f"  wouldUpload: {plan['wouldUpload']}; blockers:")
    for b in plan["blockers"]:
        print(f"    - {b}")
    print(f"wrote {args.out_dir / PLAN_NAME}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="robotics101", description="Robotics 101 episode pipeline")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="validate an EpisodeSpec JSON file")
    v.add_argument("episode", type=Path)
    v.add_argument("--strict", action="store_true", help="treat warnings as errors")
    v.set_defaults(func=_cmd_validate)

    n = sub.add_parser("narrate", help="synthesize per-scene narration, timing.json and captions.srt")
    n.add_argument("episode", type=Path)
    n.add_argument("--out", type=Path, required=True)
    n.add_argument("--provider", choices=["espeak", "fixture", "external"], default=None,
                   help="TTS provider (default: env TTS_PROVIDER, else espeak)")
    n.set_defaults(func=_cmd_narrate)

    rs = sub.add_parser("render-scenes", help="render Manim + Blender scenes to <out>/scenes/<sceneId>.mp4 (video only)")
    rs.add_argument("episode", type=Path)
    rs.add_argument("--out", type=Path, required=True,
                    help="episode output dir; uses <out>/timing.json from `narrate` if present")
    rs.add_argument("--profile", choices=["preview", "full"], default="preview",
                    help="preview = 854x480@30 (default), full = 1920x1080@30")
    rs.add_argument("--only", action="append", metavar="SCENE_ID", help="render only this scene (repeatable)")
    rs.add_argument("--workers", type=int, default=4, help="scenes rendered in parallel (default 4)")
    rs.add_argument("--timeout", type=float, default=900.0, help="per-scene render timeout in seconds (manim / blender + encode)")
    rs.set_defaults(func=_cmd_render_scenes)

    r = sub.add_parser("render", help="end-to-end: validate -> narrate -> render-scenes -> compose -> manifest -> QA")
    r.add_argument("episode", type=Path)
    r.add_argument("--out", type=Path, required=True, help="bundle directory, e.g. out/episode-001")
    r.add_argument("--profile", choices=["preview", "full"], default="preview",
                   help="preview = 854x480@30 (default, fast), full = 1920x1080@30")
    r.add_argument("--tts", choices=["espeak", "fixture"], default=None,
                   help="TTS provider (default: env TTS_PROVIDER, else espeak)")
    r.add_argument("--workers", type=int, default=4, help="scenes rendered in parallel (default 4)")
    r.add_argument("--timeout", type=float, default=900.0, help="per-scene render timeout in seconds")
    r.set_defaults(func=_cmd_render)

    q = sub.add_parser("qa", help="re-run QA on an existing bundle (rewrites qa_report.*, re-seals manifest)")
    q.add_argument("out_dir", type=Path)
    q.add_argument("--profile", choices=["preview", "full"], default=None,
                   help="expected profile (default: from manifest.json / compose.json)")
    q.set_defaults(func=_cmd_qa)

    pb = sub.add_parser("publish", help="YouTube publisher STUB: --dry-run writes publish_plan.json; never uploads")
    pb.add_argument("out_dir", type=Path)
    pb.add_argument("--dry-run", action="store_true",
                    help="build publish_plan.json (metadata, file refs, chapters, blockers). Without it: refused.")
    pb.set_defaults(func=_cmd_publish)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
