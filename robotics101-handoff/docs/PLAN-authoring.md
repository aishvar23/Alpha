# Plan: topic-to-script authoring for Robotics 101 cartoon episodes

Status: **PLAN ONLY**, revision 2 (2026-11-24, after review of c857f3e). Nothing here is built; no code, installs or
paid API calls were made to write it. It replaces the generic `tasks/M02_AI_AUTHORING.md` outline with a design that
targets the real cartoon contract (schema 1.1) and the pipeline defaults the owner asked for in M03–M05
(ADR-020…029). Owner decisions are in §12.

Revision 2 changes: parametric visual kit (§5), blocking engagement gate (§6.2), three human reviews (§7), single
vendor (Anthropic) for v1 (§8), definition of independent sources (§3.3), curriculum sequence (§2), updated
milestones (§10) and costs (§8.2).

Names used below are the real ones in the repo: `contracts/episode.v1.1.schema.json`, `characters/registry.json`,
`robotics101.validation._check_cartoon`, `cartoon/lint.py` (`fact_problems`, `kidsafe_problems`),
`cartoon/episode.py` (`expand_episode`, `plan_shots`, `DEFAULT_SHOTS`, `intro_scene`, `insert_concept_stings`,
`resolve_transitions`), `cartoon/visuals.py` (`VISUALS`, `concept_visual`), `cartoon/vignettes.py` (`KINDS`),
`cartoon/acting.py` (`POSES`, `auto_pose`, `auto_react`), `cartoon/subtitles.py` (`wrap`, `cue_chunks`,
`text_width`), `cartoon/layout.py` (`CAPTION_BAND`, `ILLUSTRATION_MIN_AREA`), `templates/registry.py` (cartoon
`TemplateSpec`s), `cartoon/__init__.py` (`SFX_IDS`, `MUSIC_CUES`, `SETS`), `publish/youtube_stub.py`
(`check_approval`).

## 0. Summary
- **Input:** a lesson topic (+ optional age band, length, objectives), normally picked from the curriculum sequence.
  **Output:** an authoring bundle whose core is an `episode.source.json` that passes `robotics101 validate --strict`
  unchanged, plus a fact sheet, a visual-gap report and a cost/trace record. `render` (which runs `expand_episode`) is
  untouched.
- **Shape:** a fixed, typed stage pipeline (no free-form agent loop): `plan → research → verify → outline → script →
  critique/revise → bind visuals → gates → human review`. Every stage writes a JSON artifact with a SHA-256; later
  stages only read earlier artifacts.
- **Visuals scale through data, not drawing code:** a parametric visual kit (7 primitives) that authoring fills
  declaratively; estimated to cover ≈ 80 % of the first three topics' visual needs. Whatever it cannot show is an
  explicit visual gap (report + placeholder + publish block).
- **Engagement is a hard gate**, like accuracy: deterministic pacing checks plus a critic rubric with fun/engagement
  scores; both block.
- **Three human reviews:** R1 outline + fact sheet, R2 screenplay + visual gaps, R3 final video; paid-spend yeses stay
  separate.
- **v1 is single-vendor (Anthropic), one API key.** ≈ **$4–4.7 of LLM + search per episode** (estimate, range
  $3–6.5), plus ≈ **3,850 ElevenLabs credits** to voice it. All model names/prices are to be verified against the
  official pricing pages at A8 (the first paid milestone).

## 1. Input and output contract

### 1.1 Input: `authoring/request.json` (validated by a new `contracts/authoring-request.schema.json`)
| field | required | default | notes |
|---|---|---|---|
| `topicId` or `topic` | yes | – | `topicId` from `curriculum/sequence.yaml` (§2) preferred; free `topic` allowed (3–120 chars) |
| `episodeNumber` | yes | – | becomes `episodeId` `ep-NNN` |
| `ageBand` | no | `"6-9"` | `"6-9"` or `"9-12"`; drives reading level and joke style |
| `audience` | no | `"beginner"` | schema enum `beginner/intermediate/advanced` |
| `durationTargetSeconds` | no | `300` | 240–360 recommended (validation warns outside 270–330 today) |
| `learningObjectives` | no | from sequence | 1–5 strings (schema limit); given ones are fixed, not rewritten |
| `mustInclude` / `avoid` | no | `[]` | concepts/terms the owner wants in or out |
| `madeForKids` | no | `true` | copied to `publishing.madeForKids`; kid-safe errors become hard |
| `cast` | no | `["bolt","maya","nib"]` | must exist in the registry |
| `budgetUsd` | no | `8.00` | hard cap for the whole authoring run (§8.4) |
| `mode` | no | `"fixture"` | `fixture` (no network), `record` (paid, writes fixtures), `live` (paid) |

### 1.2 Output: `out/authoring/<episodeId>/<runId>/`
| file | contents |
|---|---|
| `request.json` | normalised input (run identity = its hash + prompt versions + model ids) |
| `curriculum.json` | objectives, NGSS/CSTA alignments, prerequisites taken from earlier episodes, concept list (2–4) |
| `sources.json` | each retrieved source: id, URL, title, publisher, `publisherGroup`, tier, retrieval time, content SHA-256 |
| `facts.json` | fact sheet: claims with `claimId`, kid wording, supporting excerpts, independence evidence, status (§3) |
| `outline.json` | beat outline per scene (§4.1) with claim ids, gag tags, hook id, visual intents |
| `episode.source.json` | the schema-1.1 EpisodeSpec (author file; `render` expands it into `episode.json`) |
| `visual_bindings.json` | per explain beat: chosen template / visual / kit primitive + params, or gap id (§5) |
| `visual_gaps.json` | what neither templates nor the kit can show yet (§5.5) |
| `critique/*.json` | each critic pass: rubric scores, findings, severity, what changed (§6.3) |
| `authoring_report.json` | all gate results (§6) |
| `trace.jsonl` | one record per model/tool call: stage, model, prompt id+version, tokens, searches, USD, latency, cache hit |
| `review/R1.json`, `review/R2.json` | review packets + approvals (§7) |

