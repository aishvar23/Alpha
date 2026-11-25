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
from robotics101.cartoon.obstacle import BOLT_FRONT, Approach, assert_no_collision, hud_lines, plan_approach
from robotics101.cartoon.rigs import build
from robotics101.cartoon.backgrounds import backdrop
from robotics101.cartoon.sets import GROUND, METER, SOCKET_POS

FPS = 30
SCALES = {"bolt": 0.78, "maya": 0.8, "nib": 0.95}
HALF_W = {"bolt": 1.58, "maya": 1.2, "nib": 0.53}       # nominal half widths (world units, at SCALES)
HEIGHT = {"bolt": 3.3, "maya": 3.96, "nib": 1.12}
FRAME_X, FRAME_Y = 7.11, 4.0
STAGED_LINE_ACTIONS = {"drive", "stop", "resume", "skid", "spin", "turn"}   # handled by template staging
Overlay = Callable[[float, dict], list]


_WORDS_CACHE: dict = {}


def line_words(voice_dir, b: dict) -> list[dict] | None:
    """Word alignment of a timing line beat in scene seconds: [{text, start_s, end_s}] or None. The words file
    (``<voice line>.words.json``, written by the voice stage from the ElevenLabs alignment) is relative to the
    line start (M05.8)."""
    rel = b.get("words")
    if not rel or voice_dir is None:
        return None
    path = Path(voice_dir) / rel
    key = (str(path), b.get("start_s"))
    if key not in _WORDS_CACHE:
        try:
            import json as _json
            ws = _json.loads(path.read_text(encoding="utf-8")).get("words") or []
        except (OSError, ValueError):
            ws = []
        lead = float(b.get("lead_s") or 0.0)
        _WORDS_CACHE[key] = [{"text": w["text"], "start_s": round(b["start_s"] + lead + float(w["start_s"]), 3),
                              "end_s": round(b["start_s"] + lead + float(w["end_s"]), 3)} for w in ws] or None
    return _WORDS_CACHE[key]


def _token_index(text: str, offset: int) -> int:
    return len(text[:offset].split())


def word_time_in_line(voice_dir, b: dict, word: str) -> float | None:
    m = re.search(rf"\b{re.escape(word)}", b["text"], re.I)
    if not m:
        return None
    ws = line_words(voice_dir, b)
    if ws and len(ws) == len(b["text"].split()):
        return ws[min(_token_index(b["text"], m.start()), len(ws) - 1)]["start_s"]
    return b["start_s"] + (b["end_s"] - b["start_s"]) * m.start() / max(1, len(b["text"]))


def word_end_in_line(voice_dir, b: dict, word: str) -> float | None:
    """End time of the last token of the first match of ``word`` in the line."""
    m = re.search(rf"\b{re.escape(word)}\w*", b["text"], re.I)
    if not m:
        return None
    ws = line_words(voice_dir, b)
    if ws and len(ws) == len(b["text"].split()):
        return ws[min(_token_index(b["text"], m.end() - 1), len(ws) - 1)]["end_s"]
    return b["start_s"] + (b["end_s"] - b["start_s"]) * m.end() / max(1, len(b["text"]))


def line_span(voice_dir, b: dict) -> tuple[float, float]:
    ws = line_words(voice_dir, b)
    if ws:
        return ws[0]["start_s"], ws[-1]["end_s"]
    return b["start_s"], b["end_s"]




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
    background: dict = field(default_factory=lambda: {"theme": "workshop", "palette": "sunny"})   # M05.5 section set
    top_busy: list = field(default_factory=list)            # M05.5 (start, end) when the top-centre band is in use

    @property
    def n_frames(self) -> int:
        return round(self.duration * FPS)

    def lines(self, speaker: str | None = None) -> list[dict]:
        return [b for b in self.beats if b["type"] == "line" and (speaker is None or b["speaker"] == speaker)]

    def beat(self, type_: str, key: str, value: str, nth: int = 0) -> dict | None:
        hits = [b for b in self.beats if b["type"] == type_ and str(b.get(key, "")).split(":")[0] == value]
        return hits[nth] if len(hits) > nth else None

    def line_words(self, b: dict) -> list[dict] | None:
        """M05.8: the ElevenLabs word alignment of a line (scene seconds), or None (fixture / espeak voices)."""
        return line_words(self.voice_dir, b)

    def word_time(self, word: str, after: float = 0.0) -> float | None:
        """Time a word is spoken (first match whose line ends after ``after``). M05.8: uses the real ElevenLabs
        word timings when the line has them; the old character-fraction estimate is only the fallback."""
        for b in self.lines():
            if b["end_s"] < after:
                continue
            t = word_time_in_line(self.voice_dir, b, word)
            if t is not None:
                return t
        return None

    def line_span(self, b: dict) -> tuple[float, float]:
        """(first word start, last word end) of a line in scene seconds (aligned when available)."""
        return line_span(self.voice_dir, b)


FIT_MARGIN = 0.025            # M05.8: overlays are nudged inside the frame with this margin (QA uses SAFE_MARGIN)


