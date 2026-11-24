"""Cartoon scene engine (M02.6): timing.json beats -> staged performance -> frames, per template.

Every scene is a pure function of time built from the voiced timeline (``timing.json`` v2): lines drive lip sync
(Rhubarb, RMS fallback), expressions, listener gaze and talk gestures; action beats drive the rigs; sfx beats drive
comic lettering; per-template staging adds blocking, props and teaching overlays (rulers, readouts, the rule, the
servo gauge, the quiz). Scene 7 cuts to the cartoon-styled Blender "robot-cam" for the sensing/stop moment.

Nothing is random and nothing accumulates between frames, so scenes render in parallel chunks and re-render
bit-exactly. Character presence is computed analytically (``presence``) for QA.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from robotics101.cartoon import props as PR
from robotics101.cartoon.lipsync import line_cues
from robotics101.cartoon.motion import Performer, clamp01, ease_in_out, ease_out
from robotics101.cartoon.obstacle import BOLT_FRONT, Approach, assert_no_collision, plan_approach
from robotics101.cartoon.rigs import build
from robotics101.cartoon.sets import GROUND, METER, SOCKET_POS, garage

FPS = 30
SCALES = {"bolt": 0.78, "maya": 0.8, "nib": 0.95}
HALF_W = {"bolt": 1.58, "maya": 1.2, "nib": 0.53}       # nominal half widths (world units, at SCALES)
HEIGHT = {"bolt": 3.3, "maya": 3.96, "nib": 1.12}
FRAME_X, FRAME_Y = 7.11, 4.0
STAGED_LINE_ACTIONS = {"drive", "stop", "resume", "skid", "spin", "turn"}   # handled by template staging
Overlay = Callable[[float, dict], list]


@dataclass
class Scene:
    sid: str
    template: str
    params: dict
    beats: list[dict]
    duration: float
    voice_dir: Path
    perf: dict[str, Performer] = field(default_factory=dict)
    back: list[Overlay] = field(default_factory=list)      # drawn after the set, before characters
    front: list[Overlay] = field(default_factory=list)     # after characters
    screen: list[Overlay] = field(default_factory=list)    # HUD layer (not affected by camera)
    set_variant: str = "default"
    cast: tuple[str, ...] = ("maya", "bolt", "nib")
    cutaways: list[dict] = field(default_factory=list)     # {"start","end","clip","clip_offset"}
    lipsync_methods: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)              # teaching values shown on screen (for QA)
    illustrations: list = field(default_factory=list)       # M03.4 animated illustration regions (static-hold QA)
    keepouts: list = field(default_factory=list)            # M03.5 teaching visuals subtitles must not cover
    enter_at: dict = field(default_factory=dict)           # cid -> time the character is on stage (presence QA)
    trans_in: str | None = None                            # M03.2 transition into this scene (None/cut = none)
    trans_out: str | None = None                           # transition into the NEXT scene (drawn at our end)
    trans_half: float = 0.4
    concepts: list = field(default_factory=list)           # [{id,title,subtitle,icon,start,end}]
    shots: list = field(default_factory=list)              # M05.1 [{layout,visual,character,start,end,...}]
    top: list[Overlay] = field(default_factory=list)       # M05.1 shot layer: above everything but transitions

    @property
    def n_frames(self) -> int:
        return round(self.duration * FPS)

    def lines(self, speaker: str | None = None) -> list[dict]:
        return [b for b in self.beats if b["type"] == "line" and (speaker is None or b["speaker"] == speaker)]

    def beat(self, type_: str, key: str, value: str, nth: int = 0) -> dict | None:
        hits = [b for b in self.beats if b["type"] == type_ and str(b.get(key, "")).split(":")[0] == value]
        return hits[nth] if len(hits) > nth else None

    def word_time(self, word: str, after: float = 0.0) -> float | None:
        """Approximate time a word is spoken: character position within the line (first match after ``after``)."""
        for b in self.lines():
            if b["end_s"] < after:
                continue
            m = re.search(rf"\b{re.escape(word)}", b["text"], re.I)
            if m:
                return b["start_s"] + (b["end_s"] - b["start_s"]) * m.start() / max(1, len(b["text"]))
        return None


def sfx_word(word: str, color: str, start: float, at, dur: float = 0.9, size: int = 88) -> Overlay:
    return lambda t, m: [PR.sfx_text(word, color, (t - start) / dur, at, size=size)] if start <= t < start + dur else []


def _u(t: float, a: float, b: float) -> float:
    return clamp01((t - a) / max(1e-6, b - a))


# ------------------------------------------------------------------------------------------ generic performance

def perform_dialogue(sc: Scene) -> None:
    """Lip sync, emotions, gestures and listener gaze from the line beats; generic action beats."""
    for b in sc.lines():
        p = sc.perf.get(b["speaker"])
        if p is None:
            continue
        cues, method = line_cues(sc.voice_dir / b["wav"], b["text"])
        sc.lipsync_methods[f"{sc.sid}#{b['index']}"] = method
        p.mouth.add_line(b["start_s"], cues)
        if b.get("emotion"):
            p.feel(b["start_s"], b["emotion"])
        act = b.get("action")
        if act and act.split(":")[0] not in STAGED_LINE_ACTIONS:
            p.act(b["start_s"], min(b["end_s"], b["start_s"] + 2.2), act)
        for cid, other in sc.perf.items():               # listeners look at the speaker
            if cid != b["speaker"]:
                sx = p.position_at(b["start_s"])[0]
                ox = other.position_at(b["start_s"])[0]
                other.look(b["start_s"], (0.8 if sx > ox else -0.8, 0.1 if cid == "nib" else 0.0))
                other.listen(b["start_s"], b["end_s"], sx)
            else:
                p.look(b["start_s"], (0.0, 0.0))
    for b in sc.beats:
        if b["type"] == "action" and b["who"] in sc.perf and b["do"].split(":")[0] not in (
                "zoom", "fly_to", "return", "land", "fall", "drive", "turn", "resume", "arm_to", "plug_in"):
            sc.perf[b["who"]].act(b["start_s"], b["end_s"], b["do"])
            if b.get("emotion"):
                sc.perf[b["who"]].feel(b["start_s"], b["emotion"])


def generic_sfx_lettering(sc: Scene, positions: dict[str, np.ndarray], skip: tuple[str, ...] = ()) -> None:
    for b in sc.beats:
        if b["type"] == "sfx" and b["id"] in PR.SFX_WORDS and b["id"] not in skip:
            word, color = PR.SFX_WORDS[b["id"]]
            at = positions.get(b["id"], PR.P(0, 1.5))
            sc.front.append(sfx_word(word, color, b["start_s"], at))


def facing_toward(p: Performer, t: float, target_x: float) -> None:
    p.face(t, 1 if target_x > p.position_at(t)[0] else -1)


# ------------------------------------------------------------------------------------------ templates

def stage_cold_open(sc: Scene) -> None:
    box_x = 5.3
    face = box_x - PR.BOX_W / 2
    bolt = Performer("bolt", x=-9.5, facing=1, scale=SCALES["bolt"], expression="happy")
    maya = Performer("maya", x=-4.8, facing=1, scale=SCALES["maya"], expression="happy")
    nib = Performer("nib", x=1.0, y=4.6, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    pile = PR.box_pile(box_x)
    sc.back.append(lambda t, m: [pile])
    zoom = sc.beat("action", "do", "zoom")
    bonk_x = face - BOLT_FRONT * SCALES["bolt"]
    bolt.move(zoom["start_s"], zoom["end_s"], x=bonk_x, ease="out").act(zoom["start_s"], zoom["end_s"], "zoom")
    bolt.act(zoom["end_s"], zoom["end_s"] + 0.7, "bonk").feel(zoom["end_s"], "dizzy")
    bolt.move(zoom["end_s"], zoom["end_s"] + 0.7, x=bonk_x - 0.35, ease="out")
    maya.look(0.5, (1.0, 0.0)).feel(zoom["end_s"], "surprised")
    first_maya = sc.lines("maya")[0]["start_s"]
    bolt.act(first_maya - 0.6, first_maya + 0.2, "turn")          # turns to Maya when she starts talking
    land, fall = sc.beat("action", "do", "land"), sc.beat("action", "do", "fall")
    nib.move(0.0, 3.0, x=0.5, y=4.2).act(0.0, 3.0, "hover")
    nib.move(land["start_s"] - 1.0, land["start_s"] + 0.3, x=box_x + 0.1, y=PR.PILE_H - 0.02, arc=1.6)
    nib.act(land["start_s"], land["end_s"], "land").fly(land["end_s"], False).feel(land["end_s"], "proud")
    nib.act(fall["start_s"], fall["end_s"], "fall").feel(fall["start_s"], "surprised")
    nib.move(fall["start_s"] + 0.2, fall["end_s"], x=box_x + 1.35, y=0.0, arc=0.3).feel(fall["end_s"], "dizzy")
    generic_sfx_lettering(sc, {"zoom": PR.P(-1.5, 1.6), "bonk": PR.P(face - 0.3, 1.7),
                               "boing": PR.P(box_x + 1.0, 0.6)})
    title = sc.beat("music", "cue", "title_sting")
    sc.screen.append(lambda t, m: [PR.title_card(_u(t, title["start_s"], title["end_s"] + 0.3))]
                     if t >= title["start_s"] else [])


ALBUM_AT, ALBUM_SCALE = (0.6, 1.75), 0.85


def world_box(x: float, y: float, w: float, h: float) -> list[float]:
    """World-space box (centre, size) -> normalised frame box [x0, y0, x1, y1] (0..1, y down)."""
    x, y, w, h = float(x), float(y), float(w), float(h)
    return [round((x - w / 2 + FRAME_X) / (2 * FRAME_X), 4), round((FRAME_Y - y - h / 2) / (2 * FRAME_Y), 4),
            round((x + w / 2 + FRAME_X) / (2 * FRAME_X), 4), round((FRAME_Y - y + h / 2) / (2 * FRAME_Y), 4)]


def keep_out(sc: Scene, kid: str, mob, start: float = 0.0, end: float | None = None, pad: float = 0.15) -> None:
    """M03.5: register an on-screen teaching visual (bounds of ``mob``) that burned-in subtitles must avoid."""
    c = mob.get_center()
    sc.keepouts.append({"id": kid, "box": world_box(float(c[0]), float(c[1]), mob.width + 2 * pad, mob.height + 2 * pad),
                        "start": round(max(0.0, start), 3), "end": round(sc.duration if end is None else end, 3)})


def stage_robot_family(sc: Scene) -> None:
    bolt = Performer("bolt", x=0.6, facing=-1, scale=SCALES["bolt"], expression="worried")
    maya = Performer("maya", x=-4.6, facing=1, scale=SCALES["maya"])
    nib = Performer("nib", x=6.1, y=4.1, facing=-1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    pop = sc.beat("sfx", "id", "toaster_pop")
    sc.back.append(lambda t, m: [PR.toaster(4.9, _u(t, pop["start_s"], pop["start_s"] + 0.7))])
    bolt.look(pop["start_s"], (1.0, 0.3))
    # SENSE / THINK / ACT chips pop as Maya says them
    chips = [(w.upper(), sc.word_time(w)) for w in ("sense", "think", "act")]
    sc.screen.append(lambda t, m: [PR.stc_chips(next((n for n, wt in reversed(chips) if wt and t >= wt), None))]
                     if chips[0][1] and chips[0][1] <= t < chips[0][1] + 12 else [])
    flip = sc.beat("sfx", "id", "page_flip")
    examples = ["vacuum", "arm", "rover"]
    reveal = [sc.word_time(w, after=flip["start_s"]) for w in examples]
    sc.facts["examples"] = examples

    def album(t, m):
        if t < flip["start_s"]:
            return []
        g = PR.album(examples, [_u(t, r, r + 0.5) if r else 0 for r in reveal], _u(t, flip["start_s"], flip["start_s"] + 0.5),
                     t=t)
        return [g.scale(ALBUM_SCALE).move_to(PR.P(*ALBUM_AT))]
    sc.front.append(album)
    n = len(examples)
    for i, (name, r) in enumerate(zip(examples, reveal)):     # M03.4: animated robot-family tiles (static-hold QA)
        if r:
            cx = -(2.1 * n + 0.6) / 2 + 0.3 + 2.1 * (i + 0.5)
            x, y = ALBUM_AT[0] + ALBUM_SCALE * cx, ALBUM_AT[1] + ALBUM_SCALE * 0.1
            sc.illustrations.append({"id": f"family-{name}", "kind": name, "start": round(r + 0.5, 3),
                                     "end": round(sc.duration, 3),
                                     "box": world_box(x, y, ALBUM_SCALE * 1.5, ALBUM_SCALE * 1.2)})
    generic_sfx_lettering(sc, {"toaster_pop": PR.P(4.9, 1.6)})


def stage_checkup(sc: Scene) -> None:
    bolt = Performer("bolt", x=0.2, facing=-1, scale=SCALES["bolt"])
    maya = Performer("maya", x=-4.4, facing=1, scale=SCALES["maya"])
    nib = Performer("nib", x=-1.9, y=4.0, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    parts = sc.params.get("parts", ["structure", "sensors", "actuators", "power", "controller"])
    words = {"structure": "structure", "sensors": "sensors", "actuators": "actuators", "power": "power",
             "controller": "controller"}
    ticks = [sc.word_time(words.get(p, p)) or 0.0 for p in parts]
    rig_parts = {"structure": ("body",), "sensors": ("screen",), "actuators": ("wheels", "arm_l", "arm_r"),
                 "power": ("belly",), "controller": ("bulb",)}
    sc.facts["parts"] = parts
    sc.front.append(lambda t, m: [PR.checklist(parts, [_u(t, k, k + 0.4) if k else 0 for k in ticks])
                                  .move_to(PR.P(4.9, 1.35))])

    def glow(t, m):
        out = []
        b = m.get("bolt")
        for name, k in zip(parts, ticks):
            if k and k <= t < k + 3.0 and b is not None:
                for rp in rig_parts.get(name, ()):
                    if rp in b.parts:
                        out.append(PR.glow_outline(b.parts[rp], (t - k) / 3.0))
                out.append(PR.part_label(name.capitalize(), b.get_top() + PR.P(0, 0.45), _u(t, k, k + 0.3)))
        return out
    sc.front.append(glow)
    plug = sc.beat("action", "do", "plug_in")
    low_t = sc.word_time("battery") or plug["start_s"] - 4
    maya.move(plug["start_s"] - 0.6, plug["start_s"], x=-3.2)
    maya.act(plug["start_s"], plug["end_s"], "point")
    maya.move(plug["end_s"] + 0.3, plug["end_s"] + 1.0, x=-4.4)

    def batt(t, m):
        if t < low_t:
            return []
        charging = t >= plug["end_s"]
        lvl = 0.18 + 0.82 * _u(t, plug["end_s"], plug["end_s"] + 4.0)
        out = [PR.battery(lvl, charging).scale(1.4).move_to(PR.P(2.6, -0.95))]
        b = m.get("bolt")
        if t >= plug["start_s"] and b is not None:
            out.insert(0, PR.cable(SOCKET_POS, b.get_left() + PR.P(0.25, -1.05), _u(t, plug["start_s"], plug["end_s"])))
        return out
    sc.back.append(lambda t, m: [])
    sc.front.append(batt)
    bolt.feel(low_t, "sleepy").feel(plug["end_s"] + 1.2, "happy")
    generic_sfx_lettering(sc, {"charge": PR.P(1.3, 1.25), "ding": PR.P(1.2, 2.1)})


def stage_sensor_ping(sc: Scene) -> None:
    bolt = Performer("bolt", x=-3.3, facing=1, scale=SCALES["bolt"])
    maya = Performer("maya", x=-5.75, facing=1, scale=SCALES["maya"])
    sensor_x = -3.3 + BOLT_FRONT * SCALES["bolt"] * 0.62
    sensor_y = GROUND + 1.55 * SCALES["bolt"] / 0.78
    rng = float(sc.params.get("rangeMeters", 3.0))
    d_nib = float(sc.params.get("obstacleDistanceMeters", 1.2))
    nib = Performer("nib", x=-5.0, y=4.9, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    sc.cast = ("maya", "bolt", "nib")
    sc.facts.update(rangeMeters=rng, nibMeters=d_nib)
    tape = PR.ruler(sensor_x, 4.0, step=0.5)
    sc.back.append(lambda t, m: [tape])
    keep_out(sc, "ruler", tape)
    keep_out(sc, "readout", PR.readout([("no echo...", "#EF476F"), (f"out of range (> {rng:g} m)", "#FFD166")],
                                       PR.P(3.6, 2.9)))
    nib_y = sensor_y - GROUND - 0.35
    flies = [b for b in sc.beats if b["type"] == "action" and b["do"].startswith("fly_to")]
    for f in flies:
        meters = float(f["do"].split(":")[1])
        nib.move(f["start_s"], f["end_s"], x=sensor_x + meters * METER + 0.43, y=nib_y, arc=0.8)
        nib.act(f["start_s"], f["end_s"], "fly_to").feel(f["start_s"], "proud")
    ret = sc.beat("action", "do", "return")
    nib.move(ret["start_s"], ret["end_s"], x=sensor_x + 2.0, y=3.6, arc=0.6).act(ret["start_s"], ret["end_s"], "return")
    pings = [b for b in sc.beats if b["type"] == "sfx" and b["id"] == "ping"]
    targets = [rng, d_nib]                                   # first ping: empty room (fades at range); second: Nib

    def waves(t, m):
        out = []
        for p_, reach_m in zip(pings, targets):
            t0 = p_["start_s"]
            if t0 <= t < t0 + 1.6:
                reach = reach_m * METER
                out.append(PR.ping_waves(PR.P(sensor_x, sensor_y), _u(t, t0, t0 + 0.8), reach))
                if reach_m < rng:
                    out.append(PR.ping_waves(PR.P(sensor_x, sensor_y), _u(t, t0 + 0.8, t0 + 1.6), reach, back=True))
        lost = sc.beat("line", "action", "ping")             # "Nib? Nib! My sensor can't find you!"
        if lost and lost["start_s"] <= t < lost["end_s"] + 0.3:
            out.append(PR.ping_waves(PR.P(sensor_x, sensor_y), ((t - lost["start_s"]) / 0.9) % 1.0, rng * METER))
        return out
    sc.front.append(waves)
    hit = pings[1]["start_s"] + 0.8 if len(pings) > 1 else None
    zone_t = sc.word_time("3 meters") or sc.word_time("up to")
    out_t = flies[1]["end_s"] if len(flies) > 1 else None

    def hud(t, m):
        out = []
        if zone_t and t >= zone_t:
            out.append(PR.range_zone(sensor_x, rng, _u(t, zone_t, zone_t + 0.8)))
        if hit and hit <= t < (out_t or 1e9) - 0.6:
            out.append(PR.readout([(f"distance: {d_nib:.2f} m", "#7CFFCB")], PR.P(3.6, 2.9), _u(t, hit, hit + 0.4)))
        if out_t and out_t <= t < ret["end_s"]:
            out.append(PR.readout([("no echo...", "#EF476F"), (f"out of range (> {rng:g} m)", "#FFD166")],
                                  PR.P(3.6, 2.9), _u(t, out_t, out_t + 0.4)))
        return out
    sc.back.append(hud)
    generic_sfx_lettering(sc, {"ping": PR.P(sensor_x + 0.6, sensor_y + 1.4), "whoosh": PR.P(4.5, 2.4)},
                          skip=("ping",))


def stage_rule_board(sc: Scene) -> None:
    thr = float(sc.params.get("thresholdMeters", 0.5))
    readings = [float(r) for r in sc.params.get("readings", [1.5, 1.0, 0.6, 0.4])]
    box_x = 5.6
    face = box_x - PR.BOX_W / 2
    s = SCALES["bolt"]

    def bx(d):
        return face - d * METER - BOLT_FRONT * s
    d_start = readings[0] + 0.5
    bolt = Performer("bolt", x=bx(d_start), facing=-1, scale=s)
    maya = Performer("maya", x=-5.6, facing=1, scale=SCALES["maya"])
    nib = Performer("nib", x=box_x + 0.2, y=PR.PILE_H - 0.02, facing=-1, scale=SCALES["nib"], expression="proud")
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    sc.facts.update(thresholdMeters=thr, readings=readings)
    pile = PR.box_pile(box_x)
    tape = PR.ruler_rev(face, 2.5, danger=thr)
    rule_line = sc.lines("maya")[1]
    words = ["IF", "distance", "<", f"{thr:g} m", "→", "STOP", "&", "TURN"]
    sc.back.append(lambda t, m: [pile, tape])
    keep_out(sc, "ruler", tape)
    keep_out(sc, "rule-board", PR.chalkboard(words, 1.0, at=PR.P(-1.2, 2.45), width=7.6, height=1.7),
             rule_line["start_s"] - 1)
    sc.screen.append(lambda t, m: [PR.chalkboard(words, _u(t, rule_line["start_s"], rule_line["end_s"]),
                                                 at=PR.P(-1.2, 2.45), width=7.6, height=1.7)] if t >= rule_line["start_s"] - 1 else [])
    expl = sc.lines("maya")[2]
    marks = [(n, sc.word_time(w, after=expl["start_s"] - 0.01)) for n, w in
             (("SENSE", "sense"), ("THINK", "think"), ("ACT", "act"))]

    def chips(t, m):
        if not marks[0][1] or t < marks[0][1]:
            return []
        active = next((n for n, wt in reversed(marks) if wt and t >= wt), None)
        return [PR.stc_chips(active if t < expl["end_s"] + 3 else None, at=PR.P(-1.2, 3.68))]
    sc.screen.append(chips)
    drive = sc.beat("action", "do", "drive")
    bolt.face(drive["start_s"] - 1.2, 1)
    reading_lines = [b for b in sc.lines("bolt") if re.match(r"^\s*\d", b["text"])]
    keys = []                      # (time the reading is reached, reading)
    bolt.move(drive["start_s"], drive["end_s"], x=bx(readings[0]))
    bolt.act(drive["start_s"], drive["end_s"], "drive")
    keys.append((drive["end_s"], readings[0]))
    prev_end = reading_lines[0]["end_s"] if reading_lines else drive["end_s"]
    for r, line in zip(readings[1:], reading_lines[1:]):
        t0 = max(prev_end - 0.9, keys[-1][0] + 0.2)
        t1 = line["start_s"]
        if r == readings[-1]:                                    # "...keep going... slowly"
            slow = next((b for b in sc.lines("bolt") if "slowly" in b["text"]), None)
            t0 = slow["start_s"] + 0.4 if slow else t0
        bolt.move(t0, t1, x=bx(r)).act(t0, t1, "drive")
        keys.append((t1, r))
        prev_end = line["end_s"]
    stop_t = keys[-1][0]
    bolt.act(stop_t, stop_t + 1.0, "skid")
    sc.facts["stopReading"] = keys[-1][1]

    def hud(t, m):
        if t < drive["start_s"]:
            return []
        cur = None
        for kt, r in keys:
            if t >= kt:
                cur = r
        if cur is None:
            return [PR.readout([("sensing...", "#7CFFCB"), (f"rule: stop if < {thr:g} m", "#FFFFFF")], PR.P(4.6, 1.45))]
        alert = cur < thr
        lines = [(f"distance: {cur:.2f} m", "#EF476F" if alert else "#7CFFCB"),
                 (f"{cur:g} < {thr:g}?  {'YES' if alert else 'NO'}", "#FFFFFF"),
                 ("STOP & TURN!" if alert else "keep going", "#FFD166" if alert else "#9AE6B4")]
        return [PR.readout(lines, PR.P(4.6, 1.45))]
    sc.screen.append(hud)
    sc.front.append(sfx_word("SKREEECH!", "#EF476F", stop_t, PR.P(-1.4, 0.3), dur=1.0))
    sparkle = sc.beat("sfx", "id", "sparkle")
    if sparkle:
        bolt.act(sparkle["start_s"] - 3.0, sparkle["end_s"], "ping")
    generic_sfx_lettering(sc, {}, skip=("skid", "ping", "chalk", "sparkle"))


def stage_servo_highfive(sc: Scene) -> None:
    bolt = Performer("bolt", x=-1.4, facing=1, scale=SCALES["bolt"])
    maya = Performer("maya", x=1.45, facing=-1, scale=SCALES["maya"])
    nib = Performer("nib", x=-4.6, y=4.2, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    miss = float(sc.params.get("missAngleDegrees", 30))
    goal = float(sc.params.get("endAngleDegrees", 60))
    sc.facts.update(missAngle=miss, endAngle=goal)
    arms = [b for b in sc.beats if b["type"] == "action" and b["do"].startswith("arm_to")]
    holds = []                                              # (start, reach_t, release_t, servo angle)
    for i, a in enumerate(arms):
        ang = float(a["do"].split(":")[1])
        nxt = arms[i + 1]["start_s"] - 0.5 if i + 1 < len(arms) else a["end_s"] + 3.2
        holds.append((a["start_s"], a["end_s"], nxt, ang))
        dur = (a["end_s"] - a["start_s"]) / 0.6          # arm_to eases over the first 60 % of the act
        bolt.act(a["start_s"], a["start_s"] + dur, f"arm_to:{90 + ang}")
        bolt.act(a["start_s"] + dur, nxt, f"arm_to_hold:{90 + ang}")
    clap = sc.beat("sfx", "id", "clap")
    if clap:
        maya.act(clap["start_s"] - 0.7, clap["start_s"] + 1.0, "highfive_reach")
    hf = sc.beat("action", "do", "highfive")
    if hf:
        nib.move(hf["start_s"] - 1.2, hf["start_s"], x=-3.2, y=2.2, arc=0.5)
    goal_t = sc.word_time("60 degrees") or sc.word_time("high-five")

    def gauge(t, m):
        b = m.get("bolt")
        if b is None or not goal_t or not (goal_t <= t < holds[-1][2] + 0.6):
            return []
        ang = 0.0
        for s0, s1, rel, a in holds:
            if s0 <= t < rel:
                ang = a * ease_in_out(_u(t, s0, s1))
        shoulder = b.parts["arm_r"].get_start()
        return [PR.protractor(shoulder, ang, facing=1, radius=1.25, target=goal)]
    sc.back.append(gauge)                              # behind the rigs so the real arm reads on top
    generic_sfx_lettering(sc, {"whoosh": PR.P(-3.2, 1.4), "clap": PR.P(0.2, 2.2)})


def stage_obstacle_rematch(sc: Scene, robotcam: dict | None = None) -> None:
    thr = float(sc.params.get("thresholdMeters", 0.5))
    box_x = 5.4
    face = box_x - PR.BOX_W / 2
    s = SCALES["bolt"]
    d0 = 2.4
    x0 = face - d0 * METER - BOLT_FRONT * s
    bolt = Performer("bolt", x=x0, facing=-1, scale=s)
    maya = Performer("maya", x=-5.7, facing=1, scale=SCALES["maya"])
    nib = Performer("nib", x=-3.4, y=4.6, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    drive_line = next(b for b in sc.lines("bolt") if b.get("action") == "drive")
    stop_line = next(b for b in sc.lines("bolt") if b.get("action") == "stop")
    ping = sc.beat("action", "do", "ping")
    stop_t = ping["end_s"] if ping else stop_line["start_s"]
    a = plan_approach(drive_line["start_s"] + 0.6, stop_t, d0, thr,
                      stop_at=robotcam.get("stop_reading") if robotcam else None)   # same number as the robot-cam
    assert_no_collision(a)
    sc.facts.update(thresholdMeters=thr, stopReading=a.reading(a.stop_t), stopDistance=a.stop_d, approach=a)
    bolt.face(drive_line["start_s"], 1)
    # drive as a dense keyframe list so Bolt's x follows the kinematics exactly
    n = max(2, int((a.stop_t - a.t0) * 10))
    for k in range(n):
        t0_, t1_ = a.t0 + (a.stop_t - a.t0) * k / n, a.t0 + (a.stop_t - a.t0) * (k + 1) / n
        bolt.move(t0_, t1_, x=face - a.distance(t1_) * METER - BOLT_FRONT * s, ease="linear")
    bolt.act(a.t0, a.stop_t, "drive").act(a.stop_t, a.stop_t + 0.5, "stop").feel(a.stop_t, "surprised")
    turn, resume = sc.beat("action", "do", "turn"), sc.beat("action", "do", "resume")
    stop_x = face - a.stop_d * METER - BOLT_FRONT * s
    bolt.act(turn["start_s"], turn["end_s"], "turn")
    bolt.move(resume["start_s"], resume["end_s"] + 0.8, x=stop_x - 2.4).act(resume["start_s"], resume["end_s"], "resume")
    spin_line = next((b for b in sc.lines("bolt") if b.get("action") == "spin"), None)
    bonk = sc.beat("sfx", "id", "bonk")
    if spin_line and bonk:                                   # victory spin drifts backwards into the boxes: BONK
        bolt.act(spin_line["start_s"], bonk["start_s"], "spin")
        bolt.move(spin_line["start_s"], bonk["start_s"], x=face - BOLT_FRONT * s, ease="in")
        bolt.act(bonk["start_s"], bonk["start_s"] + 0.7, "bonk").feel(bonk["start_s"], "dizzy")
        bolt.move(bonk["start_s"], bonk["start_s"] + 0.6, x=face - BOLT_FRONT * s - 0.5, ease="out")
    pile = PR.box_pile(box_x)
    tape = PR.ruler_rev(face, 3.0, danger=thr)
    sc.back.append(lambda t, m: [pile, tape])
    keep_out(sc, "ruler", tape)

    def hud(t, m):
        if t < a.t0 - 0.3 or t > resume["end_s"] + 1.5:
            return []
        r = a.reading(t)
        alert = r < thr
        lines = [(f"distance: {r:.2f} m", "#EF476F" if alert else "#7CFFCB"), (f"rule: stop if < {thr:g} m", "#FFFFFF")]
        if alert:
            lines.append(("path clear → GO" if t >= resume["start_s"] else "STOP & TURN!", "#FFD166"))
        return [PR.readout(lines, PR.P(4.3, 2.75))]
    sc.screen.append(hud)

    def waves(t, m):
        b = m.get("bolt")
        if b is None or not (a.t0 <= t < a.stop_t):
            return []
        x = b.get_right()[0] - 0.2
        return [PR.ping_waves(PR.P(x, GROUND + 1.55), ((t - a.t0) / 0.6) % 1.0, max(0.3, face - x))]
    sc.front.append(waves)
    sc.front.append(sfx_word("SKREEECH!", "#EF476F", a.stop_t, PR.P(face - 1.2, 1.3), dur=1.0))
    generic_sfx_lettering(sc, {"bonk": PR.P(face + 0.2, 1.7)}, skip=("ping", "motor"))
    if robotcam:
        start = max(0.0, a.stop_t - robotcam.get("lead", 2.6))
        end = min(stop_line["end_s"], a.stop_t + robotcam.get("tail", 1.9))
        sc.cutaways.append({"start": round(start * FPS) / FPS, "end": round(end * FPS) / FPS, "clip": robotcam["clip"],
                            "clip_offset": robotcam["stop_s"] - (a.stop_t - start)})


def stage_recap_chant(sc: Scene) -> None:
    bolt = Performer("bolt", x=1.6, facing=-1, scale=SCALES["bolt"])
    maya = Performer("maya", x=-3.4, facing=1, scale=SCALES["maya"])
    nib = Performer("nib", x=5.3, y=2.3, facing=-1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    sc.set_variant = "default"
    chants = [("SENSE", "#4CC9F0"), ("THINK", "#FFD166"), ("ACT", "#06D6A0")]
    lines = sc.lines()[:3]
    for (word, color), b, x in zip(chants, lines, (-4.7, 0.0, 4.7)):
        sc.screen.append(sfx_word(word, color, b["start_s"], PR.P(x, 2.6), dur=2.9 - (b["start_s"] - lines[0]["start_s"]),
                                  size=100))
    q = sc.params.get("question", "")
    sc.facts["question"] = q
    q_line = next((b for b in sc.lines("maya") if q and q.split()[0] in b["text"] and "question" in b["text"]), None)
    outro = sc.beat("music", "cue", "outro")
    if q_line:
        sc.screen.append(lambda t, m: [PR.card("Quiz time!", q, _u(t, q_line["start_s"], q_line["start_s"] + 0.6),
                                               at=PR.P(-0.4, 2.45), width=8.4)] if q_line["start_s"] <= t < outro["start_s"] else [])
    dance = sc.beat("action", "do", "beep_dance")
    if dance:
        sc.front.append(lambda t, m: [PR.speech_bubble("beep boop!", m["nib"].get_top() + PR.P(-0.2, 0.05),
                                                       _u(t, dance["start_s"], dance["end_s"] + 0.6),
                                                       m["nib"].get_top() + PR.P(0.3, 1.0))]
                        if "nib" in m and dance["start_s"] <= t < dance["end_s"] + 0.6 else [])
    sc.screen.append(lambda t, m: [PR.title_card(min(0.8, _u(t, outro["start_s"], outro["start_s"] + 3.0)),
                                                 subtitle="See you next time!")] if t >= outro["start_s"] else [])


def stage_character_intro(sc: Scene) -> None:
    """M03.1 generated cast intro: each character enters (registry entrance), gets a spotlight and a nameplate
    (display name in its caption colour + personality tagline) while its intro line plays; all stay in a lineup."""
    cards = sc.params.get("characters", [])
    n = len(cards)
    slots = [(-4.6 + 9.2 * i / max(1, n - 1)) if n > 1 else 0.0 for i in range(n)]
    segs = []
    for i, (c, x) in enumerate(zip(cards, slots)):
        cid = c["id"]
        ent = next((b for b in sc.beats if b["type"] == "action" and b["who"] == cid), None)
        t0 = ent["start_s"] if ent else 0.0
        t1 = ent["end_s"] if ent else 0.6
        fly = c.get("entrance") == "fly_to"
        side = -1 if x < 0 else 1
        y = 2.6 if fly else 0.0
        start_x = x + side * 9.0 if not fly else 9.5
        p = Performer(cid, x=start_x, y=(5.0 if fly else 0.0), facing=-side if not fly else -1,
                      scale=SCALES.get(cid, 0.8) * (1.3 if fly else 1.0), airborne=fly)
        if c.get("entrance") == "zoom":
            p.move(t0, t1, x=x, ease="out").act(t0, t1, "zoom").act(t1, t1 + 0.6, "skid")
        elif fly:
            p.move(t0, t1, x=x, y=y, arc=0.8).act(t0, t1, "fly_to")
        else:
            p.move(t0, t1, x=x).act(t0, t1, "enter")
        p.face(t1 + 0.3, 1 if x < 0 else -1 if x > 0 else 1)
        sc.perf[cid] = p
        sc.enter_at[cid] = round(t1, 3)
        segs.append((cid, c, x, t0, t1))
    sc.cast = tuple(c["id"] for c in cards)
    intro_facts = []
    for i, (cid, c, x, t0, t1) in enumerate(segs):
        end = segs[i + 1][3] if i + 1 < len(segs) else sc.duration - 0.2
        line = next((b for b in sc.lines() if b.get("target") == cid), None)
        at = PR.P(max(-3.4, min(3.4, x)), 2.75)

        def plate(t, m, c=c, t1=t1, end=end, at=at):
            return [PR.nameplate(c["name"], c["tagline"], c.get("color", "#FFFFFF"), _u(t, t1 - 0.1, end), at, t)] \
                if t1 - 0.1 <= t < end else []

        def light(t, m, x=x, t0=t0, end=end, cy=(3.2 if c.get("entrance") == "fly_to" else 1.7)):
            if not (t0 <= t < end + 0.4):
                return []
            u = _u(t, t0, t0 + 0.5) * (1 - _u(t, end, end + 0.4))
            return [PR.spotlight(x, u, t, cy=cy)]
        sc.back.append(light)
        sc.screen.append(plate)
        intro_facts.append({"id": cid, "name": c["name"], "tagline": c["tagline"], "plate": [round(t1 - 0.1, 3), round(end, 3)],
                            "line": line["text"] if line else None, "lineStart": line["start_s"] if line else None})
    sc.facts["introduced"] = intro_facts


STAGING = {"cartoon_cold_open": stage_cold_open, "cartoon_robot_family": stage_robot_family,
           "cartoon_robot_checkup": stage_checkup, "cartoon_sensor_ping": stage_sensor_ping,
           "cartoon_rule_board": stage_rule_board, "cartoon_servo_highfive": stage_servo_highfive,
           "cartoon_obstacle_rematch": stage_obstacle_rematch, "cartoon_recap_chant": stage_recap_chant,
           "cartoon_character_intro": stage_character_intro}


# ------------------------------------------------------------------------------------------ build + render

def build_scene(spec_scene: dict, timing_scene: dict, voice_dir: Path, robotcam: dict | None = None,
                trans_out: str | None = None, trans_half: float = 0.4) -> Scene:
    sc = Scene(timing_scene["sceneId"], spec_scene["template"], spec_scene.get("parameters", {}),
               timing_scene["beats"], timing_scene["scene_duration_s"], Path(voice_dir))
    tin = spec_scene.get("transitionIn")
    sc.trans_in = tin if tin not in (None, "cut") else None
    sc.trans_out = trans_out if trans_out not in (None, "cut") else None
    sc.trans_half = trans_half
    stage = STAGING[sc.template]
    if sc.template == "cartoon_obstacle_rematch":
        stage(sc, robotcam)
    else:
        stage(sc)
    stage_concept_cards(sc, spec_scene.get("concepts") or [])
    stage_shots(sc, spec_scene.get("shots") or [])
    perform_dialogue(sc)
    for p in sc.perf.values():
        p.finalize(sc.duration)
    sc.facts["transitions"] = {"in": sc.trans_in, "out": sc.trans_out, "half": trans_half}
    return sc


def stage_concept_cards(sc: Scene, concepts: list[dict]) -> None:
    """M03.2: an animated title card plays during each ``concept_sting`` music beat (one per concept marker, in
    ``beforeBeat`` order), i.e. right before the beats that teach the concept."""
    stings = [b for b in sc.beats if b["type"] == "music" and b.get("cue") == "concept_sting"]
    cards = []
    for c, b in zip(sorted(concepts, key=lambda c: c.get("beforeBeat", 0)), stings):
        t0, t1 = b["start_s"], b["end_s"]
        nxt = next((x["start_s"] for x in sc.lines() if x["start_s"] >= t0), sc.duration)
        card = {"id": c["id"], "title": c["title"], "subtitle": c.get("subtitle", ""), "icon": c.get("icon", ""),
                "start": round(t0, 3), "end": round(t1, 3), "teachStart": round(nxt, 3)}
        cards.append(card)
        sc.screen.append(lambda t, m, c=card: [PR.concept_card(c["title"], c["subtitle"], c["icon"],
                                                                _u(t, c["start"], c["end"]), t)]
                         if c["start"] <= t < c["end"] else [])
    sc.concepts = cards
    sc.facts["conceptCards"] = cards


# ------------------------------------------------------------------------------------------ M05.1 shots

SHOT_IN, SHOT_OUT = 0.4, 0.35          # seconds of the pop-in / shrink-out animation
SHOT_LEAD, SHOT_TAIL = 0.15, 0.35      # shot starts a little before its first beat, ends after its last
SOLO_GAIN = 1.2                         # solo character drawn a bit bigger than on stage
CORNER_GAIN = 0.55                      # illustration corner character


def _ctx_robot_families(sc: Scene, sh: dict) -> dict:
    examples = sc.facts.get("examples") or ["vacuum", "arm", "rover"]
    return {"examples": examples, "reveal": [sc.word_time(w, after=sh["start"]) for w in examples]}


def _ctx_echo(sc: Scene, sh: dict) -> dict:
    ping = next((b["start_s"] for b in sc.beats if b["type"] == "sfx" and b["id"] == "ping"
                 and sh["start"] <= b["start_s"] < sh["end"]), sh["start"] + 0.6)
    return {"ping": ping, "faster": sc.word_time("faster", after=sh["start"]),
            "bats": sc.word_time("bats", after=sh["start"])}


def _ctx_sta(sc: Scene, sh: dict) -> dict:
    out = {w: sc.word_time(w, after=sh["start"]) for w in ("sense", "think", "act")}
    thr = sc.params.get("thresholdMeters")
    out["threshold"] = float(thr) if thr is not None else None
    if thr is not None:
        sc.facts["shotThresholdMeters"] = float(thr)
    return out


SHOT_CONTEXT = {"robot_families": _ctx_robot_families, "echo_diagram": _ctx_echo, "sense_think_act": _ctx_sta}


def shot_at(sc: Scene, t: float) -> dict | None:
    return next((sh for sh in sc.shots if sh["start"] <= t < sh["end"]), None)


def shot_character_place(sh: dict) -> tuple[float, float, float, int]:
    """(x, feet y, scale, facing) of the character drawn in a shot."""
    from robotics101.cartoon.layout import CONTENT_FLOOR_Y
    from robotics101.cartoon.visuals import SOLO_X
    cid = sh["character"]
    if sh["layout"] == "solo":
        return SOLO_X, CONTENT_FLOOR_Y, SCALES[cid] * SOLO_GAIN, 1
    left = sh.get("corner", "left") == "left"
    return (-5.9 if left else 5.9), CONTENT_FLOOR_Y + 0.05, SCALES[cid] * CORNER_GAIN, 1 if left else -1


def stage_shots(sc: Scene, shots: list[dict]) -> None:
    """M05.1: illustration / solo shots cover the stage over their beat ranges with a full-frame backdrop, the wide
    teaching visual and (solo) the one character, who keeps performing (lip sync, gestures) from its Performer."""
    from robotics101.cartoon.layout import (CORNER_MAX_AREA, box_area, norm_box)
    from robotics101.cartoon import visuals as VZ
    k = transition_frames(sc) / FPS
    for spec in shots:
        if spec["layout"] == "stage":
            continue
        b0, b1 = sc.beats[spec["fromBeat"]], sc.beats[min(spec["toBeat"], len(sc.beats) - 1)]
        start = max(b0["start_s"] - SHOT_LEAD, k if sc.trans_in else 0.0,
                    max((c["end"] for c in sc.concepts if c["start"] <= b0["start_s"]), default=0.0))
        end = min(b1["end_s"] + SHOT_TAIL, sc.duration - (k if sc.trans_out else 0.0))
        sh = {"layout": spec["layout"], "visual": spec.get("visual") or "concept_robot",
              "character": spec.get("character"), "corner": spec.get("corner", "left"),
              "fromBeat": spec["fromBeat"], "toBeat": spec["toBeat"], "start": round(start, 3), "end": round(end, 3)}
        if sh["character"] and sh["character"] not in sc.perf:
            sh["character"] = None
        box = VZ.default_box(sh["layout"])
        sh["visualBox"] = norm_box(*box)
        sh["areaShare"] = round(box_area(sh["visualBox"]), 3)
        chars = []
        if sh["character"]:
            x, fy, scale, _ = shot_character_place(sh)
            cid = sh["character"]
            hw, h = HALF_W[cid] * scale / SCALES[cid], HEIGHT[cid] * scale / SCALES[cid]
            cb = norm_box(x - hw, fy, x + hw, fy + h)
            chars.append({"id": cid, "box": cb, "area": round(box_area(cb), 3)})
            if sh["layout"] == "illustration" and box_area(cb) > CORNER_MAX_AREA:
                raise ValueError(f"{sc.sid}: illustration corner character {cid} too big ({box_area(cb):.2f})")
        sh["characters"] = chars
        ctx = SHOT_CONTEXT.get(sh["visual"], lambda sc_, sh_: {})(sc, sh)
        if sh["visual"].startswith("concept_"):
            ctx = {"title": next((c["title"] for c in sc.concepts), "")}
        sc.shots.append(sh)
        if sh["visual"] == "robot_families":
            for name, r, (cx, cy, w, h) in zip(ctx["examples"], ctx["reveal"], VZ.family_tile_boxes(ctx)):
                if r:
                    sc.illustrations.append({"id": f"shot-family-{name}", "kind": name, "start": round(r + 0.5, 3),
                                             "end": sh["end"] - SHOT_OUT, "box": world_box(cx, cy, w, h)})
        fn = VZ.visual(sh["visual"])
        x0, y0, x1, y1 = box
        sc.keepouts.append({"id": f"shot-{sh['visual']}", "box": norm_box(*box), "start": sh["start"],
                            "end": sh["end"], "shot": sh["layout"]})

        def draw(t, m, sh=sh, fn=fn, ctx=ctx):
            if not (sh["start"] <= t < sh["end"]):
                return []
            g = [VZ.backdrop(sh["layout"], t), fn(t, ctx)]
            if sh["character"]:
                x, fy, scale, facing = shot_character_place(sh)
                st = sc.perf[sh["character"]].state(t)
                pose = st.pose.with_(facing=facing, gaze=(0.6, st.pose.gaze[1]))
                perf = sc.perf[sh["character"]]
                dy = (st.y - perf.position_at(t)[1]) * scale / perf.scale    # hops / bounces, not stage height
                g.append(build(sh["character"], pose).scale(scale, about_point=np.zeros(3))
                         .shift(np.array([x, fy + dy, 0])))
            from manim import VGroup
            grp = VGroup(*g)
            u_in, u_out = (t - sh["start"]) / SHOT_IN, (sh["end"] - t) / SHOT_OUT
            kk = PR.pop(u_in) if u_in < 1 else 1.0
            if u_out < 1:
                kk *= max(0.001, ease_in_out(u_out))
            if kk != 1.0:
                grp.scale(kk, about_point=np.zeros(3))
            return [grp]
        sc.top.append(draw)
    sc.facts["shots"] = sc.shots


def frame_layers(sc: Scene, t: float) -> tuple[dict, list, list]:
    """Characters (cid -> mob), world overlays (back + front) and HUD overlays (screen + shot layer) at ``t``."""
    mobs = {}
    for cid in sc.cast:
        p = sc.perf.get(cid)
        if p is None:
            continue
        st = p.state(t)
        g = build(cid, st.pose).scale(st.scale, about_point=np.zeros(3))
        g.shift(np.array([st.x, GROUND + st.y, 0]))
        mobs[cid] = g
    back = [m for f in sc.back for m in f(t, mobs)]
    over = [m for f in sc.front + sc.screen + sc.top for m in f(t, mobs)]
    return mobs, back, over


def _layer_name(f) -> str:
    code = getattr(f, "__code__", None)
    return f"{getattr(f, '__name__', 'overlay')}@{code.co_firstlineno if code else 0}"


def named_layers(sc: Scene, t: float, mobs: dict) -> tuple[list, list]:
    """Like ``frame_layers`` but each overlay mob is paired with the staging function that drew it (QA labels)."""
    back = [(f"{sc.template}:{_layer_name(f)}", m) for f in sc.back for m in f(t, mobs)]
    over = [(f"{sc.template}:{_layer_name(f)}", m) for f in sc.front + sc.screen + sc.top for m in f(t, mobs)]
    return back, over


def frame_fn(sc: Scene):
    bg = garage(sc.set_variant)

    def frame(t: float):
        mobs, back, over = frame_layers(sc, t)
        return [bg] + back + list(mobs.values()) + over + transition_overlay(sc, t)
    return frame


# ------------------------------------------------------------------------------------------ M05.2 caption band

BAND_SAMPLE_S = 0.25


def _content_boxes(mob, out: list, name: str) -> None:
    """Normalised boxes of the visible content in ``mob``; full-frame backdrops are skipped (their children are
    measured instead), so a card / shot backdrop doesn't count but what is drawn on it does."""
    from robotics101.cartoon.layout import FRAME_H, FRAME_W, norm_box
    if getattr(mob, "decor", False) or (not mob.has_points() and not mob.submobjects):
        return
    w, h = mob.width, mob.height
    if (w >= 0.92 * FRAME_W and h >= 0.92 * FRAME_H) or any(getattr(c, "decor", False) for c in mob.submobjects):
        for m in mob.submobjects:
            _content_boxes(m, out, name)
        return
    if w < 1e-3 or h < 1e-3:
        return
    if getattr(mob, "fill_opacity", 1) == 0 and getattr(mob, "stroke_opacity", 1) == 0:
        return
    x0, y0 = mob.get_corner(np.array([-1, -1, 0]))[:2]
    x1, y1 = mob.get_corner(np.array([1, 1, 0]))[:2]
    out.append((name, norm_box(x0, y0, x1, y1)))