Contract rules: the spec carries `sources[]` (already in schema 1.1: `claimId`, `sourceUrl`, `verificationStatus`
`verified|unverified`, `note`); every teaching line maps to ≥ 1 claim id (kept in `facts.json`, not in the beat); no
URLs, model names or secrets in dialogue. Stages write only inside their run directory; they never call `render`,
`voice`, ElevenLabs or `publish`.

## 2. Curriculum sequence and topic backlog
Episodes must build on each other, so topics come from a versioned `curriculum/sequence.yaml` (owner-editable) and a
`curriculum/canon.json` of facts already taught on screen.

- `sequence.yaml` entry: `{topicId, title, concepts[], prerequisites[topicId], reuses[concept], newVocabulary[],
  standards[], expectedVisuals[], status: backlog|authoring|published}`.
- `canon.json` (written when an episode reaches R3): approved world facts that later episodes must not contradict,
  e.g. Bolt's ultrasonic range 3 m, his stop threshold 0.5 m, servo high-five at 60°, vocabulary already taught
  (sense/think/act, sensor, actuator, controller, servo, threshold).
- The `plan` stage receives the prerequisites' canon: it may recap a prior concept in ≤ 1–2 lines ("Remember Bolt's
  echo?"), must reuse earlier vocabulary consistently, and a deterministic check (`canon_problems`) fails a spoken
  number about a canon quantity that differs from canon unless the line marks it as a different robot/sensor.

### 2.1 First three topics (ordered) and why
| ep | topicId | builds on | new concepts | why this position |
|---|---|---|---|---|
| 002 | `distance_with_light` — "Seeing distance with light" | ep-001 ultrasonic sensor, sense–think–act, 0.5 m rule | infrared/light sensors, reflection, light vs sound sensors, dark/shiny surfaces fool sensors | smallest step from ep-001 (same question, new sensor); reuses the rule board, rematch and echo visuals; lowest visual-gap risk, so it is the best first authored episode |
| 003 | `line_following` — "Follow that line!" | ep-002 light sensor + reflection (pointed down) | light/dark readings, two-rule decisions (left/right), loops, two sensors vs one | turns one rule into a steering loop; needs ep-002's "light bounces more off white" fact; first top-down track visuals |
| 004 | `arms_and_grippers` — "Grab it, Bolt!" | ep-001 servo angles, actuators | joints, degrees of freedom, grippers, pick-and-place sequence, grip strength | switches from mobile robots to manipulators; extends the servo idea; needs the most new art (articulated arm), so it comes after the kit has been proven on two episodes |

### 2.2 Backlog after ep-004 (prerequisites in brackets; reorderable by the owner)
1. Wheels and motors: how robots turn (differential drive) [ep-001 actuators, ep-003 steering]
2. Power and batteries: why robots get "sleepy" [ep-001 power part]
3. Programs are recipes: steps, loops and if-then [ep-001 rule, ep-003 loop]
4. Cameras and colours: robots that see colour [ep-002 light]
5. Check and correct: feedback (thermostat → steering) [ep-003]
6. Maps and finding the way: robot vacuums and rovers [ep-002, ep-005 feedback]
7. Robot safety and helpers: robots working with people [ep-004]
8. Balance and walking robots [ep-004 joints, feedback]
Each backlog item lists `expectedVisuals` so the kit/gap work can be planned ahead of authoring.

## 3. Research and fact verification

### 3.1 Source tiers (allowlist `authoring/sources.yaml`, reviewed by the owner)
| tier | examples | used for |
|---|---|---|
| A — standards | NGSS (K-2-ETS1, 3-5-ETS1, 4-PS4 waves/light), CSTA K-12 CS Standards (1A/1B), ISTE | objectives, age fit, vocabulary |
| B — education | NASA/JPL education, university outreach (e.g. CMU Robotics Academy), IEEE Spectrum / IEEE RAS education, Smithsonian, BBC Bitesize, Khan Academy, PBS LearningMedia | explanations, kid framing |
| C — technical/manufacturer | sensor datasheets (e.g. HC-SR04, Sharp GP2Y0A IR), servo specs, LEGO Education / micro:bit / VEX docs, robot maker product pages | numbers on screen |
| D — encyclopedias | Britannica; Wikipedia only as a pointer to its own citations (never counted itself) | cross-checks |
Each allowlisted domain carries a `publisherGroup` (e.g. `nasa.gov`, `jpl.nasa.gov`, `science.nasa.gov` → `NASA`;
`bbc.co.uk`, `bbc.com` → `BBC`). Blocked: content farms, AI-generated listicles, forums, social video, unknown publishers.

### 3.2 Retrieval
1. `plan` turns the topic into 6–12 research questions (one per concept + misconceptions + on-screen numbers).
2. Search with the model's server-side web search tool restricted by `allowed_domains`; ~15–25 searches/episode,
   cap 40. Fetch with the web fetch tool; store text + SHA-256 + timestamp + outbound links in `sources.json`.
3. Only fetched pages can be cited; a deterministic check verifies each excerpt string is present in the stored text
   (no fabricated citations). Fixture mode replays stored pages; tests never hit the network (§9).

### 3.3 What counts as independent sources
Two supporting sources for a claim are **independent** only if all of these hold (each checked deterministically in
`verify`; anything ambiguous downgrades the claim to `single_source`):
1. **Different publishers:** different `publisherGroup` (registrable domain mapped through the allowlist; unknown
   subdomains inherit the parent's group). Two NASA pages are one publisher.
2. **Not copies or syndications:** the supporting passages are not near-duplicates — word 5-gram shingle Jaccard
   < 0.5 **and** no identical run of ≥ 25 words between the two fetched pages (catches syndicated articles, press
   release reprints, reseller copies of a datasheet). Datasheets for the same part number from different hosts count once.
3. **Not citing each other for the claim:** neither page links to or cites the other within the paragraph holding the
   excerpt or in a reference list entry that matches the excerpt's topic (outbound links and reference sections are
   extracted at fetch time; a match on URL or title = dependent).
