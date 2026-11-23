"""Animated robot-family vignettes (M03.4): little looping cartoons that replace the still album icons.

Each ``vignette(kind, t)`` returns a VGroup that fits a ~1.6 x 1.3 tile centred on the origin and is a pure function
of ``t`` (seconds), so frames stay independent and deterministic:

* ``vacuum`` — a robot vacuum sweeps the floor, sucking up dust, bumps the wall (squash + star) and turns back.
* ``rover``  — a space rover drives over scrolling bumpy terrain; wheels spin, body tilts with the slope.
* ``arm``    — a factory arm picks a box off one conveyor and places it on the other (2-link IK), forever.
"""

from __future__ import annotations

import math

import numpy as np
from manim import PI, Circle, Dot, Ellipse, Line, Polygon, Rectangle, RoundedRectangle, Star, VGroup

from robotics101.cartoon.motion import bump, clamp01, ease_in_out
from robotics101.cartoon.sets import ink

TILE_W, TILE_H = 1.6, 1.3


def P(x: float, y: float) -> np.ndarray:
    return np.array([x, y, 0.0])


def _o(m, w=4):
    return m.set_stroke(ink(), w)


def _bg(color: str) -> RoundedRectangle:
    return RoundedRectangle(width=TILE_W, height=TILE_H, corner_radius=0.12, fill_color=color, fill_opacity=1,
                            stroke_width=0)


# ------------------------------------------------------------------------------------------ vacuum

VAC_PERIOD = 4.0
DUST_X = (-0.45, -0.25, -0.05, 0.15, 0.35, 0.5)


def vacuum_x(t: float) -> tuple[float, int, float]:
    """(x, direction, bump 0..1) of the vacuum at time t: right sweep, wall bump, left sweep, wall bump."""
    u = (t % VAC_PERIOD) / VAC_PERIOD
    if u < 0.5:
        x, d = -0.48 + 0.96 * ease_in_out(u / 0.5), 1
    else:
        x, d = 0.48 - 0.96 * ease_in_out((u - 0.5) / 0.5), -1
    edge = min(u, abs(u - 0.5), 1 - u)
    return x, d, clamp01(1 - edge / 0.04)


def vacuum(t: float) -> VGroup:
    g = VGroup(_bg("#E0FBFC"))
    floor_y = -0.42
    g.add(Rectangle(width=TILE_W, height=0.23, fill_color="#E9C46A", fill_opacity=1, stroke_width=0)
          .move_to(P(0, -0.535)))
    for wx in (-0.78, 0.78):
        g.add(Rectangle(width=0.06, height=1.0, fill_color="#8D5524", fill_opacity=1, stroke_width=0)
              .move_to(P(wx, -0.1)))
    x, d, hit = vacuum_x(t)
    u = (t % VAC_PERIOD) / VAC_PERIOD
    for dx in DUST_X:                       # dust: cleaned once passed on the right sweep, sprinkled back at the end
        cleaned = (u < 0.5 and dx < x - 0.1) or (u >= 0.5)
        regrow = clamp01((u - 0.93) / 0.07)
        if not cleaned or regrow > 0:
            r = 0.035 * (regrow if cleaned else 1.0)
            if r > 0.004:
                g.add(Dot(P(dx, floor_y + 0.02), radius=r, color="#6D597A"))
    squash = 1 - 0.25 * hit
    body = VGroup(_o(Ellipse(width=0.56, height=0.2, fill_color="#8D99AE", fill_opacity=1)),
                  _o(Ellipse(width=0.36, height=0.12, fill_color="#2EC4B6", fill_opacity=1)).shift(P(0, 0.05)),
                  Dot(P(0.14 * d, 0.07), radius=0.025, color="#06D6A0" if int(t * 3) % 2 else "#FFFFFF"))
    brush = VGroup(*[Line(P(0, 0), P(0.09 * math.cos(a), 0.09 * math.sin(a)), stroke_width=3, color=ink())
                     for a in (t * 18 + k * PI / 2 for k in range(4))]).move_to(P(0.2 * d, -0.08))
    vac = VGroup(body, brush).scale(1.3).stretch(squash, 0).stretch(1 + 0.15 * hit, 1)
    g.add(vac.move_to(P(x, floor_y + 0.1)))
    if hit > 0.05:                          # bump star at the wall
        g.add(Star(5, outer_radius=0.12 * hit + 0.02, inner_radius=0.05, fill_color="#FFD166", fill_opacity=1,
                   stroke_width=0).move_to(P(0.62 * (1 if x > 0 else -1), 0.0)).rotate(t * 6))
    if u < 0.5:                             # little sparkles behind the clean path
        for k in range(2):
            sx = x - 0.18 - 0.14 * k
            if sx > -0.6:
                g.add(Star(4, outer_radius=0.04, inner_radius=0.015, fill_color="#FFFFFF", fill_opacity=1,
                           stroke_width=0).move_to(P(sx, floor_y + 0.12 + 0.05 * math.sin(10 * t + k))))
    return g


