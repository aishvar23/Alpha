"""Episode expansion (M03): pipeline defaults applied to EVERY cartoon episode before voicing.

``expand_episode(spec, registry)`` returns a new spec (the input is not modified) with the generated parts that
the owner wants in every episode:

* **character intro** (M03.1): a ``cartoon_character_intro`` scene built from the character registry (each main
  character's ``intro`` block: entrance, signature action, tagline, a line that says their name). Default on;
  ``spec.intro = {"enabled": false}`` turns it off; ``position`` is ``after_cold_open`` (default: right after a
  ``cartoon_cold_open`` first scene, else first) or ``start``.

* **transitions** (M03.2): every scene after the first gets a resolved ``transitionIn`` (``wipe``, ``iris``,
  ``slide``, ``character`` or an explicit ``cut``). ``auto`` (default) = ``iris`` into the intro, otherwise the
  rotating cycle wipe -> character -> slide -> iris. ``spec.transitions.seconds`` (default 0.8) is split into an
  out-half at the end of the previous scene and an in-half at the start of the next, so scene durations, audio and
  captions are unchanged.
* **concept title cards** (M03.2): each scene ``concepts`` marker gets a ``concept_sting`` music beat inserted before
  beat ``beforeBeat`` (default 0); the scene engine shows the animated card for exactly that beat.

Expansion is idempotent (an already-expanded spec is returned unchanged apart from a fresh copy), so every entry
point (``render``, ``voice``, ``render-cartoon``) can call it. The expanded spec is valid against the 1.1 schema and
is what the bundle stores as ``episode.json``.
"""

from __future__ import annotations

import copy

INTRO_TEMPLATE = "cartoon_character_intro"
INTRO_SCENE_ID = "scene-intro"
INTRO_DEFAULTS = {"enabled": True, "position": "after_cold_open"}
TRANSITION_STYLES = ("wipe", "iris", "slide", "character")
AUTO_CYCLE = ("wipe", "character", "slide", "iris")
TRANSITION_SECONDS = 0.8
CONCEPT_CUE = "concept_sting"


def transition_settings(spec: dict) -> dict:
    return {"default": "auto", "seconds": TRANSITION_SECONDS, **(spec.get("transitions") or {})}


def resolve_transitions(scenes: list[dict], cfg: dict) -> None:
    k = 0
    for i, sc in enumerate(scenes):
        if i == 0:
            sc.pop("transitionIn", None)
            continue
        want = sc.get("transitionIn") or cfg["default"]
        if want == "auto":
            if sc["template"] == INTRO_TEMPLATE:
                want = "iris"
            else:
                want = AUTO_CYCLE[k % len(AUTO_CYCLE)]
                k += 1
        sc["transitionIn"] = want


def insert_concept_stings(sc: dict) -> None:
    concepts = sc.get("concepts") or []
    have = sum(1 for b in sc["beats"] if b["type"] == "music" and b["cue"] == CONCEPT_CUE)
    if not concepts or have >= len(concepts):
        return
    for c in sorted(concepts, key=lambda c: c.get("beforeBeat", 0), reverse=True):
        sc["beats"].insert(min(c.get("beforeBeat", 0), len(sc["beats"])), {"type": "music", "cue": CONCEPT_CUE})


def intro_settings(spec: dict) -> dict:
    return {**INTRO_DEFAULTS, **(spec.get("intro") or {})}


def main_characters(registry, cast: list[str] | None = None) -> list[str]:
    """Registry characters flagged ``main`` (registry order), limited to ``cast`` when given."""
    ids = [cid for cid, c in registry.characters.items() if c.raw.get("main")]
    return [c for c in ids if cast is None or c in cast]


def intro_scene(spec: dict, registry) -> dict:
    cfg = intro_settings(spec)
    who = cfg.get("characters") or main_characters(registry, spec.get("characters"))
    beats: list[dict] = []
    cards = []
    for cid in who:
        ch = registry.get(cid)
        it = ch.raw.get("intro") or {}
        line = it.get("line") or {}
        beats.append({"type": "action", "who": cid, "do": it.get("entrance", "enter")})
        if it.get("entrance") == "zoom":
            beats.append({"type": "sfx", "id": "zoom"})
        elif it.get("entrance") == "fly_to":
            beats.append({"type": "sfx", "id": "nib_whistle", "who": cid})
        lb = {"type": "line", "speaker": line.get("speaker", cid), "text": line["text"], "target": cid}
        if it.get("emotion") and line.get("speaker", cid) == cid:
            lb["emotion"] = it["emotion"]
        if it.get("action") and line.get("speaker", cid) == cid:
            lb["action"] = it["action"]
        beats.append(lb)
        if it.get("action") and line.get("speaker", cid) != cid:
            beats.append({"type": "action", "who": cid, "do": it["action"]})
        if it.get("sfx"):
            beats.append({"type": "sfx", "id": it["sfx"], "who": cid})
        cards.append({"id": cid, "name": ch.displayName, "tagline": it.get("tagline", ch.role),
                      "color": ch.captionColor, "entrance": it.get("entrance", "enter")})
    beats.append({"type": "pause", "seconds": 0.6})
    return {"sceneId": INTRO_SCENE_ID, "sequence": 1, "title": "Meet the crew",
            "educationalObjective": "Meet the recurring characters and their personalities",
            "engine": "cartoon", "template": INTRO_TEMPLATE, "durationTargetSeconds": 6 * max(1, len(who)),
            "parameters": {"characters": cards}, "validation": {"requiredChecks": ["render_success"]},
            "beats": beats, "generated": "intro"}


def expand_episode(spec: dict, registry) -> dict:
    s = copy.deepcopy(spec)
    if s.get("schemaVersion") != "1.1":
        return s
    scenes = s["scenes"]
    cfg = intro_settings(s)
    has_intro = any(x.get("template") == INTRO_TEMPLATE for x in scenes)
    if cfg["enabled"] and not has_intro and main_characters(registry, s.get("characters")):
        at = 1 if (cfg["position"] == "after_cold_open" and scenes
                   and scenes[0]["template"] == "cartoon_cold_open") else 0
        scenes.insert(at, intro_scene(s, registry))
    for i, sc in enumerate(scenes, 1):
        sc["sequence"] = i
        insert_concept_stings(sc)
    resolve_transitions(scenes, transition_settings(s))
    return s


__all__ = ["AUTO_CYCLE", "CONCEPT_CUE", "TRANSITION_STYLES", "transition_settings", "INTRO_SCENE_ID", "INTRO_TEMPLATE", "expand_episode", "intro_scene", "intro_settings", "main_characters"]
