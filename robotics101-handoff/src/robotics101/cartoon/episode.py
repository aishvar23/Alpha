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

* **illustration-first shots** (M05.1): explanatory beats are shown as an ``illustration`` shot (full-bleed teaching
  visual, no characters or one small corner character) or a ``solo`` shot (exactly one character + a wide visual)
  instead of the crowded three-character stage. A scene's ``shots`` list is authored or filled from the per-template
  defaults in ``DEFAULT_SHOTS`` (anchored on beats, so any episode using the template gets them); lines covered by an
  illustration/solo shot are marked ``explain: true``. Generic rule: any line authored with ``explain: true`` that no
  shot covers gets a ``solo`` shot of its speaker with the scene's concept visual. Shot beat indices refer to the
  expanded beat list (they are shifted when concept stings are inserted).

* **section backgrounds** (M05.5, schema 1.2): every section gets its own background. A scene's ``section`` id
  groups consecutive scenes (default: each scene is its own section); ``background`` is ``auto`` (default) or
  ``{theme, palette}``. Auto picks the template's preferred theme (``TEMPLATE_THEMES``), never the previous section's
  theme and preferably one not used yet in the episode; a theme used again gets its next palette. Every scene ends
  up with ``background = {theme, palette, section, auto}`` and the expanded spec is 1.2 (1.1 input is upgraded).
* **card kickers** (M05.5): the small line above a concept card title comes from the concept's ``kicker``, else the
  section's ``kicker``, else the section type's default (``TEMPLATE_KICKERS``); null/empty hides it, and there is
  no global default. A section whose kicker isn't shown on a card gets a short section banner instead.