def fit_in_frame(mob, margin: float = FIT_MARGIN, shrink: bool = False):
    """M05.8 pipeline default: shift an overlay (SFX lettering, cards, chips, plates, bubbles) so its whole box
    sits inside the frame with ``margin`` (fraction of each dimension) to spare. No-op when it already fits.
    ``shrink`` scales it down about its bottom edge instead of moving it (for plates that must not drop onto
    a face)."""
    from robotics101.cartoon.layout import FRAME_X, FRAME_Y
    if not (mob.has_points() or mob.submobjects):
        return mob
    (x0, y0), (x1, y1) = mob.get_corner(np.array([-1, -1, 0]))[:2], mob.get_corner(np.array([1, 1, 0]))[:2]
    lx, ly = FRAME_X * (1 - 2 * margin), FRAME_Y * (1 - 2 * margin)
    if shrink and y1 > ly and y0 < ly:
        mob.scale(float((ly - y0) / (y1 - y0)), about_point=np.array([float((x0 + x1) / 2), float(y0), 0.0]))
        (x0, y0), (x1, y1) = mob.get_corner(np.array([-1, -1, 0]))[:2], mob.get_corner(np.array([1, 1, 0]))[:2]
    dx = (-lx - x0) if x0 < -lx else (lx - x1) if x1 > lx else 0.0
    dy = (-ly - y0) if y0 < -ly else (ly - y1) if y1 > ly else 0.0
    if dx or dy:
        mob.shift(np.array([float(dx), float(dy), 0.0]))
    return mob


def sfx_word(word: str, color: str, start: float, at, dur: float = 0.9, size: int = 88, shrink: bool = False) -> Overlay:
    return lambda t, m: [fit_in_frame(PR.sfx_text(word, color, (t - start) / dur, at, size=size), shrink=shrink)] \
        if start <= t < start + dur else []


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
    perform_acting(sc)


def perform_acting(sc: Scene) -> None:
    """M05.3 acting defaults: every line gets an emotion pose (authored ``pose`` or ``acting.auto_pose``), the
    listeners react (``react`` or ``acting.auto_react``), emotional action beats get the matching pose, and
    celebration cues (victory/chant/title stings, sparkle/ding/clap sfx) make the characters dance."""
    from robotics101.cartoon import acting as ACTING
    last = None
    for b in sc.beats:
        if b["type"] == "line" and b["speaker"] in sc.perf:
            p = sc.perf[b["speaker"]]
            name = ACTING.auto_pose(b)
            p.emote(b["start_s"], name, 1.0, end=min(b["end_s"] + 0.3, b["start_s"] + ACTING.pose_duration(name)))
            rx = ACTING.auto_react(b, name)
            if rx:
                for cid, other in sc.perf.items():
                    if cid != b["speaker"] and cid in sc.cast:
                        other.emote(b["start_s"] + 0.35, rx[0], rx[1])
            last = b["speaker"]
        elif b["type"] == "action" and b["who"] in sc.perf and b.get("emotion") in ACTING.EMOTION_TO_POSE:
            sc.perf[b["who"]].emote(b["start_s"], ACTING.EMOTION_TO_POSE[b["emotion"]], 0.9)
        elif b["type"] == "music" and b.get("cue") in ACTING.CELEBRATION_CUES:
            d = max(1.6, b["end_s"] - b["start_s"])
            for cid, perf in sc.perf.items():
                if cid in sc.cast:
                    perf.emote(b["start_s"], "celebrate", 1.0 if cid != "nib" else 0.8, end=b["start_s"] + d)
        elif b["type"] == "sfx" and b.get("id") in ACTING.CELEBRATION_SFX and last in sc.perf:
            sc.perf[last].emote(b["start_s"], "celebrate", 0.9)


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
    sc.facts["examples"] = examples
    # M05.6: the family examples are full-screen one-example illustration shots, not a stage album grid.
    # M05.8: the pop now plays on stage (the toaster frame waits for its own line): POP! sits left of the
    # toaster, below Nib and right of Bolt, never over a face.
    generic_sfx_lettering(sc, {"toaster_pop": PR.P(3.5, -0.3)})


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
    # M05.7: compact card in the top-right, above head height, so it never covers Maya after she
    # steps to Bolt's right for the charge.
    # M05.8: anchored by its top-right corner inside the 5% action-safe area (QA layout.overlays_in_frame);
    # the M05.7 centre (5.45, 2.98) put the title row above the top edge.
    sc.front.append(lambda t, m: [PR.checklist(parts, [_u(t, k, k + 0.4) if k else 0 for k in ticks])
                                  .scale(CHECKLIST_SCALE).move_to(PR.P(*CHECKLIST_CORNER), aligned_edge=np.array([1.0, 1.0, 0.0]))])

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
    # Maya steps to Bolt's RIGHT before the cable appears, facing him, so the floor-routed lead never crosses her.
    maya.face(plug["start_s"] - 0.8, -1)
    maya.move(plug["start_s"] - 0.8, plug["start_s"] - 0.05, x=3.15)
    maya.act(plug["start_s"], plug["end_s"], "point")

    def batt(t, m):
        if t < low_t:
            return []
        charging = t >= plug["end_s"]
        lvl = 0.18 + 0.82 * _u(t, plug["end_s"], plug["end_s"] + CHARGE_FILL_S)
        # Big HUD battery: upper-left, above standing head height and left of Nib's hover.
        out = [PR.battery(lvl, charging).scale(2.2).move_to(PR.P(-5.25, 2.72))]
        b, may = m.get("bolt"), m.get("maya")
        if t >= plug["start_s"] and b is not None:
            port = PR.bolt_charge_port(b)
            lead = PR.charge_lead(SOCKET_POS, port, _u(t, plug["start_s"], plug["end_s"]))
            out.insert(0, lead)
            if may is not None and t >= plug["end_s"] - 0.05:
                box = [float(may.get_left()[0]), float(may.get_bottom()[1]),
                       float(may.get_right()[0]), float(may.get_top()[1])]
                pts = [[float(p[0]), float(p[1])] for p in lead.cable_points]
                sc.facts["chargeCable"] = {"points": pts, "mayaBox": [round(v, 3) for v in box],
                                           "crossesMaya": PR.cable_crosses_box(lead.cable_points, box),
                                           "level": round(lvl, 3), "charging": charging}
        return out
    sc.back.append(lambda t, m: [])
    sc.front.append(batt)
    # M05.8: Bolt dozes from "sleepy" until his yawn line (said while the battery fills) is over, then perks up.
    sleepy_t = min(t for t in (sc.word_time("sleepy"), low_t) if t is not None)
    yawn = next((b for b in sc.beats if b["type"] == "line" and b.get("speaker") == "bolt"
                 and b["start_s"] >= plug["end_s"] - 0.05), None)
    perk = yawn["end_s"] if yawn and yawn["start_s"] < plug["end_s"] + 1.5 else plug["end_s"] + 1.2
    bolt.feel(sleepy_t, "sleepy").feel(perk, "happy")
    # BZZT! / DING! sit above Bolt, left of Maya's charge stand, so they never cover a face.
    # Above Bolt, in the gap between Nib (left-high) and Maya after she steps right.
    generic_sfx_lettering(sc, {"charge": PR.P(0.45, 2.70), "ding": PR.P(0.55, 2.95)})


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
    # Raised and shifted right so Maya's hop never goes through the board (M05.7).
    board_at, board_wh = PR.P(0.20, 2.95), dict(width=7.2, height=1.40)
    keep_out(sc, "rule-board", PR.chalkboard(words, 1.0, at=board_at, **board_wh),
             rule_line["start_s"] - 1)
    sc.screen.append(lambda t, m: [PR.chalkboard(words, _u(t, rule_line["start_s"], rule_line["end_s"]),
                                                 at=board_at, **board_wh)] if t >= rule_line["start_s"] - 1 else [])
    expl = sc.lines("maya")[2]
    marks = [(n, sc.word_time(w, after=expl["start_s"] - 0.01)) for n, w in
             (("SENSE", "sense"), ("THINK", "think"), ("ACT", "act"))]

    def chips(t, m):
        if not marks[0][1] or t < marks[0][1]:
            return []
        active = next((n for n, wt in reversed(marks) if wt and t >= wt), None)
        return [fit_in_frame(PR.stc_chips(active if t < expl["end_s"] + 3 else None, at=PR.P(0.20, 3.85)))]
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