4. **Not derived from the same upstream:** if both passages cite the same upstream source (same URL/DOI/title in
   their references for that paragraph), they count as one; the upstream itself is fetched and used instead when
   allowlisted.
5. Wikipedia and any LLM output never count; a Wikipedia citation counts only after the cited page is fetched.
`facts.json` stores the evidence (`publisherGroup`s, max shingle similarity, longest shared run, link/citation hits)
so R1 can see why two sources were judged independent.

### 3.4 Claim extraction, status and numeric checks
- Atomic claims: `{claimId: "c-07", text, kidText, kind: definition|mechanism|number|example|history,
  numbers: [{value, unit}], concept}` with supporting `{sourceId, excerpt}` pairs.
- Status: `verified` (≥ 2 independent sources per §3.3, at least one tier A–C); `single_source` (allowed only for
  non-numeric framing, flagged at R1); `unverified` (line removed or rewritten; if the owner keeps it, it goes into
  `sources[]` as `unverified` with a note and is shown at R3); `contradicted` (R1 item; script uses the conservative
  statement).
- Numeric sanity (no LLM): units normalised (extend `lint._to_si` to cm/mm/s/Hz/%); plausibility table
  `authoring/ranges.yaml` (hobby ultrasonic 0.02–4 m, hobby IR distance 0.1–1.5 m, servo 0–180°, speed of sound
  ≈ 343 m/s …); every spoken quantity must equal a scene parameter (existing `fact_problems`) **and** a verified claim
  number (new `claim_number_problems`) **and** canon (§2); one value per named quantity per episode.

### 3.5 Kid-safe simplification that stays true
1. Simplify by leaving out, never by changing ("an ultrasonic sensor sends a sound and listens for the echo" ✔;
   "robots see with sound" ✘).
