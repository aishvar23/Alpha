# M01 progress (session handoff)

Read this first in each new session. Spec: `tasks/M01_LOCAL_VERTICAL_SLICE.md`; rules: `AGENTS.md`.

| Step | Scope | Status |
|---|---|---|
| M01.1 | Scaffold: package, CLI `validate`, template registry, tests, Makefile | **done** |
| M01.2 | Narration: TTS provider interface + labelled fixture/placeholder voice, per-scene audio, SRT | **done** |
| M01.3 | Manim templates: robot_intro, robot_anatomy, sensor_range, sense_think_act, servo_rotation, recap_quiz; `render-scenes` CLI | **done** |
| M01.4 | Headless Blender scene: mobile_robot_avoidance (primitives only) | todo (next) |
| M01.5 | Composer (FFmpeg) + ffprobe QA report + SHA-256 manifest + `robotics101 render` / `make demo` | todo |
| M01.6 | First E2E run → `out/episode-001/final.mp4`; publisher dry-run stub (no uploads) | todo |

## M01.1 — what exists
- `pyproject.toml` (hatchling, src layout, console script `robotics101`, deps: jsonschema; dev: pytest).
- `src/robotics101/validation.py` — JSON Schema (`contracts/episode.schema.json`, override via `ROBOTICS101_SCHEMA`) + semantic checks. Returns `ValidationReport` of `Issue(severity, path, message)`.
  - **Errors** (exit 1): schema violations; duplicate `sceneId`; duplicate/non-contiguous `sequence` (must be 1..N); unknown `(engine, template)`; invalid template params.
  - **Warnings** (exit 0, exit 1 with `--strict`): episode `durationTargetSeconds` outside 270–330 s; sum of scene targets differs >10% from episode target. Scene targets are planning hints; real timing comes from audio in M01.2/M01.5.
- `src/robotics101/templates/registry.py` — `REGISTRY[(engine, name)] -> TemplateSpec` for the 7 templates in episode-001 (6 manim + `blender/mobile_robot_avoidance`). Each validator rejects unknown keys; notable rules: sensor_range `0 < obstacleDistanceMeters <= rangeMeters`; servo_rotation angles in 0..180; blender `robotAsset`/`obstacle` must be in a primitive-asset allowlist. Render implementations attach here in M01.3/M01.4.
- `src/robotics101/geometry.py` — pure helpers `obstacle_detected`, `servo_angle_in_limits`.
- `src/robotics101/cli.py` — `validate <episode.json> [--strict]`; `render` placeholder exits 3 with "not implemented yet (M01.5)". Exit codes: 0 ok, 1 invalid, 2 input error, 3 not implemented.
- `tests/` — 32 tests (validation, geometry, CLI). `Makefile`: `install`, `test`, `validate`, `demo` (placeholder, exits 1), `clean`.

## M01.2 — what exists
- `src/robotics101/narration/providers.py` — `TtsProvider.synthesize(text, out_wav) -> NarrationResult(path, duration_s, provider, is_synthetic_placeholder, label)`. Selection: `--provider` > env `TTS_PROVIDER` > `espeak`.
  - `espeak`: espeak-ng `en-us` @150 wpm, resampled by ffmpeg to 48 kHz mono s16 WAV. Label "offline synthetic TTS (espeak-ng) — not production narration".
  - `fixture`: pure-Python deterministic 440 Hz beeps (one per word), length = words @150 wpm, 48 kHz mono. Label "FIXTURE placeholder audio — not narration". No binaries needed.
  - `external`: stub; errors if `TTS_EXTERNAL_URL`/`TTS_EXTERNAL_API_KEY` unset, and still errors (no network call) if set.
  - Duration measured with ffprobe (falls back to WAV header if ffprobe missing).