# ------------------------------------------------------------------------------------------ rover

def terrain(x: float, t: float) -> float:
    s = x + 0.45 * t
    return -0.36 + 0.09 * math.sin(2.6 * s) + 0.04 * math.sin(6.1 * s + 1.0)


def rover(t: float) -> VGroup:
    g = VGroup(_bg("#FFE5D9"))
    g.add(_o(Circle(0.16, fill_color="#F4A261", fill_opacity=1), 3).move_to(P(0.5, 0.38)))       # planet
    g.add(Dot(P(-0.5, 0.42), radius=0.02, color="#FFFFFF"), Dot(P(-0.2, 0.3), radius=0.015, color="#FFFFFF"))
    xs = np.linspace(-TILE_W / 2, TILE_W / 2, 33)
    pts = [P(x, terrain(x, t)) for x in xs] + [P(TILE_W / 2, -TILE_H / 2), P(-TILE_W / 2, -TILE_H / 2)]
    g.add(Polygon(*pts, fill_color="#E76F51", fill_opacity=1, stroke_color=ink(), stroke_width=3))
    for k in range(3):                      # scrolling rocks
        rx = ((0.7 * k - 0.45 * t) % 2.0) - 1.0
        if -0.75 < rx < 0.75:
            g.add(_o(Ellipse(width=0.1, height=0.06, fill_color="#9C6644", fill_opacity=1), 2)
                  .move_to(P(rx, terrain(rx, t) - 0.08)))
    yb, yf = terrain(-0.15, t), terrain(0.15, t)
    tilt = math.atan2(yf - yb, 0.3)
    wheel_r = 0.07
    body = _o(RoundedRectangle(width=0.46, height=0.16, corner_radius=0.05, fill_color="#F4F1DE", fill_opacity=1), 3)
    mast = Line(P(0.12, 0.08), P(0.12, 0.24), stroke_width=4, color=ink())
    cam = _o(Rectangle(width=0.12, height=0.07, fill_color="#2EC4B6", fill_opacity=1), 2).move_to(P(0.12, 0.27))
    panel = _o(Rectangle(width=0.26, height=0.04, fill_color="#118AB2", fill_opacity=1), 2).move_to(P(-0.08, 0.1))
    wheels = VGroup()
    for wx in (-0.17, 0.0, 0.17):
        a = -t * 6.0
        wh = VGroup(_o(Circle(wheel_r, fill_color="#45505E", fill_opacity=1), 2),
                    Line(P(-wheel_r * math.cos(a), -wheel_r * math.sin(a)), P(wheel_r * math.cos(a), wheel_r * math.sin(a)),
                         stroke_width=2, color="#FFFFFF"))
        wheels.add(wh.move_to(P(wx, -0.11)))
    rv = VGroup(body, mast, cam, panel, wheels).rotate(tilt, about_point=P(0, -0.11))
    ymid = (yb + yf) / 2 + wheel_r + 0.01 + 0.012 * abs(math.sin(14 * t))    # wheels on the ground, rattling
    g.add(rv.shift(P(0, ymid + 0.11)))
    for k in range(3):                      # dust puffs behind the wheels
        pu = (t * 2 + k / 3) % 1.0
        g.add(Circle(0.02 + 0.05 * pu, fill_color="#F4A261", fill_opacity=0.6 * (1 - pu), stroke_width=0)
              .move_to(P(-0.3 - 0.35 * pu, terrain(-0.3, t) + 0.05 + 0.1 * pu)))
    return g


# ------------------------------------------------------------------------------------------ factory arm

