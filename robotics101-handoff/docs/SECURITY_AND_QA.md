# Security, technical correctness and QA gates

## Trust boundaries
- LLM output (including Python), search snippets, externally supplied source materials and storyboard JSON are **untrusted inputs**.
- Validate using JSON Schema/Pydantic; enforce limits on text size, number of scenes, render duration, asset references and allowable paths.
- No LLM or assistant agent may call cloud management or publishing endpoints directly; only reviewed, allowlisted app operations.

## Render sandbox policy
- Production: ephemeral container jobs with read-only root, writable tmp working folder, no host mounts, no default egress, dropped capabilities, nonroot UID, limits (CPU, RAM, file size, process count, wall-time); use seccomp/AppArmor where supported.
- Generated code cannot access credentials; workers receive short-lived scoped URLs or brokered input, and output only to scoped locations.
- Static analysis/AST allowlists and dependency pinning are defense-in-depth, not sufficient sandboxing alone.
- Validate `.blend` and external models (licenses, origin, safe parsing). No executing downloaded scripts without review.
- Restrict permitted URLs, inbound callback signatures, webhook replay tokens, secret scanning and audit access.

## Automated validation gates
| Gate | Hard fail | Soft/follow-up |
|---|---|---|
| Schema | Missing/invalid episode/scene fields | Weak educational objective |
| Research | Unsupported essential factual claims | Source ambiguity |
| Math | FK/IK invariant mismatch beyond configured tolerance | Nonessential pedagogical simplification |
| Python | Disallowed imports, execution timeout, sandbox violation | Recoverable renderer warnings |
| Video | ffprobe invalid, wrong dimensions, corrupt streams | Clipped text suspected by sampled vision review |
| Audio | Silent/empty narration, peak clipping, no audio track | Robotic prosody |
| Captions | Missing cues, temporal inversion, outside video duration | Minor punctuation |
| Completion | Broken artifact manifests/hashes | Model-generated commentary |
| Publish | No matching human approval hash | None; always block |

## Required tests
- Unit: schema parsing; angle arithmetic, 2-link forward kinematics; dependency invalidation; state transition guards.
- Snapshot/golden: stable parameterized Manim renders checked by hashes for metadata and tolerant frame comparisons.
- Integration: end-to-end local pilot; forced mid-scene failure then resume, no duplication.
- Security: attempts to render code reading local secrets/network must be denied inside sandbox; direct host execution forbidden.
- Approval: a single byte change in final MP4 invalidates prior approval; no publish request without matching signed approval.
- Upload: idempotent/reconciliation test using mocked YouTube API; never exercise public publishing in CI.

## Research and citation policy
Research output must contain claim IDs, source URLs, retrieval timestamp, support excerpt/notes, confidence and unresolved claims. Do not fabricate citations. An LLM agreement with another LLM is not independent verification. Technical reviewer can request external references or mark for human attention.

## Media ownership and platform
Use original or properly licensed illustrations, voice, 3D assets and music. Maintain licensing metadata. Check YouTube policies for synthetic content disclosure, reused/repetitive content, upload access and API quotas at integration time.
