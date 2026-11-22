# Plan: Robotics 101 as a Saturday-morning cartoon (M02 cartoon track)

Status: **PLAN ONLY** (2026-11-22). Nothing below is built yet except throwaway concept frames
(`docs/concept/`). Owner decisions needed are listed in §10. No paid/online service is used until the owner approves one.

## 1. Goal
Turn the M01 "animated diagram" pipeline into a **kids' cartoon that teaches robotics**: recurring, lovable
characters with consistent designs; colourful illustrated sets; bouncy squash-and-stretch motion; eye/mouth
expressions and lip-flap tied to the dialogue; jokes and a small story per episode; a distinct voice per
character; music and SFX ducked under dialogue. Keep everything M01 already guarantees: schema validation,
deterministic renders, QA gates, SHA-256 manifest, captions, publish only via approval bound to the video hash.

## 2. Art & rendering approach — decision: **Manim + code-built vector character rigs**
Feasibility checked on this box (8 CPUs, 15 GB RAM, no GPU; Manim 0.22.1, Blender 4.3.2, cairo/pango, many
Google Fonts incl. Fredoka, Baloo 2, Luckiest Guy, Bangers, Comic Neue, Nunito):

| Option | Look | Speed (measured / est.) | Determinism | Verdict |
|---|---|---|---|---|
| **Manim (cairo) + parametric vector rigs in Python** | flat, bold-outline cartoon (see concept frames) | **6 s of 1080p30 with 2 animated characters + set rendered in ~6 s wall** (≈ real time per process; scenes run in parallel → whole episode ≈ 2–3 min) | yes (pure code, no randomness unless seeded) | **Chosen.** Already integrated (job JSON, frame-exact durations, frame-bounds check, Text without LaTeX); squash/stretch, blink, expressions, mouth shapes = transforms/swaps on vector parts. |
| SVG asset library (artist- or AI-drawn) loaded via `SVGMobject` | richer hand-drawn look | similar | yes | **Later upgrade path**: same rig API, parts swapped for SVG files (needs an artist or approved image generation + licence record). |
| Blender Grease Pencil / toon shader | 2.5D, can look great | slow on CPU (M01: 6 min per 45 s Workbench; toon/EEVEE 5–10× slower) | yes | Not for characters. Keep the M01 Blender scene only as an optional "robot-cam" insert; the obstacle demo gets redrawn in 2D so the style is consistent. |
| Custom pycairo/skia frame renderer | same as Manim | faster | yes | Not worth a second renderer now; revisit if Manim becomes the bottleneck. |

Character rigs are Python classes (one per character) built from primitives (rounded rects, circles, Béziers)
with named parts (body, eyes, pupils, brows, mouth, arms, antenna…), a fixed palette and outline weight, and a
small API: `pose(name)`, `expression(name)`, `mouth(shape)`, `blink(t)`, `look_at(point)`, `squash(k)`,
`hop()`, `talk(cues)`. Designs live in **one registry**, so every episode reuses identical characters.

Lip-flap: **Rhubarb Lip Sync** (MIT, offline; verified here: v1.14 Linux binary analysed a 5 s line in 0.9 s)
turns each dialogue WAV into mouth-shape cues (A–H, X) → rig mouth shapes per frame. Fallback without Rhubarb:
per-frame RMS of the WAV → 3 mouth-open levels.

## 3. Characters (registry `characters/registry.json`, reused every episode)
| id | Name | Look | Personality (one-liner) | Voice idea |
|---|---|---|---|---|
| `bolt` | **Bolt** (hero) | teal rounded robot, dark screen-face with green LED eyes/mouth, antenna bulb that lights up when he *thinks*, orange belly panel, yellow-wheeled tread base, noodle arms | eager, over-confident learner who rushes in, bonks into things, and learns the rule by the end | Kokoro `am_puck` + light robot FX (pitch up, chorus/tremolo) |
| `maya` | **Maya** (kid inventor) | 9-year-old girl, brown skin, two curly hair puffs, purple-strap goggles on her head, yellow hoodie, tool belt, red sneakers | patient, clever, funny big-sister energy; explains with experiments, not lectures | Kokoro `af_bella` (alt `af_heart`) |
| `nib` | **Nib** (sidekick) | tiny pink bird-drone, one big eye, propeller hat, stubby wings | curious, mischievous; never talks, only beeps/whistles (SFX) — physical comedy and "measuring stick" for distance gags | SFX only (synthesised beeps) |