2. Hedge where reality varies ("many robots", "this robot", "about").
3. Analogies are labelled ("like a bat") and never claim equivalence.
4. On-screen numbers are the episode's demo numbers ("Bolt's sensor reaches 3 meters") unless verified as universal.
5. Characters may joke, but teaching lines (mostly Maya's) must be literally true; the critic tags each teaching line
   `true_as_stated`.
6. Nothing a child could copy dangerously (batteries, mains, motors near fingers) without an adult note.

## 4. Script generation into schema 1.1

### 4.1 Beat outline
Default 8–9 scenes (episode-1 rhythm); 6–10 allowed (schema max 25).
| # | beat | template (if one exists) | rule |
|---|---|---|---|
| 1 | **Hook / cold open gag**: Bolt fails at the topic in a funny way; outline records `hook {id, problem, prop}` | `cartoon_cold_open` (scene 1, so the intro lands after it) | ≤ 30 s, first gag ≤ 10 s, ends on a question |
| – | **Character intro** | generated by `expand_episode` → `intro_scene` | never authored |
| 2..n-2 | **Concept scenes** (2–4): concept card → explain → try/fail → fix | §5 | exactly one `concepts[]` marker per concept (`id`, `title` ≤ 40, `subtitle` ≤ 60, `icon`, `beforeBeat`) |
| n-1 | **Practice / apply**: Bolt uses every concept on the hook problem | `cartoon_obstacle_rematch`-style or kit `track_map` | must call back to `hook.id` |
| n | **Recap chant + quiz + celebration** | `cartoon_recap_chant` | 3-word chant from the concept titles, one quiz question taught earlier, celebration cue |
Each outline beat records purpose, concept id, claim ids, `gag` tag (kind: sight, line, sfx, reaction), visual intent
(what must be seen, in words), target seconds.

### 4.2 Cast voice from the registry
Writer prompts are built from `characters/registry.json` (`personality`, `expressions`, `actions`, `speaks`, `intro`),
so registry edits flow into prompts and the prompt version hash.
- **Bolt:** eager, over-confident, rushes in, bonks, laughs at himself, never mean; voices the misconception first and
  restates the rule in his own words at the end. ≤ 35 % of lines.
- **Maya:** patient, clever big sister; teaches through quick experiments; owns verified teaching lines;
  ~50–55 % of lines; explain lines ≤ 2 sentences.
- **Nib** (`speaks: false`): sfx beats only (`nib_beep`, `nib_whistle`) + actions (`fly_to`, `beep_dance`,
  `highfive` …); physical comedy; often "answers" the quiz first. Validation already rejects a Nib `line`.

### 4.3 Feedback defaults the script must respect
| default | how authoring handles it |
|---|---|
| character intro (ADR-020) | not written; scene 1 uses `cartoon_cold_open` so `intro.position: after_cold_open` places it |
| concept card per learning (ADR-021) | one `concepts[]` marker per concept, `beforeBeat` = beat before its first teaching line |
| illustration-first (ADR-027) | every teaching line is `explain: true`; the binder (§5) covers it with a template's `DEFAULT_SHOTS`, an authored `illustration`/`solo` shot with a library visual, or a kit visual; otherwise a reported gap |
| caption band (ADR-028) | lines written for one-line cues: ≤ 55 chars per caption chunk (measured with `subtitles.text_width` at 52 px, 78 % width), lines ≤ 110 chars, explain lines ≤ 180, schema cap 240; authoring never places anything in the bottom 18 % (kit layouts clip to `CONTENT_FLOOR_Y`) |
| acting cues (ADR-029) | every line gets an `emotion` from the speaker's registry `expressions`, optional `pose`/`react` from `acting.POSES`; actions only from the registry `actions` |
| transitions (ADR-021) | `transitionIn` left unset (`auto`); `cut` only if justified (QA warns) |
| liveliness / no long holds (ADR-022/023) | no `pause` > 1.5 s; music-only beats ≤ 4 s; see the engagement gate (§6.2) |

### 4.4 Reading level and pacing targets
- Ages 6–9: Flesch-Kincaid grade ≤ 3.5, average sentence ≤ 11 words (max 18); ages 9–12: grade ≤ 5, avg ≤ 14.
- ≤ 1 new technical term per concept, said ≥ 3 times, shown on the concept card; earlier vocabulary from canon.
- Pace: `DIALOGUE_WPS = 2.6` (validation.py); 300 s → 600–700 dialogue words (episode 1: 679 words / 3,672 chars,
  74 lines, 5:19 rendered); per scene, estimated dialogue ≥ 60 % of `durationTargetSeconds`; scene targets sum
  within 10 % of the episode target.

### 4.5 Generation procedure
1. `outline` (writer model): JSON outline only, schema-validated; ≤ 2 retries on malformed output.
2. `script` (writer model): scene by scene with outline, kid-worded facts, registry excerpt, catalogue (§5.1) and
   episode 1 as few-shot golden; parameters only from the chosen template's validator / kit schema.
3. `critique` (critic, §8.1): rubric §6.3, typed findings `blocker/major/minor`.
4. `revise` (writer): fixes blockers/majors; ≤ 2 rounds; deterministic gate errors fed back once more. Still failing
   → stop and hand to a human with the report.

## 5. Visuals: template library, parametric kit, gaps

### 5.1 Catalogue (generated from code): `robotics101 authoring catalog`
Built from cartoon `TemplateSpec`s, `STAGING` (`scenes.py`), `DEFAULT_SHOTS`, `visuals.VISUALS`,
`props.concept_icon` kinds, `vignettes.KINDS`, `SFX_IDS`, `MUSIC_CUES`, `SETS`, and the kit primitives (§5.3), each
with a capability card in `authoring/capabilities.yaml` (concepts it teaches, anchor beats it needs, parameter
meanings, what it cannot show). A consistency test fails when code and cards disagree.

Today (2026-11-24): templates `cartoon_cold_open`, `cartoon_robot_family`, `cartoon_robot_checkup`,
`cartoon_sensor_ping`, `cartoon_rule_board`, `cartoon_servo_highfive`, `cartoon_obstacle_rematch`,
`cartoon_recap_chant` (+ generated `cartoon_character_intro`); wide visuals `robot_families`, `echo_diagram`,
`sense_think_act`, `concept_<icon>`; icons `robot`, `parts`, `sensor`, `rule`, `servo`; vignettes `vacuum`, `rover`,
`arm`; set `garage`. These are mostly hand-built for episode 1, which is why the kit is needed.

### 5.2 Why a parametric kit
Hand-drawing one visual per concept does not scale to 2–3 new concepts per episode. Most teaching visuals in kids'
explainers are a few recurring forms (parts diagram, flow, beam, meter, steps, comparison, top-down map). The kit
implements each form **once** as deterministic, always-animated Manim code; authoring selects a primitive and fills
its **data** (labels, values, steps), never drawing code (ADR-002/003 stay intact: no generated code runs).

### 5.3 Kit primitives
| primitive | shows | built-in motion (satisfies `illustrations.animated`) | key params |
|---|---|---|---|
| `labeled_parts` | a body (generic robot, Bolt, sensor module, arm, gripper silhouette from `kit/bodies`) with callouts | callouts pop in on cue words, highlighted part pulses | `body`, `parts[{id,label,anchor}]`, `revealOn` |
| `flow` | boxes/icons linked by arrows (cycles or chains) | travelling dot along arrows, active node pulses | `nodes[{id,label,icon}]`, `edges[[a,b]]`, `loop`, `activeOn` |
| `beam` | sensor emitter → rays/cone/pulse → target → reflection | pulse travels out and back, hit flash, optional absorbed ray | `kind: sound|light|laser`, `shape: cone|ray|fan`, `target{kind,surface: white|black|shiny|soft}`, `distance` (`$param`), `reflect` |
| `meter` | gauge, bar, number readout, or tiny line graph over time | needle/bar animates between values per cue, threshold line blinks | `style: gauge|bar|readout|graph`, `min`, `max`, `unit`, `values[]`, `threshold` |
| `steps` | numbered step sequence (2–6 panels) | panels light up in order, check marks | `steps[{label,icon}]`, `advanceOn` |
| `compare` | two panels side by side with a "vs" divider | both panels animate (each panel hosts another primitive or a vignette), winner badge | `left{title,visual}`, `right{title,visual}`, `verdict` |
| `track_map` | top-down map: robot on a track/line/room with obstacles, sensor footprint, path trail | robot drives a scripted path, sensor footprint updates, trail draws | `map: line|room|grid`, `track` (preset or polyline), `robot{body,sensors[]}`, `obstacles[]`, `path` (preset `follow_line`, `zigzag`, `stop_before`, `overshoot_turn`), `speed` |
Common rules: clips to the shot box above the caption band (`layout.CONTENT_FLOOR_Y`), labels ≤ 18 chars in Fredoka,
palette from `props.P`/ink, everything timed from scene cues (`ctx` word/sfx times, like existing visuals), and numbers
written as `$param` references so `fact_problems` sees them.

### 5.4 Schema sketch (additive, ADR-030; schema stays 1.1 because every existing spec remains valid)
A shot gains an optional `kit` object instead of a library `visual` name:
```json
{"layout": "illustration", "fromBeat": 3, "toBeat": 6,
 "kit": {"primitive": "beam",
         "params": {"kind": "light", "shape": "ray", "target": {"kind": "wall", "surface": "white"},
                    "distance": "$distanceMeters", "reflect": true},
         "cues": {"pulseOn": "word:bounces", "hitOn": "sfx:ping"},
         "title": "Light bounces back"}}
```
JSON-schema fragment (in `$defs.shot.properties`): `"kit": {"type": "object", "additionalProperties": false,
"required": ["primitive","params"], "properties": {"primitive": {"enum": ["labeled_parts","flow","beam","meter",
"steps","compare","track_map"]}, "params": {"type": "object"}, "cues": {"type": "object"}, "title":
{"type": "string", "maxLength": 40}}}` plus `oneOf` "visual xor kit". Per-primitive param schemas live in
`contracts/kit/<primitive>.schema.json` and are checked in `_check_cartoon`; `$name` must resolve to a scene parameter;
cue strings must reference a word in the covered lines or an sfx id in the covered beats. QA reuses
`layout.illustration_first` (area ≥ 55 % / 35 %), `layout.caption_band`, `illustrations.animated`.

### 5.5 Coverage estimate for the first three topics (estimate; confirmed by the A6 coverage report)
**ep-002 `distance_with_light`**
| needed visual | covered by |
|---|---|
| IR sensor parts (emitter, receiver, lens) | kit `labeled_parts` |
| light pulse goes out, bounces off a wall, comes back | kit `beam` (light, ray, reflect) |
| sound sensor vs light sensor side by side | kit `compare` (existing `echo_diagram` vs `beam`) |
| distance readout dropping as Bolt approaches | kit `meter` (readout + threshold) |
| black/shiny surfaces fool the light sensor (absorb/scatter) | kit `beam` (`surface: black|shiny`) |
| Bolt stops before the wall using the light sensor | existing `cartoon_obstacle_rematch` (+ kit `track_map` `stop_before`) |
| sense → think → act recap with the new sensor | existing `sense_think_act` / kit `flow` |
→ 7/7 covered (5 kit, 2 existing). Gap risk: none blocking.

**ep-003 `line_following`**
| needed visual | covered by |
|---|---|
| top-down track with a black line, robot on it | kit `track_map` (`map: line`) |
| downward light sensor: white reflects a lot, black little | kit `beam` (`surface` white vs black) inside `compare` |
| sensor reading light/dark over time | kit `meter` (`graph`) |
| decision: on black turn one way, on white turn the other | kit `flow` |
| zigzag "wiggle" along the line | kit `track_map` (`path: zigzag`) |
| one sensor vs two sensors | kit `compare` of two `track_map`s |
| Bolt overshoots a sharp corner (gag) | kit `track_map` (`path: overshoot_turn`) |
| side view of Bolt with the sensor under his belly | **gap** (rig variant/prop: sensor under Bolt) |
→ 7/8 covered (all kit). Gap: Bolt side-view sensor prop (cosmetic; `labeled_parts` with `body: bolt` is the fallback).

**ep-004 `arms_and_grippers`**
| needed visual | covered by |
|---|---|
| arm parts: base, joints, links, gripper | kit `labeled_parts` (`body: arm`) |
| pick-and-place sequence | existing `vignettes.arm` + kit `steps` |
| joint angle for each joint | kit `meter` (gauge) / existing servo protractor |
| gripper types (claw, suction, soft) compared | kit `compare` (silhouettes in `kit/bodies`) |
| grip strength: too soft drops, too hard squishes | kit `meter` (bar + threshold) + **gap** (squish animation) |
| degrees of freedom: each joint moves separately | **gap** (articulated multi-joint arm rig with posable joints) |
| gripper opening/closing on an object | **gap** (articulated gripper) |
| Bolt tries to grab with noodle arms (gag) | existing Bolt rig actions (`arm_to`) |
→ 5/8 covered (4 with kit help), 3 gaps that share one new asset: an articulated arm/gripper rig (one engineering
milestone, A10).

**Overall: 19 of 23 needed visuals ≈ 83 % covered; the kit is the main cover for 16 of them (≈ 70 %); without the
kit only ≈ 4–5 of 23 (≈ 20 %) would be covered.**

### 5.6 Binding and gaps (explicit, never silent)
1. Deterministic first: concept/visual-intent keywords vs capability cards → candidates (templates, library visuals,
   kit primitives).
2. The writer model ranks candidates per explain beat with a one-sentence justification and fills kit params; output
   names must exist in the catalogue and params must pass the kit schemas.
3. A template used for a concept its card does not list is a **misfit** → treated as a gap.
4. Anything uncovered → `visual_gaps.json` entry `{gapId, sceneId, beats, concept, claimIds, whatMustBeShown,
   suggestedKind: kit_param|kit_primitive|body|template|icon|vignette, closestExisting, severity: blocker|cosmetic}`.
   The scene renders with a `visual_gap` placeholder visual ("VISUAL COMING SOON: …", unmistakably a placeholder).
   QA `authoring.visual_gaps` (new, hard) reads the list; `publish --dry-run` lists blocker gaps as publish blockers;
   R3 cannot approve a video that shows a placeholder.
5. Path to add a visual: owner prioritises → normal engineering milestone (new kit body/preset, primitive, or
   template + capability card + golden frames + existing visual QA) → catalogue regenerates → re-run `bind` only
   (dialogue unchanged → voice cache unchanged).

## 6. Gates (all in `authoring_report.json`; "block" = the run cannot reach R2)

### 6.1 Correctness and format gates
| # | gate | kind | blocks |
|---|---|---|---|
| 1 | schema 1.1 (+ kit schemas) + `_check_cartoon` | existing + kit, deterministic | yes |
| 2 | `expand_episode` dry run → re-validate the expanded spec | existing code path | yes |
| 3 | numbers: `fact_problems`, `claim_number_problems`, ranges, canon, cross-scene | deterministic | yes |
| 4 | fact-check: every explain/teaching line → ≥ 1 claim; no `unverified` claim in dialogue; independence evidence present | deterministic over `facts.json` | yes |
| 5 | kid-safe: `kidsafe_problems` + topic deny list (violence, fear, body, brands/ads, unsafe imitation) | deterministic + critic | yes (made-for-kids) |
| 6 | reading level per character/scene (pure-Python syllable counter) | deterministic | warn → block after A8 calibration |
| 7 | timing estimate vs targets (± 10 %), max pause 1.5 s | deterministic | warn |
| 8 | caption dry run (`cue_chunks`/`wrap` at 52 px): no cue > 2 lines, chunks ≥ `MIN_CUE_S`, one-line share ≥ 80 % | deterministic | yes |
| 9 | layout dry run: every explain line inside an illustration/solo shot after `plan_shots`; visuals/kit resolve; gap list consistent | deterministic | yes |

### 6.2 Engagement gate — deterministic pacing checks (blocking)
Computed from the spec's estimated timeline (lines at 2.6 words/s, sfx/action/pause/music durations as in
`timing.json` rules, concept cards 2.8 s, transitions) before any render; re-measured on the real `timing.json`
and `scenes.json` after render as cartoon QA `engagement.*` (same thresholds). Proposed thresholds for ages 6–9
(calibrated at A3 so episode 1 passes; 9–12 slightly relaxed):
| check | rule | threshold |
|---|---|---|
| `engagement.visual_change` | longest stretch without a visual event (shot start/end, concept card, transition, action beat, impact sfx with on-screen lettering, kit reveal/advance cue, entrance) | ≤ **8 s** (warn > 6 s) |
| `engagement.gag_density` | outline-tagged gags + impact sfx (`bonk`, `boing`, `skid`, `pop`, `toaster_pop`, `stars`) + `giggle`/`surprised` poses, per minute | ≥ **1.5 / min** overall, ≥ 1 per scene, no 45 s window without one |
| `engagement.reaction_density` | listener reactions / emotion changes (`react`, `auto_react` result, emotion change between consecutive lines) | ≥ **3 / min** |
| `engagement.monologue` | longest run of one speaker without another line, sfx or action | ≤ **15 s** |
| `engagement.hook` | first gag within | ≤ **10 s**; cold open ≤ 30 s |
| `engagement.hook_callback` | practice scene references `hook.id` (same prop/obstacle parameter or keyword) **and** a line in the last 25 % mentions it | both present |
| `engagement.chant` | ≥ 1 `chant_beat` music cue (or `cartoon_recap_chant` scene) with a 3-word chant built from concept titles | present |
| `engagement.audience_questions` | lines addressed to the viewer that end in "?" (quiz + at least one mid-episode prediction) | ≥ **2** |
| `engagement.first_concept` | first concept card starts by | ≤ **75 s** (after cold open + intro) |
Gag tags live in `outline.json` / `visual_bindings.json` (the schema does not change); the checker maps them to beats.