SERVO_HOLD_AFTER_S = 3.2                 # last servo angle is held this long after its move


def servo_track(sc: Scene) -> list[tuple[float, float, float, float, float]]:
    """M05.8: the scene's servo angle track from its ``arm_to:<deg>`` actions: (start, reach, release, from, to) in
    servo degrees (0 = arm straight forward, 90 = straight up). Each move starts from the previous angle (the first
    from 0, "ready"), eases over the action and holds until the next move. Stage arm and split dial both use it."""
    arms = [b for b in sc.beats if b["type"] == "action" and str(b["do"]).startswith("arm_to:")]
    out, prev = [], 0.0
    for i, a in enumerate(arms):
        ang = float(a["do"].split(":")[1])
        rel = arms[i + 1]["start_s"] if i + 1 < len(arms) else a["end_s"] + SERVO_HOLD_AFTER_S
        out.append((a["start_s"], a["end_s"], rel, prev, ang))
        prev = ang
    return out


def servo_angle(track, t: float) -> float:
    """Servo angle (degrees) at time ``t`` on a ``servo_track``."""
    if not track or t <= track[0][0]:
        return 0.0
    for s0, s1, rel, a0, a1 in track:
        if t < s0:
            break
        if t < s1:
            return a0 + (a1 - a0) * ease_in_out((t - s0) / max(1e-6, s1 - s0))
        ang = a1
    return ang