- `narration/timing.py` — `scene_duration = max(durationTargetSeconds, audio + 0.5 lead-in + 0.5 tail)`; narration starts at lead-in; remainder is hold; scenes contiguous on episode timeline. `narrate_episode()` writes `<out>/audio/<sceneId>.wav`, `<out>/timing.json` (per scene: audio path/duration, scene start/end, narration start/end, hold, speech coverage, provider label, `qa_flags`), `<out>/captions.srt`. QA flags: speech coverage <60% ("voice content too short; holds fill gap — not acceptable educational pacing") and synthetic/placeholder audio.
- `narration/captions.py` — sentence → clause → word-packed cues (≤2 lines × 42 chars), times proportional to char count inside each scene's narration window (integer ms, contiguous, non-overlapping). `parse_srt` / `validate_srt` used by tests (and by M01.5 QA).
- CLI `robotics101 narrate <episode.json> --out DIR [--provider espeak|fixture|external]`: validates first (exit 1 if invalid), exit 2 on provider/TTS error. `make narrate [TTS_PROVIDER=fixture]`.
- `tests/test_narration.py` — 15 tests (47 total); espeak tests auto-skip without espeak-ng/ffmpeg.

### Sample run (espeak, 2026-11-22)
7 WAVs, mean volume ≈ -22 dB each; speech 66 s of 300 s total (22%); **all 7 scenes flagged** voice-too-short — expected: sample narration is ~10 s/scene vs 25–55 s targets. Expand narration before treating any render as a real pilot.

### Known limitations
- espeak-ng is robotic; acceptable for timing/sync only. Production voice provider undecided (`docs/DECISIONS.md`).
- Caption timing is proportional estimate within the audio window, not forced alignment; espeak trailing silence slightly stretches the last cue.
- Timing ignores crossfades; M01.5 composer must consume `timing.json` as-is or recompute if it adds transitions.

## M01.3 — what exists
- `src/robotics101/geometry.py` (pure, unit-tested): `servo_arm_endpoint(angle, length, pivot)` (0° = +x, CCW, 90° up), `sensor_units_per_meter` / `meters_to_scene_x` (linear to-scale mapping), `tick_step_meters`, `threshold_decision(distance, threshold)` (strict `<` → `STOP_AND_TURN`, else `KEEP_GOING`), `reading_sweep(threshold)` (3× → 0.5× threshold).
- `src/robotics101/animation/timing.py`: `target_frames = round(duration × fps)`, `animation_speed` (templates script a fixed `NOMINAL_SECONDS`; compressed only when the scene is shorter than that + hold), `resolve_scene_durations(spec, timing.json)` (falls back to `durationTargetSeconds`; errors on a stale timing.json for another episode / missing scenes).
- `src/robotics101/animation/manim_templates/` — one module per template + `_base.py` (style: dark bg, Inter, title + rule at top, ≥0.45-unit margins, min font_size 24 ≈ 33 px cap height at 1080p; word-wrap that shrinks then wraps; baseline strut so texts in a row align), `_shapes.py` (primitive robot drawings), `_widgets.py` (LaTeX-free ruler, metre formatting), `entry.py` (file passed to manim; re-declares the classes because manim only discovers classes defined in that module). `TemplateScene` loads the job JSON from env `ROBOTICS101_SCENE_JOB`, re-validates params against the registry, quantises every animation/pause to whole frames, asserts all mobjects are inside the frame, then pads with a frozen-frame hold to exactly `target_frames`.
  - robot_intro: episode title card → each example robot (vacuum / arm / rover icons, generic robot for unknown names) with label → tagline.
  - robot_anatomy: robot drawing; each part label appears in turn on the side of its anchor with arrow + highlight (aliases: body/chassis, battery, motors/wheels, brain/computer…; unknown names point at the outline).
  - sensor_range: rover + beam to `rangeMeters`, metre ruler, obstacle face drawn at `obstacleDistanceMeters` to scale, ping out/back, distance arrow, readouts, red "OBSTACLE DETECTED".
  - sense_think_act: Sense → Think → Act boxes + loop arrow, rule text, scale with threshold marker; reading sweeps 3×→0.5× threshold, decision text flips KEEP GOING → STOP & TURN via `threshold_decision`.
  - servo_rotation: servo body + horn, 0–180° protractor, arm tip from `servo_arm_endpoint` every frame, sweep arc start→current, live angle readout, start/target labels.
  - recap_quiz: three Sense / Decide / Act rows, "Quick question" panel with the wrapped question.