### 6.3 Critic rubric (blocking, alongside accuracy)
The critic scores each scene and the whole episode 1–5 with a written reason and quoted evidence:
| dimension | what it judges | blocking threshold |
|---|---|---|
| accuracy | every teaching line true as stated vs `facts.json`; simplifications obey §3.5 | **5** and zero blocker findings |
| clarity | one idea at a time, concrete example before the term, quiz answerable from the episode | ≥ 4 |
| fun / humour | gags land, are kid-appropriate, come after the fact (not on top of it), variety (sight/line/sfx) | ≥ **4** |
| engagement | curiosity questions, tension → payoff, hook payoff, energy curve, no lecture stretches | ≥ **4** |
| character voice | Bolt/Maya/Nib match registry personalities; no sarcasm or put-downs | ≥ 4 |
| age fit | vocabulary, references and fears appropriate for the age band | ≥ 4 |
Two critic samples at temperature 0 with different seeds/orderings where supported; the **lower** score counts.
Episode 1 is the calibration anchor: it must pass; thresholds are tuned with the owner at A8 and then frozen per
prompt version. Fixture mode replays recorded critic outputs so the gate is deterministic in tests.

### 6.4 After render
Existing render + cartoon QA unchanged (`intro.*`, `concepts.cards`, `transitions.no_hard_cuts`,
`characters.alive`/`acting`, `illustrations.animated`, `video.no_long_holds`, `layout.*`, `subtitles.*`,
`voice.identity`, teaching facts, mix, licences) + new `authoring.visual_gaps` and `engagement.*`.

