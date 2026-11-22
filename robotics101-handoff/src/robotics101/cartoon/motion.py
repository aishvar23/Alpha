"""Character motion (M02.4): deterministic performers — moves, actions, emotions, blinks, idle, talk, lip sync.

A ``Performer`` owns one character on a timeline: position keyframes (eased moves, optional hop arcs), timed
``actions`` from the registry's action list, expression changes, gaze targets and a ``MouthTrack``. ``state(t)``
returns everything a frame needs — a rig ``Pose`` plus placement — so any frame can be rendered independently
(parallel chunked rendering, exact re-renders). Nothing here is random: blinks come from a PRNG seeded by the
character id, so the same performance always yields the same frames.
"""

from __future__ import annotations

import hashlib
import math
import random
from bisect import bisect_right
from dataclasses import dataclass, field

from robotics101.cartoon.lipsync import MouthTrack
from robotics101.cartoon.rigs import Pose


# ------------------------------------------------------------------------------------------ easing

def clamp01(u: float) -> float:
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_in_out(u: float) -> float:
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def ease_out(u: float) -> float:
    u = clamp01(u)
    return 1 - (1 - u) ** 3


def ease_out_back(u: float, k: float = 1.70158) -> float:
    u = clamp01(u) - 1
    return 1 + (k + 1) * u ** 3 + k * u ** 2


def bump(u: float) -> float:
    """0 -> 1 -> 0 (sin hump)."""
    return math.sin(math.pi * clamp01(u))


# ------------------------------------------------------------------------------------------ actions

def _hop(u: float, height: float = 0.6) -> dict:
    """Anticipation squash -> stretched take-off -> parabola -> landing squash -> settle."""
    if u < 0.18:
        return {"squash": 1 - 0.16 * bump(u / 0.36)}
    if u < 0.78:
        v = (u - 0.18) / 0.6
        return {"dy": height * 4 * v * (1 - v), "squash": 1 + 0.12 * (1 - v) * (v < 0.5)}
    v = (u - 0.78) / 0.22
    return {"squash": 1 - 0.18 * bump(v)}


def _arg_float(arg: str | None, default: float) -> float:
    try:
        return float(arg) if arg is not None else default
    except ValueError:
        return default


