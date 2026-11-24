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

* **illustration-first shots** (M05.1 / M05.6): every teaching example or explanation beat gets its own full-screen
  ``illustration`` shot (the visual fills the frame; no full-size characters, or at most a tiny corner cameo). One
  example per frame — never a grid or album of several examples. Characters come back between explainers for reactions
  and gags. A scene's ``shots`` list is authored or derived (``derive_examples``; optional per-line ``examples`` with
  ``atWord`` / ``untilWord`` when one line names two examples). Lines covered by an illustration/solo shot are marked
  ``explain: true``. Generic rule: any line authored with ``explain: true`` that no shot covers gets an illustration
  of the scene's concept visual. Shot beat indices refer to the expanded beat list (they are shifted when concept
  stings are inserted).

* **section backgrounds** (M05.5, schema 1.2): every section gets its own background. A scene's ``section`` id
  groups consecutive scenes (default: each scene is its own section); ``background`` is ``auto`` (default) or
  ``{theme, palette}``. Auto picks the template's preferred theme (``TEMPLATE_THEMES``), never the previous section's
  theme and preferably one not used yet in the episode; a theme used again gets its next palette. Every scene ends
  up with ``background = {theme, palette, section, auto}`` and the expanded spec is the latest cartoon schema
  (1.1 / 1.2 input is upgraded to 1.3).
* **card kickers** (M05.5): the small line above a concept card title comes from the concept's ``kicker``, else the
  section's ``kicker``, else the section type's default (``TEMPLATE_KICKERS``); null/empty hides it, and there is
  no global default. A section whose kicker isn't shown on a card gets a short section banner instead.

