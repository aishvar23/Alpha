# Claude Code — Robotics 101 project instructions

Treat `AGENTS.md` as the canonical engineering rules. Read it first, then `README.md`, `architecture/SYSTEM_DESIGN.md`, and the requested milestone in `tasks/`.

## Immediate assignment
Implement **M01 local vertical slice**. Do NOT implement all cloud infrastructure at once. Prefer a codebase with a reproducible local pipeline, stable interfaces, and tests over stubs for every future service.

## Claude Code workflow
- Use a written plan for multi-file changes. Identify files/tests before coding.
- Keep context in this repository; update `docs/DECISIONS.md` when changing architecture.
- Implement deterministic template scenes first, then bounded generated-code fallback.
- Build a demo that outputs `out/episode-001/final.mp4`, captions, QA report, and artifact manifest; `out/` must be gitignored.
- Use environment variables only for optional API providers. Fixture/dry-run mode must not require credentials.
- Respect review and publishing gates; never upload or publicly publish as part of a test.

## User's requested outcome
A hybrid 2D/3D five-minute beginner educational episode, generated end-to-end with the user as final reviewer. M01 proves media generation; later milestones add AI planning, Azure orchestration and reviewer UI.

## Good handoff response format
Summarize: implemented modules, commands to run, test outcomes, exact local output paths, known limitations, and the next unblocked milestone.
