# Coding agent operating instructions (Codex / other agents)

## Mission
Implement the Robotics 101 pipeline incrementally, with testable, deterministic contracts and a human publishing gate. Read `README.md` and the specific `tasks/Mxx_*.md` before editing code. **Start with M01** unless directed otherwise.

## Working protocol
1. Identify requested milestone and acceptance tests. Produce a short implementation plan and note assumptions.
2. Inspect existing code; prefer minimal edits and reusable modules.
3. Commit source/config/tests/docs together; do not add generated MP4s, cloud secrets or model credentials to Git.
4. Provide tests that run locally without paid AI APIs. Put remote integration tests behind opt-in environment flags.
5. After each milestone, report commands run, passed/failed tests, produced artifact paths, and blockers.
6. Do not skip validation/security to make a demo appear complete. State clearly when components are mocked.

## Architectural invariants
- EpisodeSpec JSON Schema is the boundary between editorial agents and renderer. External outputs are untrusted.
- PostgreSQL metadata + immutable, content-hashed artifact storage; no large video bytes in the database.
- Orchestrator owns state transitions; queues and workers do not update episode status arbitrarily.
- Every task carries episode ID, scene ID/version (if applicable), idempotency key and correlation/run ID.
- Scene asset generation is isolated; prohibit network, secrets and unrestricted filesystem on render workers.
- YouTube uploads are private by default, and release requires explicit approval bound to the **SHA-256 of the exact final MP4**.
- Template-first animation; generated Python only as bounded fallback; do not execute untrusted code on host.
- Source citations accompany research claims; deterministic numeric and physics checks precede visual QA.
- Review edits create new versions; never silently mutate approved artifacts.

## Local stack for M01
Python 3.12+; pinned Manim/FFmpeg; Blender optional but required by the M01 hybrid acceptance test; mock TTS permitted with readable placeholder audio ONLY if clearly labeled and not called production-ready. Prefer an interface for TTS provider and a fixture mode. `make demo`, `make test`, `make validate` or documented equivalent must work.

## Repo layout expected after implementation
`apps/dashboard`, `apps/api`, `services/orchestrator`, `services/ai-worker`, `services/animation-worker`, `services/narration-worker`, `services/composer-worker`, `services/publisher`, `packages/contracts`, `packages/animation-templates`, `tests`, `infra`. Create only what the current milestone requires.

## Safety and change control
Never deploy, spend money, upload media to a real account, or change service permissions without user's explicit direction. Avoid speculative vendor-specific claims; verify current APIs before integrating. No long-running cloud components for M01.

## Starting task
Read `tasks/M01_LOCAL_VERTICAL_SLICE.md`, `contracts/episode.schema.json`, and `examples/episode-001.json`. Implement a deterministic local render from the sample spec, validate its outputs, and include a test report.