def stage_servo_highfive(sc: Scene) -> None:
    bolt = Performer("bolt", x=-1.4, facing=1, scale=SCALES["bolt"])
    maya = Performer("maya", x=1.45, facing=-1, scale=SCALES["maya"])
    nib = Performer("nib", x=-4.6, y=4.2, facing=1, scale=SCALES["nib"], airborne=True)
    sc.perf = {"maya": maya, "bolt": bolt, "nib": nib}
    miss = float(sc.params.get("missAngleDegrees", 30))
    goal = float(sc.params.get("endAngleDegrees", 60))
    sc.facts.update(missAngle=miss, endAngle=goal)
    # M05.8: one servo angle track drives Bolt's stage arm AND the split-screen dial (servo_track); the arm comes up
    # to "ready" (0 deg, straight forward) just before the first move, then turns 0 -> 30, holds, 30 -> 60, holds.
    track = servo_track(sc)
    holds = [(s0, s1, rel, a1) for s0, s1, rel, a0, a1 in track]       # (start, reach_t, release_t, servo angle)
    if track:
        r0 = track[0][0]
        bolt.act(r0 - 0.9, r0 - 0.3, "arm_to:90")
        bolt.act(r0 - 0.3, r0, "arm_to_hold:90")
    for s0, s1, rel, a0, a1 in track:
        bolt.act(s0, s1, f"servo_arm:{a0:g}:{a1:g}")
        bolt.act(s1, rel, f"arm_to_hold:{90 + a1:g}")
    clap = sc.beat("sfx", "id", "clap")
    if clap:
        maya.act(clap["start_s"] - 0.7, clap["start_s"] + 1.0, "highfive_reach")
    hf = sc.beat("action", "do", "highfive")
    if hf:
        nib.move(hf["start_s"] - 1.2, hf["start_s"], x=-3.2, y=2.2, arc=0.5)
    # M05.8: the shoulder gauge only comes up on stage once the last servo move has reached its angle (the split
    # screen shows the moves themselves)
    goal_t = track[-1][1] if track else None

    def gauge(t, m):
        b = m.get("bolt")
        if b is None or not goal_t or not (goal_t <= t < holds[-1][2] + 0.6):
            return []
        ang = servo_angle(track, t)
        shoulder = b.parts["arm_r"].get_start()
        return [PR.protractor(shoulder, ang, facing=1, radius=1.25, target=goal)]
    sc.back.append(gauge)                              # behind the rigs so the real arm reads on top
    # WHOOSH sits between Bolt and Maya above their heads; CLAP stays in the gap above Bolt / Maya (M05.7).
    generic_sfx_lettering(sc, {"whoosh": PR.P(0.0, 3.0), "clap": PR.P(0.2, 2.2)})   # M05.8: WHOOSH off Nib, in frame


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
    labels = PR.lift_labels(tape)          # M05.5: distance labels drawn in front so Bolt's treads never hide them
    sc.back.append(lambda t, m: [pile, tape])
    sc.front.append(lambda t, m: [labels])
    keep_out(sc, "ruler", tape)
    keep_out(sc, "ruler-labels", labels)

    def hud(t, m):
        if t < a.t0 - 0.3 or t > resume["end_s"] + 1.5:
            return []
        turned = t >= min(turn["end_s"], resume["start_s"])     # facing away: the sensor sees open floor
        return [PR.readout(hud_lines(a.reading(t), thr, turned), PR.P(4.3, 2.75))]
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
        dur = 2.9 - (b["start_s"] - lines[0]["start_s"])
        # M05.8: shrink (not shift) into the safe area so the chant word never drops onto Maya's face
        sc.screen.append(sfx_word(word, color, b["start_s"], PR.P(x, 3.62), dur=dur, size=100, shrink=True))
        sc.top_busy.append((b["start_s"], b["start_s"] + dur))
    q = sc.params.get("question", "")
    sc.facts["question"] = q
    q_line = next((b for b in sc.lines("maya") if q and q.split()[0] in b["text"] and "question" in b["text"]), None)
    outro = sc.beat("music", "cue", "outro")
    if q_line:
        sc.top_busy.append((q_line["start_s"], outro["start_s"]))
        sc.screen.append(lambda t, m: [fit_in_frame(PR.card("Quiz time!", q, _u(t, q_line["start_s"], q_line["start_s"] + 0.6),
                                               at=PR.P(0.0, 3.22), width=7.2).scale(0.80, about_point=PR.P(0.0, 3.22)),
                                                    shrink=True)]
                         if q_line["start_s"] <= t < outro["start_s"] else [])
    dance = sc.beat("action", "do", "beep_dance")
    if dance:
        sc.front.append(lambda t, m: [fit_in_frame(PR.speech_bubble("beep boop!", m["nib"].get_top() + PR.P(-0.2, 0.05),
                                                       _u(t, dance["start_s"], dance["end_s"] + 0.6),
                                                       m["nib"].get_top() + PR.P(0.3, 1.0)))]
                        if "nib" in m and dance["start_s"] <= t < dance["end_s"] + 0.6 else [])
    sc.top_busy.append((outro["start_s"], sc.duration))
    sc.screen.append(lambda t, m: [PR.title_card(min(0.8, _u(t, outro["start_s"], outro["start_s"] + 3.0)),
                                                 subtitle="See you next time!")] if t >= outro["start_s"] else [])


INTRO_SLOT_X = 4.0