ACTIONS = {
    "idle": lambda u, a: {},
    "hop": lambda u, a: _hop(u),
    "wave": lambda u, a: {"arm_r": 150 + 22 * math.sin(2 * math.pi * 3 * u) * bump(u * 0.98 + 0.01) ** 0.3},
    "point": lambda u, a: {"arm_r": 20 + 75 * ease_out_back(u / 0.2)},
    "cheer": lambda u, a: {"arm_l": 20 + 140 * ease_out(u / 0.15), "arm_r": 20 + 140 * ease_out(u / 0.15),
                           **_hop(u, 0.35)},
    "flex": lambda u, a: {"arm_l": 20 + 100 * ease_out_back(u / 0.25), "arm_r": 20 + 100 * ease_out_back(u / 0.25),
                          "squash": 1 + 0.05 * math.sin(2 * math.pi * 2 * u), "extras": ("sparkle",)},
    "wiggle": lambda u, a: {"lean": 0.13 * math.sin(2 * math.pi * 3 * u)},
    "yawn": lambda u, a: {"squash": 1 + 0.08 * bump(u), "mouth": "D" if 0.2 < u < 0.75 else None,
                          "blink": 0.6 * bump(u), "arm_l": 20 + 120 * bump(u), "arm_r": 20 + 120 * bump(u)},
    "flinch": lambda u, a: {"lean": -0.22 * (1 - ease_out(u)), "squash": 1 - 0.12 * (1 - ease_out(u)),
                            "arm_l": 20 + 60 * (1 - u), "arm_r": 20 + 60 * (1 - u)},
    "bonk": lambda u, a: {"squash": 1 - 0.25 * bump(u / 0.4) if u < 0.4 else 1 + 0.04 * math.sin(12 * u),
                          "lean": -0.28 * (1 - ease_out(u)), "dx": -0.35 * ease_out(u), "extras": ("stars",)},
    "dizzy": lambda u, a: {"lean": 0.12 * math.sin(2 * math.pi * 2 * u), "extras": ("stars",)},
    "zoom": lambda u, a: {"lean": 0.22 * bump(u), "squash": 1 - 0.08 * bump(u)},
    "skid": lambda u, a: {"lean": -0.3 * (1 - ease_out(u)), "squash": 1 - 0.1 * bump(u)},
    "drive": lambda u, a: {"dy": 0.03 * abs(math.sin(2 * math.pi * 3 * u)), "lean": 0.06},
    "stop": lambda u, a: {"lean": -0.16 * (1 - ease_out(u)) * math.cos(3 * math.pi * u)},
    "turn": lambda u, a: {"flip": u >= 0.5, "squash": 1 - 0.1 * bump(u)},
    "resume": lambda u, a: {"lean": 0.1 * bump(u)},
    "spin": lambda u, a: {"flip": int(u * 6) % 2 == 1, "dy": 0.15 * bump(u)},
    "arm_to": lambda u, a: {"arm_r": 20 + (_arg_float(a, 90) - 20) * ease_in_out(u / 0.6)},
    "ping": lambda u, a: {"glow": 0.5 + 0.5 * bump(u)},
    "plug_in": lambda u, a: {"lean": 0.08 * bump(u), "glow": ease_in_out(u)},
    "enter": lambda u, a: {"dy": 0.05 * abs(math.sin(2 * math.pi * 3 * u))},
    "exit": lambda u, a: {"dy": 0.05 * abs(math.sin(2 * math.pi * 3 * u))},
    "look_at": lambda u, a: {},
    "facepalm": lambda u, a: {"arm_r": 20 + 150 * ease_out(u / 0.25), "lean": 0.08, "blink": 1.0 if u > 0.2 else 0},
    "write_board": lambda u, a: {"arm_r": 100 + 14 * math.sin(2 * math.pi * 4 * u)},
    "open_album": lambda u, a: {"arm_l": 20 + 50 * ease_out(u / 0.2), "arm_r": 20 + 50 * ease_out(u / 0.2)},
    "stethoscope": lambda u, a: {"arm_r": 20 + 65 * ease_out(u / 0.2), "lean": 0.08},
    "highfive": lambda u, a: {"arm_r": 20 + 140 * ease_out_back(u / 0.3), "arm_l": 20 + 70 * bump(u),
                              **_hop(u, 0.2)},
    "hover": lambda u, a: {"dy": 0.12 * math.sin(2 * math.pi * 2 * u), "arm_l": 20 + 60 * abs(math.sin(14 * u))},
    "fly_to": lambda u, a: {"arm_l": 20 + 70 * abs(math.sin(18 * u)), "lean": 0.15 * bump(u)},
    "return": lambda u, a: {"arm_l": 20 + 70 * abs(math.sin(18 * u)), "lean": 0.15 * bump(u)},
    "land": lambda u, a: {"squash": 1 - 0.2 * bump((u - 0.7) / 0.3) if u > 0.7 else 1.0,
                          "arm_l": 20 + 60 * (1 - u)},
    "fall": lambda u, a: {"lean": 1.2 * ease_in_out(u) if u < 0.6 else 1.2 * (1 - ease_out((u - 0.6) / 0.4)),
                          "extras": ("stars",) if u > 0.5 else ()},
    "beep_dance": lambda u, a: {"lean": 0.2 * math.sin(2 * math.pi * 3 * u), "mouth": "D" if int(u * 8) % 2 else "A",
                                **_hop((u * 2) % 1, 0.15)},
}
GENERIC = ACTIONS["hop"]


def action_fn(name: str):
    return ACTIONS.get(name.split(":", 1)[0], GENERIC)


# ------------------------------------------------------------------------------------------ performer

@dataclass
class Act:
    start: float
    end: float
    name: str
    arg: str | None = None


@dataclass
class Move:
    start: float
    end: float
    x0: float
    x1: float
    y0: float
    y1: float
    arc: float = 0.0          # extra height at the middle (jumps / flights)
    ease: str = "in_out"


@dataclass
class FrameState:
    pose: Pose
    x: float
    y: float
    scale: float


def _seed(cid: str) -> int:
    return int(hashlib.sha256(cid.encode()).hexdigest()[:12], 16)


def blink_schedule(cid: str, duration: float, start: float = 0.0) -> list[float]:
    rng = random.Random(_seed(cid))
    t, out = start + rng.uniform(0.6, 2.0), []
    while t < duration:
        out.append(round(t, 3))
        t += rng.uniform(2.4, 4.6) if rng.random() > 0.15 else 0.35   # occasional double blink
    return out


