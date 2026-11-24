# Plan: topic-to-script authoring for Robotics 101 cartoon episodes

Status: **PLAN ONLY** (2026-11-24). Nothing here is built. No code, installs or paid API calls were made to write
it. It replaces the generic `tasks/M02_AI_AUTHORING.md` outline with a design that targets the real cartoon contract
(schema 1.1) and the pipeline defaults the owner asked for in M03–M05 (ADR-020…029). Owner decisions are in §11.

Names used below are the real ones in the repo: `contracts/episode.v1.1.schema.json`, `characters/registry.json`,
`robotics101.validation._check_cartoon`, `cartoon/lint.py` (`fact_problems`, `kidsafe_problems`),
`cartoon/episode.py` (`expand_episode`, `plan_shots`, `DEFAULT_SHOTS`, `intro_scene`, `insert_concept_stings`,
`resolve_transitions`), `cartoon/visuals.py` (`VISUALS`, `concept_visual`), `cartoon/acting.py` (`POSES`,
`auto_pose`, `auto_react`), `cartoon/subtitles.py` (`wrap`, `cue_chunks`, `text_width`), `cartoon/layout.py`
(`CAPTION_BAND`), `templates/registry.py` (cartoon `TemplateSpec`s), `cartoon/__init__.py` (`SFX_IDS`,
`MUSIC_CUES`, `SETS`), `publish/youtube_stub.py` (`check_approval`).

## 0. Summary
- **Input:** a lesson topic (+ optional age band, length, objectives). **Output:** an *authoring bundle* whose core is
  an `episode.source.json` that passes `robotics101 validate --strict` unchanged, plus a fact sheet, a visual-gap
  report and a cost/trace record. The existing `render` path (which runs `expand_episode`) is untouched.
- **Shape:** a fixed, typed stage pipeline (no free-form agent loop): `plan → research → verify → outline → script →
  critique/revise → bind visuals → validate → human review`. Every stage writes a JSON artifact with a SHA-256;
  later stages only read earlier artifacts.
- **The hard truth about visuals:** today's library is 9 cartoon templates whose staging is mostly hand-built for
  episode 1 (robot families, checkup, sensor ping, stop rule, servo, rematch, recap, intro, cold open) + 3 wide
  visuals + 5 concept icons. Most new topics will have **visual gaps**. The plan makes gaps explicit (report +
  placeholder card + a block on final approval) instead of letting the LLM bend a topic to fit old templates.
- **Models (estimate, prices checked 2026-11-24):** Claude Opus 5.5 writes, a different vendor's model critiques
  (Gemini 4 Carbon by default, GPT-6.2 Astra as the stronger/pricier option), Claude Sonnet 5.5 / Haiku 5.5 do
  research reading and claim extraction. **≈ $3–6 of LLM + search per episode**, plus **≈ 3,850 ElevenLabs credits**
  to voice it. Every paid milestone waits for the owner's explicit yes.

## 1. Input and output contract

### 1.1 Input: `authoring/request.json` (new, validated by `contracts/authoring-request.schema.json`)
| field | required | default | notes |
|---|---|---|---|
| `topic` | yes | – | e.g. "How do robots follow a line?" (3–120 chars) |
| `episodeNumber` | yes | – | becomes `episodeId` `ep-NNN` |
| `ageBand` | no | `"6-9"` | `"6-9"` or `"9-12"`; drives reading level and joke style |
| `audience` | no | `"beginner"` | schema enum `beginner/intermediate/advanced` |
| `durationTargetSeconds` | no | `300` | 240–360 recommended (validation warns outside 270–330 today) |
| `learningObjectives` | no | generated | 1–5 strings (schema limit); if given, they are fixed, not rewritten |
| `mustInclude` / `avoid` | no | `[]` | concepts/terms the owner wants in or out |
| `madeForKids` | no | `true` | copied to `publishing.madeForKids`; kid-safe errors become hard |
| `cast` | no | `["bolt","maya","nib"]` | must exist in the registry |
| `budgetUsd` | no | `8.00` | hard cap for the whole authoring run (§7.4) |
| `mode` | no | `"fixture"` | `fixture` (no network), `record` (paid, writes fixtures), `live` (paid) |

