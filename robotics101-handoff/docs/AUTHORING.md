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

## A2 — providers, prompts, trace, budget, no network
- `robotics101.authoring.llm`: `LLMProvider.complete(stage, prompt_id, prompt_version, model, messages, schema)`;
  `FixtureProvider` (default; replays `<key>.json`, $0, missing fixture → `MissingFixture` naming the key),
  `RecordingProvider` (wraps a real provider, writes fixtures — A8), `AnthropicProvider` (lazy import; refuses
  unless `ROBOTICS101_AUTHORING_LIVE=1` and `ANTHROPIC_API_KEY` is configured; key via env/.env, never logged).
  Fixture key = SHA-256 of (prompt id, prompt version, model, whitespace-normalised messages, schema). Malformed or
  schema-violating output → `ProviderOutputError`.
- Prompt registry: `src/robotics101/authoring/prompts/<id>.md` (plan, research, extract, outline, script, bind,
  critique, revise); effective version = declared + sha12 of template + registry excerpt (a registry edit changes
  the version and every fixture key).
- `trace.py`: `trace.jsonl` records (contract-validated; fixture latency 0, no wall-clock), prices from
  `authoring/prices.yaml` (**unverified plan prices; A8 must verify**), budget guard prices the worst case before
  every call: run budget (default $8), per-stage caps, monthly cap (`ROBOTICS101_AUTHORING_MAX_USD_MONTH`).
- `authoring/config.yaml`: all plan defaults that are still open are marked `provisional` (budget caps, engagement
  and rubric thresholds, reading level, age band default, role line-up).
- Tests: conftest blocks AF_INET/AF_INET6 `connect` for the whole suite and clears the live flag/key; an AST test
  forbids network imports in `authoring/` and `cartoon/kit/` outside `llm.py`.
