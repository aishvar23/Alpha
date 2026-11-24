"""Character rigs (M02.3): Bolt, Maya and Nib as pure functions ``Pose -> VGroup`` built from vector primitives.

Conventions (rig version ``RIG_VERSION``, recorded in ``characters/registry.json`` and bundle manifests):
* local units are Manim units; the character's ground-contact point is the ORIGIN and the rig faces right
  (``facing=-1`` mirrors it). Squash/stretch and lean pivot on the ground point, so feet never slide.
* nothing random: the same Pose always produces the same geometry (deterministic renders, golden tests).
* palette comes from the registry; outlines use the registry ``outlineColor``.
* ``mouth`` takes Rhubarb Lip Sync shapes: A (M/B/P closed), B (most consonants), C (EH/AE), D (AA, wide),
  E (AO/ER, rounded), F (UW/OO, puckered), G (F/V), H (L, tongue up), X (rest = the expression's own mouth).

Every visible part is reachable via ``group.parts[name]`` for animation code (M02.4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from functools import lru_cache

import numpy as np
from manim import (DOWN, LEFT, ORIGIN, PI, RIGHT, UP, Arc, ArcBetweenPoints, Circle, CubicBezier, Dot, Ellipse,
                   Line, Polygon, Rectangle, RoundedRectangle, Star, Text, VGroup, VMobject)

from robotics101.characters import DEFAULT_REGISTRY_PATH, load_registry

RIG_VERSION = 1
MOUTH_SHAPES = ("A", "B", "C", "D", "E", "F", "G", "H", "X")
EXTRAS = ("stars", "sweat", "sparkle", "zzz", "question", "heart")


@dataclass(frozen=True)
class Pose:
    expression: str = "happy"
    mouth: str = "X"
    blink: float = 0.0                       # 0 open .. 1 closed
    gaze: tuple[float, float] = (0.0, 0.0)   # -1..1 (x right, y up)
    squash: float = 1.0                      # <1 squashed, >1 stretched (area-preserving)
    lean: float = 0.0                        # radians, positive = toward facing direction
    arm_l: float = 20.0                      # degrees from straight down (0) to straight up (180)
    arm_r: float = 20.0
    facing: int = 1
    glow: float = 0.5                        # Bolt antenna bulb glow 0..1
    prop: float = 0.0                        # Nib propeller phase (radians)
    extras: tuple[str, ...] = ()

    def with_(self, **kw) -> "Pose":
        return replace(self, **kw)


@dataclass(frozen=True)
class Style:
    ink: str
    palette: dict
    expressions: tuple[str, ...]


@lru_cache(maxsize=4)
def _styles(path: str = str(DEFAULT_REGISTRY_PATH)) -> dict[str, Style]:
    import json
    from pathlib import Path

    reg = load_registry(Path(path))
    ink = json.loads(Path(path).read_text(encoding="utf-8")).get("outlineColor", "#2B2140")
    return {cid: Style(ink, dict(c.palette), tuple(c.expressions)) for cid, c in reg.characters.items()}


def style(cid: str) -> Style:
    return _styles()[cid]


# ----------------------------------------------------------------------------------- helpers

def _o(m: VMobject, ink: str, w: float = 6) -> VMobject:
    return m.set_stroke(ink, w)


def _pt(x: float, y: float) -> np.ndarray:
    return np.array([x, y, 0.0])


def _limb(shoulder: np.ndarray, angle_deg: float, length: float, side: int, bend: float = 0.28) -> CubicBezier:
    """Noodle limb from the shoulder at ``angle_deg`` (0 down .. 180 up), bowing outward by ``bend``."""
    a = math.radians(angle_deg)
    hand = shoulder + length * np.array([side * math.sin(a), -math.cos(a), 0.0])
    d = hand - shoulder
    n = np.array([-d[1], d[0], 0.0]) / (np.linalg.norm(d) + 1e-9) * (-side)
    mid = (shoulder + hand) / 2 + n * bend
    return CubicBezier(shoulder, shoulder + 2 / 3 * (mid - shoulder), hand + 2 / 3 * (mid - hand), hand)


def _finish(g: VGroup, parts: dict, pose: Pose) -> VGroup:
    s = max(0.5, min(1.6, pose.squash))
    if s != 1.0:
        g.stretch(1 / s, 0, about_point=ORIGIN).stretch(s, 1, about_point=ORIGIN)
    if pose.lean:
        g.rotate(-pose.lean, about_point=ORIGIN)
        low = g.get_bottom()[1]
        if low < 0:                                    # M05.2: rock on the foot/tread edge, never sink below ground
            g.shift(UP * -low)
    if pose.facing < 0:
        g.stretch(-1, 0, about_point=ORIGIN)
    g.parts = parts
    return g


def _extras(names: tuple[str, ...], top: np.ndarray, ink: str, side: float = 1.0) -> VGroup:
    out = VGroup()
    for name in names:
        if name == "stars":
            out.add(*[Star(5, outer_radius=0.2, fill_color="#FFE66D", fill_opacity=1, stroke_color=ink,
                           stroke_width=3).move_to(top + _pt(x, 0.25 + 0.08 * (i % 2)))
                      for i, x in enumerate((-0.6, 0.0, 0.6))])
        elif name == "sweat":
            drop = VGroup(Circle(0.11, fill_color="#9BF6FF", fill_opacity=1, stroke_color=ink, stroke_width=3),
                          Polygon(_pt(-0.1, 0.04), _pt(0.1, 0.04), _pt(0, 0.26), fill_color="#9BF6FF",
                                  fill_opacity=1, stroke_width=0))
            out.add(drop.move_to(top + _pt(0.75 * side, -0.35)))
        elif name == "sparkle":
            out.add(*[Star(4, outer_radius=r, inner_radius=r * 0.35, fill_color="#FFE66D", fill_opacity=1,
                           stroke_width=0).move_to(top + _pt(x, y))
                      for x, y, r in ((-0.8, -0.1, 0.16), (0.85, 0.1, 0.22), (0.5, 0.5, 0.12))])
        elif name == "zzz":
            out.add(*[Text("z", font="Fredoka", weight="BOLD", font_size=fs, color=ink).move_to(top + _pt(x, y))
                      for x, y, fs in ((0.6, 0.1, 26), (0.85, 0.4, 34), (1.15, 0.75, 44))])
        elif name == "question":
            out.add(Text("?", font="Luckiest Guy", font_size=64, color="#6C4AB6").set_stroke(ink, 2, background=True)
                    .move_to(top + _pt(0.7 * side, 0.35)))
        elif name == "heart":
            h = VGroup(Circle(0.12, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0).shift(LEFT * 0.09),
                       Circle(0.12, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0).shift(RIGHT * 0.09),
                       Polygon(_pt(-0.2, -0.04), _pt(0.2, -0.04), _pt(0, -0.27), fill_color="#FF6B9A",
                               fill_opacity=1, stroke_width=0))
            out.add(h.move_to(top + _pt(0.5 * side, 0.4)))
        else:
            raise ValueError(f"unknown extra {name!r}; choose from {EXTRAS}")
    return out


# ----------------------------------------------------------------------------------- Bolt

BOLT_EXPR = {
    #           eyes        rest mouth  cheeks  bulb   extras
    "happy":    ("arc",      "smile",    0.8,   None, ()),
    "surprised": ("round",   "o",        0.4,   None, ()),
    "worried":  ("round_sad", "wobble",  0.3,   None, ("sweat",)),
    "proud":    ("arc",      "big_smile", 1.0,  None, ("sparkle",)),
    "sleepy":   ("flat",     "small",    0.4,   0.15, ("zzz",)),
    "dizzy":    ("x",        "wave",     0.3,   None, ("stars",)),
    "thinking": ("squint",   "side",     0.4,   0.9,  ("question",)),
    "laugh":    ("arc_tight", "laugh",   1.0,   None, ()),
}


def _bolt_mouth(shape: str, rest: str, c: np.ndarray, led: str, screen: str) -> VMobject:
    def ell(w, h):
        return Ellipse(width=w, height=h, color=led, fill_opacity=1, stroke_width=0).move_to(c)
    if shape == "X":
        if rest == "smile":
            return Arc(radius=0.3, start_angle=PI + 0.55, angle=PI - 1.1, color=led, stroke_width=10).move_to(c)
        if rest == "big_smile":
            m = ArcBetweenPoints(c + LEFT * 0.38 + UP * 0.05, c + RIGHT * 0.38 + UP * 0.05, angle=PI * 0.95,
                                 color=led, fill_opacity=1, stroke_width=0)
            return m
        if rest == "o":
            return ell(0.26, 0.3)
        if rest == "wobble":
            return Line(c + LEFT * 0.3, c + RIGHT * 0.3).set_stroke(led, 9).apply_function(
                lambda p: p + np.array([0, 0.05 * math.sin((p[0] - c[0]) * 16), 0]))
        if rest == "small":
            return Line(c + LEFT * 0.12, c + RIGHT * 0.12, color=led, stroke_width=9)
        if rest == "wave":
            pts = [c + np.array([x, 0.06 * math.sin(x * 22), 0]) for x in np.linspace(-0.32, 0.32, 24)]
            return VMobject(color=led, stroke_width=8).set_points_smoothly(pts)
        if rest == "side":
            return Line(c + LEFT * 0.18 + DOWN * 0.03, c + RIGHT * 0.22 + UP * 0.05, color=led, stroke_width=9)
        if rest == "laugh":
            m = ArcBetweenPoints(c + LEFT * 0.4 + UP * 0.08, c + RIGHT * 0.4 + UP * 0.08, angle=PI,
                                 color=led, fill_opacity=1, stroke_width=0)
            tongue = Ellipse(width=0.3, height=0.12, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0)
            return VGroup(m, tongue.move_to(c + DOWN * 0.15))
        raise ValueError(rest)
    sizes = {"A": None, "B": (0.42, 0.12), "C": (0.46, 0.22), "D": (0.52, 0.34), "E": (0.34, 0.28),
             "F": (0.2, 0.22), "G": (0.42, 0.1), "H": (0.44, 0.24)}
    if shape == "A":
        return Line(c + LEFT * 0.24, c + RIGHT * 0.24, color=led, stroke_width=10)
    w, h = sizes[shape]
    m = VGroup(ell(w, h))
    if shape == "G":
        m.add(Rectangle(width=w * 0.7, height=0.05, fill_color=screen, fill_opacity=1, stroke_width=0)
              .move_to(c + UP * 0.0))
    if shape in ("D", "H"):
        m.add(Ellipse(width=w * 0.5, height=h * 0.35, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0)
              .move_to(c + DOWN * h * (0.22 if shape == "D" else -0.15)))
    return m


def _bolt_eye(kind: str, c: np.ndarray, led: str, screen: str, blink: float, gx: float, gy: float, side: int):
    c = c + _pt(0.1 * gx, 0.06 * gy)
    open_ = max(0.08, 1 - blink)
    if blink > 0.85:
        return Line(c + LEFT * 0.2, c + RIGHT * 0.2, color=led, stroke_width=10)
    if kind in ("arc", "arc_tight"):
        r = 0.24 if kind == "arc" else 0.2
        e = Arc(radius=r, start_angle=0.15, angle=PI - 0.3, color=led, stroke_width=14).move_to(c)
    elif kind in ("round", "round_sad", "squint"):
        r = 0.26 if kind != "squint" else 0.22
        e = VGroup(Circle(r, color=led, fill_opacity=1, stroke_width=0),
                   Dot(radius=0.1, color=screen).shift(_pt(0.06 * gx, 0.06 * gy + 0.04))).move_to(c)
        if kind == "round_sad":
            e.add(Line(c + _pt(-0.25, 0.36), c + _pt(0.22, 0.36)).rotate(-0.35 * side).set_stroke(led, 7))
        if kind == "squint" and side > 0:
            e = Line(c + LEFT * 0.22, c + RIGHT * 0.22, color=led, stroke_width=12)
    elif kind == "flat":
        e = VGroup(Line(c + LEFT * 0.24, c + RIGHT * 0.24, color=led, stroke_width=12),
                   Arc(radius=0.24, start_angle=PI, angle=PI, color=led, stroke_width=10).move_to(c + DOWN * 0.08))
    elif kind == "x":
        e = VGroup(Line(_pt(-0.2, 0.2), _pt(0.2, -0.2)), Line(_pt(-0.2, -0.2), _pt(0.2, 0.2))) \
            .set_stroke(led, 12).move_to(c)
    else:
        raise ValueError(kind)
    if open_ < 1:
        e.stretch(open_, 1)
    return e


def bolt(pose: Pose = Pose()) -> VGroup:
    st = style("bolt")
    p, ink = st.palette, st.ink
    if pose.expression not in BOLT_EXPR:
        raise ValueError(f"bolt has no expression {pose.expression!r}")
    eyes_kind, rest, cheek_a, bulb_glow, auto_extras = BOLT_EXPR[pose.expression]
    gx, gy = pose.gaze
    tread = _o(RoundedRectangle(width=2.6, height=0.7, corner_radius=0.35, fill_color=p["tread"], fill_opacity=1),
               ink).move_to(_pt(0, 0.35))
    wheels = VGroup(*[_o(Circle(0.22, fill_color=p["wheel"], fill_opacity=1), ink, 4).move_to(_pt(x, 0.35))
                      for x in (-0.85, 0, 0.85)])
    body_c = _pt(0, 1.9)
    body = _o(RoundedRectangle(width=2.9, height=2.5, corner_radius=0.9, fill_color=p["body"], fill_opacity=1),
              ink).move_to(body_c)
    belly = _o(RoundedRectangle(width=1.3, height=0.55, corner_radius=0.2, fill_color=p["belly"], fill_opacity=1),
               ink, 4).move_to(body_c + DOWN * 0.75)
    rivets = VGroup(*[Dot(belly.get_center() + RIGHT * x, 0.07, color=ink) for x in (-0.35, 0, 0.35)])
    face_c = body_c + UP * 0.35 + RIGHT * 0.08 * (1 if pose.facing >= 0 else 1)
    screen = _o(RoundedRectangle(width=2.2, height=1.25, corner_radius=0.45, fill_color=p["screen"],
                                 fill_opacity=1), ink, 5).move_to(face_c)
    eyes = VGroup(*[_bolt_eye(eyes_kind, face_c + _pt(sx, 0.12), p["led"], p["screen"], pose.blink, gx, gy,
                              1 if sx > 0 else -1) for sx in (-0.5, 0.5)])
    mouth = _bolt_mouth(pose.mouth, rest, face_c + DOWN * 0.33 + _pt(0.06 * gx, 0), p["led"], p["screen"])
    cheeks = VGroup(*[Ellipse(width=0.3, height=0.16, color=p["cheek"], fill_opacity=cheek_a, stroke_width=0)
                      .move_to(face_c + _pt(sx, -0.25)) for sx in (-0.85, 0.85)])
    top = body_c + UP * 1.25
    stem = Line(top, top + UP * 0.6, stroke_width=8, color=ink)
    glow_v = pose.glow if bulb_glow is None else bulb_glow
    bulb = _o(Circle(0.2, fill_color=p["bulb"], fill_opacity=1), ink, 5).move_to(stem.get_end() + UP * 0.12)
    glow = Circle(0.25 + 0.2 * glow_v, fill_color=p["bulb"], fill_opacity=0.15 + 0.35 * glow_v,
                  stroke_width=0).move_to(bulb)
    sh_l, sh_r = body_c + _pt(-1.4, -0.25), body_c + _pt(1.4, -0.25)
    arm_l = _limb(sh_l, pose.arm_l, 1.25, -1).set_stroke(ink, 14)
    arm_r = _limb(sh_r, pose.arm_r, 1.25, 1).set_stroke(ink, 14)
    hands = VGroup(*[_o(Circle(0.2, fill_color=p["belly"], fill_opacity=1), ink, 4).move_to(a.get_end())
                     for a in (arm_l, arm_r)])
    extras = _extras(tuple(dict.fromkeys(auto_extras + pose.extras)), bulb.get_center() + DOWN * 0.3, ink)
    parts = dict(glow=glow, stem=stem, bulb=bulb, arm_l=arm_l, arm_r=arm_r, hands=hands, tread=tread,
                 wheels=wheels, body=body, belly=belly, rivets=rivets, screen=screen, cheeks=cheeks, eyes=eyes,
                 mouth=mouth, extras=extras)
    g = VGroup(*parts.values())
    return _finish(g, parts, pose)


# ----------------------------------------------------------------------------------- Maya

MAYA_EXPR = {
    # brow angle: + = inner ends up (worried/sad), - = inner ends down (determined); raise in units
    #            brow angle, brow raise, rest mouth, eye scale, cheek, extras
    "happy":     (0.0, 0.03, "smile", 1.0, 0.7, ()),
    "grin":      (-0.04, 0.03, "grin", 1.0, 0.8, ()),
    "surprised": (0.1, 0.13, "o", 1.25, 0.4, ()),
    "worried":   (0.38, 0.06, "frown", 1.05, 0.3, ("sweat",)),
    "thinking":  (-0.2, 0.07, "side", 0.95, 0.4, ("question",)),
    "laugh":     (0.12, 0.06, "laugh", 0.0, 0.9, ()),
    "proud":     (-0.15, 0.03, "smile_wide", 0.85, 0.9, ("sparkle",)),
}
LIP = "#7A1F3D"


def _maya_mouth(shape: str, rest: str, c: np.ndarray, ink: str) -> VMobject:
    def hole(w, h):
        return _o(Ellipse(width=w, height=h, fill_color=LIP, fill_opacity=1), ink, 4).move_to(c)
    if shape == "X":
        if rest == "smile":
            return Arc(radius=0.2, start_angle=PI + 0.6, angle=PI - 1.2, color=ink, stroke_width=6).move_to(c)
        if rest == "smile_wide":
            return Arc(radius=0.26, start_angle=PI + 0.5, angle=PI - 1.0, color=ink, stroke_width=7).move_to(c)
        if rest in ("grin", "laugh"):
            w = 0.6 if rest == "grin" else 0.7
            m = _o(ArcBetweenPoints(c + LEFT * w / 2, c + RIGHT * w / 2, angle=PI * 0.9, fill_color=LIP,
                                    fill_opacity=1), ink, 4)
            teeth = Rectangle(width=w * 0.62, height=0.07, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0) \
                .move_to(c + DOWN * 0.04)
            grp = VGroup(m, teeth)
            if rest == "laugh":
                grp.add(Ellipse(width=0.26, height=0.1, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0)
                        .move_to(c + DOWN * 0.22))
            return grp
        if rest == "o":
            return hole(0.22, 0.28)
        if rest == "frown":
            return Arc(radius=0.18, start_angle=0.6, angle=PI - 1.2, color=ink, stroke_width=6).move_to(c)
        if rest == "side":
            return Line(c + LEFT * 0.14, c + RIGHT * 0.16 + UP * 0.05, color=ink, stroke_width=6)
        raise ValueError(rest)
    if shape == "A":
        return Line(c + LEFT * 0.16, c + RIGHT * 0.16, color=ink, stroke_width=6)
    w, h = {"B": (0.3, 0.1), "C": (0.34, 0.2), "D": (0.42, 0.32), "E": (0.26, 0.24), "F": (0.16, 0.17),
            "G": (0.32, 0.12), "H": (0.32, 0.2)}[shape]
    m = VGroup(hole(w, h))
    if shape in ("B", "C", "D", "G"):
        m.add(Rectangle(width=w * 0.6, height=min(0.06, h * 0.35), fill_color="#FFFFFF", fill_opacity=1,
                        stroke_width=0).move_to(c + UP * (h / 2 - min(0.06, h * 0.35) / 2 - 0.015)))
    if shape in ("D", "H"):
        m.add(Ellipse(width=w * 0.5, height=h * 0.35, fill_color="#FF6B9A", fill_opacity=1, stroke_width=0)
              .move_to(c + (DOWN if shape == "D" else UP) * h * 0.18))
    return m


def maya(pose: Pose = Pose(expression="happy")) -> VGroup:
    st = style("maya")
    p, ink = st.palette, st.ink
    if pose.expression not in MAYA_EXPR:
        raise ValueError(f"maya has no expression {pose.expression!r}")
    brow_a, brow_up, rest, eye_s, cheek_a, auto_extras = MAYA_EXPR[pose.expression]
    gx, gy = pose.gaze
    legs = VGroup(*[_o(RoundedRectangle(width=0.35, height=1.0, corner_radius=0.15, fill_color=p["trousers"],
                                        fill_opacity=1), ink, 4).move_to(_pt(x, 0.65)) for x in (-0.3, 0.3)])
    shoes = VGroup(*[_o(Ellipse(width=0.6, height=0.3, fill_color=p["shoes"], fill_opacity=1), ink, 4)
                     .move_to(_pt(x + 0.05, 0.15)) for x in (-0.35, 0.35)])
    torso = _o(RoundedRectangle(width=1.5, height=1.5, corner_radius=0.5, fill_color=p["hoodie"], fill_opacity=1),
               ink).move_to(_pt(0, 1.85))
    belt = _o(Rectangle(width=1.5, height=0.22, fill_color=p["belt"], fill_opacity=1), ink, 3).move_to(_pt(0, 1.45))
    buckle = _o(Rectangle(width=0.22, height=0.16, fill_color="#FFD166", fill_opacity=1), ink, 3).move_to(_pt(0, 1.45))
    head_c = _pt(0, 3.45)
    puffs = VGroup(*[_o(Circle(r, fill_color=p["hair"], fill_opacity=1), ink, 5).move_to(head_c + off)
                     for r, off in ((0.55, _pt(-0.95, 0.7)), (0.55, _pt(0.95, 0.7)), (0.75, _pt(0, 0.75)))])
    head = _o(Circle(0.95, fill_color=p["skin"], fill_opacity=1), ink).move_to(head_c)
    band = Line(head_c + _pt(-0.8, 0.75), head_c + _pt(0.8, 0.75), stroke_width=12, color=p["strap"])
    goggles = VGroup(*[_o(Circle(0.27, fill_color=p["goggles"], fill_opacity=1), ink, 6)
                       .move_to(head_c + _pt(x, 0.92)) for x in (-0.33, 0.33)])
    eyes = VGroup()
    for x in (-0.33, 0.33):
        ec = head_c + _pt(x + 0.04 * gx, 0.02 + 0.03 * gy)
        if eye_s == 0.0 or pose.blink > 0.85:     # laugh squint or closed
            eyes.add(Arc(radius=0.13, start_angle=0.2, angle=PI - 0.4, color=ink, stroke_width=6).move_to(ec))
            continue
        white = Ellipse(width=0.26 * eye_s, height=0.34 * eye_s * max(0.1, 1 - pose.blink), color=WHITE_,
                        fill_opacity=1, stroke_color=ink, stroke_width=3).move_to(ec)
        pupil = Dot(ec + _pt(0.06 * gx + 0.02, 0.06 * gy), radius=0.08 * min(1.0, eye_s), color=ink)
        pupil.stretch(max(0.1, 1 - pose.blink), 1)
        eyes.add(VGroup(white, pupil, Dot(pupil.get_center() + _pt(0.03, 0.03), radius=0.022, color=WHITE_)))
    brows = VGroup(*[Line(LEFT * 0.13, RIGHT * 0.13, stroke_width=7, color=p["hair"])
                     .rotate(brow_a * (1 if x < 0 else -1)).move_to(head_c + _pt(x, 0.27 + brow_up))
                     for x in (-0.33, 0.33)])
    nose = Arc(radius=0.07, start_angle=PI * 1.1, angle=PI * 0.8, color=ink, stroke_width=4) \
        .move_to(head_c + _pt(0.02, -0.15))
    mouth = _maya_mouth(pose.mouth, rest, head_c + _pt(0.02 * gx, -0.42), ink)
    cheeks = VGroup(*[Ellipse(width=0.25, height=0.13, color=p["cheek"], fill_opacity=cheek_a, stroke_width=0)
                      .move_to(head_c + _pt(x, -0.22)) for x in (-0.55, 0.55)])
    ears = VGroup(*[_o(Circle(0.16, fill_color=p["skin"], fill_opacity=1), ink, 4).move_to(head_c + _pt(x, -0.05))
                    for x in (-0.93, 0.93)])
    sh_l, sh_r = _pt(-0.68, 2.35), _pt(0.68, 2.35)
    arms = []
    for sh, ang, side in ((sh_l, pose.arm_l, -1), (sh_r, pose.arm_r, 1)):
        c = _limb(sh, ang, 1.25, side, bend=0.18)
        arms += [c.copy().set_stroke(ink, 26), c.copy().set_stroke(p["hoodie"], 18)]
    hand_l = _o(Circle(0.18, fill_color=p["skin"], fill_opacity=1), ink, 4).move_to(arms[0].get_end())
    hand_r = _o(Circle(0.18, fill_color=p["skin"], fill_opacity=1), ink, 4).move_to(arms[2].get_end())
    extras = _extras(tuple(dict.fromkeys(auto_extras + pose.extras)), head_c + UP * 1.0, ink)
    parts = dict(legs=legs, shoes=shoes, arm_l=VGroup(arms[0], arms[1]), hand_l=hand_l,
                 arm_r=VGroup(arms[2], arms[3]), hand_r=hand_r, torso=torso, belt=belt, buckle=buckle,
                 puffs=puffs, ears=ears, head=head, cheeks=cheeks, eyes=eyes, brows=brows, nose=nose, mouth=mouth,
                 band=band, goggles=goggles, extras=extras)
    g = VGroup(*parts.values())
    return _finish(g, parts, pose)


WHITE_ = "#FFFFFF"


# ----------------------------------------------------------------------------------- Nib

NIB_EYES = {"happy": "arc", "surprised": "wide", "proud": "arc", "dizzy": "spiral"}
NIB_EXTRAS = {"proud": ("sparkle",), "dizzy": ("stars",)}


def nib(pose: Pose = Pose(expression="happy")) -> VGroup:
    st = style("nib")
    p, ink = st.palette, st.ink
    if pose.expression not in NIB_EYES:
        raise ValueError(f"nib has no expression {pose.expression!r}")
    gx, gy = pose.gaze
    body_c = _pt(0, 0.55)
    feet = VGroup(*[Line(_pt(x, 0.2), _pt(x, 0.0), color=ink, stroke_width=4) for x in (-0.12, 0.12)])
    feet.add(*[Line(_pt(x - 0.06, 0.0), _pt(x + 0.08, 0.0), color=ink, stroke_width=4) for x in (-0.12, 0.12)])
    body = _o(Ellipse(width=0.9, height=0.75, fill_color=p["body"], fill_opacity=1), ink, 5).move_to(body_c)
    belly = Ellipse(width=0.45, height=0.3, fill_color="#FFD1E0", fill_opacity=1, stroke_width=0) \
        .move_to(body_c + _pt(0.05, -0.18))
    ec = body_c + _pt(0.12, 0.08)
    kind = NIB_EYES[pose.expression]
    if pose.blink > 0.85 or kind == "arc":
        eye = Arc(radius=0.14, start_angle=0.2, angle=PI - 0.4, color=ink, stroke_width=6).move_to(ec)
    elif kind == "spiral":
        pts = [ec + 0.02 * t * np.array([math.cos(t), math.sin(t), 0]) for t in np.linspace(0, 4 * PI, 40)]
        eye = VGroup(Circle(0.2, color=WHITE_, fill_opacity=1, stroke_color=ink, stroke_width=3).move_to(ec),
                     VMobject(color=ink, stroke_width=3).set_points_smoothly(pts))
    else:
        r = 0.24 if kind == "wide" else 0.2
        white = Circle(r, color=WHITE_, fill_opacity=1, stroke_color=ink, stroke_width=3).move_to(ec)
        pupil = Dot(ec + _pt(0.05 + 0.05 * gx, 0.05 * gy), radius=0.06 if kind == "wide" else 0.09, color=ink)
        eye = VGroup(white, pupil)
        if pose.blink:
            eye.stretch(max(0.1, 1 - pose.blink), 1)
    open_amt = {"A": 0.0, "X": 0.0, "B": 0.3, "C": 0.6, "D": 1.0, "E": 0.7, "F": 0.4, "G": 0.2, "H": 0.6}[pose.mouth]
    tip = body_c + _pt(0.44, 0.0)
    upper = _o(Polygon(tip + _pt(-0.04, 0.09), tip + _pt(-0.04, -0.01), tip + _pt(0.22, 0.02 + 0.05 * open_amt),
                       fill_color=p["beak"], fill_opacity=1), ink, 3)
    lower = _o(Polygon(tip + _pt(-0.04, -0.01), tip + _pt(-0.04, -0.08), tip + _pt(0.18, -0.03 - 0.1 * open_amt),
                       fill_color=p["beak"], fill_opacity=1), ink, 3)
    beak = VGroup(lower, upper)
    flap = math.radians(pose.arm_l - 20)
    wing = _o(Ellipse(width=0.45, height=0.25, fill_color=p["wing"], fill_opacity=1), ink, 3) \
        .move_to(body_c + _pt(-0.22, -0.02)).rotate(0.4 + flap, about_point=body_c + _pt(-0.05, 0.02))
    mast = Line(body_c + UP * 0.37, body_c + UP * 0.57, color=ink, stroke_width=5)
    blade_w = 0.15 + 0.75 * abs(math.cos(pose.prop))
    prop = _o(Ellipse(width=blade_w, height=0.12, fill_color=p["prop"], fill_opacity=1), ink, 3) \
        .move_to(mast.get_end())
    hub = Dot(mast.get_end(), radius=0.05, color=ink)
    extras = _extras(tuple(dict.fromkeys(NIB_EXTRAS.get(pose.expression, ()) + pose.extras)),
                     body_c + UP * 0.6, ink)
    extras.scale(0.6, about_point=body_c + UP * 0.6)
    parts = dict(feet=feet, body=body, belly=belly, wing=wing, eye=eye, beak=beak, mast=mast, prop=prop, hub=hub,
                 extras=extras)
    g = VGroup(*parts.values())
    return _finish(g, parts, pose)


BUILDERS = {"bolt": bolt, "maya": maya, "nib": nib}


def build(cid: str, pose: Pose | None = None) -> VGroup:
    if cid not in BUILDERS:
        raise ValueError(f"no rig for character {cid!r}")
    return BUILDERS[cid](pose or Pose())
