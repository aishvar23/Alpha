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


def _cartoon_not_ready(episode: Path) -> bool:
    """Schema 1.1 (cartoon dialogue) specs are not renderable by the M01 narrator/scene pipeline."""
    try:
        version = json.loads(Path(episode).read_text(encoding="utf-8")).get("schemaVersion")
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    if version == "1.1":
        print(f"error: {episode} is a cartoon episode (schema 1.1); this command is for 1.0 "
              "narrator episodes. Use `render` (end-to-end cartoon pipeline) or `voice` / `render-cartoon` / `mix`.", file=sys.stderr)
        return True
    return False


def _cmd_narrate(args: argparse.Namespace) -> int:
    from robotics101.narration import TtsError, get_provider, narrate_episode

    rc = _cmd_validate(argparse.Namespace(episode=args.episode, strict=False))
    if rc != EXIT_OK:
        return rc
    if _cartoon_not_ready(args.episode):
        return EXIT_NOT_IMPLEMENTED
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
    if _cartoon_not_ready(args.episode):
        return EXIT_NOT_IMPLEMENTED
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


def _schema_version(path: Path) -> str | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")).get("schemaVersion")
    except (OSError, json.JSONDecodeError, AttributeError):
        return None


def _cmd_render_cartoon_episode(args: argparse.Namespace) -> int:
    from robotics101.cartoon.pipeline import CartoonPipelineError, render_cartoon_episode
    from robotics101.media import MediaError
    from robotics101.voice import VoiceError

    size = "1920x1080" if args.profile == "full" else "854x480"
    try:
        res = render_cartoon_episode(args.episode, args.out, tts=args.tts or "auto", size=size,
                                     log=lambda m: print(m, flush=True))
    except CartoonPipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.code
    except (VoiceError, MediaError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    _print_qa(res["qa"], args.out)
    print(f"stage seconds: {res['manifest'].get('stageSeconds')}")
    return EXIT_QA_FAILED if res["status"] == "FAIL" else EXIT_OK


def _cmd_render(args: argparse.Namespace) -> int:
    from robotics101.pipeline import FAIL, PipelineError, render_episode

    if _schema_version(args.episode) == "1.1":
        return _cmd_render_cartoon_episode(args)
    if args.tts in ("auto", "kokoro", "elevenlabs"):
        print(f"error: --tts {args.tts} is for cartoon (1.1) episodes; use espeak or fixture", file=sys.stderr)
        return EXIT_INPUT
    try:
        outcome = render_episode(args.episode, args.out, args.profile, args.tts, workers=args.workers,
                                 timeout_s=args.timeout, log=lambda m: print(m, flush=True))
    except PipelineError as e:
        print(f"error: {e}", file=sys.stderr)
        return e.exit_code
    _print_qa(outcome.qa, args.out)
    print(f"stage seconds: {outcome.stage_seconds}")
    return EXIT_QA_FAILED if outcome.status == FAIL else EXIT_OK


def _bundle_profile(out_dir: Path) -> str:
    try:
        return json.loads((out_dir / "manifest.json").read_text(encoding="utf-8")).get("profile") or "full"
    except (OSError, json.JSONDecodeError):
        return "full"


def _cmd_qa(args: argparse.Namespace) -> int:
    from robotics101.media import MediaError
    from robotics101.pipeline import FAIL, qa_bundle

    if not args.out_dir.is_dir():
        print(f"error: {args.out_dir} is not a directory", file=sys.stderr)
        return EXIT_INPUT
    try:
        if _schema_version(args.out_dir / "episode.json") == "1.1":
            from robotics101.cartoon.pipeline import qa_and_seal_cartoon
            doc = qa_and_seal_cartoon(args.out_dir, args.profile or _bundle_profile(args.out_dir))
        else:
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


def _cmd_voice(args: argparse.Namespace) -> int:
    from robotics101.characters import RegistryError, load_registry
    from robotics101.qa import QaReport
    from robotics101.voice import VoiceCache, VoiceError, select_backend, voice_episode
    from robotics101.voice.dialogue import cost_summary, plan_lines
    from robotics101.voice.qa import check_dialogue

    rc = _cmd_validate(argparse.Namespace(episode=args.episode, strict=False))
    if rc != EXIT_OK:
        return rc
    spec = json.loads(args.episode.read_text(encoding="utf-8"))
    if spec.get("schemaVersion") != "1.1":
        print("error: `voice` is for cartoon episodes (schema 1.1); use `narrate` for 1.0", file=sys.stderr)
        return EXIT_INPUT
    try:
        registry = load_registry()
        from robotics101.cartoon.episode import expand_episode
        spec = expand_episode(spec, registry)          # M03 defaults (intro, ...) for every episode
        backend, skipped = select_backend(args.tts)
        cache = VoiceCache()
        for why in skipped:
            print(f"voice: skipping {why}")
        if args.plan_only:
            c = cost_summary(plan_lines(spec, registry, backend, cache), backend)
            print(f"plan: {c['provider']} {c['lines']} lines, {c['cachedLines']} cached, {c['charsTotal']} chars, "
                  f"{c['billableChars']} billable (nothing synthesized)")
            return EXIT_OK
        args.out.mkdir(parents=True, exist_ok=True)
        doc = voice_episode(spec, registry, args.out, backend, cache, skipped=skipped,
                            log=lambda m: print(m, flush=True))
    except (VoiceError, RegistryError) as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT
    for s in doc["scenes"]:
        print(f"  {s['sceneId']}: {s['scene_duration_s']:6.2f}s (target {s['target_duration_s']:.0f}s)  speech "
              f"{s['speech_s']:5.1f}s ({s['speech_coverage']:.0%})")
    print(f"total {doc['totalDurationSeconds']:.1f}s, speech {doc['totalSpeechSeconds']:.1f}s "
          f"({doc['speechCoverage']:.0%}); provider {doc['provider']}")
    rep = QaReport(spec["episodeId"], "voice", str(args.out))
    check_dialogue(rep, args.out)
    for c in rep.failures + rep.warnings:
        print(f"  {c.status.upper()} {c.id}: {c.message}")
    (args.out / "voice_qa.json").write_text(json.dumps(rep.to_dict(), indent=2, ensure_ascii=False) + "\n",
                                            encoding="utf-8")
    print(f"dialogue QA {rep.status}; wrote {args.out / 'timing.json'}, {args.out / 'captions.srt'}, "
          f"{args.out / 'voice'}/")
    return EXIT_QA_FAILED if rep.failures else EXIT_OK


def _cmd_voices(args: argparse.Namespace) -> int:
    from robotics101.characters import load_registry
    from robotics101.voice import ElevenLabsBackend, VoiceCache, VoiceError
    from robotics101.voice.backends import KEY_ENV, decode_to_wav

    el = ElevenLabsBackend()
    if not el.available()[0]:
        print(f"error: {KEY_ENV} is not set; no ElevenLabs call was made", file=sys.stderr)
        return EXIT_INPUT
    try:
        if args.voices_cmd == "samples":
            reg = load_registry()
            args.out_dir.mkdir(parents=True, exist_ok=True)
            total = 0
            for cid in ("bolt", "maya"):
                voice = reg.get(cid).voice
                text = AUDITION_LINES[cid]
                total += len(text)
                req = el.request(voice, text)
                raw, cached = VoiceCache().get_or_render(el, req)
                out = args.out_dir / f"elevenlabs-sample-{cid}.wav"
                decode_to_wav(raw, out, el.fx(voice))
                print(f"{'cached' if cached else 'synthesized'} {cid} ({voice['elevenlabs']['voiceId']}, "
                      f"{len(text)} chars) -> {out}")
            print(f"{total} characters. Ask the owner to approve these voices before voicing the full episode.")
            return EXIT_OK
        if args.voices_cmd == "list":
            for v in el.list_voices():
                labels = ", ".join(f"{k}={x}" for k, x in sorted(v["labels"].items()))
                print(f"{v['voiceId']}  {v['name']}  [{v['category']}]  {labels}")
            return EXIT_OK
        ch = load_registry().get(args.character)
        if ch is None or not ch.voice:
            print(f"error: {args.character!r} is not a speaking character", file=sys.stderr)
            return EXIT_INPUT
        voice = json.loads(json.dumps(ch.voice))
        if args.voice_id:
            voice["elevenlabs"]["voiceId"] = args.voice_id
        text = args.text or AUDITION_LINES.get(ch.id, "Hi! Welcome to Robotics 101.")
        if len(text) > 200:
            print("error: audition text is limited to 200 characters", file=sys.stderr)
            return EXIT_INPUT
        req = el.request(voice, text)
        raw, cached = VoiceCache().get_or_render(el, req)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        decode_to_wav(raw, args.out, el.fx(voice))
        print(f"{'cached' if cached else 'synthesized'} {len(text)} chars with voice {voice['elevenlabs']['voiceId']}"
              f" -> {args.out}")
        return EXIT_OK
    except VoiceError as e:
        print(f"error: {e}", file=sys.stderr)
        return EXIT_INPUT


def _cmd_model_sheet(args: argparse.Namespace) -> int:
    try:
        from robotics101.cartoon.model_sheet import render_sheets
    except ImportError as e:
        print(f"error: model sheets need manim ({e})", file=sys.stderr)
        return EXIT_INPUT
    try:
        w, h = (int(x) for x in args.size.lower().split("x"))
    except ValueError:
        print("error: --size must look like 1920x1080", file=sys.stderr)
        return EXIT_INPUT
    for p in render_sheets(args.out, w, h):
        print(f"wrote {p}")
    return EXIT_OK


def _cmd_motion_test(args: argparse.Namespace) -> int:
    from robotics101.cartoon.motion_test import render_motion_test

    if not (args.voice_dir / "timing.json").is_file():
        print(f"error: {args.voice_dir}/timing.json missing — run `robotics101 voice` first", file=sys.stderr)
        return EXIT_INPUT
    w, h = (int(x) for x in args.size.lower().split("x"))
    info = render_motion_test(args.voice_dir, args.out, w, h)
    print(json.dumps(info, indent=2))
    return EXIT_OK


def _cmd_render_cartoon(args: argparse.Namespace) -> int:
    from robotics101.cartoon.scenes import render_cartoon_scenes

    if not (args.voice_dir / "timing.json").is_file():
        print(f"error: {args.voice_dir}/timing.json missing — run `robotics101 voice` first", file=sys.stderr)
        return EXIT_INPUT
    w, h = (int(x) for x in args.size.lower().split("x"))
    rep = render_cartoon_scenes(args.episode, args.voice_dir, args.out, w, h, args.only or None,
                                robotcam=not args.no_robotcam)
    print(json.dumps({s["sceneId"]: s["minPresence"] for s in rep["scenes"]}, indent=2))
    return EXIT_OK


def _cmd_mix(args: argparse.Namespace) -> int:
    from robotics101.cartoon.audio import check_mix, mix_episode
    from robotics101.qa import QaReport

    tp = args.voice_dir / "timing.json"
    if not tp.is_file():
        print(f"error: {tp} missing — run `robotics101 voice` first", file=sys.stderr)
        return EXIT_INPUT
    timing = json.loads(tp.read_text(encoding="utf-8"))
    mix_episode(timing, args.voice_dir, args.out)
    rep = QaReport(timing.get("episodeId"), "mix", str(args.out))
    lic = Path(__file__).resolve().parents[2] / "assets" / "LICENSES.json"
    res = check_mix(rep, args.out, timing, json.loads(lic.read_text(encoding="utf-8")) if lic.is_file() else None)
    for c in rep.checks:
        print(f"  {'PASS' if c.ok else 'FAIL'} {c.id}: {c.message}")
    print(json.dumps(res, indent=2))
    return EXIT_OK if all(c.ok for c in rep.checks if c.severity == "hard") else 1


AUDITION_LINES = {
    "bolt": "Ow! Who put a wall there? Sense, think, act. Like a tiny dance, but with math!",
    "maya": "Bolt, that's not a wall. It's a pile of boxes! Today, you're going to learn how robots notice things.",
}


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

    r = sub.add_parser("render", help="end-to-end: validate -> narrate/voice -> render scenes -> (mix) -> compose -> "
                                      "manifest -> QA. Schema 1.1 specs use the cartoon pipeline.")
    r.add_argument("episode", type=Path)
    r.add_argument("--out", type=Path, required=True, help="bundle directory, e.g. out/episode-001")
    r.add_argument("--profile", choices=["preview", "full"], default="preview",
                   help="preview = 854x480@30 (default, fast), full = 1920x1080@30")
    r.add_argument("--tts", choices=["espeak", "fixture", "auto", "kokoro", "elevenlabs"], default=None,
                   help="1.0: espeak|fixture (default env TTS_PROVIDER, else espeak). 1.1 cartoon: auto (default; "
                        "ElevenLabs only once the registry voices are approved, else Kokoro, else espeak)|kokoro|"
                        "espeak|elevenlabs")
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

    vo = sub.add_parser("voice", help="cartoon (schema 1.1): synthesize character lines -> timing.json, captions.srt, "
                                      "voice/ stems (ElevenLabs -> Kokoro -> espeak; cached by content hash)")
    vo.add_argument("episode", type=Path)
    vo.add_argument("--out", type=Path, required=True)
    vo.add_argument("--tts", choices=["auto", "elevenlabs", "kokoro", "espeak", "fixture"], default="auto",
                    help="auto (default) = ElevenLabs if ELEVENLABS_API_KEY is set, else Kokoro, else espeak")
    vo.add_argument("--plan-only", action="store_true",
                    help="print line/char counts and billable characters; synthesize nothing")
    vo.set_defaults(func=_cmd_voice)

    vs = sub.add_parser("voices", help="ElevenLabs voice tools (need ELEVENLABS_API_KEY)")
    vsub = vs.add_subparsers(dest="voices_cmd", required=True)
    vsub.add_parser("list", help="list voices available to the account (free; no credits)")
    sm = vsub.add_parser("samples", help="one short sample line each for Bolt and Maya with the registry voices "
                                         "(for owner approval; ~180 chars, cached)")
    sm.add_argument("--out-dir", type=Path, default=Path("/workspace/robotics101-samples"))
    au = vsub.add_parser("audition", help="synthesize one short test line for a character (<=200 chars, cached)")
    au.add_argument("character")
    au.add_argument("--voice-id", help="try a different ElevenLabs voice id (registry unchanged)")
    au.add_argument("--text")
    au.add_argument("--out", type=Path, required=True, help="output .wav")
    vs.set_defaults(func=_cmd_voices)

    ms = sub.add_parser("model-sheet", help="render the cast model sheets (rigs, expressions, mouths, poses) to PNG")
    ms.add_argument("--out", type=Path, required=True)
    ms.add_argument("--size", default="1920x1080")
    ms.set_defaults(func=_cmd_model_sheet)

    mt = sub.add_parser("motion-test", help="render the 15 s rig/lip-sync motion test from a `voice` output dir")
    mt.add_argument("--voice-dir", type=Path, required=True)
    mt.add_argument("--out", type=Path, required=True, help="output .mp4")
    mt.add_argument("--size", default="1920x1080")
    mt.set_defaults(func=_cmd_motion_test)

    rc = sub.add_parser("render-cartoon", help="render cartoon scenes (video only) from a `voice` output dir")
    rc.add_argument("episode", type=Path)
    rc.add_argument("--voice-dir", type=Path, required=True)
    rc.add_argument("--out", type=Path, required=True)
    rc.add_argument("--size", default="1920x1080")
    rc.add_argument("--only", action="append", help="sceneId (repeatable)")
    rc.add_argument("--no-robotcam", action="store_true", help="skip the Blender robot-cam cutaway in the rematch")
    rc.set_defaults(func=_cmd_render_cartoon)

    mx = sub.add_parser("mix", help="cartoon: generate music + SFX and mix with the dialogue -> <out>/audio (+ mix QA)")
    mx.add_argument("--voice-dir", type=Path, required=True)
    mx.add_argument("--out", type=Path, required=True)
    mx.set_defaults(func=_cmd_mix)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
