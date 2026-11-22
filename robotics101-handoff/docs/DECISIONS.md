# Architecture decision log

## Adopted
- ADR-001: Implement locally before distributing to cloud (reduces initial integration risk).
- ADR-002: Use template-first deterministic animation; generated code is fallback only.
- ADR-003: Isolate all AI-generated code in tightly controlled render containers.
- ADR-004: Durable Functions for orchestration, Service Bus for worker dispatch; asynchronous versioned completion events.
- ADR-005: Postgres metadata + immutable blob content, SHA-256 IDs and lineage.
- ADR-006: FFmpeg for initial composition, not a paid generalized video framework.
- ADR-007: Require final artifact hash-bound human approval before any release.
- ADR-008: Scene-level caching and dependency-aware partial rerenders.
- ADR-009: Grok Bot optional editorial coordinator, not production control plane.
- ADR-010 (M01.3): Manim templates run as a subprocess per scene. The host picks the scene class from a fixed allowlist (`animation/manim_templates/SCENE_CLASSES`) and passes only validated parameters + duration as a JSON job file (`ROBOTICS101_SCENE_JOB`); the template re-validates against the registry. Each template scripts a fixed animation sequence quantised to whole frames, then a frozen-frame hold pads the clip to exactly `round(duration × fps)` frames. Templates use `Text` only (no LaTeX dependency). Consequence: scene clips are deterministic and composable on the `timing.json` timeline; in the production architecture this subprocess becomes the isolated render-worker boundary.
- ADR-011 (M01.4): Blender 3D scenes render headless with the **Workbench** engine (studio light `paint.sl`, shadows, 8× AA full / 5× preview) on CPU. Measured in the dev container (8 CPUs, no GPU, Blender 4.3.2) at 1920×1080: EEVEE Next ≈2.1 s/frame (≈47 min for 45 s), Cycles CPU 16 spp ≈1.6 s/frame and this build has no OpenImageDenoise, Workbench ≈0.45 s/frame single-process. Motion is planned in pure Python (`robotics101.kinematics`, also run on the host for a fail-fast `collisionCheck`), each motion frame is set explicitly and rendered to PNG by up to 4 parallel Blender processes, and ffmpeg encodes H.264 while cloning the last frame for the static hold (`tpad`) so the clip is exactly `round(duration × fps)` frames. 3-point lights are in the scene for EEVEE (`ROBOTICS101_BLENDER_ENGINE=eevee`) but Workbench ignores them. Consequence: ~6 min for scene-006 at 1080p, ~70 s preview; flat-ish "illustration" look rather than photoreal. Revisit (EEVEE/Cycles + GPU workers) when the cloud render worker exists.

## Open decisions (do not block M01)
- TTS provider and desired narrator voice. (M01.2 uses offline espeak-ng / labelled fixture beeps via `TTS_PROVIDER`; production provider still open — `external` is a no-network stub.)
- Exact LLM provider/model and per-agent quality-cost routing.
- How much of pilot episode must use Blender versus stylized 2D, while satisfying hybrid test.
- Reviewer authentication provider and multi-user future.
- Azure region, CPU quotas, Container Apps resources and actual measured rendering cost.
- YouTube OAuth ownership/consent and publication scheduling rules.

## Change control
When changing an adopted decision, append a new ADR with rationale, consequences and migration plan. Do not silently rewrite contracts or accepted behavior.
