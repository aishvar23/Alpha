# System design / C4-lite

## End-to-end flow
`Curriculum -> research -> script -> technical review -> storyboard -> scene specs -> [Manim/Blender render + TTS] -> FFmpeg compose -> QA -> human review -> private upload -> approved release`

## Control and data planes
**Control**: Next.js dashboard -> ASP.NET Core API -> Durable Functions orchestration. Durable orchestration serializes progression; Service Bus carries work commands/events, including versions and idempotency. **Workers**: Python AI agents, isolated render jobs, TTS worker, FFmpeg composer, QA, YouTube publisher. **Data**: Postgres stores metadata/versions/approvals; Blob Storage stores immutable source specs, logs, rendered clips, WAV, MP4, SRT, thumbnails and QA manifests.

## Local MVP vs target deployment
| Concern | M01 local | Cloud target |
|---|---|---|
| Control | Python CLI | .NET API + Durable Functions |
| Queue | In-process task sequence | Service Bus queues/topics |
| Storage | Filesystem + SHA-256 manifest | Azure Blob + Postgres |
| 2D | Manim subprocess | Isolated Container Apps Job |
| 3D | Blender headless subprocess | Isolated Container Apps Job |
| Voice | TTS adapter / test fixture | Azure Speech or other provider |
| Compose | FFmpeg | FFmpeg container job |
| Review | Output MP4/manual inspection | Next.js reviewer UI |
| Publish | Disabled | OAuth YouTube private upload with explicit final approval |

## Work units
Each work unit references `{jobId, runId, episodeId, episodeVersion, sceneId?, sceneVersion?, jobType, inputArtifactIds, idempotencyKey, schemaVersion, attempt}`. Completion contains output artifact hashes and metadata. The orchestrator commits state changes after verifying version and hashes. Duplicated completion events must be harmless.

## Agent boundaries
Do not use free-form agent-to-agent conversation as your source of truth. For each task: versioned prompt + typed input + schema-validated output + provenance/usage. See `prompts/AGENT_CONTRACTS.md`. Research facts must be traceable; scripts and storyboard are immutable artifacts.

## Rendering
1. Select template from registry where possible. Validate animation parameters (angles, dimensions, coordinates).
2. For novel scenes, produce code as a file artifact; never directly execute on the API server. AST or lexical checks are only preliminary defense.
3. Render in an ephemeral container with CPU/memory/time constraints, read-only runtime filesystem and writable scratch; no cloud secrets and no outbound network by default.
4. Probe clip: dimensions, frame rate, duration, missing frames, transparent layers, text clipping (best-effort), numeric invariants and decoding.
5. Cache by `(sceneSpecHash, templateVersion, renderingImageDigest, renderProfile)`.

## Timing
Narration is synthesized per scene prior to final render. Word/cue timings become an immutable artifact. Each scene's animation can pause at cue boundaries; never blindly speed up to fit speech. Composer normalizes sample/frame rates, creates transitions and checks aggregate duration 270–330 s.

## Data model
See `database/migrations/0001_initial.sql`. `episodes` is the mutable control-plane record; `episode_versions`, `scene_versions`, `artifacts`, `approvals` are append-only history. Avoid storing in-flight state solely in ephemeral worker memory. Add foreign keys, status constraints, transaction boundaries and Row-Level Security based on deployment auth model.

## Selective regeneration
DAG dependencies: research -> script -> storyboard -> scene_spec -> scene_video; narration_text -> TTS_audio -> captions; all scene_video + TTS_audio -> final_video -> QA -> approval. Changing a scene invalidates its render and final composition, NOT other scene clips. Changing narration may also invalidate scene timing; match by source artifact hashes, not by filenames.

## Reviewer and publisher
Reviewer sees exact manifest and playback for a candidate episode. Approval references `approved_artifact_id`, hash, user, timestamp, decision. Publisher must retrieve that artifact and recompute/verify SHA-256; upload as private using resumable protocol; persist YouTube ID; explicit release/schedule policy; idempotent retries and ability to reconcile uncertain upload outcomes before retrying.

## Design trade-offs
Avoid AKS and Remotion in MVP (operational overhead / extra licensing). FFmpeg is enough for standard episode composition. Keep model/TTS interfaces pluggable to avoid locking in providers. Add Grok Bot only as a scoped coordinator via secure HTTP operations.
