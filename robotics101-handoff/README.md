# Robotics 101 — AI Video Production Platform

Repository-ready **implementation handoff for Claude Code and OpenAI Codex**. The desired product autonomously proposes a beginner robotics lesson, researches and verifies it, writes an ~5-minute script, creates parameterized 2D/3D visuals, synthesizes narration, assembles an MP4, validates it and presents it for **human approval** before YouTube publishing.

## Decisions
- Audience: absolute beginners; lesson duration target 300 s (acceptable 270–330 s).
- Visual style: hybrid; template-driven Manim (2D), optional headless Blender (3D); never rely on unconstrained text-to-video for technical diagrams.
- Delivery: **local vertical slice first**, then Azure Durable Functions + Service Bus + Container Apps Jobs.
- Stack: .NET API/orchestrator, Python AI/render workers, Next.js dashboard, PostgreSQL/Supabase metadata, Azure Blob assets, FFmpeg media composition.
- Single owner review: draft generation automatic, publication **never** automatic without approval of exact final artifact hash.
- Grok Bot (optional): editorial coordinator through approved endpoints only; not an execution authority or source of truth.

## Start here (human)
1. Read `docs/PRODUCT_REQUIREMENTS.md`, `architecture/SYSTEM_DESIGN.md` and `docs/SECURITY_AND_QA.md`.
2. Open this folder in Claude Code or Codex. Both have tool-specific entrypoints in `CLAUDE.md` and `AGENTS.md`.
3. Instruct the coding agent: **"Implement `tasks/M01_LOCAL_VERTICAL_SLICE.md` end-to-end. Follow AGENTS.md, do not deploy cloud resources, do not publish to YouTube. Run tests and report artifacts."**
4. Iterate on the sample episode in `examples/episode-001.json` before adding distributed orchestration.

## Local quickstart
Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and GNU make; uses the existing `.venv`. No credentials needed.
```bash
make install    # editable install of the `robotics101` package + pytest into .venv
make test       # pytest suite (no network, no API keys)
make validate   # robotics101 validate examples/episode-001.json
make narrate    # per-scene TTS -> out/episode-001/{audio/*.wav,timing.json,captions.srt}
                # needs espeak-ng + ffmpeg; or: make narrate TTS_PROVIDER=fixture (no binaries)
make scenes     # Manim 2D scenes -> out/episode-001/scenes/<sceneId>.mp4 (preview 854x480@30)
                # make scenes PROFILE=full for 1920x1080@30; needs manim 0.22.1 + ffmpeg (no LaTeX)
.venv/bin/robotics101 validate path/to/episode.json [--strict]
.venv/bin/robotics101 render-scenes examples/episode-001.json --out out/episode-001 \
    [--profile preview|full] [--only scene-003] [--workers 4] [--timeout 900]
```
`validate` exit codes: 0 valid, 1 invalid (errors, or warnings with `--strict`), 2 unreadable/bad JSON. Errors = schema, scene IDs/sequence, unknown template, invalid template parameters; warnings = duration pacing (see `src/robotics101/validation.py`). `narrate` audio is labelled synthetic (espeak-ng) or FIXTURE placeholder — never production narration; `timing.json` flags scenes where speech covers <60% of the scene. `render-scenes` renders each `engine: manim` scene for exactly its `timing.json` duration (falls back to `durationTargetSeconds` if `narrate` has not run), video only, then ffprobe-checks resolution, fps, decodability and duration (±1 frame); logs go to `out/episode-001/logs/<sceneId>.log`, a summary to `out/episode-001/scenes/render-report.json`. Blender scenes are skipped until M01.4. Exit codes: 0 ok, 1 invalid spec, 2 input error/missing prerequisites, 4 a scene failed. `render` and `make demo` are placeholders until M01.5. Milestone status: `PROGRESS.md`.

## Artifact directory
| Path | Purpose |
|---|---|
| `CLAUDE.md` | Claude Code project instructions |
| `AGENTS.md` | Codex and general coding-agent instructions |
| `docs/PRODUCT_REQUIREMENTS.md` | Product scope and acceptance |
| `architecture/SYSTEM_DESIGN.md` | Components, workflows, sequencing |
| `architecture/STATE_MACHINE.md` | Explicit events, guard conditions, retries |
| `docs/SECURITY_AND_QA.md` | Sandboxing, trust, quality checks |
| `docs/OPERATIONS_AND_COST.md` | Observability, cost model, runbook |
| `docs/GROKBOT_INTEGRATION.md` | Optional Grok Bot role + controlled API |
| `contracts/episode.schema.json` | JSON Schema contract for episode spec |
| `contracts/render-job.schema.json` | Render job contract |
| `examples/episode-001.json` | First pilot structured storyboard |
| `database/migrations/0001_initial.sql` | Relational source-of-truth schema |
| `tasks/` | Six gated milestones, implementation checklist |
| `prompts/AGENT_CONTRACTS.md` | Agent I/O and grounding rules |
| `docs/DECISIONS.md` | ADR-style agreed choices and open questions |

## Completion definition
MVP: 3 full episodes generated, each 270–330 seconds, synchronized voice/captions, >=1 deterministic 2D demonstration and >=1 3D demonstration where educationally justified; scene-level retries work; secure isolated rendering; review and version-pinned approval; no unapproved publications. Cost and failure telemetry visible per run.

## Important boundaries
This is a **design and scaffold**, not a deployed running system. The SQL is a first migration and should be reviewed against actual services before production. Do not commit API keys, private OAuth tokens, or production credentials. Validate vendor costs, API quotas, and content policies at implementation time.
