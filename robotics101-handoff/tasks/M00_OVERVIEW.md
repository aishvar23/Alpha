# Milestone roadmap and execution order

Start with `M01_LOCAL_VERTICAL_SLICE.md`. Each milestone is a separate coding-agent prompt and PR. No vendor subscription or cloud deployment required for M01.

| Milestone | Goal | Gate |
|---|---|---|
| M01 | Local episode rendering | MP4 + SRT + QA JSON + SHA-256 manifest |
| M02 | Source-backed AI generation | Reproducible validated script/storyboard; no invented citations |
| M03 | Template library + sandbox | Isolated template/code render with QA/math tests |
| M04 | Azure async control plane | Crash-safe replay, idempotency, DLQ and tracing |
| M05 | Human review application | Selective scene revision; approval bound to hash |
| M06 | YouTube private publishing | No unapproved release; dedupe/reconcile uploads |

For each milestone, update architecture decisions and documentation and prove a real use case; avoid speculative boilerplate.