def band_report(sc: Scene, step: float = BAND_SAMPLE_S) -> dict:
    """M05.2: sample the scene and measure how far characters / teaching visuals / props reach into the caption band
    (actual geometry of every drawn overlay and rig; transitions, robot-cam cutaways and shot pop animations are
    skipped). Returns the worst intrusion and the offenders (normalised height, 0 = clear)."""
    from robotics101.cartoon.layout import BAND_OVERLAP_TOL, band_overlap
    k = transition_frames(sc) / FPS
    worst, offenders, n = 0.0, {}, 0
    t = 0.0
    while t < sc.duration:
        skip = ((sc.trans_in and t < k) or (sc.trans_out and t >= sc.duration - k)
                or any(c["start"] <= t < c["end"] for c in sc.cutaways)
                or any(sh["start"] <= t < sh["start"] + SHOT_IN or sh["end"] - SHOT_OUT <= t < sh["end"]
                       for sh in sc.shots))
        if not skip:
            n += 1
            mobs, _, _ = frame_layers(sc, t)
            back, over = named_layers(sc, t, mobs)
            shot = shot_at(sc, t)
            card = any(c["start"] <= t < c["end"] for c in sc.concepts)
            boxes: list = []
            if not shot and not card:
                for cid, m in mobs.items():
                    boxes.append((cid, _bbox(m)))
                for name, m in back:
                    _content_boxes(m, boxes, name)
            for name, m in over:
                _content_boxes(m, boxes, name)
            for name, b in boxes:
                d = band_overlap(b)
                if d > BAND_OVERLAP_TOL:
                    o = offenders.setdefault(name, {"what": name, "maxIntrusion": 0.0, "first": round(t, 2), "n": 0})
                    o["n"] += 1
                    o["maxIntrusion"] = max(o["maxIntrusion"], round(d, 4))
                worst = max(worst, d)
        t += step
    return {"samples": n, "maxIntrusion": round(worst, 4), "offenders": list(offenders.values())}


