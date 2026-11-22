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

## Open decisions (do not block M01)
- TTS provider and desired narrator voice. (M01.2 uses offline espeak-ng / labelled fixture beeps via `TTS_PROVIDER`; production provider still open — `external` is a no-network stub.)
- Exact LLM provider/model and per-agent quality-cost routing.
- How much of pilot episode must use Blender versus stylized 2D, while satisfying hybrid test.
- Reviewer authentication provider and multi-user future.
- Azure region, CPU quotas, Container Apps resources and actual measured rendering cost.
- YouTube OAuth ownership/consent and publication scheduling rules.

## Change control
When changing an adopted decision, append a new ADR with rationale, consequences and migration plan. Do not silently rewrite contracts or accepted behavior.
