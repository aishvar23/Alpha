# M06 — publication and ops

## Implement
- YouTube OAuth user consent, secure token store and resumable video uploads, private by default.
- Metadata/title/description/chapters and license/disclosure review before publishing.
- Idempotent publication job, reconcile uncertain upload before retry; persist YouTube video ID.
- Separate authenticated approval-to-release policy; scheduled or public visibility only with explicit reviewer authority.
- Full E2E dry-run tests with mocked YouTube API and optional private integration test.
- Monitoring, monthly budget warnings, incident playbooks and 3-episode trial report.

## Acceptance
Unsigned, missing, or stale approvals block. A private upload never changes public visibility just because a render completed. Retries never intentionally create a duplicate YouTube video.