def _bbox(m) -> list[float]:
    from robotics101.cartoon.layout import norm_box
    x0, y0 = m.get_corner(np.array([-1, -1, 0]))[:2]
    x1, y1 = m.get_corner(np.array([1, 1, 0]))[:2]
    return norm_box(x0, y0, x1, y1)


def transition_frames(sc: Scene) -> int:
    return max(1, round(sc.trans_half * FPS))


def transition_overlay(sc: Scene, t: float) -> list:
    """M03.2: in-half over the first frames (uncovering), out-half over the last frames (covering; the final frame is
    fully covered, identical to the next scene's first frame)."""
    n, k, total = round(t * FPS), transition_frames(sc), sc.n_frames
    if sc.trans_in and n < k:
        return [PR.transition(sc.trans_in, n / k, entering=True)]
    if sc.trans_out and n >= total - k:
        return [PR.transition(sc.trans_out, (n - (total - k) + 1) / k, entering=False)]
    return []


def presence(sc: Scene, t: float) -> dict[str, float]:
    """Visible fraction of each performer's nominal box inside the frame (analytic, for QA)."""
    out = {}
    for cid, p in sc.perf.items():
        x, y = p.position_at(t)
        hw, h = HALF_W[cid], HEIGHT[cid]
        x0, x1 = x - hw, x + hw
        y0, y1 = GROUND + y, GROUND + y + h
        vis_x = max(0.0, min(x1, FRAME_X) - max(x0, -FRAME_X)) / (2 * hw)
        vis_y = max(0.0, min(y1, FRAME_Y) - max(y0, -FRAME_Y)) / h
        out[cid] = round(vis_x * vis_y, 3)
    return out