## 7. Human review points (three) and approvals
| # | when | reviewer sees | decision |
|---|---|---|---|
| **R1** | after `outline` + `verify` | outline (scenes, beats, hook, concepts, gags, visual intents), fact sheet (claims, kid wording, sources, independence evidence, single-source / contradicted items), curriculum fit, cost so far + estimate | approve / edit / strike claims / reject |
| **R2** | after gates pass | screenplay generated from the spec (speaker, line, emotion, action, cards, shots, kit visuals described in words), visual-gap list with severities, gate + rubric report | approve (draft render may use cosmetic placeholders) / request changes |
| **R3** | after render | final cut + QA report | existing `approval.json` bound to `finalVideoSha256` |
Paid-spend yeses stay separate from reviews: **S1** authoring LLM spend (first at A8; afterwards only if a run's
estimate exceeds the approved per-episode cap) and **S2** ElevenLabs voicing (existing ADR-017 gate, with credits
for new/changed lines only).

Hash binding: each review writes a packet `review/R1.json` / `review/R2.json` listing the artifacts and their
SHA-256 (R1: `outline.json`, `facts.json`, `sources.json`; R2: `episode.source.json`, `visual_bindings.json`,
`visual_gaps.json`, `authoring_report.json`) and the packet's own SHA-256. The approval record is
`{point, approvedSha256 (= packet hash), reviewer, decision, timestamp, notes}`, checked with the same semantics as
`publish/youtube_stub.check_approval` (missing | invalid | not_approved | sha_mismatch | approved). Any edit to a
listed artifact changes the packet hash and invalidates that approval and every later one (R1 change → R2 void).
`render` of an authored spec refuses unless R1 and R2 match current hashes (`--allow-unapproved-draft` marks the
bundle `draft`, which publish refuses). The manifest records the authoring run id and both packet hashes; R3 binds to
the video. Approvals come from the owner's own words relayed by Grok Bot, never inferred by an agent.