Registry fields: id, displayName, role, palette (hex), outline width, rig class, allowed expressions
(`happy, surprised, worried, proud, sleepy, dizzy, thinking`), poses, voice (provider, voiceId, speed, fx chain,
espeak fallback voice), caption colour, personality notes for writers/LLM (M03 authoring). The registry file's
SHA-256 goes into the manifest; QA fails if an episode references an unknown character or expression.

## 4. Schema changes (episode v1.1, backward compatible with v1.0)
- Episode: `characters: ["bolt","maya","nib"]`, `set: "garage"`, `music: {theme, stings}`.
- Scene: keep `template` (now cartoon templates), add `beats: [...]` replacing the single `narration` string:
  `{"type":"line","speaker":"maya","text":"…","emotion":"grin","action":"point:ruler"}`,
  `{"type":"sfx","id":"bonk","at":"after:prev"}`, `{"type":"action","who":"bolt","do":"hop"}`,
  `{"type":"pause","seconds":0.6}`. Scene duration = sum of beat timings (dialogue-driven, no padding holds).
- `narration` (v1.0) still accepted → converted to a single narrator line (keeps M01 fixtures/tests valid).
- Teaching parameters stay explicit (`thresholdMeters: 0.5`, `rangeMeters: 3`, …) and a lint checks that numbers
  spoken in dialogue match them.

## 5. Episode 001 rewrite — "Bolt Bumps Into Everything" (concepts unchanged: what a robot is, parts, sensors, sense–think–act, 0.5 m stop-and-turn)
Target ≈ 5:00, ≈ 600–650 words of dialogue + gags; no silent hold longer than ~2.5 s.

| # | ~Time | Beat | Teaching point | Jokes / gags |
|---|---|---|---|---|
| 1 | 0:00–0:25 | **Cold open.** Bolt zooms across the garage — *BONK* — into the box pile. Stars circle his antenna. | (hook) | Bolt: "Ow! Who put a wall there?" Maya: "Bolt… that box has been there since Tuesday." Nib lands on the box, beeps, falls off. Theme sting + title card "ROBOTICS 101". |
| 2 | 0:25–1:05 | **"Am I even a robot?"** Bolt panics. Maya: a robot **senses, thinks, acts**. Bolt's "family album": robot vacuum, factory arm, Mars-style rover. | definition + examples | Bolt insists the toaster is his cousin ("it senses bread!"); Maya: "It doesn't decide anything… it just burns things." Toaster pops, Bolt flinches. |
| 3 | 1:05–1:50 | **Robot check-up.** Maya with a toy stethoscope: structure, sensors, actuators, power, controller — each part glows on Bolt. | five parts | Bolt flexes "my structure"; battery check makes him go sleepy-eyed and yawn mid-sentence; Maya plugs him in: "Better?" "…I can see sounds." |
| 4 | 1:50–2:40 | **Sensors.** Bolt's ultrasonic sensor "pings" like a bat; Nib flies away until the echo says **1.2 m**; range bubble shows **3 m**. | distance sensor, range | Nib keeps flying further to "help" until he's out of range (3 m) — "Nib? NIB?" — Nib peeks back in. |
| 5 | 2:40–3:30 | **The rule.** Maya chalks *if distance < 0.5 m: stop & turn*. Bolt practises: readings 1.5 → 1.0 → 0.6 → 0.4 m, antenna lights up on "think", STOP. | sense–think–act loop, threshold | Bolt over-brakes with a cartoon skid and screech; first try he stops for a sock at 3 m ("…it looked dangerous"). |
| 6 | 3:30–4:05 | **Actuators.** Motors turn decisions into motion: wheels roll, Bolt's arm servo rotates **0° → 60°** for a high-five. | actuators, servo angle | Bolt misses the high-five at 30°, nails it at 60°; Nib gets a "high-one". |
| 7 | 4:05–4:40 | **Problem solved.** Rematch with the box pile: drive → sense 0.49 m → stop → turn → resume. Victory dance. | full loop applied | Bolt stops perfectly… then celebrates by spinning into the door — Maya: "The rule only works if your sensor is facing forward!" |
| 8 | 4:40–5:00 | **Recap & quiz.** Sense! Think! Act! (3-beat chant with stings). Question: "Which part of the robot measures distance?" Sign-off. | recap + question | Nib beeps the answer before anyone else; Bolt: "Show-off." |

