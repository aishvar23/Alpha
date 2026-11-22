# M01 progress (session handoff)

Read this first in each new session. Spec: `tasks/M01_LOCAL_VERTICAL_SLICE.md`; rules: `AGENTS.md`.

| Step | Scope | Status |
|---|---|---|
| M01.1 | Scaffold: package, CLI `validate`, template registry, tests, Makefile | **done** |
| M01.2 | Narration: TTS provider interface + labelled fixture/placeholder voice, per-scene audio, SRT | **done** |
| M01.3 | Manim templates: robot_intro, robot_anatomy, sensor_range, sense_think_act, servo_rotation, recap_quiz; `render-scenes` CLI | **done** |
| M01.4 | Headless Blender scene: mobile_robot_avoidance (primitives only) | **done** |
| M01.5 | Composer (FFmpeg) + ffprobe QA report + SHA-256 manifest + `robotics101 render` / `make demo` | **done** |
| M01.6 | First E2E run → `out/episode-001/final.mp4`; publisher dry-run stub (no uploads) | **done** |
| M02.1 | Cartoon contract v1.1 (dialogue beats), character registry, cartoon episode-001 script, fact + kid-safe lints | **done** |
| M02.2 | Voice layer: ElevenLabs (env key, content-hash cache) → Kokoro → espeak; dialogue timeline; speaker SRT | **done** (ElevenLabs path tested with a mocked API; real calls wait for the key) |
| M02.3 | Character rigs (Bolt, Maya, Nib): expressions, Rhubarb mouth shapes, blink/gaze/squash/lean/arms/facing; model sheets + golden-image tests | **done** |
| M02.4 | Motion (performers, actions, blinks, idle/talk, squash/stretch hops) + Rhubarb lip sync (RMS fallback) + parallel 2D clip renderer; 15 s motion test | **done** |
| M02.5–M02.8 | Sets/props, cartoon scene engine, music/SFX, full episode (see docs/PLAN-cartoon.md) | todo |

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

