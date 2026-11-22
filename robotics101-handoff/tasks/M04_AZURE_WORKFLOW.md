# M04 — durable cloud orchestration

## Implement
- .NET API for episode creation/status; durable orchestrator implementing `architecture/STATE_MACHINE.md`.
- Service Bus job dispatch, transactional outbox or equivalent reliable handoff, dedicated render completion events.
- Container Apps Jobs or worker adapter, Blob artifact store, Postgres state with migration.
- Crash recovery, bounded retries/backoff, dead-letter handling, cost budgets and end-to-end tracing.
- Infrastructure-as-code dev environment; least privilege managed identities; dry-run mode.

## Acceptance
Kill a render worker midway; one retry resumes without duplicate artifacts. Duplicate queue delivery is harmless. Per-stage state survives restart. No publication enabled by default.