def stage_character_intro(sc: Scene) -> None:
    """M03.1 generated cast intro: each character enters (registry entrance), gets a spotlight and a nameplate
    (display name in its caption colour + personality tagline) while its intro line plays; all stay in a lineup."""
    cards = sc.params.get("characters", [])
    n = len(cards)
    # M05.5: lineup slots ±4.0 (was ±4.6) so the outer characters' hops/arm swings stay inside the frame
    slots = [(-INTRO_SLOT_X + 2 * INTRO_SLOT_X * i / max(1, n - 1)) if n > 1 else 0.0 for i in range(n)]
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
        p.emote(t1 + 0.15, "excited")          # M05.4: "ta-da!" hop on arrival
        sc.perf[cid] = p
        sc.enter_at[cid] = round(t1, 3)
        segs.append((cid, c, x, t0, t1))
    sc.cast = tuple(c["id"] for c in cards)
    for i, (cid, c, x, t0, t1) in enumerate(segs):   # M05.4: the lineup greets each newcomer (nobody waits idle)
        for prev, *_ in segs[:i]:
            sc.perf[prev].emote(t1 + 0.1, "giggle" if i % 2 else "curious", gain=0.7)
    intro_facts = []
    for i, (cid, c, x, t0, t1) in enumerate(segs):
        end = segs[i + 1][3] if i + 1 < len(segs) else sc.duration - 0.2
        line = next((b for b in sc.lines() if b.get("target") == cid), None)
        at = PR.P(max(-3.4, min(3.4, x)), 3.20)

        def plate(t, m, c=c, t1=t1, end=end, at=at):
            return [fit_in_frame(PR.nameplate(c["name"], c["tagline"], c.get("color", "#FFFFFF"),
                                              _u(t, t1 - 0.1, end), at, t), shrink=True)] \
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
    if isinstance(spec_scene.get("background"), dict) and spec_scene["background"].get("theme") not in (None, "auto"):
        sc.background = dict(spec_scene["background"])       # M05.5: resolved by episode.resolve_backgrounds
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
    stage_section_banner(sc, spec_scene.get("kicker"))
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
                "kicker": c.get("kicker") or None,
                "start": round(t0, 3), "end": round(t1, 3), "teachStart": round(nxt, 3)}
        cards.append(card)
        sc.screen.append(lambda t, m, c=card: [PR.concept_card(c["title"], c["subtitle"], c["icon"],
                                                                _u(t, c["start"], c["end"]), t, kicker=c["kicker"])]
                         if c["start"] <= t < c["end"] else [])
    sc.concepts = cards
    sc.facts["conceptCards"] = cards


BANNER_S = 2.4


def stage_section_banner(sc: Scene, kicker: str | None) -> None:
    """M05.5: a section whose kicker isn't shown on one of its concept cards announces itself with a short top
    banner right after the transition in (no timing change)."""
    if not kicker or any((c.get("kicker") or "").casefold() == kicker.casefold() for c in sc.concepts):
        return
    t0 = (sc.trans_half if sc.trans_in else 0.0) + 0.1
    limit = sc.duration - 0.5
    if sc.concepts:
        limit = min(limit, sc.concepts[0]["start"])
    busy = sorted(sc.top_busy + [(c["start"], c["end"]) for c in sc.concepts])
    for a, b in busy:                       # wait for the top band to be free (recap chants, question cards)
        if a < t0 + BANNER_S and b > t0:
            t0 = max(t0, b + 0.1)
    t1 = min(limit, t0 + BANNER_S, *[a for a, _ in busy if a >= t0] or [limit])
    if t1 - t0 < 1.0 or t0 > (sc.trans_half if sc.trans_in else 0.0) + 8.0:
        return
    sc.facts["sectionBanner"] = {"kicker": kicker, "start": round(t0, 3), "end": round(t1, 3)}
    sc.screen.append(lambda t, m: [PR.section_banner(kicker, _u(t, t0, t1), t)] if t0 <= t < t1 else [])


# ------------------------------------------------------------------------------------------ M05.1 shots

SHOT_IN, SHOT_OUT = 0.4, 0.35          # seconds of the pop-in / shrink-out animation
SHOT_LEAD, SHOT_TAIL = 0.15, 0.35      # shot starts a little before its first beat, ends after its last
# Keep the seated charger + filling battery visible this long after the plug seats.
CHARGE_HOLD_S = 2.2
CHECKLIST_CORNER = (6.32, 3.56)            # M05.8: checkup card top-right corner, inside the 5% safe area
CHECKLIST_SCALE = 0.82                     # M05.8: card bottom (~1.84) stays above Maya's head after she steps right
CHARGE_FILL_S = 1.2                     # M05.8: the battery fills red -> green before the controller frame
SYNC_HOLD_MAX = 0.6                     # M05.8: a shot may start at most this late after its first word
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



def _ctx_rule(sc: Scene, sh: dict) -> dict:
    thr = sc.params.get("thresholdMeters")
    out = {"threshold": float(thr) if thr is not None else 0.5}
    if thr is not None:
        sc.facts["shotThresholdMeters"] = float(thr)
    return out


def _ctx_servo_dial(sc: Scene, sh: dict) -> dict:
    t30 = sc.word_time("30", after=sh["start"]) or sc.word_time("thirty", after=sh["start"])
    t60 = sc.word_time("60", after=sh["start"]) or sc.word_time("sixty", after=sh["start"])
    return {"t30": t30, "t60": t60, "t0": sh["start"]}


def _ctx_servo_split(sc: Scene, sh: dict) -> dict:
    """M05.8 split screen: Bolt (live performer: lip sync, blinks) with his arm on the shared servo track, and the
    dial reading the same angle at the same instant."""
    clap = next((b["start_s"] for b in sc.beats if b["type"] == "sfx" and b.get("id") == "clap"
                 and sh["start"] <= b["start_s"] < sh["end"]), None)
    goal = float(sc.params.get("endAngleDegrees", 60))
    return {"track": servo_track(sc), "perf": sc.perf.get("bolt"), "clap": clap, "goal": goal, "t0": sh["start"]}