def splice_cutaways(sc: Scene, video: Path, out: Path, width: int, height: int) -> Path:
    """Replace [start, end) of ``video`` with the robot-cam clip (scaled to the frame), keeping exact frame count."""
    if not sc.cutaways:
        return video
    c = sc.cutaways[0]
    s0, s1 = round(c["start"] * FPS), round(c["end"] * FPS)
    off = max(0.0, c["clip_offset"])
    filt = (f"[1:v]trim=start={off:.4f}:duration={(s1 - s0) / FPS:.4f},setpts=PTS-STARTPTS+{s0}/{FPS}/TB,"
            f"scale={width}:{height}:flags=lanczos,format=yuv420p,"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=0x2B2140:t={max(6, width // 120)}[cam];"
            f"[0:v][cam]overlay=enable='between(n,{s0},{s1 - 1})':eof_action=pass[v]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(video), "-i", str(c["clip"]), "-filter_complex", filt,
                    "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high",
                    "-pix_fmt", "yuv420p", "-frames:v", str(sc.n_frames), str(out)], check=True)
    return out


def load_inputs(spec_path: Path, voice_dir: Path) -> tuple[dict, dict]:
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    spec = expand_episode(json.loads(Path(spec_path).read_text(encoding="utf-8")), load_registry())
    timing = json.loads((Path(voice_dir) / "timing.json").read_text(encoding="utf-8"))
    return spec, timing


def render_cartoon_scenes(spec_path: Path, voice_dir: Path, out_dir: Path, width: int = 1920, height: int = 1080,
                          only: list[str] | None = None, robotcam: bool = True, log=print) -> dict:
    """Render every cartoon scene (video only) to ``<out>/scenes/<sceneId>.mp4``; writes ``<out>/scenes.json``."""
    import time

    from robotics101.cartoon.render2d import render_clip
    from robotics101.cartoon.robotcam import render_robotcam, robotcam_job, robotcam_stop

    spec, timing = load_inputs(spec_path, voice_dir)
    out_dir = Path(out_dir)
    (out_dir / "scenes").mkdir(parents=True, exist_ok=True)
    by_id = {s["sceneId"]: s for s in spec["scenes"]}
    order = [t["sceneId"] for t in timing["scenes"]]
    from robotics101.cartoon.episode import transition_settings
    half = transition_settings(spec)["seconds"] / 2
    report = {"width": width, "height": height, "fps": FPS, "transitionHalfSeconds": half, "scenes": []}
    for ts in timing["scenes"]:
        sid = ts["sceneId"]
        if only and sid not in only:
            continue
        ss = by_id[sid]
        cam = None
        if robotcam and ss["template"] == "cartoon_obstacle_rematch":
            thr = float(ss.get("parameters", {}).get("thresholdMeters", 0.5))
            job = robotcam_job(9.0, thr, clip_id=f"{sid}-robotcam")
            clip = out_dir / "robotcam" / "scenes" / f"{sid}-robotcam.mp4"
            if not clip.exists():
                log(f"  {sid}: rendering robot-cam insert (Blender, cartoon style, threshold {thr} m)")
                clip = render_robotcam(out_dir, 9.0, thr, clip_id=f"{sid}-robotcam",
                                       profile="full" if height >= 1080 else "preview")
            stop_s, stop_m = robotcam_stop(job)
            cam = {"clip": clip, "stop_s": stop_s, "stop_reading": stop_m}
        t0 = time.monotonic()
        i = order.index(sid)
        nxt = by_id[order[i + 1]].get("transitionIn") if i + 1 < len(order) else None
        sc = build_scene(ss, ts, Path(voice_dir), cam, trans_out=nxt, trans_half=half)
        raw = out_dir / "scenes" / (f"{sid}.2d.mp4" if sc.cutaways else f"{sid}.mp4")
        render_clip(frame_fn(sc), sc.n_frames, raw, fps=FPS, width=width, height=height, background="#FFE8C2")
        final = out_dir / "scenes" / f"{sid}.mp4"
        if sc.cutaways:
            splice_cutaways(sc, raw, final, width, height)
            raw.unlink()
        samples = [round(k * 0.5, 2) for k in range(int(sc.duration * 2) + 1)]
        pres = {cid: min((presence(sc, t)[cid] for t in samples
                          if (t >= 6.0 or sc.template != "cartoon_cold_open") and t >= sc.enter_at.get(cid, 0.0)),
                         default=0.0)
                for cid in sc.perf}
        from robotics101.cartoon.liveliness import scene_liveliness
        live = scene_liveliness(sc, presence, HEIGHT, SCALES)
        band = band_report(sc)
        facts = {k: v for k, v in sc.facts.items() if k != "approach"}
        from robotics101.cartoon.lipsync import lipsync_agreement
        agree = {f"{sid}#{b['index']}": round(lipsync_agreement(sc.perf[b["speaker"]].mouth, Path(voice_dir) / b["wav"],
                                                                 b["start_s"]), 3)
                 for b in sc.lines() if b["speaker"] in sc.perf}
        report["scenes"].append({"sceneId": sid, "template": sc.template, "frames": sc.n_frames,
                                 "duration_s": sc.duration, "video": str(final.relative_to(out_dir)),
                                 "minPresence": pres, "enterAt": sc.enter_at, "lipsync": sc.lipsync_methods,
                                 "lipsyncAgreement": agree, "liveliness": live, "captionBand": band,
                                 "illustrations": sc.illustrations, "keepouts": sc.keepouts, "facts": facts,
                                 "cutaways": [{**c, "clip": str(Path(c["clip"]).relative_to(out_dir))}
                                              for c in sc.cutaways],
                                 "render_s": round(time.monotonic() - t0, 1)})
        log(f"  {sid}: {sc.n_frames} frames in {time.monotonic() - t0:.1f}s -> {final}")
    rp = out_dir / "scenes.json"
    if only and rp.exists():                                   # partial re-render: merge with earlier entries
        old = json.loads(rp.read_text(encoding="utf-8"))
        if (old.get("width"), old.get("height")) == (width, height):
            done = {x["sceneId"] for x in report["scenes"]}
            report["scenes"] = sorted([x for x in old["scenes"] if x["sceneId"] not in done] + report["scenes"],
                                      key=lambda x: x["sceneId"])
    rp.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    return report
