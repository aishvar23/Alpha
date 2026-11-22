"""`robotics101` command-line entry point.

Exit codes: 0 ok, 1 validation failed, 2 usage/input error (missing file, bad JSON,
missing render prerequisites), 3 command not implemented yet, 4 a scene render/probe failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from robotics101 import __version__
from robotics101.validation import validate_file

EXIT_OK, EXIT_INVALID, EXIT_INPUT, EXIT_NOT_IMPLEMENTED, EXIT_RENDER_FAILED = 0, 1, 2, 3, 4


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


def _cmd_render(args: argparse.Namespace) -> int:
    print("error: render not implemented yet (M01.5)", file=sys.stderr)
    return EXIT_NOT_IMPLEMENTED


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

    r = sub.add_parser("render", help="render an episode (not implemented yet: M01.5)")
    r.add_argument("episode", type=Path)
    r.add_argument("--out", type=Path, default=None)
    r.set_defaults(func=_cmd_render)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