### 1.2 Output: `out/authoring/<episodeId>/<runId>/`
| file | contents |
|---|---|
| `request.json` | normalised input (hash = run identity together with prompt + model versions) |
| `curriculum.json` | objectives, standard alignments (NGSS/CSTA codes), prerequisite assumptions, concept list (2–4) |
| `sources.json` | every retrieved source: id, URL, title, publisher, tier, retrieval timestamp, content SHA-256, licence note |
| `facts.json` | the fact sheet: claims with `claimId`, kid wording, supporting excerpts, status (§2) |
| `outline.json` | beat outline per scene (§3.1) with claim ids per teaching beat |
| `episode.source.json` | the schema-1.1 EpisodeSpec (author file; `render` expands it into `episode.json`) |
| `visual_gaps.json` | concepts/beats the template library cannot show yet (§4.3) |
| `critique/*.json` | each critic pass: findings, severity, what changed |
| `authoring_report.json` | validation + lint + reading-level + timing + layout dry-run results (§5) |
| `trace.jsonl` | one record per model/tool call: stage, provider, model, prompt id+version, tokens, searches, USD, latency, cache hit |
| `approvals/*.json` | hash-bound human approvals for each review point (§6) |

Contract rules: the spec carries `sources[]` (already in schema 1.1: `claimId`, `sourceUrl`,
`verificationStatus` `verified|unverified`, `note`); every teaching line maps to ≥ 1 claim id (kept in
`facts.json`, not in the beat, so the schema does not change); the spec never contains URLs in dialogue,
model names, or anything secret. Agents write files only inside their run directory; they never call
`render`, `voice`, ElevenLabs or `publish`.

## 2. Research and fact verification

### 2.1 Source tiers (allowlist in `authoring/sources.yaml`, reviewed by the owner)
| tier | examples | used for |
|---|---|---|
| A — standards | NGSS (nextgenscience.org: K-2-ETS1, 3-5-ETS1, 4-PS3/4-PS4 energy & waves), CSTA K-12 CS Standards (1A/1B: algorithms, computing systems), ISTE | objectives, age fit, vocabulary |
| B — education | NASA/JPL education (Mars rovers), university outreach (e.g. CMU Robotics Academy), IEEE Spectrum/IEEE RAS education, Smithsonian, BBC Bitesize, Khan Academy, PBS LearningMedia | explanations, kid-level framing |
| C — technical/manufacturer | sensor datasheets (e.g. HC-SR04 ultrasonic, Sharp IR), servo specs, LEGO Education / micro:bit / VEX docs, iRobot/Boston Dynamics/ABB product pages | numbers: ranges, angles, speeds |
| D — encyclopedias | Britannica, Wikipedia (as a pointer to its own citations, never as the only source) | cross-checks |
Blocked: content farms, AI-generated listicles, forums, social video, anything without a publisher.

