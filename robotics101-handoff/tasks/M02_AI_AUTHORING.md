# M02 — typed authoring agents

## Implement
- LLM adapter, prompt registry/versioning, bounded retries and token cost recording.
- Curriculum planner -> researcher -> scriptwriter -> technical checker -> storyboarder.
- Pydantic validators matching `contracts/episode.schema.json`; output provenance with claim/source IDs.
- Source retrieval and verification interface; no fabrication of citations. Fallback to `needs_review` when sources unavailable.
- Deterministic local fixture mode and unit tests for malformed model outputs.
- Target 600–700 words per full episode, then adjust to actual voice timing; scenes must sum to target.

## Acceptance
From a given topic, produces a schema-valid episode spec with distinct objectives, readable narration, verified references or explicit `unverified` flags, and cost/trace record. Agents cannot write directly to database or publish.