def _ctx_servo_cause(sc: Scene, sh: dict) -> dict:
    """M05.8 cause -> effect: the brain sends the target angle, the signal travels, the servo turns, the arm moves.
    Timed to the line: the angle command lands on "brain", the motion finishes before the line ends."""
    goal = float(sc.params.get("endAngleDegrees", 60))
    line = sc.beats[sh["fromBeat"]]
    tb = word_time_in_line(sc.voice_dir, line, "brain") if line.get("type") == "line" else None
    t0 = sh["start"] + 0.35
    t_brain = tb if tb is not None and tb > t0 else t0 + 0.8
    t_end = sh["end"] - 0.6
    return {"goal": goal, "t0": t0, "send": max(t0, min(t_brain - 0.9, t_end - 2.4)), "end": t_end}


def _ctx_quiz(sc: Scene, sh: dict) -> dict:
    line = next((b for b in sc.lines() if "which part" in b["text"].lower()), None)
    return {"question": line["text"] if line else "Which part of a robot measures distance?"}


def _ctx_part(sc: Scene, sh: dict) -> dict:
    vis = sh.get("visual") or ""
    part = vis[len("part_"):] if vis.startswith("part_") else sh.get("example")
    plug = sc.beat("action", "do", "plug_in")
    fill = None
    if plug and part == "power":
        # illustration is on the power *line*; show a filling battery and a seated plug
        fill = 0.25 + 0.75 * 0.85
    return {"part": part, "seated": True, "fill": fill if part == "power" else None}


def _ctx_example(sc: Scene, sh: dict) -> dict:
    vis = sh.get("visual") or ""
    kind = vis[len("example_"):] if vis.startswith("example_") else sh.get("example")
    return {"kind": kind, "example": kind, "t0": sh.get("start"), "shot": sh}   # t1 = shot end at draw time


def _ctx_range(sc: Scene, sh: dict) -> dict:
    rng = float(sc.params.get("rangeMeters", 3.0))
    nib = float(sc.params.get("obstacleDistanceMeters", 1.2))
    if sh.get("visual") == "sensor_out_of_range":
        far = [float(b["do"].split(":")[1]) for b in sc.beats if b["type"] == "action"
               and b["do"].startswith("fly_to:") and float(b["do"].split(":")[1]) > rng]
        nib = far[0] if far else rng + 0.6
    return {"range": rng, "nibMeters": nib, "t0": sh["start"]}


def shot_context(sc: Scene, sh: dict) -> dict:
    vis = sh.get("visual") or ""
    if vis in SHOT_CONTEXT:
        return SHOT_CONTEXT[vis](sc, sh)
    if vis.startswith("part_"):
        return _ctx_part(sc, sh)
    if vis.startswith("example_"):
        return _ctx_example(sc, sh)
    return {}


SHOT_CONTEXT = {"robot_families": _ctx_robot_families, "echo_diagram": _ctx_echo, "sense_think_act": _ctx_sta,
                "the_rule": _ctx_rule, "rule_test": _ctx_rule, "servo_dial": _ctx_servo_dial,
                "servo_split": _ctx_servo_split, "servo_cause": _ctx_servo_cause,
                "quiz_question": _ctx_quiz, "sensor_range": _ctx_range, "sensor_out_of_range": _ctx_range,
                "part_power": _ctx_part}


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


def _clip_overlapping_shots(sc: Scene) -> None:
    """Consecutive illustration/solo shots must not share the screen (one example per frame)."""
    ordered = sorted((sh for sh in sc.shots if sh["layout"] != "stage"), key=lambda s: s["start"])
    for a, b in zip(ordered, ordered[1:]):
        if a["end"] > b["start"]:
            a["end"] = b["start"]
    by_id = {f"shot-{sh.get('example') or sh['visual']}": sh for sh in sc.shots}
    for il in sc.illustrations:
        sh = by_id.get(il["id"])
        if sh is not None:
            il["end"] = min(il["end"], max(il["start"], sh["end"] - SHOT_OUT))
            il["start"] = max(il["start"], sh["start"] + SHOT_IN)


def illustrated_span(sc: Scene, spec: dict) -> tuple[float, float]:
    """M05.8: (start, end) of what a shot illustrates, from the word timings (see ``illustrated_span_beats``)."""
    return illustrated_span_beats(sc.beats, sc.voice_dir, spec)