## 8. Models and cost (v1: single vendor, Anthropic, one API key)
**All model names and prices below are as seen on 2026-11-24 and must be verified against the official pricing pages
at A8 before any paid call** (platform.claude.com/docs/en/about-claude/pricing; Anthropic rate card effective
2026-11-09). Prices = list, USD per 1M tokens, input / output.

### 8.1 Roles
| role | model | why | price (to verify at A8) |
|---|---|---|---|
| writer (outline, script, revise, kit params) | **Claude Opus 5.5** | strongest writing + structured JSON in the family | $4 / $20 (batch $2 / $10; cache hit $0.20) |
| critic | **Claude Opus 5.5 with a separate critic prompt** in a fresh context (never sees the writer's prompt or reasoning; sees facts, sources, registry, rubric) | same quality bar as the writer; independence comes from prompt, context and the deterministic gates | $4 / $20 |
| second critic sample / cheap re-score | Claude Sonnet 5.5 (different model) | a different model as the second rubric sample, halves its cost | $2 / $10 |
| research reading, claim extraction, independence notes | Claude Sonnet 5.5 | long-context reading at half Opus price | $2 / $10 |
| bulk classification (reading-level rewrites, keyword tagging) | Claude Haiku 5.5 | very cheap | $0.10 / $0.50 (prompts ≤ 100K) |
| search / fetch | Claude web search (`allowed_domains`) / web fetch | allowlist enforcement, citations | $10 per 1,000 searches; fetch: tokens only |
One key: `ANTHROPIC_API_KEY` (env or gitignored `.env` via python-dotenv, never logged — same pattern as ElevenLabs).
Optional later step (A12): a cross-vendor critic (e.g. Google Gemini or OpenAI flagship) behind the same provider
interface, only if A8/A9 show critic blind spots; needs a second key and a new spend yes.

### 8.2 Token assumptions per episode (estimate)
| stage | model | input tok | output tok | other | est. USD |
|---|---|---|---|---|---|
| plan + research questions | Opus 5.5 | 15k | 3k | – | 0.12 |
| search + read sources | Sonnet 5.5 | 150k | 10k | 25 searches | 0.65 |
| claim extraction + independence notes | Sonnet 5.5 | 80k | 12k | – | 0.28 |
| outline | Opus 5.5 | 30k | 4k | – | 0.20 |
| script (8–9 scenes, ~18k-token JSON) | Opus 5.5 | 45k | 18k | – | 0.54 |
| visual binding + kit params | Opus 5.5 | 30k | 6k | – | 0.24 |
| critique round 1 (Opus sample + Sonnet sample) | Opus + Sonnet | 55k + 55k | 8k + 8k | – | 0.57 |
| revise × 2 | Opus 5.5 | 2 × 55k | 2 × 18k | – | 1.16 |
| critique round 2 (Opus + Sonnet) | Opus + Sonnet | 55k + 55k | 8k + 8k | – | 0.57 |
| gate-error fix pass | Opus 5.5 | 40k | 8k | – | 0.32 |
| **total (one clean run)** | | ~720k | ~130k | 25 searches | **≈ $4.65** |
Range: **$3 (prompt caching on the shared registry/catalogue/episode-1 context) – $6.5 (extra retries)**; typical
with caching **≈ $4**. A rework after R2 (outline and facts unchanged, script onward) ≈ $2–3.5. Batch API
(−50 %) is possible because authoring is not interactive, at the cost of hours of latency. Revision 1's cross-vendor
estimate ($3.9) is replaced by this; the extra ≈ $0.75 is the second critic sample and the kit-binding stage.

### 8.3 TTS (existing, for context)
≈ 1 ElevenLabs credit per character with `eleven_v4` on the Creator plan (ADR-026): episode 1 = 3,672 dialogue chars
≈ **3,850 credits** with intro lines (≈ 3 % of 131k monthly credits, ≈ $0.65 of the $22 plan pro rata). The content-
hash cache makes re-renders with unchanged lines free; S2 shows credits for new/changed lines only.

### 8.4 Cost controls
`trace.jsonl` per call priced from a versioned `authoring/prices.yaml` (updated at A8 from the official page);
pre-call budget check vs `budgetUsd` (default $8) and per-stage caps; hard stop + report on overrun; monthly cap
`ROBOTICS101_AUTHORING_MAX_USD_MONTH`; ≤ 2 retries per stage.

## 9. Offline / fixture testing
- Provider interface `authoring/llm.py`: `LLMProvider.complete(prompt_id, prompt_version, messages, schema) -> Result`;
  `FixtureProvider` (default), `RecordingProvider` (wraps a real one, writes fixtures), `AnthropicProvider` (opt-in,
  lazy import); room for a second vendor later.
- Fixtures keyed by SHA-256 of (prompt id, prompt version, model, normalised messages, schema) →
  `tests/fixtures/authoring/<key>.json`; a missing fixture in fixture mode is an error naming the key. Search/fetch
  fixtures are stored page texts with their hashes (also exercising the §3.3 independence checks).
- Deterministic mode: temperature 0 where supported, sorted JSON, stable ids (`c-01` …), no wall-clock in artifacts.
- No network in tests: conftest blocks sockets and SDK clients (as the voice tests block ElevenLabs and point
  `ROBOTICS101_DOTENV` at a missing file); an AST test forbids network imports outside provider modules.
- Golden specs: `tests/golden/authoring/<topicId>/episode.source.json` for the episode-1 topic and ep-002; fixture
  run → byte-identical spec + report; every golden passes `validate --strict`, all gates, and `expand_episode`
  idempotence. Kit primitives get golden frames like the existing model sheets.
- Malformed-output tests: truncated JSON, unknown template/visual/kit primitive/sfx, bad kit params or unresolved
  `$param`, Nib speaking, number not in parameters or canon, fabricated citation, syndicated "second source",
  unverified claim in dialogue, caption overflow, missing hook callback / chant, 12 s without a visual change, low
  fun score, over-budget trace → each yields the right error and no partial spec.
- Live tests only behind `ROBOTICS101_AUTHORING_LIVE=1` and an owner-approved budget.

## 10. Milestones — authoring track A1–A12
Each milestone: tests + QA evidence + doc/ADR, committed to `feature/pipeline-impl`. Named A* so they do not collide
with M03–M05 (feedback rounds) or the roadmap's M06 YouTube upload. Renumbered in revision 2 (old A6 paid recording →
A8; old A7 first episode → A9; the kit is new A5–A6, before both).
| id | scope | verification | paid? |
|---|---|---|---|
| **A1** | Contracts: request/facts/outline/bindings/gaps/trace schemas, review packets + approval checker (3 reviews), `curriculum/sequence.yaml` (ep-002…004 + backlog) and `canon.json` (from ep-001), `authoring catalog` + capability cards for the 9 templates | schema + snapshot + card↔code tests | no |
| **A2** | Anthropic-only provider interface, fixture/recording providers, prompt registry with versions, trace, budget guard, socket block | unit tests incl. budget stop, missing-fixture error | no |
| **A3** | Deterministic gates: numbers/canon, independence checks (§3.3), reading level, timing, caption + layout dry run, **engagement gate** (§6.2) calibrated on episode 1; screenplay view | episode-1 baseline passes; broken variants fail each check | no |
| **A4** | Visual-gap report + `visual_gap` placeholder + QA `authoring.visual_gaps` + publish blocker | placeholder golden frame, QA tests | no |
| **A5** | Visual kit part 1: schema `kit` field (ADR-030) + per-primitive schemas + `labeled_parts`, `flow`, `steps`, `compare` | golden frames, caption-band/area/animated QA on a kit demo spec | no |
| **A6** | Visual kit part 2: `beam`, `meter` (incl. graph), `track_map` with presets; **coverage report** of ep-002…004 `expectedVisuals` vs catalogue (target ≥ 80 %) | golden frames, QA, coverage report committed | no |
| **A7** | End-to-end fixture mode with hand-written fixtures (episode-1 topic): plan → … → binding (incl. kit) → critic rubric → gates → golden spec | golden + malformed-output tests | no |
| **A8** | Record real fixtures for ep-002 `distance_with_light` (verify model names/prices first; update `prices.yaml`); owner R1 and R2; calibrate rubric thresholds | trace cost vs estimate; reviews recorded | **yes: S1, one `ANTHROPIC_API_KEY`, cap ≈ $15** |
| **A9** | First authored episode ep-002 draft render with Kokoro (no credits) | full cartoon QA incl. `engagement.*`, gap list | no |
| **A10** | Visuals for remaining gaps (per-visual milestones; e.g. articulated arm/gripper rig before ep-004) | existing visual QA + goldens | no |
| **A11** | ElevenLabs voicing of ep-002 after S2, final render, R3 `approval.json`; canon updated | existing gates | **yes: S2, ≈ 3,850 credits** |
| **A12** | Optional: cross-vendor critic | A/B on recorded episodes | **yes: second key + S1** |

