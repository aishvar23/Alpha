"""M05.8 narration sync: every teaching visual is on screen while — and only while — its own line(s) are spoken.

``sync_rows(spec, timing, by, voice_dir)`` measures each illustration / solo / split shot of the rendered scenes
(``scenes.json`` facts) against the ElevenLabs word timings of the line(s) it illustrates:

* ``startDrift``  = shot start − first illustrated word (negative = early, includes the 0.15 s lead-in)
* ``overhang``    = shot end − last illustrated word (the picture outstays its line)
* ``cutEarly``    = last illustrated word − shot end (the picture leaves before its line is done)
* ``foreign``     = other lines spoken for more than the tolerance while the shot is up (narration moved on)
* ``hiddenGags``  = character action beats (not depicted by the visual) that play behind the shot
* ``topic``       = whether a keyword of the visual is spoken while it is on screen

QA ``sync.visual_narration`` (hard) fails on any drift / overhang / cut-early / foreign speech beyond
``SYNC_TOL_S`` or any hidden gag; ``sync.visual_topic`` (hard) fails when a frame's topic isn't being said.
"""

from __future__ import annotations

import re
from pathlib import Path

SYNC_TOL_S = 1.0
SHOT_IN = 0.4            # pop-in; a gag hidden only during the pop-in/out animation is not hidden
SHOT_OUT = 0.35

# what each visual is about: at least one of these must be spoken while it is on screen
VISUAL_KEYWORDS = {
    "example_toaster": ("toaster", "toast"), "example_vacuum": ("vacuum",), "example_arm": ("arm", "factory"),
    "example_rover": ("rover",),
    "part_structure": ("structure", "body", "frame"), "part_sensors": ("sensor",),
    "part_actuators": ("actuator", "move", "wheel", "arm"), "part_power": ("power", "battery", "energy"),
    "part_controller": ("controller", "brain"),
    "echo_diagram": ("sound", "echo", "bounce", "sensor", "distance"), "sensor_range": ("measure", "meter", "range"),
    "sensor_out_of_range": ("range", "farther"),
    "the_rule": ("distance", "meter", "stop"), "sense_think_act": ("sense", "think", "act"),
    "servo_cutaway": ("servo", "motor"), "servo_dial": ("degree", "30", "60", "thirty", "sixty", "angle", "servo"),
    "servo_head": ("servo",), "servo_cause": ("servo", "brain", "turn"),
    "servo_split": ("degree", "30", "60", "thirty", "sixty", "high-five"),
    "rule_test": ("rematch", "boxes", "test"), "quiz_question": ("question", "which", "answer"),
}
# actions a visual itself depicts (allowed to happen while it is up)
DEPICTS = {"echo_diagram": {"ping"}, "servo_split": {"arm_to", "highfive"}, "servo_dial": {"arm_to"}}


def keywords_for(sh: dict) -> tuple[str, ...]:
    vis = sh.get("visual") or ""
    if vis in VISUAL_KEYWORDS:
        return VISUAL_KEYWORDS[vis]
    base = (sh.get("example") or vis.split("_", 1)[-1] or "").replace("_", " ")
    return tuple(w for w in base.split() if len(w) > 2) or (base,)


def _hit(kws, text: str) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}", text.lower()) for k in kws)


def first_keyword_time(voice_dir, line: dict, sh: dict) -> float | None:
    """Start of the first word of ``line`` that names the visual's topic (aligned words; None if none)."""
    from robotics101.cartoon.scenes import line_words
    kws = keywords_for(sh)
    ws = line_words(Path(voice_dir), line) if voice_dir is not None else None
    if ws and len(ws) == len(line["text"].split()):
        return next((w["start_s"] for w in ws if _hit(kws, w["text"])), None)
    return None


def _spoken(beats: list[dict], voice_dir, a: float, b: float) -> list[str]:
    from robotics101.cartoon.scenes import line_words
    out = []
    for ln in beats:
        if ln["type"] != "line" or ln["end_s"] < a or ln["start_s"] > b:
            continue
        ws = line_words(voice_dir, ln)
        if ws:
            out += [w["text"] for w in ws if a <= (w["start_s"] + w["end_s"]) / 2 <= b]
        else:
            out += ln["text"].split()
    return out