Expansion is idempotent (an already-expanded spec is returned unchanged apart from a fresh copy), so every entry
point (``render``, ``voice``, ``render-cartoon``) can call it. The expanded spec is valid against the 1.1 schema and
is what the bundle stores as ``episode.json`` (valid against the 1.2 schema).
"""

from __future__ import annotations

import copy

from robotics101.cartoon import BACKGROUND_THEMES, CARTOON_SCHEMA_VERSIONS, LATEST_CARTOON_SCHEMA

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
        at = min(c.get("beforeBeat", 0), len(sc["beats"]))
        sc["beats"].insert(at, {"type": "music", "cue": CONCEPT_CUE})
        for sh in sc.get("shots") or []:            # keep shot ranges on the same beats
            if sh["fromBeat"] >= at:
                sh["fromBeat"] += 1
            if sh["toBeat"] >= at:
                sh["toBeat"] += 1


# ------------------------------------------------------------------------------------------ M05.1 shots

LAYOUTS = ("stage", "illustration", "solo")
EXPLAIN_LAYOUTS = ("illustration", "solo")


def _first(beats: list[dict], pred, start: int = 0) -> int | None:
    return next((i for i in range(start, len(beats)) if pred(beats[i])), None)


def _is_sfx(name: str):
    return lambda b: b["type"] == "sfx" and b.get("id") == name


def _is_line(b: dict) -> bool:
    return b["type"] == "line"


def shots_robot_family(beats: list[dict]) -> list[dict]:
    """The robot families are a full-screen illustration from the album page-flip through the last example line."""
    a = _first(beats, _is_sfx("page_flip"))
    if a is None:
        return []
    end = _first(beats, _is_sfx("sparkle"), a)
    lines = [i for i in range(a, end if end is not None else len(beats)) if _is_line(beats[i])]
    if not lines:
        return []
    return [{"layout": "illustration", "fromBeat": a, "toBeat": lines[-1], "visual": "robot_families"}]


def shots_sensor_ping(beats: list[dict]) -> list[dict]:
    """The echo explanation (first line through the line after the first echo) is a solo of the explainer with a wide
    sound-wave diagram."""
    first = _first(beats, _is_line)
    echo = _first(beats, _is_sfx("echo"))
    if first is None or echo is None:
        return []
    last = _first(beats, _is_line, echo)
    if last is None:
        return []
    who = beats[first]["speaker"]
    return [{"layout": "solo", "fromBeat": first, "toBeat": last, "visual": "echo_diagram", "character": who}]


def shots_rule_board(beats: list[dict]) -> list[dict]:
    """The sense -> think -> act walkthrough line ("Here's how it works ...") is a solo with the STA loop diagram."""
    i = _first(beats, lambda b: _is_line(b) and "how it works" in b["text"].lower())
    if i is None:
        return []
    return [{"layout": "solo", "fromBeat": i, "toBeat": i, "visual": "sense_think_act",
             "character": beats[i]["speaker"]}]


DEFAULT_SHOTS = {"cartoon_robot_family": shots_robot_family, "cartoon_sensor_ping": shots_sensor_ping,
                 "cartoon_rule_board": shots_rule_board}


def plan_shots(sc: dict) -> None:
    """Fill ``sc['shots']`` from the template defaults (unless authored), add generic solo shots for uncovered
    ``explain`` lines, and mark every line inside an illustration/solo shot ``explain: true``."""
    beats = sc["beats"]
    if "shots" not in sc:
        fn = DEFAULT_SHOTS.get(sc.get("template", ""))
        sc["shots"] = fn(beats) if fn else []
    shots = sc["shots"]

    def covered(i: int) -> bool:
        return any(s["layout"] in EXPLAIN_LAYOUTS and s["fromBeat"] <= i <= s["toBeat"] for s in shots)
    icon = next((c.get("icon") for c in sc.get("concepts") or [] if c.get("icon")), "robot")
    for i, b in enumerate(beats):
        if _is_line(b) and b.get("explain") and not covered(i):
            shots.append({"layout": "solo", "fromBeat": i, "toBeat": i, "visual": f"concept_{icon}",
                          "character": b["speaker"], "generated": True})
    shots.sort(key=lambda s: s["fromBeat"])
    for i, b in enumerate(beats):
        if _is_line(b) and covered(i):
            b["explain"] = True
    if not shots:
        sc.pop("shots")


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
            "engine": "cartoon", "template": INTRO_TEMPLATE, "section": "intro", "durationTargetSeconds": 6 * max(1, len(who)),
            "parameters": {"characters": cards}, "validation": {"requiredChecks": ["render_success"]},
            "beats": beats, "generated": "intro"}


# M05.5: preferred background themes per template (first free one wins; unknown templates take any free theme)
TEMPLATE_THEMES = {
    "cartoon_cold_open": ("workshop",),
    INTRO_TEMPLATE: ("studio",),
    "cartoon_robot_family": ("museum",),
    "cartoon_robot_checkup": ("lab_bench",),
    "cartoon_sensor_ping": ("sound_lab", "lab_bench"),
    "cartoon_rule_board": ("control_room", "blueprint"),
    "cartoon_servo_highfive": ("blueprint", "lab_bench"),
    "cartoon_obstacle_rematch": ("test_track",),
    "cartoon_recap_chant": ("quiz_stage", "studio"),
}


def sections(scenes: list[dict]) -> list[list[dict]]:
    """Consecutive scenes grouped by section id (default: the scene's own id)."""
    out: list[list[dict]] = []
    for sc in scenes:
        sid = sc.get("section") or sc["sceneId"]
        if out and (out[-1][0].get("section") or out[-1][0]["sceneId"]) == sid:
            out[-1].append(sc)
        else:
            out.append([sc])
    return out


def _authored(sc: dict) -> tuple[str | None, str | None]:
    bg = sc.get("background")
    if not isinstance(bg, dict) or bg.get("auto"):
        return None, None
    theme = bg.get("theme")
    return (None if theme in (None, "auto") else theme), (None if bg.get("palette") in (None, "auto") else bg.get("palette"))


def resolve_backgrounds(scenes: list[dict]) -> None:
    """Give every scene its section's background; adjacent sections never share a theme (auto) and a re-used
    theme takes its next palette. Authored themes/palettes win (validation reports clashes)."""
    used: dict[str, int] = {}
    prev = None
    for grp in sections(scenes):
        sid = grp[0].get("section") or grp[0]["sceneId"]
        theme, palette = next(((t, p) for t, p in map(_authored, grp) if t), (None, None))
        auto = theme is None
        if auto:
            cands = list(TEMPLATE_THEMES.get(grp[0]["template"], ())) + list(BACKGROUND_THEMES)
            theme = next((c for c in cands if c != prev and not used.get(c)), None) \
                or next(c for c in cands if c != prev)
        pals = BACKGROUND_THEMES.get(theme, ("default",))
        palette = palette or pals[used.get(theme, 0) % len(pals)]
        used[theme] = used.get(theme, 0) + 1
        for sc in grp:
            sc["background"] = {"theme": theme, "palette": palette, "section": sid, "auto": auto}
        prev = theme


# M05.5: default card kickers by section type (None = no good default -> hidden; there is no global fallback)
TEMPLATE_KICKERS = {
    "cartoon_cold_open": None,
    INTRO_TEMPLATE: None,
    "cartoon_robot_family": "Meet the robots!",
    "cartoon_robot_checkup": "Checkup time!",
    "cartoon_sensor_ping": "Sensor science!",
    "cartoon_rule_board": "The Rule",
    "cartoon_servo_highfive": "Servo time!",
    "cartoon_obstacle_rematch": "Let's test it!",
    "cartoon_recap_chant": "Recap & quiz!",
}


def _kicker_key(k: str | None) -> str:
    return " ".join((k or "").split()).casefold()


def resolve_kickers(scenes: list[dict]) -> None:
    """Section kicker -> first scene of the section (``kicker``: authored, else the section type's default, else
    hidden); concept cards keep an authored ``kicker`` (null/'' = hidden), else the first card of a section gets the
    section kicker and later cards none. A default never repeats an earlier kicker (it is hidden instead)."""
    seen: set[str] = set()
    for grp in sections(scenes):
        authored = next((sc["kicker"] for sc in grp if "kicker" in sc), "__default__")
        for sc in grp:
            sc.pop("kicker", None)
        sec = TEMPLATE_KICKERS.get(grp[0]["template"]) if authored == "__default__" else authored
        if authored == "__default__" and _kicker_key(sec) in seen:
            sec = None
        sec = sec or None
        grp[0]["kicker"] = sec
        used_section = False
        for sc in grp:
            for c in sorted(sc.get("concepts") or [], key=lambda c: c.get("beforeBeat", 0)):
                if "kicker" in c:
                    c["kicker"] = c["kicker"] or None
                elif sec and not used_section:
                    c["kicker"] = sec
                else:
                    c["kicker"] = None
                if c["kicker"] and _kicker_key(c["kicker"]) == _kicker_key(sec):
                    used_section = True
                if c["kicker"]:
                    seen.add(_kicker_key(c["kicker"]))
        if sec:
            seen.add(_kicker_key(sec))


def expand_episode(spec: dict, registry) -> dict:
    s = copy.deepcopy(spec)
    if s.get("schemaVersion") not in CARTOON_SCHEMA_VERSIONS:
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
        if not any(b["type"] == "music" and b.get("cue") == CONCEPT_CUE for b in sc["beats"]):
            plan_shots(sc)                      # anchored on authored beats, shifted by the sting insertion
        insert_concept_stings(sc)
    resolve_transitions(scenes, transition_settings(s))
    resolve_backgrounds(scenes)
    resolve_kickers(scenes)
    s["schemaVersion"] = LATEST_CARTOON_SCHEMA
    return s


__all__ = ["TEMPLATE_KICKERS", "resolve_kickers", "TEMPLATE_THEMES", "resolve_backgrounds", "sections", "DEFAULT_SHOTS", "EXPLAIN_LAYOUTS", "LAYOUTS", "plan_shots", "AUTO_CYCLE", "CONCEPT_CUE", "TRANSITION_STYLES", "transition_settings", "INTRO_SCENE_ID", "INTRO_TEMPLATE", "expand_episode", "intro_scene", "intro_settings", "main_characters"]
