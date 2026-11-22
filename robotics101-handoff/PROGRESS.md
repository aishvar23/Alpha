# M01 progress (session handoff)

Read this first in each new session. Spec: `tasks/M01_LOCAL_VERTICAL_SLICE.md`; rules: `AGENTS.md`.

| Step | Scope | Status |
|---|---|---|
| M01.1 | Scaffold: package, CLI `validate`, template registry, tests, Makefile | **done** |
| M01.2 | Narration: TTS provider interface + labelled fixture/placeholder voice, per-scene audio, SRT | todo (next) |
| M01.3 | Manim templates: robot_intro, robot_anatomy, sensor_range, sense_think_act, servo_rotation, recap_quiz | todo |
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

## Commands
```bash
make install && make test && make validate
```
Environment notes: `.venv` is Python 3.12 with manim/jsonschema/pytest; add packages with `uv pip install --python .venv/bin/python <pkg>`. GNU `make` was installed via apt in the dev container (wasn't present by default). FFmpeg/Blender availability not yet checked — M01.4/M01.5 must detect binaries and print exact prerequisites.

## Next step: M01.2
Add `robotics101.narration`: a `TtsProvider` interface, a deterministic fixture provider whose output is explicitly labelled placeholder audio (never presented as real narration), optional env-configured external provider (off by default, no credentials needed for tests), per-scene WAV + measured duration, and SRT generation with tests. Note: sample narration is ~20 s/scene of text vs 25–55 s targets — QA must flag this (see task "Clarification on sample").
