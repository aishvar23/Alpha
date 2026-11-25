# Robotics 101 — AI Video Production Platform

Repository-ready **implementation handoff for Claude Code and OpenAI Codex**. The desired product autonomously proposes a beginner robotics lesson, researches and verifies it, writes an ~5-minute script, creates parameterized 2D/3D visuals, synthesizes narration, assembles an MP4, validates it and presents it for **human approval** before YouTube publishing.

## Decisions
- Audience: absolute beginners; lesson duration target 300 s (acceptable 270–420 s by default, configurable per episode: ADR-034).
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
Requires Python 3.12, [uv](https://docs.astral.sh/uv/) and GNU make; uses the existing `.venv`. No credentials, no network.

### Prerequisites (checked at runtime; missing/old tools fail with an exact install hint)
| Tool | Tested | Needed for | Check |
|---|---|---|---|
| Python + `robotics101` (`make install`) | 3.12 | everything | — |
| Manim Community (`uv pip install --python .venv/bin/python 'manim==0.22.1'`), cairo/pango libs | 0.22.1 | 2D scenes | `render-scenes`/`render` (no LaTeX needed) |
| Blender (headless, no GPU) | 4.3.2 | 3D scene | `>= 4.2` via `blender --background --version`; `BLENDER_BIN` overrides |
| FFmpeg + ffprobe (libx264, AAC) | 7.1 | encode, compose, QA | `>= 5.1` (`-fps_mode`, `alimiter latency`) |
| espeak-ng | 1.52 | `--tts espeak` only | provider errors if absent; `--tts fixture` needs nothing |

Exact versions used for a bundle are recorded in its `manifest.json` → `toolVersions`.

### Commands
```bash
make install    # editable install of the `robotics101` package + pytest into .venv
make test       # pytest suite (~25 s; no network, no API keys; real render smoke tests auto-skip if tools are missing)
make test-e2e   # + full sample-episode render test (~100 s; or ROBOTICS101_E2E=1)
make validate   # robotics101 validate examples/episode-001.json
make demo       # END-TO-END, preview 854x480@30 (~1.5-2 min on 8 CPUs) -> out/episode-001/
make demo-full  # same at 1920x1080@30 (~8-10 min on 8 CPUs; the Blender scene dominates)
make demo TTS_PROVIDER=fixture   # labelled beep placeholder instead of espeak-ng
make qa         # re-run QA on out/episode-001 (e.g. after inspecting/tampering)
make publish-dry-run  # YouTube publisher STUB -> out/episode-001/publish_plan.json (no network, never uploads)

# equivalent CLI
.venv/bin/robotics101 render examples/episode-001.json --out out/episode-001 [--profile preview|full] [--tts espeak|fixture]
.venv/bin/robotics101 qa out/episode-001 [--profile preview|full]

# individual stages (what `render` chains)
make narrate    # per-scene TTS -> out/episode-001/{audio/*.wav,timing.json,captions.srt}
make scenes     # Manim 2D + Blender 3D scenes -> out/episode-001/scenes/<sceneId>.mp4 (PROFILE=full for 1080p)
.venv/bin/robotics101 render-scenes examples/episode-001.json --out out/episode-001 \
    [--profile preview|full] [--only scene-003] [--workers 4] [--timeout 900]
```
`render` = validate → narrate → render-scenes → compose → manifest → QA. Re-running regenerates everything (stale `final.mp4`/clips/QA/manifest are deleted first, so a failed run never leaves a valid-looking bundle). Exit codes: 0 QA `PASS`/`PASS_WITH_WARNINGS`, 1 invalid spec, 2 input error / missing prerequisites / TTS failure, 4 a scene render or the composer failed, 5 QA `FAIL`. `qa` uses the same 0/2/5 codes.

### Output bundle (`out/` is gitignored)
| Path | Content |
|---|---|
| `final.mp4` | H.264 High yuv420p, CFR 30 fps, +faststart; AAC-LC 48 kHz stereo 192 kb/s; narration normalised to −16 LUFS, limited at −1.5 dBFS; hard cuts |
| `captions.srt` | cues on the final (frame-quantised) timeline |
| `qa_report.json` / `qa_report.md` | status `PASS` / `PASS_WITH_WARNINGS` / `FAIL`, every check, per-scene table |
| `manifest.json` | every artifact: relative path, SHA-256, bytes, ffprobe summary; `finalVideoSha256`; `publish.status = not_published`, `requiresApprovalOfSha256`; tool versions, run id, TTS label, stage timings |
| `thumbnail.png` | 1280x720 frame (3D demo scene ≈10 s in, else mid-video) + episode title band |
| `publish_plan.json` | only after `publish --dry-run`: what an upload would send + why it is blocked |
| `episode.json`, `timing.json`, `compose.json` | exact input spec copy, narration timeline, composer report |
| `audio/<sceneId>.wav`, `scenes/<sceneId>.mp4`, `clips/<sceneId>.mp4` | narration, video-only scene renders, per-scene A/V clips |
| `logs/<sceneId>.log`, `scenes/render-report.json` | render logs |

QA hard gates (→ `FAIL`): decodable; h264 High yuv420p; resolution of the profile; 30 fps CFR; AAC 48 kHz stereo present; not silent (programme mean > −60 dBFS, each narrated clip peak > −50 dBFS); no clipping (max < −0.1 dBFS); total inside the episode length window (default 270–420 s, `final.durationRangeSeconds`, ADR-034) and equal to the scene timeline (±2 frames); audio/video stream lengths within 0.1 s; captions present, monotonic, inside the video; every scene + clip present with its scheduled duration (±1 frame); manifest hashes/sizes match and publish block untouched. Warnings (→ `PASS_WITH_WARNINGS`): synthetic/fixture TTS, voice coverage < 60 % of a scene ("holds fill gap — not acceptable educational pacing"), preview profile (not publishable), loudness outside −16 ± 2 LUFS, missing +faststart.

`validate` exit codes: 0 valid, 1 invalid (errors, or warnings with `--strict`), 2 unreadable/bad JSON. Errors = schema, scene IDs/sequence, unknown template, invalid template parameters; warnings = duration pacing (see `src/robotics101/validation.py`). `narrate` audio is labelled synthetic (espeak-ng) or FIXTURE placeholder — never production narration. `render-scenes` renders each `engine: manim` scene (Manim) and `engine: blender` scene (headless Blender, Workbench engine, primitives only; `collisionCheck` asserted before and inside Blender; the robot's stop threshold is the episode's `sense_think_act.thresholdMeters`, default 0.5 m) for exactly its `timing.json` duration, video only, then ffprobe-checks it. Blender: `BLENDER_BIN`, `ROBOTICS101_BLENDER_PROCS` (default min(4, CPUs/2), capped by free RAM), `ROBOTICS101_BLENDER_ENGINE=eevee` (slower). Nothing in this repo uploads or publishes.

### Publisher stub (dry run only)
`robotics101 publish <out_dir> --dry-run` re-hashes `final.mp4` against `manifest.json` (any mismatch or tampered manifest → refused, exit 6) and writes `publish_plan.json`: YouTube `snippet` (title, description with learning objectives + chapters + synthetic-voice note, tags, category 27 Education), `status` (`privacyStatus: private`, `containsSyntheticMedia`, `selfDeclaredMadeForKids` copied from the spec's `publishing.madeForKids`; missing = blocker), caption/thumbnail file refs with SHA-256, chapters from the scene timeline, QA summary, the state of `approval.json`, and the list of blockers. `wouldUpload` is always `false`. Without `--dry-run` the command refuses (exit 6): real upload is M06 and needs an owner approval file bound to the exact video hash:
```json
{"approvedSha256": "<sha256 of final.mp4>", "reviewer": "<name>", "decision": "approved", "timestamp": "<ISO-8601>"}
```
The stub imports no network/Google/OAuth library and reads no credentials (enforced by tests).

### Cartoon episodes (M02, in progress)
`examples/episode-001-cartoon.json` uses contract v1.1 (`contracts/episode.v1.1.schema.json`): dialogue `beats` for the recurring cast in `characters/registry.json` (Bolt, Maya, Nib). `robotics101 validate examples/episode-001-cartoon.json --strict` checks cast/expressions/actions/SFX/music cues against the registry, dialogue coverage, that every spoken number+unit matches the scene parameters, and kid-safe wording (error when `publishing.madeForKids` is true). Rendering cartoon specs is not implemented yet (narrate/render exit 3). Plan: `docs/PLAN-cartoon.md`.

Voices (M02.2): `robotics101 voice examples/episode-001-cartoon.json --out out/ep1-cartoon [--tts auto|elevenlabs|kokoro|espeak|fixture] [--plan-only]` synthesizes every line with the character's voice from the registry and writes `voice/lines/*.wav`, per-scene dialogue stems `voice/scenes/<sceneId>.wav` (48 kHz mono, exactly the scene length), speaker-labelled `captions.srt`, `timing.json` (schema `robotics101.timing/2`: every beat timed, scene durations in whole frames) and `voice_qa.json`. `auto` = ElevenLabs (official SDK, `eleven_v4`, with word timestamps) if `ELEVENLABS_API_KEY` is set — exported, or in the gitignored project `.env` (loaded with python-dotenv) — and the registry voices are approved, else Kokoro, else espeak. Audio is cached in `tts-cache/` by content hash, so reruns never re-bill; `--plan-only` prints billable characters without synthesizing; `ROBOTICS101_ELEVENLABS_MAX_CHARS` (default 8000) caps uncached characters per run. Owner approval gate: ElevenLabs voices are used for a full episode only after `voice.elevenlabs.approved` is set to `true` in the registry; first, once the owner says yes, run `robotics101 voices samples --yes` (one short line each for Bolt and Maya, 179 characters, written to /workspace/robotics101-samples/) and get the owner's OK. With a key: `robotics101 voices account` and `robotics101 voices list` (free) and `robotics101 voices audition bolt --voice-id <id> --out /tmp/bolt.wav --yes` (one short line). Never commit the key; keep it in your environment or the gitignored `.env`.

Model sheets (M02.3): `robotics101 model-sheet --out out/model-sheets` renders the cast lineup and each character's expressions, mouth shapes and poses (`src/robotics101/cartoon/rigs.py`).

Motion + lip sync (M02.4): `robotics101 motion-test --voice-dir out/ep1-cartoon --out out/motion-test.mp4` renders a 15 s performance of the cold-open gag (Bolt bonks the boxes, Maya laughs, Nib topples) with lip sync from Rhubarb Lip Sync (MIT). Install Rhubarb 1.14 by unzipping the Linux release from https://github.com/DanielSWolf/rhubarb-lip-sync/releases into `tools/rhubarb/` (gitignored) or set `RHUBARB_BIN`; without it mouths follow loudness (RMS fallback).

Kokoro fallback setup: `uv pip install --python .venv/bin/python -e '.[kokoro]'`, then download `kokoro-v1.0.onnx` and `voices-v1.0.bin` from https://github.com/thewh1teagle/kokoro-onnx/releases (model-files-v1.0) into `models/kokoro/` (gitignored).

Milestone status: `PROGRESS.md`.

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
