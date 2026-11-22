# M01 progress (session handoff)

Read this first in each new session. Spec: `tasks/M01_LOCAL_VERTICAL_SLICE.md`; rules: `AGENTS.md`.

| Step | Scope | Status |
|---|---|---|
| M01.1 | Scaffold: package, CLI `validate`, template registry, tests, Makefile | **done** |
| M01.2 | Narration: TTS provider interface + labelled fixture/placeholder voice, per-scene audio, SRT | **done** |
| M01.3 | Manim templates: robot_intro, robot_anatomy, sensor_range, sense_think_act, servo_rotation, recap_quiz | todo (next) |
| M01.4 | Headless Blender scene: mobile_robot_avoidance (primitives only) | todo |
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

## Commands
```bash
make install && make test && make validate
make narrate                       # espeak (needs espeak-ng + ffmpeg)
make narrate TTS_PROVIDER=fixture  # no external binaries
```
Environment notes: `.venv` is Python 3.12 with manim/jsonschema/pytest; add packages with `uv pip install --python .venv/bin/python <pkg>`. GNU `make` was installed via apt in the dev container (wasn't present by default). espeak-ng 1.52, ffmpeg/ffprobe and sox are installed in the dev container; Blender not yet checked — M01.4/M01.5 must detect binaries and print exact prerequisites.

## Next step: M01.3
Manim templates for the 6 manim scenes in the registry (`robot_intro`, `robot_anatomy`, `sensor_range`, `sense_think_act`, `servo_rotation`, `recap_quiz`). Each renders a clip whose length is the scene's `scene_duration_s` from `timing.json` (animations during narration window, hold after). Provide a low-res preview flag; keep Blender (M01.4) and FFmpeg composition (M01.5) out of scope.