Expansion is idempotent (an already-expanded spec is returned unchanged apart from a fresh copy), so every entry
point (``render``, ``voice``, ``render-cartoon``) can call it. The expanded spec is valid against the 1.1 schema and
is what the bundle stores as ``episode.json`` (valid against the 1.3 schema).
"""

from __future__ import annotations

import copy
import re

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


# ------------------------------------------------------------------------------------------ M05.1 / M05.6 shots

LAYOUTS = ("stage", "illustration", "solo")
EXPLAIN_LAYOUTS = ("illustration", "solo")

# Known family-example phrases, in display order. Unknown names still get a labelled one-example frame.
_FAMILY_KINDS = (
    ("toaster", "Toaster", "example_toaster", ("toaster",)),
    ("vacuum", "Robot vacuum", "example_vacuum", ("robot vacuum", "vacuum")),
    ("arm", "Factory arm", "example_arm", ("factory arm", "factory")),
    ("rover", "Space rover", "example_rover", ("space rover", "rover")),
)


def _first(beats: list[dict], pred, start: int = 0) -> int | None:
    return next((i for i in range(start, len(beats)) if pred(beats[i])), None)


def _is_sfx(name: str):
    return lambda b: b["type"] == "sfx" and b.get("id") == name


def _is_line(b: dict) -> bool:
    return b["type"] == "line"


def _line_has(b: dict, *needles: str) -> bool:
    if b.get("type") != "line":
        return False
    text = b["text"].lower()
    return any(re.search(rf"\b{re.escape(n.lower())}", text) for n in needles)


def _word_in(text: str, word: str) -> int | None:
    m = re.search(rf"\b{re.escape(word)}", text, re.I)
    return m.start() if m else None


def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "example"


def derive_examples(sc: dict) -> list[dict]:
    """One teaching example / explanation per record. Authored beat ``examples`` win for those beats; the rest
    are derived from the template and the lines (including a split when one line names two examples)."""
    beats = sc["beats"]
    authored, authored_beats = [], set()
    for i, b in enumerate(beats):
        if b.get("type") != "line" or not b.get("examples"):
            continue
        authored_beats.add(i)
        for ex in b["examples"]:
            rec = {"id": ex["id"], "label": ex.get("label") or ex["id"].replace("_", " ").title(),
                   "visual": ex.get("visual") or f"example_{ex['id']}", "fromBeat": i, "toBeat": i}
            if ex.get("atWord"):
                rec["atWord"] = ex["atWord"]
            if ex.get("untilWord"):
                rec["untilWord"] = ex["untilWord"]
            if ex.get("subtitle"):
                rec["subtitle"] = ex["subtitle"]
            authored.append(rec)
    derived = [d for d in _derive_template_examples(sc) if d["fromBeat"] not in authored_beats]
    return authored + derived


def _mention(beats, words, start=0):
    """First (beat index, matched word) after ``start`` whose line contains one of ``words`` (longest first)."""
    ordered = sorted(words, key=len, reverse=True)
    for i in range(start, len(beats)):
        if beats[i].get("type") != "line":
            continue
        for w in ordered:
            if _word_in(beats[i]["text"], w) is not None:
                return i, w
    return None


def _split_same_line(beats, mentions):
    """Attach atWord / untilWord so two examples named on the same line get sequential frames."""
    mentions = sorted(mentions, key=lambda m: (m[0], _word_in(beats[m[0]]["text"], m[1]) or 0))
    out = []
    for n, (i, at, extra) in enumerate(mentions):
        rec = {**extra, "fromBeat": i, "toBeat": i, "atWord": at}
        if n + 1 < len(mentions) and mentions[n + 1][0] == i:
            rec["untilWord"] = mentions[n + 1][1]
        out.append(rec)
    return out


def _derive_template_examples(sc: dict) -> list[dict]:
    tmpl, beats, params = sc.get("template", ""), sc["beats"], sc.get("parameters") or {}
    out: list[dict] = []
    if tmpl == "cartoon_robot_family":
        hit = _mention(beats, ("toaster",))
        if hit:
            i, _ = hit
            # M05.8: the toaster frame illustrates the line that explains it ("doesn't think"), not the joke
            # that first names it; the joke, the pop and the flinch play on stage with the toaster prop.
            j = _first(beats, lambda b: _line_has(b, "doesn't think", "does not think"), i)
            k = j if j is not None else i
            out.append({"id": "toaster", "label": "Toaster", "visual": "example_toaster",
                        "fromBeat": k, "toBeat": k, "subtitle": "Not a robot — it doesn't think"})
        mentions = []
        seen = set()
        for eid, label, vis, words in _FAMILY_KINDS:
            if eid == "toaster":
                continue
            hit = _mention(beats, words)
            if hit:
                mentions.append((hit[0], hit[1], {"id": eid, "label": label, "visual": vis}))
                seen.add(eid)
        # parameters.examples (and leftover lines after the page-flip) for template-wide / other families
        named = [str(x) for x in (params.get("examples") or [])]
        flip = _first(beats, _is_sfx("page_flip")) or 0
        sparkle = _first(beats, _is_sfx("sparkle"), flip)
        end = sparkle if sparkle is not None else len(beats)
        for label in named:
            eid = _slug(label.replace("robot ", "").replace("space ", "").replace("factory ", ""))
            if eid in seen or eid == "toaster":
                continue
            words = (label, *tuple(w for w in label.split() if w.lower() not in {"a", "the", "an"}))
            hit = _mention(beats, words, start=flip)
            if hit and eid not in seen:
                vis = f"example_{eid}"
                mentions.append((hit[0], hit[1], {"id": eid, "label": label.title() if label.islower() else label,
                                                  "visual": vis}))
                seen.add(eid)
        if not mentions:
            for i in range(flip, end):
                if not _is_line(beats[i]):
                    continue
                if _line_has(beats[i], "here's your", "here is your", "robot family"):
                    continue
                text = beats[i]["text"]
                # "A drone flies" / "A robot dog walks" -> the noun phrase, not the verb that follows
                m = re.search(r"\b(?:a|an|the)\s+((?:robot|space|factory)\s+)?([A-Za-z]+)", text, re.I)
                if m:
                    label = " ".join(part for part in (m.group(1), m.group(2)) if part).strip()
                    at = m.group(2)
                else:
                    label, at = text.split(".")[0].strip(), text.split()[0]
                eid = _slug(re.sub(r"^(a|an|the)\s+", "", label, flags=re.I))
                if eid in seen:
                    continue
                mentions.append((i, at, {"id": eid, "label": label.title(), "visual": f"example_{eid}"}))
                seen.add(eid)
        out.extend(_split_same_line(beats, mentions))

    elif tmpl == "cartoon_robot_checkup":
        parts = params.get("parts") or ["structure", "sensors", "actuators", "power", "controller"]
        labels = {"structure": "Structure", "sensors": "Sensors", "actuators": "Actuators", "power": "Power",
                  "controller": "Controller"}
        for p in parts:
            i = _first(beats, lambda b, p=p: _line_has(b, p))
            if i is not None:
                out.append({"id": p, "label": labels.get(p, p.title()), "visual": f"part_{p}",
                            "fromBeat": i, "toBeat": i})

    elif tmpl == "cartoon_sensor_ping":
        first = _first(beats, _is_line)
        echo_line = _first(beats, lambda b: _line_has(b, "bounces", "echo comes back", "bats"))
        if first is not None and echo_line is not None:
            out.append({"id": "echo", "label": "Distance sensor", "visual": "echo_diagram",
                        "fromBeat": first, "toBeat": echo_line})
        three = _first(beats, lambda b: _line_has(b, "3 meters", "three meters", "3 metres"))
        oor = _first(beats, lambda b: _line_has(b, "out of range"))
        # M05.8: one frame per idea, each on its own line: "measures up to 3 m" (Nib inside the range), then
        # Nib's flight away plays on stage, then "out of range" gets its own frame (Nib past 3 m).
        if three is not None:
            out.append({"id": "range", "label": "Sensor range", "visual": "sensor_range",
                        "fromBeat": three, "toBeat": three})
        if oor is not None and oor != three:
            out.append({"id": "out_of_range", "label": "Out of range", "visual": "sensor_out_of_range",
                        "fromBeat": oor, "toBeat": oor})

    elif tmpl == "cartoon_rule_board":
        # Maya's rule line, not Bolt's "Got it!" repeat.
        i = _first(beats, lambda b: _is_line(b) and "if the distance" in b["text"].lower())
        if i is None:
            i = _first(beats, lambda b: _line_has(b, "stop and turn") and "got it" not in b["text"].lower())
        if i is not None:
            out.append({"id": "the_rule", "label": "The Rule", "visual": "the_rule", "fromBeat": i, "toBeat": i})
        j = _first(beats, lambda b: _is_line(b) and "how it works" in b["text"].lower())
        if j is not None:
            out.append({"id": "sta", "label": "Sense, think, act", "visual": "sense_think_act",
                        "fromBeat": j, "toBeat": j})

    elif tmpl == "cartoon_servo_highfive":
        i = _first(beats, lambda b: _line_has(b, "servo motor", "exact angle") or _line_has(b, "actuators turn"))
        if i is not None:
            out.append({"id": "servo_what", "label": "What is a servo?", "visual": "servo_cutaway",
                        "fromBeat": i, "toBeat": i})
        a = _first(beats, lambda b: _line_has(b, "30 degrees", "only 30", "only thirty"))
        b = _first(beats, lambda b: _is_line(b) and "high-five!" in b["text"].lower())
        if a is not None:
            out.append({"id": "servo_dial", "label": "Exact angle", "visual": "servo_dial",
                        "fromBeat": a, "toBeat": b if b is not None else a})
        k = _first(beats, lambda b: _line_has(b, "servos turn arms", "turn wheels"))
        if k is not None:
            out.append({"id": "servo_head", "label": "How Bolt uses a servo", "visual": "servo_head",
                        "fromBeat": k, "toBeat": k})

    elif tmpl == "cartoon_obstacle_rematch":
        i = _first(beats, _is_line)
        if i is not None:
            out.append({"id": "rule_test", "label": "Test of the Rule", "visual": "rule_test",
                        "fromBeat": i, "toBeat": i})

    elif tmpl == "cartoon_recap_chant":
        i = _first(beats, lambda b: _line_has(b, "which part") or (_line_has(b, "question") and "here's" in b["text"].lower()))
        if i is not None:
            j = _first(beats, lambda b: _line_has(b, "say your answer", "think about it"), i)
            out.append({"id": "quiz", "label": "Quiz", "visual": "quiz_question",
                        "fromBeat": i, "toBeat": j if j is not None else i})
    return out


def shots_from_examples(examples: list[dict]) -> list[dict]:
    shots = []
    for ex in examples:
        sh = {"layout": "illustration", "fromBeat": ex["fromBeat"], "toBeat": ex["toBeat"],
              "visual": ex["visual"], "example": ex["id"]}
        if ex.get("atWord"):
            sh["atWord"] = ex["atWord"]
        if ex.get("untilWord"):
            sh["untilWord"] = ex["untilWord"]
        shots.append(sh)
    return shots


def shots_robot_family(beats: list[dict], params: dict | None = None) -> list[dict]:
    return shots_from_examples(_derive_template_examples(
        {"template": "cartoon_robot_family", "beats": beats, "parameters": params or {}}))


def shots_sensor_ping(beats: list[dict], params: dict | None = None) -> list[dict]:
    return shots_from_examples(_derive_template_examples(
        {"template": "cartoon_sensor_ping", "beats": beats, "parameters": params or {}}))


def shots_rule_board(beats: list[dict], params: dict | None = None) -> list[dict]:
    return shots_from_examples(_derive_template_examples(
        {"template": "cartoon_rule_board", "beats": beats, "parameters": params or {}}))


DEFAULT_SHOTS = {"cartoon_robot_family": shots_robot_family, "cartoon_sensor_ping": shots_sensor_ping,
                 "cartoon_rule_board": shots_rule_board}


def _stamp_examples(sc: dict, examples: list[dict]) -> None:
    """Record derived examples on their starting line beat (authored lists are left as-is)."""
    beats = sc["beats"]
    for ex in examples:
        b = beats[ex["fromBeat"]]
        if b.get("type") != "line":
            continue
        existing = {e["id"] for e in b.get("examples") or []}
        if ex["id"] in existing:
            continue
        rec = {k: ex[k] for k in ("id", "label", "visual", "atWord", "untilWord", "subtitle") if ex.get(k) is not None}
        b.setdefault("examples", []).append(rec)


# M05.8: actions a teaching visual itself depicts (they may sit inside its beat range); any other character
# action / gag beat inside a derived shot's range ends the shot before it, so the gag plays on stage.
SHOT_DEPICTS = {"echo_diagram": {"ping"}, "servo_split": {"arm_to"}, "servo_dial": {"arm_to"}}


def trim_shots_at_gags(sc: dict) -> None:
    beats = sc["beats"]
    for sh in sc.get("shots") or []:
        if sh.get("layout") not in EXPLAIN_LAYOUTS + ("split",):
            continue
        allowed = SHOT_DEPICTS.get(sh.get("visual"), set())
        lo, hi = sh["fromBeat"], sh["toBeat"]
        for i in range(lo + 1, hi + 1):
            b = beats[i]
            if b.get("type") == "action" and b.get("who") and str(b.get("do", "")).split(":")[0] not in allowed:
                last = max((j for j in range(lo, i) if beats[j].get("type") == "line"), default=lo)
                sh["toBeat"] = last
                break


def plan_shots(sc: dict) -> None:
    """Fill ``sc['shots']`` from derived teaching examples (unless authored), add generic illustration shots for
    uncovered ``explain`` lines, and mark every line inside an illustration/solo shot ``explain: true``."""
    beats = sc["beats"]
    if "shots" not in sc:
        examples = derive_examples(sc)
        sc["shots"] = shots_from_examples(examples)
        trim_shots_at_gags(sc)                  # derived shots only; authored ranges are checked by QA
        _stamp_examples(sc, examples)
    shots = sc["shots"]

    def covered(i: int) -> bool:
        return any(s["layout"] in EXPLAIN_LAYOUTS and s["fromBeat"] <= i <= s["toBeat"] for s in shots)
    icon = next((c.get("icon") for c in sc.get("concepts") or [] if c.get("icon")), "robot")
    for i, b in enumerate(beats):
        if _is_line(b) and b.get("explain") and not covered(i):
            shots.append({"layout": "illustration", "fromBeat": i, "toBeat": i, "visual": f"concept_{icon}",
                          "generated": True})
    shots.sort(key=lambda s: (s["fromBeat"], _word_in(beats[s["fromBeat"]]["text"], s["atWord"]) if s.get("atWord") and _is_line(beats[s["fromBeat"]]) else -1))
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
