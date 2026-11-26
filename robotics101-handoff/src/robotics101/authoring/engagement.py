"""Engagement gate — deterministic pacing checks (PLAN-authoring §6.2), blocking.

Runs on an *expanded* EpisodeSpec plus a timeline: the pre-render estimate (``timeline.estimate_timing``) or the
real ``timing.json`` (+ ``scenes.json`` shot windows) after render, with the same thresholds
(``authoring/config.yaml`` → ``engagement``; PROVISIONAL plan defaults, calibrated so episode 1 passes).

Checks (ids are shared with cartoon QA ``engagement.*``):
visual_change, gag_density, reaction_density, monologue, hook, hook_callback, chant, audience_questions,
first_concept. Gag tags from an outline (``{sceneId, beat, kind}``) count on top of impact sfx and
giggle/surprised poses; the schema does not change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from robotics101.authoring.config import config, engagement_thresholds

IMPACT_SFX = frozenset({"bonk", "boing", "skid", "pop", "toaster_pop", "stars"})
GAG_POSES = frozenset({"giggle", "surprised"})
ENTRANCE_ACTIONS = ("enter", "fly_to", "zoom", "exit")
CONCEPT_CARD_S = 2.8
VIEWER_MARKERS = ("can you", "do you", "what do you", "which", "guess", "everyone", "friends", "at home",
                  "you think", "what would", "who can", "how does", "how do", "what happens", "why")


@dataclass
class EngagementResult:
    checks: list[dict] = field(default_factory=list)
    timeline: str = "estimate"

    def add(self, cid: str, ok: bool, message: str, value=None, warn: bool = False) -> None:
        self.checks.append({"id": f"engagement.{cid}", "blocking": True, "ok": bool(ok), "message": message,
                            "value": value, **({"warning": True} if warn else {})})

    @property
    def ok(self) -> bool:
        return all(c["ok"] for c in self.checks)

    @property
    def failures(self) -> list[dict]:
        return [c for c in self.checks if not c["ok"]]


def _pose(line: dict) -> str | None:
    from robotics101.cartoon.acting import auto_pose
    if line.get("pose"):
        return line["pose"]
    try:
        return auto_pose(line)
    except Exception:                                  # pragma: no cover - defensive
        return None


def _react(line: dict, pose: str | None):
    from robotics101.cartoon.acting import auto_react
    if line.get("react"):
        return line["react"]
    try:
        return auto_react(line, pose or "")
    except Exception:                                  # pragma: no cover
        return None


def _flat(spec: dict, timing: dict, shots_by_scene: dict | None):
    """Episode-time beats (spec fields merged into timing entries), scene spans, shot windows."""
    by_spec = {s["sceneId"]: s for s in spec["scenes"]}
    beats, scenes, shots = [], [], []
    shot_specs = []
    for ts in timing["scenes"]:
        sid = ts["sceneId"]
        sc = by_spec.get(sid, {})
        off = float(ts.get("scene_start_s", 0.0))
        sb = sc.get("beats") or []
        scenes.append({"sceneId": sid, "template": sc.get("template"), "start": off,
                       "end": off + float(ts["scene_duration_s"]), "parameters": sc.get("parameters") or {}})
        for e in ts["beats"]:
            src = sb[e["index"]] if e["index"] < len(sb) else {}
            beats.append({**src, **{k: v for k, v in e.items() if v is not None}, "sceneId": sid,
                          "t0": off + e["start_s"], "t1": off + e["end_s"], "type": e["type"]})
        for sh in sc.get("shots") or []:
            if sh.get("layout") != "stage":
                shot_specs.append({**sh, "sceneId": sid})
        if shots_by_scene is not None:
            for sh in shots_by_scene.get(sid) or []:
                shots.append((off + sh["start"], off + sh["end"]))
        else:                                          # estimate: shot = its beat range
            for sh in sc.get("shots") or []:
                if sh.get("layout") == "stage":
                    continue
                ents = [e for e in ts["beats"] if sh["fromBeat"] <= e["index"] <= sh["toBeat"]]
                if ents:
                    shots.append((off + min(e["start_s"] for e in ents), off + max(e["end_s"] for e in ents)))
    return beats, scenes, shots, shot_specs


READOUT_TEMPLATES_KEY = "readout"


def _readout_templates() -> set[str]:
    """Templates whose capability card says they show a live readout: a spoken reading updates it on screen."""
    try:
        from robotics101.authoring.catalog import cards
        return {n for n, c in (cards().get("templates") or {}).items() if READOUT_TEMPLATES_KEY in (c or {}).get("shows", [])}
    except Exception:                                  # pragma: no cover
        return set()


def _cue_words() -> dict[str, list[str]]:
    try:
        from robotics101.authoring.catalog import cards
        c = cards()
        return {n: [str(w).lower() for w in (v or {}).get("cueWords", [])]
                for sect in ("visuals", "kit") for n, v in (c.get(sect) or {}).items() if (v or {}).get("cueWords")}
    except Exception:                                  # pragma: no cover
        return {}


def shot_cue_events(beats, shot_specs: list[dict]) -> list[float]:
    """Reveal/advance cues inside teaching shots: a cue word of the shot's visual (capability card ``cueWords``,
    or a kit shot's ``cues``) spoken in a covered line, timed proportionally inside the line."""
    words = _cue_words()
    out = []
    for sh in shot_specs:
        cw = list(words.get(sh.get("visual") or "", []))
        kit = sh.get("kit") or {}
        for v in (kit.get("cues") or {}).values():
            if isinstance(v, str) and v.startswith("word:"):
                cw.append(v[5:].lower())
        if not cw:
            continue
        for b in beats:
            if b["sceneId"] != sh["sceneId"] or b["type"] != "line" or not sh["fromBeat"] <= b["index"] <= sh["toBeat"]:
                continue
            toks = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in b.get("text", "").split()]
            for k, w in enumerate(toks):
                if w and w in cw:
                    out.append(b["t0"] + (b["t1"] - b["t0"]) * k / max(1, len(toks)))
    return out


