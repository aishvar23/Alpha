# Versioned AI-agent contracts

Each logical agent receives `{episodeId, episodeVersion, inputArtifactIds, schemaVersion, promptVersion, audience:'beginner', durationTargetSeconds:300, brandStyle, budget}` and emits `{status, outputArtifactId, validationReport, provenance, usage, errors}`. Prefer tool-free deterministic JSON to free-form chat.

## Planner
Input: curriculum DAG, accepted/finished episodes, desired progression. Output: proposed topic, prerequisites, one learning objective, intended animation types. No fabricated certainty about unexplored topics.

## Researcher
Input: topic. Output: list of factual `claims[{id,text,sourceUrls,sourceNotes,confidence}]`, references, exceptions, terms, unresolved items. All source claims require traceable evidence. If browsing unavailable, mark claims unverified and block technical approval.

## Scriptwriter
Input: verified concept brief; beginner editorial style, 5-min goal. Output: lesson opening, scene-aligned narration text, definitions, examples, quiz, estimated words, source claim IDs. Do not invent sources or advanced math without explanation.

## Technical reviewer
Input: researched claims, script, scene specs. Output: `checks[{claimId,pass,reason}]`, corrections, must-fix, human attention needed. Validate independently using trusted reference calculations; LLM agreement not proof.

## Storyboarder
Input: reviewed script. Output: `EpisodeSpec` matching schema; every scene has educational objective, narration, duration hint, visual parameters, engine, required validation. Reuse known templates first.

## Animator
Input: single validated scene, template registry/version. Output: parameters or isolated Python source file, dependency lock, expected visual checkpoints. Never execute or ask to execute outside sandbox.

## Visual QA
Input: representative sample frames, scene spec, narration. Output: issues linked to frame times, severity, suggested patch; never certify math from video appearance alone.

## Composer/Publisher
Not agents. Deterministic services with explicit inputs and state guards. The publisher must enforce approval hash in application code, never a prompt.

## Example task prompt — storyboard
"Using only the verified claims provided, create a beginner-friendly 5-minute Robotics 101 episode. Output strictly valid EpisodeSpec JSON. Use existing animation templates for robot parts, sensors and control loop, plus one Blender obstacle avoidance demonstration. Mark every unmapped or uncertain claim as requiring reviewer attention. Do not invent URLs." 