All numbers on screen match the parameters (3 m range, 1.2 m obstacle, 0.5 m threshold, 60° servo). The script
is hand-written for episode 1 (M02.1); LLM authoring of future scripts stays a later milestone, with fixture mode.

## 6. Voices / TTS
Each character gets its own voice from the registry; espeak-ng stays the offline fallback (and the CI/test provider).
Checked on this box (CPU only):

| Option | Licence | Quality / expressiveness | Cost | Runs here? |
|---|---|---|---|---|
| **Kokoro-82M** (`kokoro-onnx`) | Apache-2.0 (weights + code) | natural, clear; 54 voices (≈20 US-English), speed control; no emotion tags | free, offline | **Yes — tested**: installed in a side venv, model 310 MB + voices 28 MB, **RTF ≈ 0.15** (5 s line in 0.7 s) |
| Piper (`piper-tts` 1.8) | code GPL-3.0 (piper1-gpl); voices vary per model card (e.g. LibriTTS-R CC BY 4.0; some voices restricted) | good, many multi-speaker voices, less expressive than Kokoro | free, offline | **Yes — tested**: installs, voices 60–120 MB, faster than real time. Use as a subprocess only (GPL). |
| Chatterbox / Chatterbox-Nano (Resemble AI) | MIT; **retired/unmaintained since Aug 2026** | most expressive local option (emotion "exaggeration", [laugh] tags, voice cloning from a reference clip) | free, offline | Not tested (PyTorch ≈ 2 GB). Nano claims ~3× real time on 8 CPUs. Unmaintained → risky. |
| Coqui XTTS-v2 | **Coqui Public Model Licence: non-commercial** | expressive, cloning | free | Possible but slow on CPU; **excluded** for a monetisable channel |
| F5-TTS / other research models | weights often CC-BY-NC | good | free | excluded (NC) |
| **ElevenLabs** (online, paid) | commercial use from Starter plan | best character/emotion range, voice design for cartoon voices, also SFX/music | Starter $6/mo (30k credits ≈ 30 min speech); Creator $22/mo (121k). One episode ≈ 5–6k characters ≈ 5–6k credits | online — **needs approval + API key** |
| OpenAI TTS (`gpt-4o-mini-tts`) / Azure Neural TTS / Google TTS (online, paid) | commercial | very good; OpenAI takes style instructions, Azure has SSML styles (fits M04 Azure plan) | cents per episode | online — **needs approval + key** |

**Recommendation:** build the per-character voice layer on **Kokoro** (offline, Apache-2.0, fast here) with
espeak-ng as fallback; give Bolt a light deterministic robot FX chain (sox). If the owner wants more acting
range later, add **ElevenLabs** (or Azure) as an opt-in provider behind the same interface — only after approval.
Audio samples for comparison: `/workspace/robotics101-samples/concept-voices-kokoro.wav` and
`concept-voices-compare-espeak-piper-kokoro.wav` (espeak → Piper → Kokoro → Kokoro+robot FX, same line).

Determinism: per-line WAVs cached by SHA-256 of (text, voice, speed, FX chain, model file hash); manifest records
model/voice hashes; QA re-synthesises one line and compares hashes.

## 7. Music & SFX
- **Theme + stings: generated in-repo** (deterministic Python/numpy synth — bouncy ukulele/chiptune-style loop,
  title sting, "idea!" ding, recap chant beat). Zero licence risk, fully reproducible. (AI music generators are
  avoided by default: MusicGen weights are CC-BY-NC; online ones need approval.)
- **SFX:** synthesised where easy (beeps, boings, pings, whooshes, skid) + a vendored **CC0** pack (Kenney.nl
  audio packs) for bonks/pops/clicks. Every asset listed in `assets/LICENSES.json` (source URL, licence, SHA-256).
- **Mix:** dialogue at −16 LUFS; music bed ≈ −30 LUFS, **ducked by ~12 dB under dialogue** using a deterministic gain
  envelope computed from the dialogue timeline (not an adaptive compressor); SFX placed by beat timings; limiter
  at −1.5 dBFS. Stems (dialogue/music/SFX) kept for QA.