@dataclass
class Performer:
    cid: str
    x: float
    y: float = 0.0
    facing: int = 1
    scale: float = 1.0
    expression: str = "happy"
    airborne: bool = False                 # Nib: propeller spins, idle hover
    moves: list[Move] = field(default_factory=list)
    acts: list[Act] = field(default_factory=list)
    emotions: list[tuple[float, str]] = field(default_factory=list)
    facings: list[tuple[float, int]] = field(default_factory=list)
    gazes: list[tuple[float, tuple[float, float]]] = field(default_factory=list)
    mouth: MouthTrack = field(default_factory=MouthTrack)
    blinks: list[float] = field(default_factory=list)
    airs: list[tuple[float, bool]] = field(default_factory=list)

    # -- authoring helpers
    def move(self, start: float, end: float, x: float | None = None, y: float | None = None, arc: float = 0.0,
             ease: str = "in_out") -> "Performer":
        x0, y0 = self.position_at(start)
        self.moves.append(Move(start, end, x0, x0 if x is None else x, y0, y0 if y is None else y, arc, ease))
        self.moves.sort(key=lambda m: m.start)
        return self

    def act(self, start: float, end: float, name: str) -> "Performer":
        base, _, arg = name.partition(":")
        self.acts.append(Act(start, end, base, arg or None))
        if base == "turn":           # the flip happens mid-action and persists afterwards
            self.face(end, -self._held(self.facings, start, self.facing))
        return self

    def feel(self, t: float, expression: str) -> "Performer":
        self.emotions.append((t, expression))
        self.emotions.sort()
        return self

    def face(self, t: float, facing: int) -> "Performer":
        self.facings.append((t, 1 if facing >= 0 else -1))
        self.facings.sort()
        return self

    def look(self, t: float, gaze: tuple[float, float]) -> "Performer":
        self.gazes.append((t, gaze))
        self.gazes.sort()
        return self

    def fly(self, t: float, airborne: bool = True) -> "Performer":
        self.airs.append((t, airborne))
        self.airs.sort()
        return self

    def airborne_at(self, t: float) -> bool:
        return bool(self._held(self.airs, t, self.airborne))

    def finalize(self, duration: float) -> "Performer":
        self.blinks = blink_schedule(self.cid, duration)
        return self

    # -- evaluation
    def position_at(self, t: float) -> tuple[float, float]:
        x, y = self.x, self.y
        for m in self.moves:
            if t >= m.end:
                x, y = m.x1, m.y1
            elif t > m.start:
                u = (t - m.start) / max(1e-6, m.end - m.start)
                e = ease_in_out(u) if m.ease == "in_out" else ease_out(u) if m.ease == "out" else u
                return m.x0 + (m.x1 - m.x0) * e, m.y0 + (m.y1 - m.y0) * e + m.arc * 4 * u * (1 - u)
            else:
                break
        return x, y

    def moving_at(self, t: float) -> bool:
        return any(m.start < t < m.end and m.x0 != m.x1 for m in self.moves)

    @staticmethod
    def _held(keys: list, t: float, default):
        i = bisect_right([k[0] for k in keys], t) - 1
        return keys[i][1] if i >= 0 else default

    def blink_at(self, t: float) -> float:
        i = bisect_right(self.blinks, t) - 1
        if i < 0:
            return 0.0
        d = t - self.blinks[i]
        return max(0.0, 1 - abs(d - 0.07) / 0.07) if d < 0.14 else 0.0

    def state(self, t: float) -> FrameState:
        x, y = self.position_at(t)
        facing = self._held(self.facings, t, self.facing)
        expr = self._held(self.emotions, t, self.expression)
        gaze = self._held(self.gazes, t, (0.0, 0.0))
        p = {"squash": 1.0, "lean": 0.0, "arm_l": 20.0, "arm_r": 20.0, "dy": 0.0, "dx": 0.0, "glow": 0.5,
             "blink": self.blink_at(t), "extras": (), "mouth": None, "flip": False}
        # idle breathing / hover, talk gestures
        phase = (_seed(self.cid) % 1000) / 1000 * 2 * math.pi
        airborne = self.airborne_at(t)
        if airborne:
            p["dy"] += 0.1 * math.sin(2 * math.pi * t / 1.3 + phase)
            p["arm_l"] = 20 + 55 * abs(math.sin(2 * math.pi * 3.5 * t))
        else:
            p["squash"] *= 1 + 0.018 * math.sin(2 * math.pi * t / 1.7 + phase)
        talking = self.mouth.talking_at(t)
        if talking:
            p["dy"] += 0.025 * abs(math.sin(2 * math.pi * 2.2 * t))
            p["arm_l"] += 10 * (1 + math.sin(2 * math.pi * 0.8 * t + phase))
            p["arm_r"] += 14 * (1 + math.sin(2 * math.pi * 0.6 * t + phase + 1.0))
        if self.moving_at(t) and not airborne:
            p["dy"] += 0.04 * abs(math.sin(2 * math.pi * 3 * t))
        for a in self.acts:
            if a.start <= t <= a.end:
                u = (t - a.start) / max(1e-6, a.end - a.start)
                o = action_fn(a.name)(u, a.arg)
                for k, v in o.items():
                    if v is None:
                        continue
                    if k in ("squash",):
                        p[k] *= v
                    elif k in ("lean", "dy", "dx"):
                        p[k] += v
                    elif k == "extras":
                        p[k] = tuple(dict.fromkeys(p[k] + tuple(v)))
                    else:
                        p[k] = v
        if p.pop("flip"):
            facing = -facing
        mouth = p.pop("mouth") or self.mouth.shape_at(t)
        pose = Pose(expression=expr, mouth=mouth, blink=p["blink"], gaze=gaze, squash=p["squash"],
                    lean=p["lean"], arm_l=p["arm_l"], arm_r=p["arm_r"], facing=facing, glow=p["glow"],
                    prop=(t * 26.0) if airborne else 0.3, extras=p["extras"])
        return FrameState(pose, x + p["dx"] * facing, y + p["dy"], self.scale)
