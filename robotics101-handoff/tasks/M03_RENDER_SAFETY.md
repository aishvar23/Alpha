# M03 — templates, novel animations and secure runtime

## Implement
- Versioned Manim template catalog and Blender rig catalog.
- Scene spec -> template parameters; fallback generated code artifact with AST prechecks.
- Production container sandbox (nonroot, read-only root, no network/credentials, quotas/timeouts, restricted mounted inputs/outputs).
- Render-cache keys and golden scene tests, numeric invariants and sampled visual review hooks.
- Rejected dangerous imports/IO/network test cases; unsafe scenes fail closed.
- Dependency manifest pins Python, Manim, Blender and FFmpeg versions/container digests.

## Acceptance
A safe new scene renders isolated; unsafe code cannot access host/network/secrets; deterministic template scenes remain verifiable; failures produce actionable logs.
