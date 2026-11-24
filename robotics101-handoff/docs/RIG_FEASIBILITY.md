# Rig feasibility note (M05.3): how far the Manim vector rig can go toward "Cocomelon-level" acting

## What the current rig does now (implemented, pipeline default)
The characters are pure-Python vector rigs (`cartoon/rigs.py`, `Pose -> VGroup`, rig v2), animated
analytically per frame (`cartoon/motion.py`), so any frame renders independently (parallel chunks, exact
re-renders). M05.3 added, for every episode:

| Feedback item | Status in the Manim rig |
|---|---|
| Squash & stretch | yes: area-preserving squash on the ground pivot; anticipation squash → stretched take-off → landing squash on every hop/pose |
| Bouncy walks / hops | yes: Maya's walk has leg swing from the hip + bounce; Bolt's wheels turn with distance; `excited` = double hop, `surprised` = jump-back |
| Head tilts | yes: `Pose.head_tilt` (Maya's head on the neck, Bolt's upper body on the treads, Nib's body); listeners tilt toward the speaker, questions → `curious` |
| Expressive brows / mouth shapes | yes: Maya brows raise/angle per pose and pop on open vowels; Bolt gets LED brows for strong feelings; Rhubarb mouth shapes unchanged |
| Emotion poses | yes: library `cartoon/acting.py` (surprised, giggle, proud, excited, thinking, worried, curious, nod, talk_bounce, celebrate) |
| Secondary motion | yes: Bolt's antenna and Nib's mast lag sideways motion / lean (damped follow-through), Maya's hair puffs bounce with vertical motion. Maya has no scarf in her model sheet, so none was added |
| Reactions while others talk | yes: listener nods/sway/tilt (M03.3) + reaction poses (giggle back, small surprise, nod) |
| Dance / celebration beats | yes: victory/chant/title stings and sparkle/ding/clap make characters `celebrate` |
| Script control | per-line `pose` / `react` cues in the 1.1 schema with automatic defaults from `emotion` + text |
| QA | `characters.acting`: motion energy per character per scene, still share ≤ 30 %, ≥ 3 distinct emotion poses per speaker |

Measured on ep1 (same timing): mean key-point speed per character went from ~65–115 px/s (M03.6 rig) to
~110–250 px/s.

## Where the Manim rig hits its limits
* **Rigid parts.** Limbs are single Bézier "noodles" and the head/torso are rigid shapes. There are no
  elbows/knees, no hand poses (open/fist/point), no overlapping deformation (cheeks squishing when smiling,
  belly jiggle). Cocomelon-style acting relies heavily on hands and on soft, mesh-like deformation.
* **No turnarounds.** Characters only face left/right (mirror). 3/4 views, turning heads, looking at camera
  require drawing extra views per part.
* **Hand-tuned curves.** Poses are code functions; an animator cannot scrub/edit them visually. Iteration speed
  for nuanced acting is the real bottleneck, not rendering.
* **Cost.** Manim rebuilds every vector each frame (≈ 2–4 frames/s/core at 1080p); fine for ~6 min episodes.

## Options for a bigger step
| Option | What it gives | Effort / risks | Fit |
|---|---|---|---|
| A. Richer pose library in the current rig (bendy limbs with elbows/knees, hand shapes, 3/4 head view, more mouth shapes) | Keeps the pipeline, determinism and QA; incremental | 2–4 weeks for a solid set; still code-authored poses; quality ceiling stays "simple flash cartoon" | Best short-term (next milestone) |
| B. Cut-out / bone rig in Python (2D skeleton + skinned meshes, e.g. our own small deformer over Pillow/Skia/cairo or `pyglet`), poses as keyframe data | Real bone hierarchy, mesh deformation (squishy faces), pose blending, IK for feet/hands | 4–8 weeks to build + art re-cut into layered parts; we own the tool | Good long-term if we stay all-Python |
| C. Spine / Live2D-style rig (Spine runtime, or DragonBones) | Industry-standard 2D skeletal + mesh deformation, animator-friendly editor, animation blending/tracks | Spine editor licence; runtime is C/C++/JS — needs a headless renderer (e.g. spine-c + Skia, or a headless browser) in the render worker; art must be redrawn as layered PSD | Highest quality per effort for 2D cut-out acting |
| D. Rive or Lottie (After Effects/Bodymovin) | State machines (Rive), vector bones, easy designer workflow, small files | Rendering headless needs rive-cpp/Skia or a browser (rlottie for Lottie); Lottie has no runtime blending; character art re-authored | Good for UI-like motion; less for long lip-synced dialogue |
| E. Blender Grease Pencil (2D in 3D, armatures, already have Blender in the pipeline) | Bones + deform on 2D strokes, cameras, lighting, line art; Python-scriptable; same tool as the robot-cam | Slower renders than Manim; needs redrawing characters as GP objects; rig authoring skill | Strong option: reuses Blender + Python, deterministic headless renders |
| F. Full 3D toon-shaded characters (Blender EEVEE + toon shader) | Turnarounds, camera moves, richest acting, closest to Cocomelon's actual look | Biggest change: modelling/rigging/animation per character, much slower renders, GPU workers | Only if the series becomes a long-running production |

**Recommendation.** Ship option A next (hands, elbows/knees, 3/4 head, more brow/mouth sets) because it is cheap
and keeps every QA gate. In parallel, prototype option E (Grease Pencil) or C (Spine) with one character and one
scene (e.g. scene-002) and compare acting quality, render cost and authoring time before committing.
