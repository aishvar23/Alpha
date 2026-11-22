# Workflow and state transitions

## Episode states
`PLANNED -> RESEARCHING -> SCRIPTING -> STORYBOARDING -> GENERATING -> RENDERING -> COMPOSING -> VALIDATING -> AWAITING_REVIEW -> APPROVED -> UPLOADING_PRIVATE -> READY_TO_RELEASE -> PUBLISHED`

Exception states: `FAILED`, `RETRY_PENDING`, `CANCELLED`, `REJECTED` (record `resume_state` or `failed_stage` separately). A scene follows `PENDING -> GENERATING -> RENDERING -> VALIDATING -> READY` or `REVISION_REQUESTED -> ...`.

| Event | From | Preconditions | To |
|---|---|---|---|
| `TopicAccepted` | PLANNED | Valid topic, generation budget | RESEARCHING |
| `ResearchValidated` | RESEARCHING | Provenance and checks passed | SCRIPTING |
| `ScriptValidated` | SCRIPTING | Editorial + technical QA passed | STORYBOARDING |
| `StoryboardsValidated` | STORYBOARDING | Scene specs valid | GENERATING |
| `AssetsPrepared` | GENERATING | Source specs, audio ready | RENDERING |
| `AllSceneRendersReady` | RENDERING | All required scene hashes recorded | COMPOSING |
| `Composed` | COMPOSING | MP4 probe passed | VALIDATING |
| `QAApproved` | VALIDATING | All hard checks pass | AWAITING_REVIEW |
| `ReviewerApproves` | AWAITING_REVIEW | Reviewer identity and exact final hash | APPROVED |
| `PreparePrivateUpload` | APPROVED | Authorization + hash matches | UPLOADING_PRIVATE |
| `PrivateUploadVerified` | UPLOADING_PRIVATE | YouTube ID and upload confirmed | READY_TO_RELEASE |
| `ReviewerAuthorizesRelease` | READY_TO_RELEASE | Current approved hash, explicit release authorization | PUBLISHED (after API confirmation) |
| `RequestRevision` | AWAITING_REVIEW | Target scene/script; feedback; new version | GENERATING or SCRIPTING |

## Invalid transitions
- `VALIDATING -> PUBLISHED` forbidden.
- `AWAITING_REVIEW -> UPLOADING_PRIVATE` forbidden without approval.
- Approvals expire if any contributing artifact changes; create new final hash and require reapproval.
- No public/scheduled release triggered by completion of AI QA alone.

## Retry handling
- Only transient errors retry (network throttling, known temporary failures, worker interruption) with exponential backoff and jitter.
- Validation/unsafe code errors are not retried without a new input or generation revision.
- Limit retries per job (default 3), persist attempts, dead-letter exhausted jobs.
- Use optimistic concurrency on episode versions and `idempotency_key UNIQUE` for jobs.
- Durable external events carry `episodeId`, `reviewRequestId`, `approvedArtifactId/hash`, and caller identity validated in API layer.

## Outbox recommended
Persist job command and episode state change atomically in Postgres transaction with an outbox entry; dispatcher publishes to Service Bus and marks delivered. Consume idempotently. This avoids state claiming a task exists that was never enqueued.
