# Product requirements (PRD)

## Product and audience
Channel: Robotics 101. Audience: curious absolute beginners with no coding, engineering or robotics prerequisites. Episodes: 5 minutes target, 16:9, 1080p, 30fps, voiceover and captions. Tone: clear, technically correct, engaging, non-sensational.

## Core user journey
1. Reviewer approves topic/curriculum order or selects an episode manually.
2. Pipeline produces source-backed educational brief and 600–700-word first-pass script; actual voice timing determines pacing.
3. Storyboard produces 8–15 scenes with ordered narration, visual purpose, engine, parameters and expected checks.
4. Renderers produce deterministic 2D Manim and 3D Blender clips in isolated jobs; TTS emits per-scene audio and timings.
5. Composer assembles a single MP4 with transitions and synchronized subtitles; QA blocks invalid outputs.
6. Reviewer previews the draft and requests regeneration of scenes or script. Only affected descendants are invalidated.
7. Reviewer approves exact final MP4 hash. Publication workflow creates a private YouTube upload and only schedules/publishes under explicit approval policy.

## P0 functional requirements
- FR-01: Create/version episode and scene specifications against JSON Schema.
- FR-02: Generate/source-check a brief, narration and visual storyboard with provenance records.
- FR-03: Render deterministic 2D template scenes and at least one reusable 3D robot rig.
- FR-04: Generate narration using pluggable TTS; align captions and scenes to actual duration.
- FR-05: Compose final H.264/AAC MP4 plus SRT and thumbnail/metadata.
- FR-06: Validate formulas/invariants, code/renderer, duration, media decodability, audio and captions.
- FR-07: Persist immutable artifacts and manifest with checksums; retry failed scenes idempotently.
- FR-08: Show review dashboard; provide approve, reject, and scene revision actions.
- FR-09: Enforce final-video hash approval before any publication state change.
- FR-10: Emit cost, latency and error metrics per scene/stage.

## Non-functional requirements
- Security: generated code is untrusted; run in locked-down containers, zero production credentials.
- Reliability: retry transient jobs with backoff; dead-letter permanent failures; no duplicate published videos.
- Maintainability: contracts and templates versioned; no monolithic multi-agent prompt.
- Modularity: provider interfaces for LLM, TTS, storage and publisher.
- Cost: spend limits per episode and month; reuse cached successful assets.
- Observability: correlation IDs and stage-level logs; reviewer sees reason for failed jobs.

## MVP objective / acceptance
- Produce 3 distinct 270–330-second beginner episodes, with aligned SRT and technically useful 2D + 3D visuals.
- 95%+ scene render success after bounded retries is the operating target, not a guarantee.
- Review requires <=30 minutes per episode **as an evaluation target**.
- Human approval cannot be bypassed; successful QA is necessary, not sufficient.
- Selective scene regeneration avoids rerunning unchanged scenes.

## Exclusions
No auto-publication, ROS/Gazebo physics, multilingual dubbing, audience-driven A/B optimization, Shorts pipeline, generative video as primary animation source, fully featured timeline editor or AKS in MVP.

## Pilot content
Episode 1: What Is a Robot? Sequence: definition; sensors; controller; actuators; obstacle-avoidance 3D demo; recap. Do not show physically inaccurate effects to illustrate the robot loop.

## Editorial guidelines
- Every episode begins with a concrete, relatable example.
- Introduce new vocabulary only after showing an example.
- Avoid claiming that all robots are humanoids or that all autonomous systems necessarily use AI.
- Keep formulas correct with units and coordinate assumptions when used.
- Avoid fabricated research sources and unsupported claims; require reviewer attention for unresolved assertions.