def illustrated_span_beats(beats: list[dict], voice_dir, spec: dict) -> tuple[float, float]:
    """(start, end) of what a shot illustrates: the first relevant word (``atWord``, else the first word of the
    first line / the start of the first staged action) to the last word of the last line (or ``untilWord``).
    Shared by staging and QA ``sync.visual_narration``."""
    lo, hi = spec["fromBeat"], min(spec["toBeat"], len(beats) - 1)
    rng = beats[lo:hi + 1]
    first = rng[0]
    if first["type"] == "line":
        s0 = line_span(voice_dir, first)[0]
        if spec.get("atWord"):
            wt = word_time_in_line(voice_dir, first, spec["atWord"])
            s0 = wt if wt is not None else s0
        else:
            # M05.8 default: the frame starts at the first word of its topic ("And last, | the controller"),
            # so a lead-in ("Perfect!", "Here's how it works.") plays on stage, not over the picture
            from robotics101.cartoon.sync import first_keyword_time
            kt = first_keyword_time(voice_dir, first, spec)
            s0 = kt if kt is not None else s0
    else:
        s0 = first["start_s"]
    last_line = next((b for b in reversed(rng) if b["type"] == "line"), None)
    s1 = line_span(voice_dir, last_line)[1] if last_line is not None else rng[-1]["end_s"]
    if last_line is not None and rng[-1]["type"] != "line":
        s1 = max(s1, rng[-1]["end_s"])
    if spec.get("untilWord"):
        for b in rng:
            if b["type"] == "line":
                wt = word_time_in_line(voice_dir, b, spec["untilWord"])
                if wt is not None and wt > s0:
                    s1 = wt
                    break
    return round(s0, 3), round(max(s0 + 0.1, s1), 3)


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
        span0, span1 = illustrated_span(sc, spec)
        floor = max(k if sc.trans_in else 0.0,
                    max((c["end"] for c in sc.concepts if c["start"] <= b0["start_s"]), default=0.0))
        # M05.8: the shot is timed to the words it illustrates (ElevenLabs word timings): it starts at the first
        # relevant word and cuts away when the last illustrated line ends. No intervening gag can extend it.
        start = max(span0 - SHOT_LEAD, floor)
        end = min(span1 + SHOT_TAIL, sc.duration - (k if sc.trans_out else 0.0))
        plug = sc.beat("action", "do", "plug_in")
        if plug and start < plug["end_s"] + CHARGE_HOLD_S < end:
            # keep the seated charger visible (spark + battery) a moment, but never more than SYNC_HOLD_MAX
            # past the first illustrated word: the narration must not move on without the picture (M05.8)
            start = max(start, min(plug["end_s"] + CHARGE_HOLD_S, span0 + SYNC_HOLD_MAX))
        sh = {"layout": spec["layout"], "visual": spec.get("visual") or "concept_robot",
              "character": spec.get("character"), "corner": spec.get("corner", "left"),
              "fromBeat": spec["fromBeat"], "toBeat": spec["toBeat"], "start": round(start, 3), "end": round(end, 3)}
        if spec.get("example"):
            sh["example"] = spec["example"]
        if spec.get("atWord"):
            sh["atWord"] = spec["atWord"]
        if spec.get("untilWord"):
            sh["untilWord"] = spec["untilWord"]
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
        ctx = shot_context(sc, sh)
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
        # Register the teaching board itself so illustrations.animated measures the new full-screen shots
        # (the old robot_families tile regions are gone).
        sc.illustrations.append({"id": f"shot-{sh.get('example') or sh['visual']}",
                                 "kind": sh.get("example") or sh["visual"],
                                 "start": round(sh["start"] + SHOT_IN, 3),
                                 "end": round(max(sh["start"] + SHOT_IN, sh["end"] - SHOT_OUT), 3),
                                 "box": list(sh["visualBox"])})

        def draw(t, m, sh=sh, fn=fn, ctx=ctx):
            if not (sh["start"] <= t < sh["end"]):
                return []
            g = [VZ.backdrop(sh["layout"], t), fn(t, ctx, box)]
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
    _clip_overlapping_shots(sc)
    sc.facts["shots"] = sc.shots
    hide_covered_illustrations(sc)