## 8. QA additions (on top of M01's gates)
| Check | Rule | Severity |
|---|---|---|
| Dialogue coverage | dialogue + SFX activity ≥ 70 % of each scene | hard (pilot), soft (fixtures) |
| Max silent gap | no gap without dialogue/SFX > 2.5 s (music-only "beats" ≤ 4 s if tagged) | hard |
| Character presence | the speaker is on screen (bbox inside frame, not occluded) for ≥ 95 % of their line's frames — from a per-frame character track the renderer writes | hard |
| Lip-sync | mouth open only while that character's audio is active (≥ 90 % frame agreement); closed in silence | soft→hard after tuning |
| Character consistency | registry SHA-256 + rig version in manifest; model-sheet golden images match | hard |
| Voice identity | each line used the registry voice for its speaker; distinct voices per speaking character | hard |
| Mix | dialogue −16 ± 2 LUFS; music ≥ 12 dB under dialogue during lines; no clipping | hard |
| Asset licences | every music/SFX/font/model/voice asset has an allowed licence (CC0, MIT, Apache-2.0, OFL, CC-BY with attribution in description); NC/unknown → fail | hard |
| Captions | speaker-labelled, ≤ 15 chars/s reading speed, inside safe area | soft |
| Teaching facts | numbers in dialogue match scene parameters (0.5 m, 3 m, 1.2 m, 60°) | hard |
| Existing | codec/resolution/fps/duration/A-V sync/manifest/thumbnail | unchanged |

## 9. Milestones (cartoon track, each small and verified: tests + render + frames + audio, then commit/push)
- **M02.1** Character registry + schema v1.1 (beats/dialogue) + v1.0 compatibility + `examples/episode-001-cartoon.json` script; validator + teaching-facts lint. No rendering.
- **M02.2** Voice layer: per-character provider config, Kokoro provider (after approval; espeak path works without it), Bolt FX chain, line cache, dialogue timeline (`timing.json` v2), speaker-labelled SRT; dialogue-coverage/gap QA.
- **M02.3** Character rigs: Bolt, Maya, Nib with expressions, blink, poses; model sheet PNG + golden-image tests.
- **M02.4** Motion: squash/stretch, hop/roll/idle cycles, gestures, gaze, Rhubarb lip-flap (+ RMS fallback); 15 s test clip reviewed frame-by-frame.
- **M02.5** Sets & props: garage set, chalkboard, ruler, sensor ping, servo high-five, 2D obstacle demo (replaces Blender for this episode); speech bubbles / SFX lettering.
- **M02.6** Scene engine: beats → staging (entrances, who faces whom, camera push-ins), character tracks; render all 8 scenes video-only.
- **M02.7** Music & SFX: generated theme/stings, CC0 SFX + licence manifest, ducked mix, stems; mix/licence QA.
- **M02.8** Full episode at 1080p: frame-by-frame + listening review, all new QA gates, character thumbnail, publish plan with made-for-kids setting; owner review.
- Then the original roadmap resumes (renumbered): AI script authoring in fixture mode, render sandbox, Azure orchestration, review dashboard (writes `approval.json`), real YouTube private upload.

## 10. Decisions needed from the owner
1. **Look:** OK with the concept style (`concept-cast.png`, `concept-gag-bonk.png`)? Any changes to names/designs (Bolt, Maya, Nib)?
2. **TTS:** approve **Kokoro (offline, free, Apache-2.0)** as the default character voice engine (downloads a 310 MB model)? Or approve a paid online voice (ElevenLabs Starter $6/mo, or Azure/OpenAI pay-per-use) for more expressive acting — needs an account/API key from the owner.
3. **YouTube "made for kids":** if the audience is children under 13 the channel must mark videos *made for kids* (COPPA): no comments, no personalised ads, no notifications/mini-player features. Choose *made for kids* vs *general audience (beginners of all ages)* — this also steers tone and the script.
4. **Music:** generated-in-repo theme (recommended, zero licence risk) vs. licensed/stock music.
5. **Scope of episode 1 rewrite:** OK to replace the M01 Blender scene with a 2D cartoon demo for consistency?