def _overlap(a0, a1, b0, b1) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def sync_rows(spec: dict, timing: dict, by: dict, voice_dir, only: list[str] | None = None) -> list[dict]:
    from robotics101.cartoon.scenes import illustrated_span_beats, line_span, line_words
    rows = []
    for ts in timing["scenes"]:
        sid = ts["sceneId"]
        if only and sid not in only:
            continue
        r = by.get(sid)
        if not r:
            continue
        beats = ts["beats"]
        off = ts.get("scene_start_s", 0.0)
        for sh in (r.get("facts") or {}).get("shots") or []:
            if sh.get("layout") == "stage":
                continue
            s0, s1 = illustrated_span_beats(beats, Path(voice_dir), sh)
            a, b = float(sh["start"]), float(sh["end"])
            lo, hi = sh["fromBeat"], sh["toBeat"]
            foreign = []
            for i, ln in enumerate(beats):
                if ln["type"] != "line" or lo <= i <= hi:
                    continue
                w0, w1 = line_span(Path(voice_dir), ln)
                ov = _overlap(a, b, w0, w1)
                if ov > SYNC_TOL_S:
                    foreign.append({"beat": i, "text": ln["text"][:60], "seconds": round(ov, 2)})
            allowed = DEPICTS.get(sh.get("visual"), set())
            gags = [{"beat": i, "do": x["do"], "who": x.get("who"), "at": round(x["start_s"], 2)}
                    for i, x in enumerate(beats)
                    if x["type"] == "action" and x.get("who") and str(x["do"]).split(":")[0] not in allowed
                    and a + SHOT_IN <= x["start_s"] < b - SHOT_OUT]
            kws = keywords_for(sh)

            def hit(text: str) -> bool:
                return any(re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}", text.lower()) for k in kws)
            said = " ".join(_spoken(beats, voice_dir, a, b))
            # first keyword actually spoken while the frame is up (aligned word times)
            first_kw = None
            for ln in beats:
                if ln["type"] != "line" or ln["end_s"] < a - SYNC_TOL_S or ln["start_s"] > b:
                    continue
                ws = line_words(Path(voice_dir), ln) or [{"text": ln["text"], "start_s": ln["start_s"]}]
                kw = next((w["start_s"] for w in ws if a - SYNC_TOL_S <= w["start_s"] <= b and hit(w["text"])), None)
                if kw is not None:
                    first_kw = kw
                    break
            lead = round(first_kw - a, 2) if first_kw is not None else None
            off_lines = []
            for i, ln in enumerate(beats):
                if ln["type"] != "line":
                    continue
                w0, w1 = line_span(Path(voice_dir), ln)
                if _overlap(a, b, w0, w1) > SYNC_TOL_S and not hit(ln["text"]):
                    off_lines.append({"beat": i, "text": ln["text"][:60]})
            topic = lead is not None and abs(lead) <= SYNC_TOL_S and not off_lines
            rows.append({"scene": sid, "visual": sh.get("visual"), "beats": [lo, hi],
                         "shot": [round(a, 3), round(b, 3)], "line": [s0, s1],
                         "episodeShot": [round(off + a, 2), round(off + b, 2)],
                         "startDrift": round(a - s0, 2), "overhang": round(b - s1, 2), "cutEarly": round(s1 - b, 2),
                         "foreign": foreign, "hiddenGags": gags, "keywords": list(kws), "keywordLead": lead,
                         "offTopicLines": off_lines, "topic": topic})
    return rows


def row_problems(row: dict, tol: float = SYNC_TOL_S) -> list[str]:
    p = []
    tag = f"{row['scene']} {row['visual']} @{row['episodeShot'][0]:.1f}s"
    if abs(row["startDrift"]) > tol:
        p.append(f"{tag}: starts {row['startDrift']:+.2f}s from its first word")
    if row["overhang"] > tol:
        p.append(f"{tag}: stays {row['overhang']:.2f}s after its line ends")
    if row["cutEarly"] > tol:
        p.append(f"{tag}: leaves {row['cutEarly']:.2f}s before its line ends")
    for f in row["foreign"]:
        p.append(f"{tag}: up for {f['seconds']}s of another line ({f['text']!r})")
    for g in row["hiddenGags"]:
        p.append(f"{tag}: hides {g['who']} {g['do']} at {g['at']}s")
    return p


def check_sync(rep, spec: dict, timing: dict, by: dict, voice_dir, only: list[str] | None = None) -> list[dict]:
    rows = sync_rows(spec, timing, by, voice_dir, only)
    bad = [p for r in rows for p in row_problems(r)]
    rep.hard("sync.visual_narration", bool(rows) and not bad,
             f"{len(rows)} teaching shots timed to their lines (tolerance {SYNC_TOL_S}s); problems: {bad or 'none'}",
             rows)
    off = [f"{r['scene']} {r['visual']} @{r['episodeShot'][0]:.1f}s: "
           + (f"first of {r['keywords']} said {r['keywordLead']}s after it appears" if r["keywordLead"] is not None
              else f"none of {r['keywords']} said")
           + (f"; off-topic lines {[x['text'] for x in r['offTopicLines']]}" if r["offTopicLines"] else "")
           for r in rows if not r["topic"]]
    rep.hard("sync.visual_topic", bool(rows) and not off,
             f"{len(rows)} teaching frames match what is said; off-topic: {off or 'none'}",
             [{k: r[k] for k in ("scene", "visual", "keywords", "keywordLead", "offTopicLines", "topic")} for r in rows])
    return rows


__all__ = ["SYNC_TOL_S", "VISUAL_KEYWORDS", "check_sync", "first_keyword_time", "keywords_for", "row_problems", "sync_rows"]