## M01.4 — what exists
- `src/robotics101/kinematics.py` (pure, stdlib, Python 3.11-compatible because Blender imports it): `Box2D`, `RobotGeometry` (box chassis 0.60×0.40 m, 2 drive wheels r=0.11 m on a 0.52 m track + front caster, sensor 0.32 m ahead of centre), `AvoidanceConfig` (cube 0.6 m at x=4, sensor range 1.5 m, stop threshold 0.5 m (M01.5: overridden by the episode's sense_think_act thresholdMeters), 0.35 m/s, 45°/s, 90° left turn, 2.4 m resume, 0.05 m collision margin). `generate_avoidance_path()` simulates sense→think→act once per frame with `geometry.threshold_decision` (stop on the first reading < threshold) → `Pose` per frame (x, y, heading, cumulative wheel angles = distance / r, differential counter-rotation when turning, reading, alert, phase start/drive/detected/turn/resume). `time_scale` compresses the script for short scenes. `ray_box_distance` (slab), `footprint_corners`, `polygon_intersects_box` (SAT, margin-grown box), `find_collision`, `assert_collision_free` (`CollisionError`), `scene_bounds`.
- `src/robotics101/animation/blender_templates/__init__.py`: `TEMPLATE_SCRIPTS` allowlist + `plan_mobile_robot_avoidance(params, duration, fps)` (nominal ≈19.8 s script, `animation_speed` compression only if the scene is too short, `collisionCheck` default on). Shared by host and Blender so both run the identical plan.
- `src/robotics101/animation/blender_templates/mobile_robot_avoidance.py` — Blender script (`blender --background --factory-startup --python-exit-code 1 --python … -- --params job.json --out FRAMES --width W --height H --fps 30 [--engine workbench|eevee] [--aa N] [--frames A:B] [--summary plan.json]`). Re-validates params via the registry, re-runs the plan + collision check, builds primitives only (ground + 1 m grid, blue box chassis + lid, wheels with yellow spoke so spin is visible, caster, two-"eye" ultrasonic sensor, cube or cylinder obstacle, translucent cone beam whose length = the reading, green clear / amber in range / red < threshold), 3-point lights (EEVEE only), camera at a 3/4 front-left angle pulled back + lens-shifted until every footprint, beam tip and the obstacle project inside a safe region clear of the HUD (fails otherwise). Camera-parented HUD (sizes in 1080p px, resolution-independent): title, live "Sensor: 0.59 m" / "path clear" readout, the rule "stop & turn if distance < 0.60 m", and step chips "Drive → Obstacle detected → Stop → Turn → Resume" with the current step highlighted. Each motion frame is set explicitly and rendered to `NNNNN.png`.
- `src/robotics101/animation/blender_render.py` — `find_blender()` (`$BLENDER_BIN` → PATH, runs `--background --version`, requires ≥ 4.2, else `RenderSetupError` with `BLENDER_PREREQS`), host-side plan + collision check (fails the scene without launching Blender), frames split over `ROBOTICS101_BLENDER_PROCS` Blender processes (default min(4, CPUs/2), capped so N × ~800 MB (full) / ~500 MB (preview) fits in 75% of MemAvailable), overall timeout (kills all), per-process logs merged into `<out>/logs/<sceneId>.log`, frame-completeness check, ffmpeg encode (libx264 crf 18 yuv420p, `tpad` clones the last frame for the hold, `-frames:v` = target), then the shared `render.verify_clip` (same ffprobe checks as Manim). Work dir `<out>/.blender/<sceneId>` removed on success.
- `render.py`: `render_scenes` dispatches by engine; prerequisites are checked only for engines actually needed (a Blender-only run doesn't need manim); Blender jobs start first in the pool; unknown engine/template → failed result. CLI unchanged (`render-scenes` now renders both). ADR-011 documents the engine choice.
- Tests: 120 total (`make test` ≈ 9 s, includes a real 160×90 1 s Blender smoke render → 30 frames). New `test_kinematics.py` (17: ray sensing, phase order, stop within one step below threshold & no alert while driving, robot still while stopped, heading +90° after turn in place, resume end position, wheel angle = distance / r incl. turn counter-rotation, compression, never-detected and invalid configs, collision negative/positive/rotated-with-margin, too-small threshold → `CollisionError`, plan duration/hold, Python 3.11 + stdlib-only import check) and `test_blender.py` (13: registry↔script, script import allowlist / no asset loading, prerequisites + old-version messages, memory-aware process count, Blender-only run doesn't need manim, chunking, encode command, collision fails before launch, smoke render).

### Sample run (2026-11-22, espeak timing.json → scene-006 = 45.0 s)
- `render-scenes … --profile preview --only scene-006`: **~70 s wall**, 595 motion frames rendered (4 Blender procs) + 755 hold frames → h264 854×480 30/1, **1350 frames, 45.000 s**. Robot stops at frame 269 with reading 0.592 m < 0.60 m; collisionCheck passed.
- `--profile full`: **6 m 16 s wall** (1920×1080, 8× AA, ~2.4 s/frame per process × 4 procs, ~47 CPU-min), 1350 frames / 45.000 s. Peak RSS measured at ~760 MB per Blender process at 1080p (≈3 GB for 4 procs; hence the memory-aware default).
- Frames at 0.5 / 9.5 / 11.2 / 44.9 s inspected: robot + green beam driving; stopped with red short beam at the cube and "Obstacle detected → Stop" highlighted, "Sensor: 0.59 m" in red; mid-turn with beam back to green; resumed to the left and held, "Resume" highlighted. Everything inside the frame, nothing under the HUD.

### Known limitations
- Workbench look (studio light, simple shadows) — clean and readable, not photoreal; EEVEE path exists (`ROBOTICS101_BLENDER_ENGINE=eevee`; lights tuned, HUD emissive) but is ~5–10× slower (one 854×480 frame ≈4.5 s incl. shader compile, ~1.6 GB RSS) and was only checked on a single frame, not a full clip.
- Motion is ~20 s; the rest of the 45 s scene is a frozen hold (same limitation as the Manim scenes; already flagged by narrate's QA because the sample narration is short).
- Scene layout (obstacle position, distances, speeds) is fixed in `AvoidanceConfig`; spec params only choose cube/cylinder and toggle `collisionCheck`. A cylinder is sensed/collision-checked by its bounding square (conservative).
- Collision check samples every rendered frame (≤1.2 cm motion per frame at nominal speed); it is not a continuous swept-volume check.
- Blender runs as a normal local subprocess (`--factory-startup`, `PYTHONNOUSERSITE=1`, no asset loading) — not sandboxed; isolation is still a production requirement.

## M01.5 — what exists
- **Threshold fix**: the Blender scene's stop threshold now comes from the episode's first `sense_think_act.thresholdMeters` (`blender_templates.episode_stop_threshold`, default 0.5 m), passed as job context `stopThresholdMeters` (not a template param); `AvoidanceConfig.stop_threshold` default 0.5. HUD readout is truncated to the cm (`format_reading_m`: 0.4983 → "0.49 m", never "0.50 m" next to "< 0.5 m") and the rule is written like the 2D scene ("< 0.5 m"). ADR-013.
- `src/robotics101/media.py` — ffmpeg/ffprobe discovery + version check, `run`, probe `summarize`, EBU R128 / volumedetect `audio_levels`, loudness gain + limiter filter, faststart check, `tool_versions`.
- `src/robotics101/compose/composer.py` — per scene: narration → 48 kHz stereo, gain to −16 LUFS + `alimiter` −1.5 dBFS, delayed by the lead-in, padded sample-exactly to the clip's frame count, 5 ms edge fades → `clips/<id>.mp4` (video stream copy + AAC). `final.mp4` = concat filter, one re-encode (libx264 High yuv420p CFR 30, GOP 60, crf 20, +faststart) + concatenated PCM → AAC 192k. Hard cuts. Captions regenerated on the frame-quantised timeline. Writes `compose.json`. ADR-012.
- `src/robotics101/manifest.py` — every artifact (path, SHA-256, bytes, probe summary), `specSha256`, `finalVideoSha256`, `publish = {status: not_published, requiresApprovalOfSha256}`, tool versions, run id, TTS label, stage timings; `verify_manifest`; QA report hashes sealed in after QA.
- `src/robotics101/qa.py` — hard gates (decodable, h264 High yuv420p, resolution, 30 fps CFR, AAC 48k stereo, not silent, no clipping, 270–330 s and = timeline, A/V lengths ±0.1 s, captions, scene/clip durations, manifest hashes) and soft warnings (synthetic TTS, voice coverage < 60 %, preview profile, loudness ±2 LU, faststart) → `qa_report.json` + `qa_report.md` (per-scene table). Status PASS / PASS_WITH_WARNINGS / FAIL.
- `src/robotics101/pipeline.py` + CLI: `robotics101 render <episode> --out DIR [--profile preview|full] [--tts espeak|fixture]` (validate → narrate → render-scenes → compose → manifest → QA; stale outputs deleted first) and `robotics101 qa DIR`. Exit codes 0 / 1 / 2 / 4 / 5 (QA FAIL). Make: `render`, `qa`, `demo` (preview), `demo-full`, `test-e2e`.
- Tests: 151 collected (`make test`: 150 passed, 1 skipped = the slow E2E, run with `make test-e2e` / `ROBOTICS101_E2E=1`, 2 passed in ~110 s). New `test_compose.py` (synthetic colour clips + tones → compose, durations/streams, QA FAILs on wrong resolution / silent audio, manifest detects a 1-byte change, …), `test_render_e2e.py`, threshold tests in `test_kinematics.py` / `test_blender.py`.

### Sample run (2026-11-22, `render … --profile full --tts espeak` → out/episode-001-full)
- Stage seconds: narrate 0.9, render-scenes 406 (scene-006 Blender ≈ 6–7 min dominates; Manim scenes 25–65 s each in parallel), compose 34, manifest 2, QA 22; total ≈ 7.7 min on 8 CPUs.
- final.mp4: h264 High yuv420p 1920×1080 30/1, 9000 frames, 300.000 s; AAC-LC 48 kHz stereo 300.000 s; 16.2 MB. Integrated −16.1 LUFS, max −1.2 dBFS, mean −26 dB. captions.srt 16 cues, last ends 284.7 s. 29 manifest artifacts. QA **PASS_WITH_WARNINGS**: 0 hard failures, 8 warnings (7× voice coverage 18–41 %, synthetic espeak TTS). Robot stops at reading 0.498 m < 0.5 m (HUD "Sensor: 0.49 m", "rule: … < 0.5 m").

### Known limitations
- Sample narration is a short stub (66 s of speech in 300 s): each scene animates for ~10–20 s then holds a still; QA warns per scene. espeak voice is a robotic placeholder.
- AAC bitrate shows ~40 kb/s average because most of the programme is silence (encoder target 192k).
- Audio built in Python from PCM (whole programme in memory: ~115 MB at 300 s stereo 48 kHz float) — fine for 5-min episodes.

## M01.6 — what exists
- **First E2E run + frame-by-frame review** of `examples/episode-001.json` at 1080p (`render … --out out/episode-001 --profile full --tts espeak`). Every second of every scene was sampled into contact sheets (plus key frames at cuts and beats) and inspected; narration onsets checked with `silencedetect` (speech starts at +0.5 s of every scene, matching captions). Defects found and fixed:
  1. scene-004 (sense_think_act): the distance scale had only "0 m" and the threshold label — no end value, so the bar's scale was unreadable. Scale end is now rounded up to a 0.5 m step (2.0 m for threshold 0.5) and labelled.
  2. scene-006 (Blender HUD): the active "Drive" step chip was red (the alert colour) while the robot simply drove; Drive/Resume chips are now green, Detected/Stop/Turn red.
  (M01.5 already fixed the 0.6 m vs 0.5 m threshold and the "Sensor: 0.50 m" < "0.50 m" readout.) No sync, cut, overflow or clipping defects found.
- `compose/thumbnail.py` — `thumbnail.png` 1280×720 from the 3D demo (≈10 s into scene-006, the obstacle-detected beat) with an "Ep. 1: What Is a Robot?" band (ffmpeg `drawtext`, Inter via fontconfig; untitled if no font). Listed in the manifest (role `thumbnail`); QA soft-checks 1280×720.
- `publish/youtube_stub.py` + `robotics101 publish <out> --dry-run` / `make publish-dry-run` — dry run only: verifies final.mp4 against manifest (mismatch/tampering → refused, exit 6), writes `publish_plan.json` (snippet title/description/tags/category 27, status private + containsSyntheticMedia, selfDeclaredMadeForKids left null for the owner, captions/thumbnail refs with SHA-256, chapters from scene starts, QA summary, `approval.json` state, blockers; `wouldUpload: false`, `networkCalls: 0`). Without `--dry-run`: "real upload not implemented (M06); requires owner approval…", exit 6. `approval.json` = `{approvedSha256, reviewer, decision: "approved", timestamp}` bound to the exact video hash. No network/Google/OAuth imports (AST test) and a socket-blocking test. ADR-014.
- Tests: 162 collected — `make test` 161 passed, 1 skipped (E2E; `make test-e2e` 2 passed, ~110 s). New `test_publish.py` (11).

### Sample run (2026-11-22, espeak, full)
- Stage seconds: narrate 1.0, render-scenes 468, compose+thumbnail 36, manifest 2, QA 22 (total ≈ 8.8 min on 8 CPUs).
- final.mp4: h264 High yuv420p 1920×1080 30/1, 9000 frames, 300.000 s; AAC-LC 48 kHz stereo 300.000 s; 16.2 MB; −16.1 LUFS integrated, max −1.2 dBFS. captions.srt 16 cues. manifest 30 artifacts, `finalVideoSha256` 193dee4f…7b42, publish not_published. QA PASS_WITH_WARNINGS (0 hard, 8 warnings: voice coverage 18–41 % ×7, synthetic TTS).

## M02.1 — what exists
- `contracts/episode.v1.1.schema.json`: schemaVersion "1.1", required `characters`, `set`, `publishing.madeForKids`; scenes on engine `cartoon` carry `beats` (line{speaker,text,emotion?,action?,target?} / sfx{id,who?} / action{who,do,emotion?,seconds?} / pause{seconds} / music{cue}). v1.0 still validates and renders as before.
- `characters/registry.json` + `src/robotics101/characters.py`: Bolt (speaks; ElevenLabs voice provisional "Lawrence" ktkP7Nsj67dw2zcplQYt, Kokoro am_puck, espeak en-us+m3 + robot fx), Maya (speaks; provisional "Jade" g7LVvkPWALzPxOQbF6OE, Kokoro af_bella, espeak en-us+f4), Nib (no voice; beeps). Expressions/actions/palette/caption colour per character; registry is hashed and checked (no credential fields, espeak fallback required).
- `src/robotics101/cartoon/`: SFX ids, music cues, sets; `lint.py` spoken-quantity parser (digits or words + unit, "half a meter", "zero point six") → teaching facts must match scene parameters; kid-safe deny list.
- 8 cartoon templates in the registry (cold_open, robot_family, robot_checkup, sensor_ping, rule_board, servo_highfive, obstacle_rematch, recap_chant) with parameter validation.
- `examples/episode-001-cartoon.json` "Bolt Bumps Into Everything": 8 scenes, 300 s target, 679 spoken words (Bolt/Maya), madeForKids true; `validate --strict` clean. `examples/episode-001.json` (v1.0) unchanged.
- Publish plan: `selfDeclaredMadeForKids` from `publishing.madeForKids`; undeclared audience is a blocker.
- `narrate`/`render-scenes`/`render` refuse schema-1.1 specs with exit 3 (cartoon pipeline lands in M02.2–M02.8).

## M02.2 — what exists
- `src/robotics101/voice/`: `backends.py` (ElevenLabs via stdlib urllib, key from env only, redacted errors, retry on 429/5xx, `list_voices`; Kokoro via kokoro-onnx with models in `models/kokoro/`; espeak-ng; fixture tones), `cache.py` (content-hash raw-audio cache in `tts-cache/`, atomic writes, ElevenLabs char ledger), `dialogue.py` (line plan, per-run char budget, beat timeline, whole-frame scene durations, per-scene 48 kHz stems, speaker-labelled SRT, timing.json v2), `qa.py` (stems match scene length, every line audible, speech-rate sanity, coverage, pacing vs target, total 270–330 s, production-voice warning, captions valid, API key not in any artifact).
- CLI: `voice` (+ `--plan-only`), `voices list|audition` (need the key).
- Registry: Bolt Kokoro speed 1.0; Bolt ElevenLabs gets a light chorus only (heavier pitch/tremolo fx stay for the fallbacks).
- Episode-001 cartoon targets re-balanced to dialogue (30/40/40/45/50/35/30/30 = 300 s).
- Kokoro run: 74 lines, 3,672 chars, 293.3 s, speech 74 %, QA PASS_WITH_WARNINGS (2 slightly fast short lines, not production voice); rerun fully cached and byte-identical. espeak run 342.4 s (over target; fallback only).
- Waiting on the owner: ELEVENLABS_API_KEY; then `voices list` → audition Bolt/Maya (≈200 chars) → confirm voice ids → full episode ≈3.7k credits.

## M02.3 — what exists
- `src/robotics101/cartoon/rigs.py` (rig v1 = registry `rigVersion`): pure `Pose -> VGroup` builders for Bolt, Maya, Nib. Pose = expression, mouth (Rhubarb A–H, X = expression's rest mouth), blink, gaze, squash (area-preserving, pivot at the feet), lean, arm angles (Nib: wing flap), facing, antenna glow, propeller phase, extras (stars, sweat, sparkle, zzz, question, heart). Ground contact at y=0 for every rig; every part addressable via `group.parts`. Palette/outline from the registry.
- Expressions implemented exactly match the registry lists (test). Bolt: happy, surprised, worried, proud, sleepy, dizzy, thinking, laugh; Maya: happy, grin, surprised, worried, thinking, laugh, proud; Nib: happy, surprised, proud, dizzy.
- `src/robotics101/cartoon/model_sheet.py` + `robotics101 model-sheet --out DIR`: cast lineup + one sheet per character (expressions / mouths / poses) via Manim's Cairo camera (~1 s per sheet).
- Golden images `tests/golden/model-sheet-*-960.png`: renders are bit-identical run to run; the test allows ≤ 60 changed pixels (a flipped Bolt smile changes ~400 px and fails). Re-bless after an intended rig change with `ROBOTICS101_UPDATE_GOLDEN=1 pytest tests/test_rigs.py` and review the PNGs.

## M02.4 — what exists
- `cartoon/motion.py`: `Performer` per character — eased moves (with flight/jump arcs), timed actions (every registry action has a motion: hop with anticipation/landing squash, bonk, dizzy, zoom, skid, turn (persists), wave, point, cheer, highfive, fly_to, land, fall, beep_dance, …), expression changes, gaze, airborne/perched, deterministic seeded blinks, idle breathing/hover and talk gestures. `state(t)` is a pure function of time → any frame renders independently.
- `cartoon/lipsync.py`: Rhubarb Lip Sync 1.14 (phonetic recogniser, ~1 s per line, deterministic; `tools/rhubarb/` or `RHUBARB_BIN`) → mouth cues A–H/X per line, cached in `tts-cache/lipsync/`; RMS fallback; `lipsync_agreement` metric (share of voiced frames with an open mouth).
- `cartoon/render2d.py`: frame function → Cairo frames → H.264 High yuv420p, chunked across processes and concatenated (450 frames of 1080p in ~10 s on this box); optional AAC 48 kHz stereo track trimmed sample-exactly.
- `robotics101 motion-test`: 15 s cold-open gag with real voiced lines (Kokoro) — lip-sync agreement 0.89–1.0.

## M02.5 — what exists
- `cartoon/sets.py` (garage set + variants, door, stage constants GROUND/FLOOR_Y/METER=2.2 u/m), `cartoon/props.py` (box pile, toaster, robot-family album, check-up list, battery/cable, glow outlines, ping/echo waves, floor tape measure (forward + reverse), range zone, HUD readout, chalkboard rule, SENSE/THINK/ACT chips, servo protractor, comic SFX lettering, speech bubble, title/quiz cards with word wrap, top-view inset).
- `cartoon/obstacle.py`: 10 Hz sensor, cm-truncated readings, `plan_approach` lands the stop on a beat at 0.49 m (< 0.5 m), `assert_no_collision`; 2D staging measured from Bolt's frontmost point (hands).
- Robot-cam cutaway (owner direction): the M01 Blender scene with `style: "cartoon"` (cartoon palette + ink outlines in Workbench, HUD title "ROBOT-CAM"), same motion plan/collision check/threshold; `cartoon/robotcam.py` builds/renders the job with the episode threshold (0.5 m).
- render2d: per-worker Manim media dir (parallel Text SVG cache race fixed).

## M01 status vs acceptance (tasks/M01_LOCAL_VERTICAL_SLICE.md)
- Done: validate CLI + schema/semantic checks; labelled offline TTS + per-scene timing + SRT; six Manim templates + headless Blender scene with collision check; composer (H.264/AAC 1080p30, −16 LUFS), QA report, SHA-256 manifest, `render`/`make demo`; thumbnail; publisher dry-run stub; no uploads/cloud.
- Not met by design / owner decisions pending: the sample narration is a short stub (66 s of speech in 300 s) so QA flags every scene for voice coverage and each scene animates ~10–20 s then holds; espeak is a robotic placeholder voice. Fuller narration + production voice (and then pacing animations to the narration window) are pending the owner's decision.

### Known limitations
- Thumbnail title band is 88 % opaque, so the HUD step chips faintly show through under it.
- Thumbnail frame choice is a fixed heuristic (not content-aware).
- Publisher is a stub: no OAuth, no upload, no resumable-upload/quota logic (M06).

## Commands
```bash
make install && make test && make validate
make narrate                       # espeak (needs espeak-ng + ffmpeg)
make narrate TTS_PROVIDER=fixture  # no external binaries
make scenes                        # Manim + Blender preview clips -> out/episode-001/scenes/*.mp4 (needs manim, blender, ffmpeg)
make scenes PROFILE=full           # 1920x1080@30 (scene-006 alone takes ~6 min on 8 CPUs)
make demo                          # end-to-end preview -> out/episode-001/{final.mp4,captions.srt,qa_report.*,manifest.json}
make demo-full                     # end-to-end 1920x1080@30 (~8 min)
.venv/bin/robotics101 render examples/episode-001.json --out out/episode-001-full --profile full --tts espeak
.venv/bin/robotics101 qa out/episode-001-full
.venv/bin/robotics101 render-scenes examples/episode-001.json --out out/episode-001 --only scene-003
.venv/bin/robotics101 render-scenes examples/episode-001.json --out out/episode-001 --profile preview --only scene-006
```
Environment notes: `.venv` is Python 3.12 with manim/jsonschema/pytest; add packages with `uv pip install --python .venv/bin/python <pkg>`. GNU `make` was installed via apt in the dev container (wasn't present by default). espeak-ng 1.52, ffmpeg/ffprobe and sox are installed in the dev container; Blender 4.3.2 is at /usr/bin/blender (headless, no GPU; EEVEE Next works via software GL but is slow; Cycles build lacks OpenImageDenoise).

## Next steps
- Owner decisions: expand narration to ~600–700 words (then pace animation beats to each scene's narration window) and pick a production TTS voice.
- M02 AI authoring (fixture LLM mode), M03 template library + render sandbox, M04 Azure orchestration, M05 review dashboard (approval UI writing `approval.json`), M06 real YouTube private upload (needs owner OAuth + explicit approval bound to `finalVideoSha256`).