def visual_events(beats, scenes, shots, extra: list[float] | None = None) -> list[float]:
    """Times of visual events (§6.2): scene in/out, shot start/end, concept card in/out, action beats (incl. line
    actions and acted emotion poses), impact sfx, readout updates (a spoken quantity in a readout template),
    entrances, kit reveal/advance cues (``extra``) and, after render, overlay keep-outs appearing/disappearing."""
    from robotics101.cartoon.acting import EMOTION_POSES
    from robotics101.cartoon.lint import spoken_quantities
    readout = _readout_templates()
    tmpl = {s["sceneId"]: s.get("template") for s in scenes}
    ev = []
    for s in scenes:
        ev += [s["start"], s["end"]]
    for a, b in shots:
        ev += [a, b]
    for b in beats:
        if b["type"] == "action":
            ev.append(b["t0"])
        elif b["type"] == "line" and (b.get("action") or _pose(b) in EMOTION_POSES):
            ev.append(b["t0"])
        elif b["type"] == "line" and tmpl.get(b["sceneId"]) in readout and spoken_quantities(b.get("text", "")):
            ev.append(b["t0"])
        elif b["type"] == "sfx" and b.get("id") in IMPACT_SFX:
            ev.append(b["t0"])
        elif b["type"] == "music" and b.get("cue") == "concept_sting":
            ev += [b["t0"], b["t0"] + CONCEPT_CARD_S]
    return sorted(set(round(x, 3) for x in ev + (extra or [])))


def gag_times(beats, outline_gags: list[dict] | None = None) -> list[tuple[float, str, str]]:
    out = []
    tagged = {(g["sceneId"], g["beat"]) for g in outline_gags or []}
    for b in beats:
        why = None
        if (b["sceneId"], b.get("index")) in tagged:
            why = "outline gag"
        elif b["type"] == "sfx" and b.get("id") in IMPACT_SFX:
            why = f"sfx {b['id']}"
        elif b["type"] == "line" and _pose(b) in GAG_POSES:
            why = f"pose {_pose(b)}"
        if why:
            out.append((b["t0"], b["sceneId"], why))
    return out


def chant_words(text: str) -> list[str]:
    """Leading run of one-word phrases: "Sense, think, act. Like a dance" -> [sense, think, act]."""
    parts = [p.strip(" .!?…'\"").lower() for p in re.split(r"[,.!?…]|\s-\s", text)]
    out = []
    for p in (x for x in parts if x):
        if len(p.split()) != 1:
            break
        out.append(p)
    return out


