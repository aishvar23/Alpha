# Authoring track A1–A7 (built, offline) — implementation notes

Plan: `docs/PLAN-authoring.md` (rev 2, ff11426). Owner approved building A1–A7 (free, offline, fixture-only) on
2026-11-26 (relayed by Grok Bot, 10:00 AM CST). A8 (first paid milestone: `ANTHROPIC_API_KEY` + ≈ $15 S1 cap) is
**not** started and needs the owner's explicit yes.

No paid calls: no LLM/API calls, no ElevenLabs credits; tests run with recorded/hand-written fixtures and sockets
blocked.

## A1 — contracts, curriculum, catalogue, reviews
- Contracts: `contracts/authoring/*.schema.json` (request, curriculum, sources, facts, outline, visual_bindings,
  visual_gaps, trace, critique, authoring_report, review_packet, review_approval, sequence, canon);
  `robotics101.authoring.schemas` validates and writes canonical JSON (sorted keys, no wall-clock) and returns the
  SHA-256. (The plan's `contracts/authoring-request.schema.json` lives at `contracts/authoring/request.schema.json`.)
- Curriculum: `curriculum/sequence.yaml` (ep-001 published; ep-002 `distance_with_light`, ep-003 `line_following`,
  ep-004 `arms_and_grippers`; 8 backlog topics, each with `expectedVisuals`). **Topic order is the plan's
  provisional default** (`provisional: [order]`), owner-editable. `curriculum/canon.json` from ep-001 (3 m range,
  0.5 m threshold, 60° high-five, vocabulary); `canon_problems` flags a spoken value for a canon quantity that
  differs, unless the line marks a different robot/sensor.
- Catalogue: `robotics101 authoring catalog [--out]` joins code (cartoon templates, visuals, icons, vignettes, SFX,
  music, sets, backgrounds, kit primitives) with capability cards in `authoring/capabilities.yaml`; the card↔code
  test fails on any mismatch; snapshot `tests/golden/authoring/catalog.json`.
- Reviews: `robotics101.authoring.review` — packets R1/R2 with artifact hashes (R2 embeds the R1 packet hash, so an
  R1 change voids R2), approval checker (missing | invalid | not_approved | sha_mismatch | stale_chain | approved),
  R3 = existing `approval.json`. `robotics101 authoring review <run> R1|R2 [--write]` never approves.
