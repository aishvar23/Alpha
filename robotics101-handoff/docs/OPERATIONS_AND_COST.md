# Operations, budget and incident response

## Starting financial model
Assumption: 4 x 5-min episodes/month, ~12 scenes each, one or two iterations. A planning band of **$30–$175/month** is a placeholder only, not a vendor quote. Biggest variables: scene-retry count, 3D CPU time, narration provider, multimodal review, hosting and logs. Do not optimize around this figure without collecting actual usage. Use the vendor's current pricing calculator before deployment.

## Cost ledger
Store `{provider, model, operation, episode_id, scene_id, run_id, input_tokens, output_tokens, billed_chars, cpu_seconds, gpu_seconds, blob_bytes, estimated_usd, invoiced_usd}` per generation run. Budget configuration: `$ per episode`, `$ per day`, `$ per month`, max retries, max total rendering minutes. Pause new jobs on limit; reconcile async charges and in-flight jobs.

## Observability
Trace each episode and scene using correlation IDs. Track workflow duration (p50/p95), model errors, average tokens per stage, render failure by template, percentage scenes reused from cache, duration drift, audio/caption mismatches, QA failures, manual edit requests, approval/rejection rates, upload failures, total USD/episode.

## Runbooks
- **Scene render failing**: inspect render stdout/stderr + spec hash + image digest; classify deterministic vs transient; rerender only affected scene.
- **Stuck episode**: inspect Durable instance and outbox; reconcile completion events; never manually skip checks.
- **High spend**: disable topic scheduler/new jobs; cap expensive model and QA retries; verify ledger against provider usage.
- **Upload uncertain**: reconcile YouTube video state/ID before retry; avoid duplicate uploads.
- **Approval discrepancy**: block release, invalidate approval, generate new candidate and seek approval.
- **Secrets exposure**: revoke credentials, stop affected workers, audit logs and regenerate secure deploy credentials.

## SLO and rollout
MVP operates weekly; no strict uptime SLA. Focus on recoverability and quality. Start with private uploads and dry-run publisher; switch to scheduled publishing after explicit acceptance tests.