def evaluate(spec: dict, timing: dict, *, age_band: str = "6-9", shots_by_scene: dict | None = None,
             outline: dict | None = None, vocabulary: list[str] | None = None, cfg: dict | None = None,
             kit_events: list[float] | None = None) -> EngagementResult:
    th = engagement_thresholds(age_band, cfg)
    res = EngagementResult(timeline="real" if shots_by_scene is not None else "estimate")
    beats, scenes, shots, shot_specs = _flat(spec, timing, shots_by_scene)
    total = scenes[-1]["end"] if scenes else 0.0
    minutes = max(total / 60.0, 1e-6)
    lines = [b for b in beats if b["type"] == "line"]

    # 1 visual change
    ev = visual_events(beats, scenes, shots, list(kit_events or []) + shot_cue_events(beats, shot_specs))
    gaps = [(b - a, a) for a, b in zip(ev, ev[1:])]
    longest, at = max(gaps, default=(0.0, 0.0))
    warn = longest > th["visualChangeWarnS"]
    res.add("visual_change", longest <= th["visualChangeMaxS"],
            f"longest stretch without a visual event {longest:.2f}s at {at:.1f}s (≤ {th['visualChangeMaxS']:g}s"
            f"{'; warn > ' + format(th['visualChangeWarnS'], 'g') + 's' if warn else ''})", round(longest, 3), warn)

    # 2 gag density
    gags = gag_times(beats, (outline or {}).get("gags"))
    per_min = len(gags) / minutes
    no_gag = [s["sceneId"] for s in scenes if sum(1 for g in gags if g[1] == s["sceneId"]) < th["gagPerScene"]]
    pts = [0.0] + sorted(g[0] for g in gags) + [total]
    window = max((b - a for a, b in zip(pts, pts[1:])), default=total)
    res.add("gag_density", per_min >= th["gagPerMin"] and not no_gag and window <= th["gagWindowS"],
            f"{len(gags)} gags = {per_min:.2f}/min (≥ {th['gagPerMin']:g}); scenes without one: "
            f"{no_gag or 'none'}; longest gap {window:.1f}s (≤ {th['gagWindowS']:g}s)",
            {"perMin": round(per_min, 3), "scenesWithout": no_gag, "longestGapS": round(window, 2)})

    # 3 reaction density: listener reactions + emotion changes between consecutive lines
    reacts = sum(1 for b in lines if _react(b, _pose(b)))
    changes = sum(1 for a, b in zip(lines, lines[1:]) if a.get("emotion") and b.get("emotion")
                  and a["emotion"] != b["emotion"])
    rpm = (reacts + changes) / minutes
    res.add("reaction_density", rpm >= th["reactionPerMin"],
            f"{reacts} reactions + {changes} emotion changes = {rpm:.2f}/min (≥ {th['reactionPerMin']:g})",
            round(rpm, 3))

    # 4 monologue: one speaker's run without another line, sfx or action in between
    best, run_start, who, run_end, best_at = 0.0, None, None, None, None
    for b in beats:
        if b["type"] == "line" and b["speaker"] == who and run_start is not None:
            run_end = b["t1"]
        elif b["type"] == "line":
            run_start, run_end, who = b["t0"], b["t1"], b["speaker"]
        elif b["type"] in ("sfx", "action"):
            run_start, who = None, None
        if run_start is not None and run_end - run_start > best:
            best, best_at = run_end - run_start, (who, round(run_start, 1))
    res.add("monologue", best <= th["monologueMaxS"],
            f"longest single-speaker run {best:.1f}s {best_at or ''} (≤ {th['monologueMaxS']:g}s)", round(best, 2))

    # 5 hook
    first_gag = min((g[0] for g in gags), default=None)
    cold = next((s for s in scenes if s["template"] == "cartoon_cold_open"), scenes[0] if scenes else None)
    cold_s = (cold["end"] - cold["start"]) if cold else 0.0
    res.add("hook", first_gag is not None and first_gag <= th["hookFirstGagS"] and cold_s <= th["coldOpenMaxS"],
            f"first gag at {first_gag if first_gag is None else round(first_gag, 2)}s (≤ {th['hookFirstGagS']:g}s); "
            f"cold open {cold_s:.1f}s (≤ {th['coldOpenMaxS']:g}s)", {"firstGagS": first_gag, "coldOpenS": round(cold_s, 2)})

    # 6 hook callback
    hook = (outline or {}).get("hook") or {}
    keys = [k.lower() for k in ([hook.get("id"), hook.get("prop")] + list(hook.get("keywords") or [])) if k]
    if not keys and cold:                                    # authored spec without an outline: the cold-open prop
        keys = [str(v).lower() for v in cold["parameters"].values() if isinstance(v, str)]
    practice = next((s for s in scenes if s["template"] == "cartoon_obstacle_rematch"), None)
    if practice is None and outline:
        sid = next((x["sceneId"] for x in outline.get("scenes", []) if x["role"] == "practice"), None)
        practice = next((s for s in scenes if s["sceneId"] == sid), None)

    def mentions(b):
        low = (b.get("text") or "").lower()
        return any(k.replace("_", " ") in low for k in keys)
    in_practice = bool(practice) and (any(str(v).lower() in keys for v in practice["parameters"].values()
                                          if isinstance(v, str))
                                      or any(mentions(b) for b in lines if b["sceneId"] == practice["sceneId"]))
    tail = [b for b in lines if b["t0"] >= total * (1 - th["hookCallbackTail"])]
    in_tail = any(mentions(b) for b in tail)
    res.add("hook_callback", in_practice and in_tail,
            f"hook {keys or '?'}: practice scene {'references it' if in_practice else 'does NOT reference it'}; "
            f"last {th['hookCallbackTail']:.0%} {'mentions it' if in_tail else 'does NOT mention it'}",
            {"practice": in_practice, "tail": in_tail})

    # 7 chant: a chant_beat cue or recap scene + a 3-word chant from taught vocabulary / concept titles
    has_cue = any(b["type"] == "music" and b.get("cue") == "chant_beat" for b in beats) or \
        any(s["template"] == "cartoon_recap_chant" for s in scenes)
    vocab = {v.lower() for v in vocabulary or []}
    for sc in spec["scenes"]:
        for c in sc.get("concepts") or []:
            vocab |= {w.lower() for w in re.findall(r"[A-Za-z]+", c.get("title", ""))}
    chant = None
    for k, b in enumerate(lines):
        ws = chant_words(b.get("text", ""))
        if len(ws) == 1:                                # call-and-response chant over consecutive one-word lines
            for nb in lines[k + 1:k + 3]:
                nw = chant_words(nb.get("text", ""))
                if len(nw) != 1 or nb["sceneId"] != b["sceneId"]:
                    break
                ws = ws + nw
        if len(ws) >= 3 and all(w in vocab for w in ws[:3]):
            chant = ws[:3]
            break
    res.add("chant", has_cue and chant is not None,
            f"chant cue/scene {'present' if has_cue else 'missing'}; chant {chant or 'not found'}",
            {"cue": has_cue, "chant": chant})

    # 8 audience questions
    teacher = th.get("teacher", "maya")
    names = {str(sc_id).lower() for sc_id in spec.get("characters") or []}

    def to_viewer(b) -> bool:
        low = b["text"].lower()
        if any(m in low for m in VIEWER_MARKERS):
            return True
        # the teacher's question that names no cast member is one the audience can answer (a prediction)
        return b.get("speaker") == teacher and not any(re.search(rf"\b{n}\b", low) for n in names)
    qs = [b for b in lines if b.get("text", "").rstrip().endswith("?") and to_viewer(b)]
    mid = [b for b in qs if b["t0"] < total * 0.75]
    res.add("audience_questions", len(qs) >= th["audienceQuestionsMin"] and bool(mid),
            f"{len(qs)} viewer questions (≥ {th['audienceQuestionsMin']}), {len(mid)} before the last quarter: "
            + "; ".join(repr(b["text"][:50]) for b in qs[:4]), len(qs))

    # 9 first concept card
    first_card = min((b["t0"] for b in beats if b["type"] == "music" and b.get("cue") == "concept_sting"),
                     default=None)
    res.add("first_concept", first_card is not None and first_card <= th["firstConceptMaxS"],
            f"first concept card at {first_card if first_card is None else round(first_card, 1)}s "
            f"(≤ {th['firstConceptMaxS']:g}s)", first_card)
    return res


def shots_from_scenes_json(scenes_json: dict) -> dict:
    return {s["sceneId"]: [x for x in ((s.get("facts") or {}).get("shots") or []) if x.get("layout") != "stage"]
            for s in scenes_json.get("scenes", [])}


__all__ = ["CONCEPT_CARD_S", "EngagementResult", "GAG_POSES", "IMPACT_SFX", "evaluate", "gag_times",
           "shots_from_scenes_json", "visual_events"]