ARM_PERIOD = 3.2
L1, L2 = 0.5, 0.46
BASE = P(0.0, -0.42)
PICK, PLACE, LIFT = P(-0.55, -0.3), P(0.55, -0.3), P(0.0, 0.3)


def _ik(target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    v = target - BASE
    d = min(L1 + L2 - 1e-3, max(abs(L1 - L2) + 1e-3, float(np.hypot(v[0], v[1]))))
    a = math.atan2(v[1], v[0])
    c = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    k = math.acos(max(-1.0, min(1.0, c)))
    elbow = max((BASE + P(L1 * math.cos(a + sg * k), L1 * math.sin(a + sg * k)) for sg in (1, -1)),
                key=lambda e: e[1])                     # elbow up (the higher solution)
    tip = BASE + P(d * math.cos(a), d * math.sin(a))
    return elbow, tip


def arm_target(t: float) -> tuple[np.ndarray, str]:
    """Gripper target + phase: reach, grip, carry, drop, back."""
    u = (t % ARM_PERIOD) / ARM_PERIOD

    def lerp(a, b, k):
        k = ease_in_out(k)
        return a + (b - a) * k
    if u < 0.2:
        return lerp(LIFT, PICK, u / 0.2), "reach"
    if u < 0.3:
        return PICK, "grip"
    if u < 0.45:
        return lerp(PICK, LIFT, (u - 0.3) / 0.15), "carry"
    if u < 0.62:
        return lerp(LIFT, PLACE, (u - 0.45) / 0.17), "carry"
    if u < 0.72:
        return PLACE, "drop"
    return lerp(PLACE, LIFT, (u - 0.72) / 0.28), "back"


def arm(t: float) -> VGroup:
    g = VGroup(_bg("#EDF2F4"))
    for cx in (-0.55, 0.55):                # conveyors with moving stripes
        belt = _o(Rectangle(width=0.5, height=0.08, fill_color="#45505E", fill_opacity=1), 2).move_to(P(cx, -0.41))
        g.add(belt)
        for k in range(3):
            sx = cx - 0.2 + ((0.15 * k + 0.25 * t) % 0.45)
            g.add(Line(P(sx, -0.45), P(sx, -0.37), stroke_width=2, color="#FFD166"))
    g.add(_o(Rectangle(width=0.3, height=0.12, fill_color="#45505E", fill_opacity=1), 3).move_to(BASE + P(0, -0.06)))
    target, phase = arm_target(t)
    elbow, tip = _ik(target)
    u = (t % ARM_PERIOD) / ARM_PERIOD
    box = _o(Rectangle(width=0.16, height=0.14, fill_color="#FF9F1C", fill_opacity=1), 2)
    if phase in ("reach",):
        g.add(box.copy().move_to(PICK + P(0, -0.04)))                       # next box waiting
    elif phase == "grip" or phase == "carry":
        g.add(box.copy().move_to(tip + P(0, -0.1)))
    else:                                                                   # placed box rides away
        away = clamp01((u - 0.62) / 0.38)
        bx = 0.55 + 0.35 * away
        if bx < 0.78:
            g.add(box.copy().move_to(P(bx, -0.34)))
    g.add(Line(BASE, elbow, stroke_width=12, color="#FF9F1C"), Line(elbow, tip, stroke_width=9, color="#FF9F1C"))
    for j in (BASE, elbow):
        g.add(_o(Circle(0.05, fill_color="#FFE66D", fill_opacity=1), 2).move_to(j))
    grip_open = 0.07 if phase in ("reach", "back", "drop") else 0.035
    g.add(Line(tip, tip + P(-grip_open, -0.08), stroke_width=4, color=ink()),
          Line(tip, tip + P(grip_open, -0.08), stroke_width=4, color=ink()))
    if phase == "grip":
        g.add(Star(4, outer_radius=0.06, inner_radius=0.02, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0)
              .move_to(tip + P(0.12, 0.05)).rotate(t * 8))
    return g


KINDS = {"vacuum": vacuum, "rover": rover, "arm": arm}


def vignette(kind: str, t: float) -> VGroup | None:
    k = kind.lower()
    for name, fn in KINDS.items():
        if name in k:
            return fn(t)
    return None


__all__ = ["KINDS", "arm", "arm_target", "rover", "terrain", "vacuum", "vacuum_x", "vignette"]
