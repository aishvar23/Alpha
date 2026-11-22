# Optional Grok Bot integration

## Recommended role
Use Grok Bot as an **editorial operations assistant**, not the data store or job runner. Candidate responsibilities: weekly curriculum proposals, summarize generation failures and reviewer queue, request new draft generation via approved API, prepare feedback digests, monitor due dates, and remind the reviewer of episodes awaiting review.

## Trust model
- Durable Functions controls actual episode workflow; Grok Bot has *no direct database writes* or arbitrary container execution.
- Grant read-only episode status endpoints by default.
- For actions, expose narrow, authenticated routes with fine-grained scopes and policy checks; use workload credentials, rate limits and audit logs.
- Never expose OAuth refresh tokens, Azure management credentials or media-signing secrets.
- Actions to release/publish require **separate explicit human confirmation in the review app**; do not let a bot approve on behalf of the reviewer.

## Proposed API contract (conceptual, not vendor-specific integration)
- `GET /api/episodes?status=AWAITING_REVIEW` — list reviewer queue.
- `GET /api/episodes/{episodeId}` — read progress, warnings, estimated spend.
- `POST /api/episodes` — request new episode from approved curriculum topic, with budget/idempotency checks.
- `POST /api/episodes/{episodeId}/revision-requests` — submit review feedback, but require authenticated human identity and authorization; no synthetic approvals.
- **No bot-facing `POST /publish`** endpoint.

## Suggested weekly routine
1. Monday: summarize next topic and confirm prerequisite sequence.
2. Tuesday–Thursday: surface blocked episodes and budget alerts from your API.
3. Friday: send an actionable review summary including draft playback link and flagged technical claims.
4. Human reviews and approves inside your own dashboard.

## Caveat
Confirm the available integrations/actions and their current permissions in the actual Grok Bot product before implementation. This file describes a safe integration pattern, not a claim that any specific webhook or endpoint is currently available.