## 11. Risks and mitigations
| risk | mitigation |
|---|---|
| Hallucinated facts or citations | fetched-only citations, excerpt-presence check, independence rules §3.3, numeric checks vs claims/parameters/canon, unverified lines removed, R1 fact review |
| Correlated blind spots (same vendor writes and critiques) | separate critic prompt + fresh context + second model sample; accuracy rests mainly on deterministic gates and sources, not the critic; optional cross-vendor critic A12 |
| Simplification that becomes false | §3.5 rules; `true_as_stated` per teaching line; teaching lines mapped to claims |
| Boring but correct episodes | blocking engagement gate (§6.2) + fun/engagement rubric ≥ 4 (§6.3), calibrated on episode 1 |
| Age-inappropriate content | made-for-kids hard lint + topic deny list + critic + R2 read-through |
| Copyright | n-gram overlap check of dialogue vs fetched pages (no run > 8 words); no third-party characters/logos; all visuals in-repo code; sources in the description |
| Visual gaps / topics bent to old templates | parametric kit (≈ 83 % coverage on the first three topics), misfit rule, placeholders block R3, gaps planned from `expectedVisuals` |
| Kit looks generic or samey | per-primitive style presets, character presence in solo shots, owner review of A5/A6 goldens; vary primitives (rubric "variety") |
| Episodes not building on each other / contradictions | curriculum sequence + canon checks + recap rules |
| Cost overruns | per-run/stage/month caps, trace, bounded retries, fixture default, prompt caching, batch API |
| Drift from character voice | registry-driven prompts, episode-1 few-shot, voice rubric, line-share limits, R2 |
| Model/price churn | verify at A8, provider interface, prompt+model ids in trace and fixture keys |
| Prompt injection from web pages | fetched text is untrusted data, never executed; tools limited to allowlisted search/fetch; schema-validated outputs; no stage can render/voice/publish |
| Schema pressure | claim mapping and gag tags stay outside the spec; `kit` is the only additive field (ADR-030); further changes need a new ADR |

## 12. Decisions needed from the owner
1. Approve v1 single-vendor line-up: Opus 5.5 writer, Opus 5.5 critic (separate prompt) + Sonnet 5.5 second sample,
   Sonnet/Haiku for research (names/prices verified at A8).
2. Provide **one** `ANTHROPIC_API_KEY` when A8 starts, and the S1 yes for its ≈ $15 cap.
3. Per-episode cap (default $8) and monthly authoring cap.
4. Engagement thresholds (§6.2) and rubric thresholds (§6.3) as proposed, or adjust.
5. Topic order ep-002 light → ep-003 line following → ep-004 arms/grippers, and the backlog order.
6. Age band default (6–9 vs 9–12) and reading-level targets.
7. Source allowlist and publisher groups (§3.1).
8. Kit scope: all 7 primitives before ep-002 (A5–A6), or ship A5 first and start A7/A8 in parallel with A6.