### 2.2 Retrieval
1. `plan` stage turns the topic into 6–12 research questions (one per concept + "common misconceptions" + "numbers a
   kid will see on screen").
2. Search: the model's server-side web search tool (Claude web search, $10 / 1,000 searches) restricted with
   `allowed_domains` from the allowlist; ~15–25 searches per episode, capped at 40.
3. Fetch: web fetch (no extra charge beyond tokens), HTML → text, store text + SHA-256 + timestamp in
   `sources.json`. Only pages actually fetched can be cited (citation = URL + excerpt that exists in the stored text;
   a deterministic check verifies the excerpt string is present — no fabricated citations).
4. Fixture mode replays stored pages; tests never hit the network (§8).

### 2.3 Claim extraction and mapping
- After the outline exists, every teaching statement becomes an atomic claim: `{claimId: "c-07", text, kidText,
  kind: definition|mechanism|number|example|history, numbers: [{value, unit}], concept}`.
- Each claim maps to supporting `{sourceId, excerpt}` pairs. Status rules:
  - `verified`: ≥ 2 independent sources (different publishers; at least one tier A–C) support it.
  - `single_source`: 1 tier-A/B/C source → allowed only for non-numeric framing, flagged at review.
  - `unverified`: no support → the line is **removed or rewritten**; never shipped. If the owner keeps it anyway it
    goes into `sources[]` as `unverified` with a note, and the final approval card shows it.
  - `contradicted`: sources disagree → human review item; script uses the conservative statement.
- Independence: two pages quoting the same original count once; LLM agreement is never verification
  (docs/SECURITY_AND_QA.md).

### 2.4 Numeric sanity checks (deterministic, no LLM)
- Units normalised (reuse `lint._to_si`; extend to cm/mm/s/Hz/% ).
- Plausibility ranges table (`authoring/ranges.yaml`): e.g. hobby ultrasonic sensor range 0.02–4 m, servo sweep
  0–180°, speed of sound ≈ 343 m/s, robot vacuum speed < 1 m/s. Out-of-range → error.
- Every spoken quantity must equal a scene parameter (existing `fact_problems`) **and** match a verified claim
  number (new `claim_number_problems`), so dialogue = animation = source.
- Cross-scene consistency (existing threshold rule generalised: one value per named quantity per episode).

### 2.5 Kid-safe simplification that stays true
Rules given to the writer and checked by the critic:
1. Simplify by **leaving out**, never by changing: "an ultrasonic sensor sends a sound and listens for the echo" ✔;
   "robots see with sound" ✘ (only some do).
2. Use hedges where reality varies: "many robots", "this robot", "about".
3. Analogies are labelled as analogies ("like a bat") and never claim equivalence.
4. Numbers on screen are the episode's demo numbers ("Bolt's sensor reaches 3 meters"), not universal facts, unless
   verified as universal.
5. No anthropomorphic falsehoods presented as fact ("the robot feels"): characters may joke, but the teaching line
   (Maya's) must be literally true. The critic tags each teaching line `true_as_stated: yes/no`.
6. Safety: nothing a child could copy dangerously (batteries, mains, motors on fingers) without an adult note.

## 3. Script generation into schema 1.1

### 3.1 Beat outline (stage `outline`, then `script`)
Default 8–9 scene skeleton (matches the episode-1 rhythm the owner liked); scene count 6–10, ≤ 25 by schema.
| # | beat | template (if one exists) | rule |
|---|---|---|---|
| 1 | **Hook / cold open gag**: Bolt fails at the topic in a funny way | `cartoon_cold_open` (scene 1, so the intro lands after it) | ≤ 30 s, a sight gag + one question |
| – | **Character intro** | generated by `expand_episode` → `intro_scene` | never authored; the writer must not re-introduce the cast |
| 2..n-2 | **Concept scenes** (2–4 concepts): concept intro card → explain → try/fail → fix | per §4 | each scene has exactly one `concepts[]` marker (`id`, `title` ≤ 40, `subtitle` ≤ 60, `icon`, `beforeBeat`) → `insert_concept_stings` adds the card |
| n-1 | **Practice / apply**: Bolt uses all concepts on the cold-open problem | `cartoon_obstacle_rematch`-style | callback to the hook |
| n | **Recap + quiz + celebration** | `cartoon_recap_chant` | chant of 3 key words, one quiz question whose answer was taught, celebration cue (`victory_sting`/`chant_beat`) |
Each outline beat records: purpose, concept id, claim ids, gag (if any), target seconds.

### 3.2 Cast voice from the registry
The writer prompt is built from `characters/registry.json` (`personality`, `expressions`, `actions`, `speaks`,
`intro`) — never hard-coded text — so registry edits flow into prompts and the prompt version hash.
- **Bolt** (hero, `speaks`): eager, over-confident, rushes in, bonks, laughs at himself, *never mean*; gets the
  misconception first, says the rule back in his own words at the end. Max ~35 % of lines.
- **Maya** (kid inventor): patient, clever big-sister; teaches through quick experiments, not lectures; owns the
  verified teaching lines. ~50–55 % of lines; explanatory lines ≤ 2 sentences.
- **Nib** (`speaks: false`): **sfx beats only** (`nib_beep`, `nib_whistle`) + actions (`fly_to`, `beep_dance`,
  `highfive`…); physical comedy; often "answers" the quiz first. Validation already rejects a Nib `line`.
- Voice consistency check (§5): a character-voice rubric scored by the critic + simple lexical checks (Bolt
  exclamations/self-deprecation, Maya question-led explanations, no sarcasm or put-downs).

### 3.3 Feedback defaults the script must respect
| default | how authoring handles it |
|---|---|
| character intro (ADR-020) | not written; first scene uses `cartoon_cold_open` so `intro.position: after_cold_open` places it |
| concept intro card per learning (ADR-021) | one `concepts[]` marker per concept, `beforeBeat` = the beat before its first teaching line; validation already rejects duplicate ids |
| illustration-first (ADR-027) | every teaching line is authored `explain: true`; the binder (§4) either picks a template whose `DEFAULT_SHOTS` covers it or authors `shots` (`illustration`/`solo` + `visual`); uncovered explain lines get the generic `concept_<icon>` solo from `plan_shots` and are **reported as a visual gap** |
| caption band (ADR-028) | lines are written for one-line cues: target ≤ 55 characters per caption chunk (measured with `subtitles.text_width` at 52 px, 78 % width), lines ≤ 110 chars (2 cues), explain lines ≤ 180, schema hard cap 240; no line needs > 2 lines on screen; no on-screen text is authored in the bottom 18 % (authoring never sets coordinates) |
| acting cues (ADR-029) | every line gets `emotion` (from the speaker's registry `expressions`), optional `pose`/`react` from `acting.POSES`; `auto_pose` covers the rest; the writer adds 1 celebration per episode and listener reactions on punchlines; actions only from the character's registry `actions` |
| transitions (ADR-021) | leave `transitionIn` unset (`auto` cycle); `cut` only if the outline justifies it (QA warns) |
| liveliness / no long holds (ADR-022/023) | no `pause` > 1.5 s; music-only beats ≤ 4 s; at least one action or sfx per ~12 s of dialogue |

### 3.4 Reading level and pacing targets
- Ages 6–9: Flesch-Kincaid grade ≤ 3.5, average sentence ≤ 11 words, max 18; ages 9–12: grade ≤ 5, avg ≤ 14.
- New vocabulary: ≤ 1 new technical term per concept, said ≥ 3 times, shown on the concept card.
- Pace: planning rate `DIALOGUE_WPS = 2.6` (validation.py); 300 s target → **600–700 dialogue words**
  (episode 1: 679 words / 3,672 chars, 74 lines, ~5:19 rendered). Per scene, estimated dialogue ≥ 60 % of
  `durationTargetSeconds` (existing warning); scene targets sum within 10 % of the episode target.
- Gags: ≥ 1 per scene, never on top of the teaching line; the joke lands *after* the fact.

### 3.5 Generation procedure
1. `outline` (strong model): JSON outline only, validated by a JSON schema; retry ≤ 2 on malformed output.
2. `script` (strong model): writes scenes one at a time with the outline, fact sheet (kid wording only), registry
   excerpt, template catalogue (§4.1) and episode-1 as a few-shot golden. Output must be a schema-1.1 scene object;
   parameters only from the chosen template's validator.
3. `critique` (different vendor): rubric = factual (vs `facts.json`), true-as-stated, kid-safe, character voice,
   reading level, pacing, gag quality, caption fit, explain coverage. Findings are typed (`blocker/major/minor`).
4. `revise` (strong model): fixes blockers/majors only, 2 rounds max; then deterministic validators (§5) run and
   their errors are fed back once more. Still failing → stop and hand to a human with the report (no endless loop).

## 4. Visual selection from the template library

### 4.1 Catalogue (generated, not hand-written): `robotics101 authoring catalog`
Built from code so it cannot drift: cartoon `TemplateSpec`s (`templates/registry.py`: name, description,
parameter validator → JSON-schema-ish param doc), `STAGING` in `scenes.py`, `DEFAULT_SHOTS` in `episode.py`,
`visuals.VISUALS`, `props.concept_icon` kinds, `vignettes.KINDS`, `SFX_IDS`, `MUSIC_CUES`, `SETS`. Each entry gets a
hand-maintained **capability card** (`authoring/capabilities.yaml`): concepts it can teach, required beats/sfx it
anchors on (e.g. `cartoon_sensor_ping` needs an `echo` sfx; `cartoon_robot_family` needs `page_flip`…`sparkle`),
parameter meanings, what it cannot show.

Today (2026-11-24): templates `cartoon_cold_open`, `cartoon_robot_family`, `cartoon_robot_checkup`,
`cartoon_sensor_ping`, `cartoon_rule_board`, `cartoon_servo_highfive`, `cartoon_obstacle_rematch`,
`cartoon_recap_chant` (+ generated `cartoon_character_intro`); wide visuals `robot_families`, `echo_diagram`,
`sense_think_act`, `concept_<icon>`; concept icons `robot`, `parts`, `sensor`, `rule`, `servo`; vignettes `vacuum`,
`rover`, `arm`; set `garage`.

### 4.2 Matching
1. Deterministic first: concept ids/keywords in the capability cards → candidate templates/visuals.
2. LLM ranks candidates per outline beat and must justify the fit in one sentence; it may only output names that
   exist in the catalogue (validated). A template is chosen only if its anchoring beats can be authored naturally
   and its parameters can express the verified numbers.
3. Reuse rules: a template used for a different concept than its card says is a **misfit** (e.g. using
   `cartoon_servo_highfive` to teach gears) → treated as a gap, not accepted silently.

### 4.3 Visual gaps — explicit, never silent
- Any explain beat/concept with no fitting template/visual → entry in `visual_gaps.json`: `{gapId, sceneId, beats,
  concept, claimIds, whatMustBeShown (1–3 sentences), suggestedKind: template|visual|icon|vignette|prop,
  closestExisting, severity: blocker|cosmetic}`.
- The spec still renders: the scene uses a neutral stage template plus an authored `solo` shot with
  `visual: "concept_<icon>"` (closest icon) and the concept card; a new **placeholder card** visual
  (`visual_gap` in `VISUALS`, A4) draws a clearly marked "VISUAL COMING SOON: <whatMustBeShown>" board so a
  reviewer can never mistake a placeholder for final art.
- QA: new hard check `authoring.visual_gaps` in cartoon QA reads the gap list from the bundle; `publish --dry-run`
  lists `blocker` gaps as publish blockers. Final approval is impossible while a blocker gap renders as a placeholder.

### 4.4 Path to add a visual
Gap report → owner prioritises → a normal engineering milestone adds a `visuals.py` visual / `concept_icon` kind /
vignette / template + capability card + golden frames + QA (`illustrations.animated`, `layout.caption_band`,
`layout.illustration_first`) → catalogue regenerates → re-run `bind` only (script and voice cache unchanged when
dialogue is unchanged). Generated Python visuals from an LLM stay out of scope (ADR-002/003: template-first; no
untrusted code on host).

## 5. Validation and QA (in order; each writes into `authoring_report.json`)
| # | gate | kind | blocks |
|---|---|---|---|
| 1 | JSON schema 1.1 + `_check_cartoon` (cast, speakers, emotions, actions, sfx/music ids, concepts, poses, shots, template params) | existing, deterministic | yes |
| 2 | `expand_episode` dry run → re-validate the expanded spec (intro, stings, shots, transitions resolve) | existing code path | yes |
| 3 | teaching facts `fact_problems` + new `claim_number_problems` + ranges + cross-scene consistency | deterministic | yes |
| 4 | fact-check gate: every `explain`/teaching line → ≥ 1 claim; claims `verified` (or owner-accepted `single_source`); zero `unverified` in dialogue | deterministic over `facts.json` | yes |
| 5 | kid-safe: `kidsafe_problems` deny list + new topic list (violence, fear, body, brands/ads, unsafe imitation) + critic review | det. + LLM | yes (made-for-kids) |
| 6 | reading level (FK grade, sentence length, new-term count) per character and per scene | deterministic (pure-Python syllable counter, no install) | warn → yes after tuning |
| 7 | timing estimate: words/2.6 per scene vs targets, total vs `durationTargetSeconds` ± 10 %, max pause, holds | deterministic | warn |
| 8 | caption dry run: `subtitles.cue_chunks`/`wrap` at 52 px over each line with estimated durations → no cue > 2 lines, chunks ≥ `MIN_CUE_S`, one-line share ≥ 80 % | deterministic, no render | yes |
| 9 | layout dry run: every `explain` line inside an illustration/solo shot after `plan_shots`; shot visuals exist; gap list consistent | deterministic | yes |
| 10 | character-voice + gag rubric (critic scores ≥ threshold) | LLM | warn |
| 11 | after owner OKs render: existing render + cartoon QA unchanged (`intro.*`, `concepts.cards`, `transitions.no_hard_cuts`, `characters.alive`/`acting`, `illustrations.animated`, `video.no_long_holds`, `layout.*`, `subtitles.*`, `voice.identity`, teaching facts, mix, licences) + new `authoring.visual_gaps` | existing + 1 new | yes |

## 6. Human review points (owner = aishvar23; Grok Bot relays)
| # | when | reviewer sees | decision |
|---|---|---|---|
| R1 | after `plan` | topic, objectives, standards, concept list, planned scenes, cost estimate | approve / edit / reject (cheap: < $0.50 spent) |
| R2 | after `verify` | fact sheet: each claim, kid wording, sources, status; contradictions & single-source items | approve / strike claims |
| R3 | after `revise` | script read-through (screenplay view generated from the spec: speaker, line, emotion, action, cards, shots) + authoring report | approve / request changes (→ new version, R3 again) |
| R4 | with R3 | visual-gap list with severities | accept placeholders for a draft render, or schedule visuals |
| R5 | before voicing | TTS cost (chars → credits) | explicit yes for ElevenLabs (existing ADR-017 gate) |
| R6 | after render | final cut + QA report | existing `approval.json` bound to `finalVideoSha256` |

Recording: `approvals/<point>.json` = `{point, approvedSha256, artifact, reviewer, decision, timestamp, notes}` —
same shape and semantics as `publish/youtube_stub.check_approval` (missing | invalid | not_approved |
sha_mismatch | approved). Each approval binds to the SHA-256 of the exact artifact (`facts.json`,
`episode.source.json`, `visual_gaps.json`); any edit invalidates downstream approvals; `render` of an authored
spec refuses unless R2 + R3 + R4 approvals match the current hashes (`--allow-unapproved-draft` for internal
previews, which marks the bundle `draft` so publish refuses). The manifest records the authoring run id and
approval hashes for lineage. Approvals are written by the owner via Grok Bot relaying their own words (as for
the voice approvals), never inferred by an agent.

## 7. LLM choice and cost

### 7.1 Models (researched 2026-11-24; prices = list, USD per 1M tokens, input / output)
| role | recommended | why | price | source (checked 2026-11-24) |
|---|---|---|---|---|
| writer (outline, script, revise) | **Claude Opus 5.5** | strong long-form writing + reliable structured JSON output | $4 / $20 (batch $2 / $10; cache hit $0.20) | platform.claude.com/docs/en/about-claude/pricing; Anthropic rate card effective 2026-11-09 |
| critic (independent vendor) | **Gemini 4 Carbon** | different vendor = less correlated blind spots; Google positions it for "high factual accuracy" (pricing page description) | $2 / $10 through 2026-11-30, **$4 / $20 from 2026-12-01** (use the Dec price) | ai.google.dev/gemini-api/docs/pricing |
| critic, stronger option | GPT-6.2 Astra | OpenAI's current flagship | $8 / $40 (batch 50 %) | developers.openai.com/api/docs/pricing |
| research reading, claim extraction, cross-check | **Claude Sonnet 5.5** | long-context reading at half Opus price | $2 / $10 | Anthropic pricing page |
| cheap drafting / bulk classification | Claude Haiku 5.5 (or Gemini 3.8 Flash) | very cheap for extraction, reading-level rewrites | $0.10 / $0.50 (≤100K prompt) | Anthropic pricing page; Gemini 3.8 Flash $0.75 / $3.75 (doubles 2027-01-01) |
| search | Claude web search tool (allowed_domains) | allowlist enforcement, citations | $10 / 1,000 searches; web fetch no extra fee | Anthropic pricing page |
Budget mode: Sonnet 5.5 drafts, Opus 5.5 critiques once. Premium mode: Opus writes, GPT-6.2 Astra critiques.
All names/prices must be re-checked at A3 (they change monthly; Gemini prices double on 2026-12-01/2027-01-01).

### 7.2 Token assumptions per episode (estimates)
| stage | model | input tok | output tok | other | est. USD |
|---|---|---|---|---|---|
| plan + research questions | Opus 5.5 | 15k | 3k | – | 0.12 |
| search + read sources | Sonnet 5.5 | 150k | 10k | 25 searches | 0.65 |
| claim extraction + mapping | Sonnet 5.5 | 80k | 12k | – | 0.28 |
| outline | Opus 5.5 | 30k | 4k | – | 0.20 |
| script (8–9 scenes, ~18k-token JSON) | Opus 5.5 | 45k | 18k | – | 0.54 |
| critique × 2 | Gemini 4 Carbon | 2 × 50k | 2 × 6k | – | 0.64 |
| revise × 2 | Opus 5.5 | 2 × 55k | 2 × 18k | – | 1.16 |
| validator-error fix pass | Opus 5.5 | 40k | 8k | – | 0.32 |
| **total (1 clean run)** | | ~570k | ~105k | 25 searches | **≈ $3.9** |
Range: **$2.5 (budget mode, prompt caching) – $6 (retries)**; premium critic (GPT-6.2 Astra instead of Gemini 4 Carbon) adds ≈ $0.65.
A full re-run after R3 changes costs ≈ $1.5–2 (only outline→revise). Batch API (−50 %) is possible because
authoring is not interactive, at the price of hours of latency.

### 7.3 TTS (existing, for context)
Voicing ≈ 1 ElevenLabs credit per character with `eleven_v4` on the Creator plan (ADR-026): episode 1 =
3,672 dialogue chars ≈ **3,850 credits** with intro lines (≈ 3 % of the 131k monthly credits, ≈ $0.65 of the
$22 plan pro rata). Content-hash cache means re-renders with unchanged lines cost 0. Authoring reports the
expected credits at R5 (chars of new/changed lines only).

### 7.4 Cost controls
`trace.jsonl` per call (tokens, searches, USD from a versioned price table `authoring/prices.yaml`); a
pre-call budget check against `budgetUsd` (default $8) and a per-stage cap; hard stop + report on overrun;
monthly cap env `ROBOTICS101_AUTHORING_MAX_USD_MONTH`; retries bounded (2 per stage). Keys only from env/.env
via python-dotenv (same pattern as ElevenLabs), never logged; trace redacts.

## 8. Offline / fixture testing
- Provider interface `authoring/llm.py`: `LLMProvider.complete(prompt_id, prompt_version, messages, schema) ->
  Result` with implementations `FixtureProvider` (default), `RecordingProvider` (wraps a real one, writes fixtures),
  `AnthropicProvider` / `GeminiProvider` / `OpenAIProvider` (opt-in, imported lazily).
- Fixtures keyed by SHA-256 of (prompt id, prompt version, model, normalised messages, schema) →
  `tests/fixtures/authoring/<key>.json`; a missing fixture in fixture mode is an error naming the key (no silent
  network). Search/fetch fixtures are stored page texts with their hashes.
- Deterministic mode: temperature 0 where supported, fixed seeds, sorted JSON, stable ids (`c-01`…), no clocks in
  artifacts except recorded timestamps from fixtures.
- No network in tests: conftest blocks sockets and the SDK clients (as the voice tests already block ElevenLabs
  and point `ROBOTICS101_DOTENV` at a missing file); an AST test forbids network imports outside provider modules.
- Golden specs: `tests/golden/authoring/<topic>/episode.source.json` for 2–3 topics (episode-1 topic re-authored,
  "line following", "robot arms & grippers"); test = fixture run → byte-identical spec + report; plus property
  tests: every golden passes `validate --strict`, gates 1–9, and `expand_episode` idempotence.
- Malformed-output tests: truncated JSON, unknown template/visual/sfx, Nib speaking, number not in parameters,
  fabricated citation (excerpt not in page), unverified claim in dialogue, line too long for one-line captions,
  over-budget trace → each yields the right error and no partial spec.
- Remote integration tests only behind `ROBOTICS101_AUTHORING_LIVE=1` and an owner-approved budget.

## 9. Milestones — authoring track A1–A9 (each: tests + QA evidence + doc/ADR, commit to `feature/pipeline-impl`)
Named A1…A9 so they do not collide with the M0x numbers already used by the feedback rounds (M03–M05) or the
roadmap's M06 YouTube upload.
| id | scope | verification | paid API? |
|---|---|---|---|
| **A1** | Contracts: `authoring-request.schema.json`, facts/outline/gaps/trace schemas, `approvals/*.json` checker (reuse `check_approval` semantics), run-dir layout; `robotics101 authoring catalog` + `capabilities.yaml` for the 9 templates | schema tests, catalog snapshot test, capability card ↔ code consistency test | no |
| **A2** | Provider interface + fixture/recording providers, prompt registry with versions, trace + budget guard, socket block | unit tests incl. budget stop, missing fixture error | no |
| **A3** | Deterministic gates 3–9: `claim_number_problems`, ranges, reading level, timing estimate, caption + layout dry run, screenplay view; run them on episode-1 as a baseline | tests on episode-1 + broken variants | no |
| **A4** | Visual-gap report + `visual_gap` placeholder visual + QA `authoring.visual_gaps` + publish blocker | golden frame of placeholder, QA tests | no |
| **A5** | Pipeline stages wired end-to-end in fixture mode with **hand-written fixtures** (episode-1 topic) → spec equals a golden | golden + malformed-output tests | no |
| **A6** | Record real fixtures for the episode-1 topic + 1 new topic (research, script, critique) | owner reviews R1–R4 artifacts; cost vs estimate | **yes — needs owner yes (≈ $10 cap)** |
| **A7** | First new authored episode: owner R1–R4 → draft render with placeholders (Kokoro, no credits) | full cartoon QA, gap list | no (render only) |
| **A8** | Visuals for the top gaps from A7 (one milestone per visual/template) | existing visual QA + goldens | no |
| **A9** | Voice with ElevenLabs after R5, final render, R6 approval.json | existing gates | **yes — ElevenLabs credits (~3,850), owner yes** |

## 10. Risks and mitigations
| risk | mitigation |
|---|---|
| Hallucinated facts or citations | only fetched pages citable; excerpt-presence check; ≥ 2 independent sources; numbers checked deterministically against claims and parameters; unverified claims removed; R2 human fact review |
| Simplification that becomes false | §2.5 rules; critic tags `true_as_stated`; teaching lines owned by Maya and mapped to claims |
| Age-inappropriate content | made-for-kids hard lint + topic deny list + critic + R3 read-through; no brands/ads/links; safety notes for imitable actions |
| Copyright | no copying of source text into dialogue (n-gram overlap check vs fetched pages, ≤ 8-word runs); no third-party characters/logos/brand robots; all visuals in-repo code; sources cited in the description |
| Visual gaps / topic bent to fit old templates | explicit gap report, misfit rule, placeholder blocks final approval, visuals as normal milestones; prefer topics adjacent to existing visuals first |
| Cost overruns | per-run/stage/month caps, trace, bounded retries, fixture default, batch API, prices table re-checked |
| Drift from character voice | registry-driven prompts, episode-1 few-shot, voice rubric + lexical checks, line-share limits, R3 |
| Model/price churn | provider interface, prompt+model versions in trace and fixture keys, re-record only on change |
| Prompt injection from web pages | fetched text is untrusted data, wrapped and never executed; models get no tools except search/fetch on the allowlist; outputs validated against schemas; no agent can render/voice/publish |
| Schema pressure (needs new fields) | keep claim mapping outside the spec; any schema change = new ADR + 1.x minor version with migration |

## 11. Decisions needed from the owner
1. Approve the model line-up (Opus 5.5 writer + Gemini 4 Carbon critic) or the budget/premium variant.
2. Provide API keys when A6 starts: Anthropic (required), Google Gemini (critic), OpenAI (only for premium critic).
3. Per-episode cap (default $8) and monthly authoring cap.
4. Age band default (6–9 vs 9–12) and reading-level targets.
5. Source allowlist (tier A–D list in §2.1) — add or remove publishers.
6. First new topics to author (suggest ones near existing visuals: "how robots measure distance with light", "line
   following", "robot arms and grippers").
7. Whether R1/R2/R3 may be combined into one review for low-risk topics later.