def uncovered_spans(a: float, b: float, covers: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Parts of [a, b) not inside any of ``covers`` (sorted, merged), dropping slivers < 0.1 s."""
    out, t = [], a
    for c0, c1 in sorted(covers):
        if c1 <= t or c0 >= b:
            continue
        if c0 > t:
            out.append((t, c0))
        t = max(t, c1)
    if t < b:
        out.append((t, b))
    return [(x, y) for x, y in out if y - x >= 0.1]


def hide_covered_illustrations(sc: Scene) -> None:
    """M05.4: a full-screen shot (its backdrop covers the stage) hides the stage's own illustration regions, so the
    static-hold QA must not measure them while covered (it saw the shot's board as a 7 s 'still' vacuum tile).
    Stage regions are cut to the uncovered spans (extra spans get ``#2``, ``#3`` ids); shot regions are kept."""
    covers = [(sh["start"] + SHOT_IN, sh["end"] - SHOT_OUT) for sh in sc.shots if sh["layout"] != "stage"]
    if not covers:
        return
    kept = []
    for il in sc.illustrations:
        if il["id"].startswith("shot-"):
            kept.append(il)
            continue
        for j, (x, y) in enumerate(uncovered_spans(il["start"], il["end"], covers)):
            kept.append({**il, "id": il["id"] if j == 0 else f"{il['id']}#{j + 1}", "start": round(x, 3),
                         "end": round(y, 3)})
    sc.illustrations[:] = kept


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
    bg = backdrop(sc.background["theme"], sc.background.get("palette"), sc.set_variant)

    def frame(t: float):
        mobs, back, over = frame_layers(sc, t)
        return [bg] + back + list(mobs.values()) + over + transition_overlay(sc, t)
    return frame


def background_record(sc: Scene) -> dict:
    """M05.5 scenes.json entry: the section background actually drawn + a 4x3 colour swatch of it (QA compares
    adjacent sections' swatches, so two differently-named but look-alike sets still fail)."""
    from robotics101.cartoon.backgrounds import swatch
    b = sc.background
    return {"theme": b["theme"], "palette": b.get("palette"), "section": b.get("section", sc.sid),
            "auto": b.get("auto", True), "swatch": swatch(b["theme"], b.get("palette"))}


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


# Head / face parts measured for layout.faces_clear (M05.7). Antennae and bodies stay out so a
# label above a head is allowed; the union of these parts is the face box.
FACE_PARTS = {
    "maya": ("head", "eyes", "mouth", "brows", "nose", "cheeks", "ears", "puffs", "band", "goggles"),
    "bolt": ("screen", "eyes", "mouth", "brows", "cheeks"),
    "nib": ("body", "eye", "beak"),
}


def face_box(cid: str, mob) -> list[float]:
    """Normalised box of ``cid``'s head/face, from named rig parts (fallback: the top 40% of the body)."""
    from robotics101.cartoon.layout import norm_box
    parts = getattr(mob, "parts", None) or {}
    xs, ys = [], []
    for k in FACE_PARTS.get(cid, ()):
        p = parts.get(k)
        if p is None or (not p.has_points() and not p.submobjects):
            continue
        x0, y0 = p.get_corner(np.array([-1, -1, 0]))[:2]
        x1, y1 = p.get_corner(np.array([1, 1, 0]))[:2]
        xs += [float(x0), float(x1)]
        ys += [float(y0), float(y1)]
    if not xs:
        x0, y0 = mob.get_corner(np.array([-1, -1, 0]))[:2]
        x1, y1 = mob.get_corner(np.array([1, 1, 0]))[:2]
        y0 = float(y0) + 0.60 * (float(y1) - float(y0))
        return norm_box(x0, y0, x1, y1)
    return norm_box(min(xs), min(ys), max(xs), max(ys))


def faces_report(sc: Scene, step: float = BAND_SAMPLE_S) -> dict:
    """M05.7: sample real overlay geometry and flag cards, HUD, SFX and similar overlays that cover
    a character's head or face. Teaching shots, concept cards, transitions and cutaways are skipped
    (the stage is fully covered on purpose). Props tagged ``on_character``, ``decor``,
    ``scene_fx`` (e.g. a ping meant to hit an obstacle) or ``covers_stage`` (title cards) are ignored."""
    from robotics101.cartoon.layout import boxes_collide
    k = transition_frames(sc) / FPS
    offenders, off_frame, n = {}, {}, 0
    t = 0.0
    while t < sc.duration:
        skip = ((sc.trans_in and t < k) or (sc.trans_out and t >= sc.duration - k)
                or any(c["start"] <= t < c["end"] for c in sc.cutaways)
                or any(c["start"] <= t < c["end"] for c in sc.concepts)
                or any(sh["start"] <= t < sh["end"] for sh in sc.shots))
        if not skip:
            n += 1
            mobs, _, _ = frame_layers(sc, t)
            _, over = named_layers(sc, t, mobs)
            faces = [(cid, face_box(cid, m)) for cid, m in mobs.items()]
            boxes: list = []
            for name, m in over:
                if (getattr(m, "on_character", False) or getattr(m, "decor", False)
                        or getattr(m, "scene_fx", False) or getattr(m, "covers_stage", False)):
                    continue
                _content_boxes(m, boxes, name)
                # M05.8: cards / HUD / lettering stay inside the action-safe area (QA layout.overlays_in_frame)
                if m.has_points() or m.submobjects:
                    out_by = safe_area_excess(_bbox(m))
                    if out_by > FACE_SAFE_TOL:
                        o = off_frame.setdefault(name, {"what": name, "first": round(t, 2), "n": 0, "maxExcess": 0.0})
                        o["n"] += 1
                        o["maxExcess"] = max(o["maxExcess"], round(out_by, 4))
            for oname, ob in boxes:
                for cid, fb in faces:
                    if boxes_collide(ob, fb):
                        key = f"{cid}/{oname}"
                        o = offenders.setdefault(key, {"character": cid, "what": oname,
                                                       "first": round(t, 2), "n": 0})
                        o["n"] += 1
        t += step
    return {"samples": n, "offenders": list(offenders.values()), "offFrame": list(off_frame.values())}


SAFE_MARGIN = 0.02            # M05.8: overlays stay inside the frame with a 2% margin (QA layout.overlays_in_frame)
FACE_SAFE_TOL = 0.004         # ~4 px slack for anti-aliased outlines


def safe_area_excess(b: list[float], margin: float = SAFE_MARGIN) -> float:
    """How far (normalised) a box pokes out of the action-safe area on its worst side (0 = inside)."""
    return max(0.0, margin - b[0], margin - b[1], b[2] - (1 - margin), b[3] - (1 - margin))


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
        faces = faces_report(sc)
        from robotics101.cartoon.liveliness import scene_acting
        acting = scene_acting(sc, presence, HEIGHT, SCALES)
        facts = {k: v for k, v in sc.facts.items() if k != "approach"}
        from robotics101.cartoon.lipsync import lipsync_agreement
        agree = {f"{sid}#{b['index']}": round(lipsync_agreement(sc.perf[b["speaker"]].mouth, Path(voice_dir) / b["wav"],
                                                                 b["start_s"]), 3)
                 for b in sc.lines() if b["speaker"] in sc.perf}
        report["scenes"].append({"sceneId": sid, "template": sc.template, "frames": sc.n_frames,
                                 "duration_s": sc.duration, "video": str(final.relative_to(out_dir)),
                                 "minPresence": pres, "enterAt": sc.enter_at, "lipsync": sc.lipsync_methods,
                                 "lipsyncAgreement": agree, "liveliness": live, "captionBand": band,
                                 "acting": acting, "background": background_record(sc),
                                 "facesClear": faces,
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
