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

## A3 — deterministic gates + engagement gate (calibrated on ep-001)
- `robotics101 authoring gate <spec> [--facts F] [--outline O] [--gaps G] [--age-band B] [--out DIR] [--screenplay]`
  writes a contract-valid `authoring_report.json` (+ optional Markdown screenplay). Blocking gates: format.schema
  (existing validator incl. `lint.fact_problems`), facts.numbers (every spoken number ↔ a verified claim, exact or
  min..max range, plus canon `curriculum/canon.json`), facts.ranges (`authoring/ranges.yaml`), facts.cross_scene,
  facts.teaching_lines (every teaching line cites a verified claim via `lineClaims`), kidsafe.topic, caption.dry_run
  (subtitle chunker on an estimated timeline: max 2 lines, ≥ 80 % one-line), layout.dry_run (explain lines inside an
  illustration/solo shot; `visual_gap` only if listed in visual_gaps.json), engagement.*. Warnings: reading level
  (Flesch-Kincaid), timing vs `durationTargetSeconds`.
- `timeline.estimate_timing(spec, wps=2.6)` gives a timing.json-shaped estimate with the voice.dialogue rules, so
  gates run before any audio exists.
- `independence.py`: source allowlist `authoring/sources.yaml` (tiers/groups, blocked list), independence reasons
  (not allowlisted, wikipedia, same publisher group, near-duplicate / syndicated by shingle Jaccard + longest shared
  run, cites each other, same upstream), `verify_claims` recomputes status (verified needs 2 independent sources
  with the excerpt present; else single_source / unverified; contradicted kept).
- Engagement (`engagement.py`, provisional thresholds in `authoring/config.yaml`): visual change ≤ **9.0 s**
  (plan said 8; ep-001 measures 8.43 s estimated / 7.58 s on real v7 timing), cold open ≤ **40 s** (plan said 30;
  ep-001 = 37.4 s), gag density, reaction density, monologue length, hook + hook callback, chant, audience
  questions, first concept time. Visual events counted: scene/shot bounds, concept card, actions, emotion poses,
  readouts, impact SFX, card/kit cue words. Both changes are calibration to the shipped, owner-approved ep-001 and
  are user-tunable.
- **ep-001 result:** all blocking gates pass with `tests/golden/authoring/robots_sense_think_act/facts.extracted.json`
  + `curriculum/outlines/ep-001.json`; the QA check `engagement.*` (cartoon/qa.py, hard when an outline exists) passes
  9/9 on the real out/m05.8-v7 timing. Fixture source pages are hand-written, labelled, on `*.fixture.test` domains.
- `cartoon/lint.py` units extended (mm, seconds, Hz, percent). lint.py and qa.py are outside the scene-lock code
  hash, so no ep-001 lock changed.