- `src/robotics101/animation/render.py`: profiles `preview` 854×480@30 / `full` 1920×1080@30; finds manim (`$MANIM_BIN` → venv → PATH) and ffmpeg/ffprobe or prints exact prerequisites; runs manim per scene in a subprocess (timeout, cwd/media in `<out>/.manim/<sceneId>`, log `<out>/logs/<sceneId>.log`), up to 4 in parallel; moves the clip to `<out>/scenes/<sceneId>.mp4`; skips `engine=blender` with a message pointing to M01.4. `probe.py`: ffprobe (decodes/counts frames) → resolution, nominal fps, frames & container duration within ±1 frame, no audio.
- CLI `robotics101 render-scenes <episode.json> --out DIR [--profile preview|full] [--only SCENE_ID]... [--workers N] [--timeout S]` → validates first; writes `<out>/scenes/render-report.json`. Exit 0 ok / 1 invalid spec / 2 input error or missing prereqs / 4 a scene failed. `make scenes [PROFILE=full]`, `make scenes-full`.
- `pyproject.toml` extra `render = ["manim==0.22.1"]`. ADR-010 in `docs/DECISIONS.md`.
- Tests: 90 total (`make test` ≈ 5 s). New: geometry (servo endpoint, sensor scale, ticks, threshold), timing/duration resolution, registry↔scene-class wiring, AST check that templates import no LaTeX-backed manim classes, job contract, ffprobe checks on an ffmpeg testsrc clip, prerequisites message, CLI errors, Blender skip, and a real Manim smoke render (servo, 2 s preview → 60 frames). Render tests auto-skip if manim/ffmpeg are missing.

### Sample run (2026-11-22, espeak timing.json, preview, 8 CPUs)
`narrate` + `render-scenes --profile preview`: 6 clips in ~17 s wall, frame counts exactly 900/1500/1500/1650/1350/750 (= timing.json 30/50/50/55/45/25 s), h264 854×480 30/1; scene-006 skipped (Blender). `--profile full` checked on scene-003/007 (1920×1080, ~10–13 s each). End and mid frames of every scene were extracted and inspected: no overflow/overlap; sensor obstacle measured at 1.2 m of 3 m on screen; servo arm at 60°.

### Known limitations
- Animations occupy the first ~9–14 s of each scene (fixed script), not synchronised to individual narration words; the rest is a static hold. With the short sample narration this means long frozen holds (already flagged by narrate's QA). Expanding narration should come with longer/beat-based template scripts.
- Templates are tuned for episode-001-like parameters; extreme inputs (8 long anatomy parts, 6 long example names, very long question) shrink to min font size and then scale, which the frame check guards but might look cramped.
- `Text` rendering depends on the Inter font being installed (pango falls back silently otherwise). Manim 0.22's `-o` is unusable with multi-class entry files, so the clip is located by class name.
- Not sandboxed yet: manim runs as a normal local subprocess (acceptable for template-only code; isolation is a production requirement per AGENTS.md).

## Commands
```bash
make install && make test && make validate
make narrate                       # espeak (needs espeak-ng + ffmpeg)
make narrate TTS_PROVIDER=fixture  # no external binaries
make scenes                        # Manim preview clips -> out/episode-001/scenes/*.mp4 (needs manim + ffmpeg)
make scenes PROFILE=full           # 1920x1080@30
.venv/bin/robotics101 render-scenes examples/episode-001.json --out out/episode-001 --only scene-003
```
Environment notes: `.venv` is Python 3.12 with manim/jsonschema/pytest; add packages with `uv pip install --python .venv/bin/python <pkg>`. GNU `make` was installed via apt in the dev container (wasn't present by default). espeak-ng 1.52, ffmpeg/ffprobe and sox are installed in the dev container; Blender not yet checked — M01.4/M01.5 must detect binaries and print exact prerequisites.

## Next step: M01.4
Headless Blender scene `mobile_robot_avoidance` (primitive robot + cube/cylinder obstacle from the allowlist): drive forward, detect obstacle, stop, turn, resume. Render to `<out>/scenes/scene-006.mp4` for exactly its `timing.json` duration with the same profiles (preview/full, 30 fps), reuse `animation/probe.py` checks and the `render-scenes` CLI (currently prints "skipped … M01.4" for blender scenes). Detect the `blender` binary and print exact prerequisites if missing; Blender was not yet checked in the dev container. Keep FFmpeg composition (M01.5) out of scope.
