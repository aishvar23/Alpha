"""Full-screen teaching visuals (M05.6): one example or idea per illustration frame.

Each visual is ``fn(t, ctx, box) -> VGroup``, drawn inside ``box`` (world corners) above the caption band.
They are registered on ``visuals.VISUALS`` and used as illustration-only shots (no full-size characters).
"""

from __future__ import annotations

import math

import numpy as np
from manim import (DOWN, LEFT, PI, RIGHT, UP, Annulus, Arc, Circle, Ellipse, Line, Polygon, Rectangle,
                   RoundedRectangle, Square, Star, VGroup)

from robotics101.cartoon import props as PR
from robotics101.cartoon.layout import CONTENT_FLOOR_Y
from robotics101.cartoon.motion import bump, clamp01, ease_in_out, ease_out
from robotics101.cartoon.sets import ink
from robotics101.cartoon.vignettes import KINDS, arm_target, vacuum_x, vignette, terrain as rover_terrain

P = PR.P
ILLUSTRATION_BOX = (-7.05, CONTENT_FLOOR_Y, 7.05, 3.95)


def _o(m, w=5):
    return m.set_stroke(ink(), w)


def _u(t: float, a: float | None, d: float = 0.45) -> float:
    return 0.0 if a is None else clamp01((t - a) / d)


def board(box, color: str = "#FFFFFF") -> RoundedRectangle:
    """Flush fill of the teaching box — no inset card and no wide cream border."""
    x0, y0, x1, y1 = box
    return RoundedRectangle(width=x1 - x0, height=y1 - y0, corner_radius=0.08, fill_color=color,
                            fill_opacity=1, stroke_width=0).move_to(P((x0 + x1) / 2, (y0 + y1) / 2))


def title(text: str, box, y_off: float = 0.0, size: int = 64) -> VGroup:
    x0, y0, x1, y1 = box
    t = PR.txt(text, size, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL", stroke=5)
    if t.width > (x1 - x0) - 0.6:
        t.scale(((x1 - x0) - 0.6) / t.width)
    return t.move_to(P((x0 + x1) / 2, y1 - 0.48 + y_off))


def caption(text: str, box, size: int = 36, color: str = ink()) -> VGroup:
    x0, y0, x1, y1 = box
    t = PR.txt(text, size, color=color, font="Fredoka", weight="BOLD", stroke=3)
    if t.width > (x1 - x0) - 1.0:
        t.scale(((x1 - x0) - 1.0) / t.width)
    return t.move_to(P((x0 + x1) / 2, y0 + 0.55))


def _fit(art: VGroup, box, margin: float = 0.25, top: float = 1.05, bottom: float = 0.95) -> VGroup:
    x0, y0, x1, y1 = box
    aw, ah = max(art.width, 0.01), max(art.height, 0.01)
    art.scale(min((x1 - x0 - 2 * margin) / aw, (y1 - y0 - top - bottom) / ah))
    return art.move_to(P((x0 + x1) / 2, (y0 + bottom + y1 - top) / 2))


# ------------------------------------------------------------------------------------------ one example

def _toaster_art(t: float) -> VGroup:
    pop = 0.15 + 0.55 * abs(math.sin(PI * t / 1.6))
    body = _o(RoundedRectangle(width=2.4, height=1.7, corner_radius=0.3, fill_color="#C0C0C8", fill_opacity=1), 7)
    slot = Rectangle(width=1.4, height=0.12, fill_color=ink(), fill_opacity=1, stroke_width=0).move_to(P(0, 0.65))
    toast = _o(RoundedRectangle(width=1.15, height=1.05, corner_radius=0.15, fill_color="#E9C46A", fill_opacity=1), 5)
    toast.move_to(P(0, 0.7 + pop))
    lever = _o(Rectangle(width=0.18, height=0.5, fill_color="#FF9F1C", fill_opacity=1), 4).move_to(P(1.35, 0.05))
    base = _o(Rectangle(width=2.6, height=0.18, fill_color="#8D5524", fill_opacity=1), 4).move_to(P(0, -0.95))
    return VGroup(base, toast, body, slot, lever)


def _art_box(box, top: float = 1.05, bottom: float = 0.95, pad: float = 0.15):
    x0, y0, x1, y1 = box
    return (x0 + pad, y0 + bottom, x1 - pad, y1 - top)


def _vacuum_full(t: float, area) -> VGroup:
    """Robot vacuum sweeping a wide room that fills the teaching frame."""
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    g = VGroup(Rectangle(width=w, height=h, fill_color="#E0FBFC", fill_opacity=1, stroke_width=0).move_to(P(cx, cy)))
    floor_h = 0.28 * h
    g.add(Rectangle(width=w, height=floor_h, fill_color="#E9C46A", fill_opacity=1, stroke_width=0)
          .move_to(P(cx, y0 + floor_h / 2)))
    for wx in (x0 + 0.12, x1 - 0.12):
        g.add(Rectangle(width=0.22, height=h, fill_color="#8D5524", fill_opacity=1, stroke_width=0)
              .move_to(P(wx, cy)))
    vx, d, hit = vacuum_x(t)
    px = x0 + 2.6 + ((vx + 0.48) / 0.96) * (w - 5.2)
    fy = y0 + floor_h + 0.05
    squash = 1 - 0.25 * hit
    body = VGroup(_o(Ellipse(width=6.2, height=2.25, fill_color="#8D99AE", fill_opacity=1), 8),
                  _o(Ellipse(width=3.9, height=1.3, fill_color="#2EC4B6", fill_opacity=1), 6).shift(P(0, 0.42)),
                  Circle(0.30, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0).move_to(P(1.4 * d, 0.52)))
    vac = VGroup(body).stretch(squash, 0).stretch(1 + 0.15 * hit, 1)
    g.add(vac.move_to(P(px, fy + 1.15)))
    if hit > 0.05:
        g.add(Star(5, outer_radius=0.7 * hit + 0.18, inner_radius=0.16, fill_color="#FFD166", fill_opacity=1,
                   stroke_width=0).move_to(P(px + 2.2 * d, fy + 1.5)).rotate(t * 6))
    return g


def _rover_full(t: float, area) -> VGroup:
    """Space rover on a wide Martian slope that fills the teaching frame."""
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    g = VGroup(Rectangle(width=w, height=h, fill_color="#FFE5D9", fill_opacity=1, stroke_width=0).move_to(P(cx, cy)))
    g.add(_o(Circle(0.7, fill_color="#F4A261", fill_opacity=1), 4).move_to(P(x1 - 1.8, y1 - 1.1)))
    def gy(x):
        return y0 + 0.55 * h + 0.55 * math.sin((x - x0) * 0.45 + 0.45 * t)
    xs = np.linspace(x0, x1, 48)
    pts = [P(x, gy(x)) for x in xs] + [P(x1, y0), P(x0, y0)]
    g.add(Polygon(*pts, fill_color="#E76F51", fill_opacity=1, stroke_color=ink(), stroke_width=4))
    rx0 = cx
    yb, yf = gy(rx0 - 0.7), gy(rx0 + 0.7)
    tilt = math.atan2(yf - yb, 1.4)
    wr = 0.55
    body = _o(RoundedRectangle(width=3.8, height=1.25, corner_radius=0.28, fill_color="#F4F1DE", fill_opacity=1), 8)
    mast = Line(P(0.85, 0.55), P(0.85, 1.85), stroke_width=12, color=ink())
    cam = _o(Rectangle(width=0.95, height=0.52, fill_color="#2EC4B6", fill_opacity=1), 5).move_to(P(0.85, 2.1))
    panel = _o(Rectangle(width=1.9, height=0.26, fill_color="#118AB2", fill_opacity=1), 4).move_to(P(-0.45, 0.75))
    wheels = VGroup()
    for wx in (-1.35, 0.0, 1.35):
        a = -t * 6.0
        wh = VGroup(_o(Circle(wr, fill_color="#45505E", fill_opacity=1), 6),
                    Line(P(-wr * math.cos(a), -wr * math.sin(a)), P(wr * math.cos(a), wr * math.sin(a)),
                         stroke_width=7, color="#FFFFFF"))
        wheels.add(wh.move_to(P(wx, -0.85)))
    rv = VGroup(body, mast, cam, panel, wheels).rotate(tilt, about_point=P(0, -0.85))
    g.add(rv.move_to(P(rx0, (yb + yf) / 2 + 0.95)))
    return g


def _arm_full(t: float, area) -> VGroup:
    """Factory arm on wide conveyors that fills the teaching frame."""
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    g = VGroup(Rectangle(width=w, height=h, fill_color="#EDF2F4", fill_opacity=1, stroke_width=0).move_to(P(cx, cy)))
    gy = y0 + 0.28 * h
    for side, sx in ((-1, cx - 3.6), (1, cx + 3.6)):
        belt = _o(RoundedRectangle(width=5.2, height=0.7, corner_radius=0.1, fill_color="#45505E", fill_opacity=1), 5)
        g.add(belt.move_to(P(sx, gy)))
        for k in range(7):
            bx = sx - 2.3 + ((0.7 * k + 0.9 * t) % 4.6)
            if sx - 2.5 < bx < sx + 2.5:
                g.add(Line(P(bx, gy - 0.28), P(bx, gy + 0.28), stroke_width=6, color="#FFD166"))
    base = P(cx, gy + 0.5)
    target, phase = arm_target(t)
    def map_pt(pt):
        return P(cx + (pt[0] - 0.0) * 6.4, gy + 0.5 + (pt[1] + 0.42) * 6.0)
    tgt, elbow_t = map_pt(target), None
    L1, L2 = 3.0, 2.7
    v = tgt - base
    d = min(L1 + L2 - 1e-3, max(abs(L1 - L2) + 1e-3, float(np.hypot(v[0], v[1]))))
    a = math.atan2(v[1], v[0])
    c = (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d)
    k = math.acos(max(-1.0, min(1.0, c)))
    elbow = max((base + P(L1 * math.cos(a + sg * k), L1 * math.sin(a + sg * k)) for sg in (1, -1)),
                key=lambda e: e[1])
    tip = base + P(d * math.cos(a), d * math.sin(a))
    g.add(_o(Rectangle(width=2.0, height=0.7, fill_color="#45505E", fill_opacity=1), 5).move_to(base + P(0, -0.2)))
    g.add(Line(base, elbow, stroke_width=36, color="#FF9F1C"), Line(elbow, tip, stroke_width=28, color="#FF9F1C"))
    for j in (base, elbow):
        g.add(_o(Circle(0.32, fill_color="#FFE66D", fill_opacity=1), 6).move_to(j))
    grip = 0.45 if phase in ("reach", "back", "drop") else 0.18
    g.add(Line(tip, tip + P(-grip, -0.5), stroke_width=14, color=ink()),
          Line(tip, tip + P(grip, -0.5), stroke_width=14, color=ink()))
    box = _o(RoundedRectangle(width=1.05, height=0.9, corner_radius=0.1, fill_color="#FF9F1C", fill_opacity=1), 6)
    if phase == "reach":
        g.add(box.move_to(P(cx - 3.6, gy + 0.8)))
    elif phase in ("grip", "carry"):
        g.add(box.move_to(tip + P(0, -0.65)))
    else:
        g.add(box.move_to(P(cx + 3.6, gy + 0.8)))
    return g


def one_example(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """One example, full screen: a large animated illustration and its name. Never a grid of several examples."""
    kind = (ctx.get("kind") or ctx.get("example") or "robot").lower()
    label = ctx.get("label") or kind.replace("_", " ").title()
    sub = ctx.get("subtitle") or ""
    g = VGroup(board(box, "#FFFDF6"))
    area = box  # full-bleed into the teaching box; title and caption sit on top of the scene
    if kind == "toaster":
        g.add(_fit(_toaster_art(t), box, margin=0.4, top=1.1, bottom=1.0))
        sub = sub or "Not a robot — it doesn't think"
    elif "vacuum" in kind:
        g.add(_vacuum_full(t, area))
    elif kind in ("arm", "factory_arm") or "arm" in kind:
        g.add(_arm_full(t, area))
    elif "rover" in kind:
        g.add(_rover_full(t, area))
    elif kind in KINDS:
        g.add(_fit(vignette(kind, t), box))
    else:
        g.add(_fit(PR.icon(kind), box))
    g.add(title(label.upper() + "!", box))
    if sub:
        g.add(caption(sub, box))
    else:
        g.add(caption(label, box))
    return g


# ------------------------------------------------------------------------------------------ checkup parts

_PART_SUB = {
    "structure": "The body — the frame that holds everything together",
    "sensors": "They notice the world, like eyes and ears",
    "actuators": "The parts that move — wheels and arms",
    "power": "The battery that gives the robot energy",
    "controller": "The robot brain that decides what to do",
}


def _part_structure(t: float) -> VGroup:
    """A wide robot frame that breathes so the board never freezes."""
    pulse = 1.0 + 0.045 * math.sin(2.4 * t)
    body = _o(RoundedRectangle(width=5.6, height=3.1, corner_radius=0.9, fill_color="#2EC4B6", fill_opacity=1), 8)
    riv = VGroup()
    for x, y in ((-1.85, 0.95), (1.85, 0.95), (-1.85, -0.95), (1.85, -0.95)):
        tw = 0.12 + 0.04 * math.sin(3.1 * t + x + y)
        riv.add(Circle(tw, fill_color=ink(), fill_opacity=1, stroke_width=0).move_to(P(x, y)))
    return VGroup(body, riv, PR.txt("FRAME", 52, color="#FFFFFF", font="Luckiest Guy", stroke=3)).scale(pulse)


def _part_sensors(t: float) -> VGroup:
    """Eye-like distance sensor: a recognisable transducer head sending out ping waves."""
    house = _o(RoundedRectangle(width=4.4, height=3.0, corner_radius=0.7, fill_color="#2EC4B6", fill_opacity=1), 8)
    # two 'eyes' / transducers
    eyes = VGroup()
    for dx in (-0.55, 0.55):
        ring = _o(Circle(0.78, fill_color="#1B263B", fill_opacity=1), 6).move_to(P(dx * 1.35, 0.1))
        disc = Circle(0.38, fill_color="#E8F6FF", fill_opacity=1, stroke_width=0).move_to(P(dx * 1.35, 0.1))
        eyes.add(ring, disc)
    # ping waves travelling right
    waves = VGroup()
    for i in range(4):
        phase = (t * 1.4 + i * 0.35) % 1.4
        rad = 1.1 + 1.15 * phase
        waves.add(Arc(radius=rad, start_angle=-0.55, angle=1.1, color="#4CC9F0",
                      stroke_width=10 * (1 - phase / 1.4)).move_to(P(2.35 + 0.15 * phase, 0.1)))
    return VGroup(waves, house, eyes)


def _part_actuators(t: float) -> VGroup:
    """A spinning wheel plus a two-joint arm that moves — recognisable actuators, not abstract shapes."""
    spin = t * 2.2
    tire = _o(Circle(1.15, fill_color="#2B2B2B", fill_opacity=1), 8).move_to(P(-2.1, -0.15))
    hub = _o(Circle(0.38, fill_color="#FFD166", fill_opacity=1), 5).move_to(tire)
    spokes = VGroup()
    for i in range(6):
        a = spin + i * PI / 3
        spokes.add(Line(tire.get_center(), tire.get_center() + 0.95 * np.array([math.cos(a), math.sin(a), 0]),
                        stroke_width=8, color="#FFD166"))
    # 2-link arm on the right
    sh = P(0.6, -0.2)
    a1 = math.radians(55 + 40 * math.sin(t))
    a2 = math.radians(40 + 35 * math.sin(1.3 * t + 0.6))
    e = sh + P(1.6 * math.cos(a1), 1.6 * math.sin(a1))
    tip = e + P(1.25 * math.cos(a1 + a2), 1.25 * math.sin(a1 + a2))
    arm1 = Line(sh, e, stroke_width=26, color="#FF9F1C")
    arm2 = Line(e, tip, stroke_width=20, color="#FF9F1C")
    joints = VGroup(_o(Circle(0.28, fill_color="#FFE66D", fill_opacity=1), 5).move_to(sh),
                    _o(Circle(0.22, fill_color="#FFE66D", fill_opacity=1), 5).move_to(e))
    grip = VGroup(Line(tip, tip + P(0.28, -0.28), stroke_width=10, color=ink()),
                  Line(tip, tip + P(-0.08, -0.38), stroke_width=10, color=ink()))
    base = _o(RoundedRectangle(width=1.1, height=0.45, corner_radius=0.08, fill_color="#45505E", fill_opacity=1), 5)
    base.move_to(sh + P(0, -0.35))
    return VGroup(tire, spokes, hub, base, arm1, arm2, joints, grip)


def _part_power(t: float, ctx: dict) -> VGroup:
    """Big battery that fills, with a plug seating into a port and a spark when connected."""
    seated = bool(ctx.get("seated", True))
    fill_u = ctx.get("fill")
    if fill_u is None:
        fill_u = 0.2 + 0.8 * clamp01((t - (ctx.get("t0") or 0)) / 3.0)
    batt = PR.battery(fill_u, charging=seated).scale(3.2)
    # port + plug on the left of the battery
    port = _o(RoundedRectangle(width=0.55, height=0.7, corner_radius=0.08, fill_color="#3D3D3D", fill_opacity=1), 5)
    port.move_to(batt.get_left() + LEFT * 0.15)
    plug = _o(RoundedRectangle(width=0.7, height=0.45, corner_radius=0.08, fill_color="#FFD166", fill_opacity=1), 5)
    # fully seated: plug overlaps the port opening, no gap
    plug.move_to(port.get_center() + LEFT * 0.05)
    prongs = VGroup(*[Rectangle(width=0.22, height=0.08, fill_color="#C0C0C8", fill_opacity=1, stroke_width=0)
                      .move_to(plug.get_right() + RIGHT * 0.02 + UP * dy) for dy in (0.1, -0.1)])
    spark = VGroup()
    if seated:
        spark = VGroup(*[Star(4, outer_radius=0.22 + 0.06 * (i % 2), inner_radius=0.07,
                              fill_color="#FFE66D", fill_opacity=1, stroke_color=ink(), stroke_width=2)
                         .move_to(port.get_center() + P(-0.15 + 0.25 * math.cos(i), 0.35 * math.sin(i + 2 * t)))
                         for i in range(4)])
    cable = Line(plug.get_left() + LEFT * 0.05, plug.get_left() + LEFT * 1.6, stroke_width=14, color="#45505E")
    return VGroup(cable, port, plug, prongs, batt, spark)


def _part_controller(t: float) -> VGroup:
    chip = _o(RoundedRectangle(width=4.4, height=2.8, corner_radius=0.25, fill_color="#22223B", fill_opacity=1), 7)
    pins = VGroup()
    for x in np.linspace(-1.6, 1.6, 8):
        for y in (1.55, -1.55):
            on = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(4.0 * t + x * 1.3 + y))
            pins.add(Rectangle(width=0.16, height=0.45, fill_color="#C0C0C8", fill_opacity=on, stroke_width=0)
                     .move_to(P(x, y)))
    glow = Circle(0.85 + 0.22 * math.sin(3.2 * t), fill_color="#7CFFCB",
                  fill_opacity=0.22 + 0.16 * math.sin(3.2 * t), stroke_width=0)
    brain = PR.txt("CPU", 80, color="#7CFFCB", font="Luckiest Guy", stroke=3)
    return VGroup(pins, chip, glow, brain)


_PART_ART = {
    "structure": _part_structure,
    "sensors": _part_sensors,
    "actuators": _part_actuators,
    "controller": _part_controller,
}


def checkup_part(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    part = (ctx.get("part") or ctx.get("example") or "structure").lower()
    g = VGroup(board(box, "#F4FBFF"), title((ctx.get("label") or part).upper(), box))
    art = _part_power(t, ctx) if part == "power" else _PART_ART.get(part, _part_structure)(t)
    g.add(_fit(art, box, margin=0.2, top=1.05, bottom=1.0))
    g.add(caption(_PART_SUB.get(part, part), box))
    return g


# ------------------------------------------------------------------------------------------ the Rule + rematch

def the_rule(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#F7FFF4"), title("THE RULE", box))
    thr = ctx.get("threshold")
    thr_s = f"{thr:g} m" if thr is not None else "0.5 m"
    words = [("IF", "#FFFFFF"), ("distance", "#4CC9F0"), ("<", "#FFFFFF"), (thr_s, "#FFD166"),
             ("→", "#FFFFFF"), ("STOP", "#EF476F"), ("&", "#FFFFFF"), ("TURN", "#EF476F")]
    row = VGroup()
    for w, col in words:
        pill = _o(RoundedRectangle(width=0.1, height=1.15, corner_radius=0.2,
                                   fill_color="#1E1633" if col != "#FFFFFF" else "#3D3A5C", fill_opacity=1), 5)
        tx = PR.txt(w, 48 if len(w) < 8 else 36, color=col, font="Luckiest Guy", stroke=3)
        pill.stretch_to_fit_width(tx.width + 0.45)
        row.add(VGroup(pill, tx.move_to(pill)))
    row.arrange(RIGHT, buff=0.18)
    if row.width > (x1 - x0) - 1.2:
        row.scale(((x1 - x0) - 1.2) / row.width)
    # walk a highlight along the pills so the board never sits still
    n = len(row)
    hi = int((t * 1.3) % max(n, 1))
    for i, pill in enumerate(row):
        if i == hi:
            pill.scale(1.12)
            pill.shift(UP * 0.08)
    g.add(row.move_to(P((x0 + x1) / 2, (y0 + y1) / 2 + 0.1)))
    g.add(caption("Too close? Stop and turn!", box))
    return g


def rule_test(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """Side-view diagram of the rematch: drive, the 0.5 m line, stop & turn, then go."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#EAF7FF"), title("LET'S TEST THE RULE", box))
    # ground + 0.5 m mark + boxes on the right
    gy = (y0 + y1) / 2 - 0.4
    ground = Line(P(x0 + 0.8, gy), P(x1 - 0.8, gy), stroke_width=10, color=ink())
    thr = ctx.get("threshold") or 0.5
    mark_x = (x0 + x1) / 2 + 1.3
    mark = Line(P(mark_x, gy), P(mark_x, gy + 1.6), stroke_width=8, color="#EF476F")
    dash = VGroup(*[Line(P(mark_x - 0.12, gy + k), P(mark_x + 0.12, gy + k), stroke_width=4, color="#EF476F")
                    for k in np.linspace(0.15, 1.45, 5)])
    lab = PR.txt(f"{thr:g} m", 32, color="#EF476F", font="Luckiest Guy", stroke=3).move_to(P(mark_x, gy + 1.95))
    boxp = _o(RoundedRectangle(width=1.3, height=1.1, corner_radius=0.1, fill_color="#E76F51", fill_opacity=1), 5)
    boxp.move_to(P(x1 - 1.8, gy + 0.55))
    box2 = _o(RoundedRectangle(width=0.9, height=0.7, corner_radius=0.1, fill_color="#F4A261", fill_opacity=1), 5)
    box2.move_to(P(x1 - 1.8, gy + 1.45))
    # bolt triangle / simple robot on the left, arrow to the mark, then turn arrow
    # Bolt rolls toward the 0.5 m mark, then eases back, so the diagram keeps moving.
    u = 0.5 + 0.5 * math.sin(1.1 * t)
    rx = x0 + 2.0 + 1.6 * u
    robot = _o(RoundedRectangle(width=1.4, height=1.2, corner_radius=0.4, fill_color="#2EC4B6", fill_opacity=1), 6)
    robot.move_to(P(rx, gy + 0.7))
    arr = VGroup(Line(P(rx + 0.9, gy + 1.3), P(mark_x - 0.35, gy + 1.3), stroke_width=8, color="#06D6A0"),
                 Polygon(P(mark_x - 0.35, gy + 1.5), P(mark_x - 0.35, gy + 1.1), P(mark_x - 0.1, gy + 1.3),
                         fill_color="#06D6A0", fill_opacity=1, stroke_width=0))
    go = PR.txt("STOP & TURN", 36, color="#EF476F", font="Luckiest Guy", stroke=3).move_to(P(mark_x - 1.6, gy + 2.35))
    g.add(ground, mark, dash, lab, boxp, box2, robot, arr, go)
    g.add(caption("Sense the distance, stop before the boxes, then turn.", box))
    return g


# ------------------------------------------------------------------------------------------ servo

def servo_cutaway(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """A labelled cutaway: motor + gears + a position sensor that knows the angle, and the output horn."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#F4F7FF"), title("WHAT IS A SERVO?", box))
    cy = (y0 + y1) / 2 + 0.15
    # housing
    house = _o(RoundedRectangle(width=8.2, height=2.8, corner_radius=0.3, fill_color="#EEF2F7", fill_opacity=1), 7)
    house.move_to(P((x0 + x1) / 2, cy))
    # motor
    motor = _o(RoundedRectangle(width=1.7, height=1.6, corner_radius=0.15, fill_color="#4CC9F0", fill_opacity=1), 6)
    motor.move_to(P((x0 + x1) / 2 - 2.7, cy))
    mx = motor.get_center()
    motor.add(Circle(0.35, fill_color="#1B263B", fill_opacity=1, stroke_width=0).move_to(mx),
              PR.txt("MOTOR", 22, color=ink()).move_to(mx + DOWN * 1.15))
    # gears
    def gear(at, r, teeth, spin):
        pts = []
        for i in range(teeth * 2):
            a = 2 * PI * i / (teeth * 2) + spin
            rr = r * (1.18 if i % 2 == 0 else 0.88)
            pts.append(P(at[0] + rr * math.cos(a), at[1] + rr * math.sin(a)))
        return _o(Polygon(*pts, fill_color="#FFD166", fill_opacity=1), 4)
    spin = 0.4 * t
    g1 = gear(P((x0 + x1) / 2 - 0.85, cy + 0.15), 0.62, 8, spin)
    g2 = gear(P((x0 + x1) / 2 + 0.35, cy - 0.2), 0.48, 7, -spin * 1.3)
    glab = PR.txt("GEARS", 22, color=ink()).move_to(P((x0 + x1) / 2 - 0.2, cy - 1.15))
    # position sensor (potentiometer)
    pot = _o(Circle(0.42, fill_color="#06D6A0", fill_opacity=1), 5).move_to(P((x0 + x1) / 2 + 1.5, cy + 0.55))
    pot.add(Line(pot.get_center(), pot.get_center() + 0.28 * np.array([math.cos(spin), math.sin(spin), 0]),
                 stroke_width=6, color=ink()))
    plab = PR.txt("POSITION\nSENSOR", 20, color=ink()).move_to(P((x0 + x1) / 2 + 1.5, cy + 1.35))
    # horn
    ang = 20 * math.sin(0.8 * t)
    horn = VGroup(_o(Circle(0.28, fill_color="#EF476F", fill_opacity=1), 5),
                  _o(RoundedRectangle(width=1.5, height=0.28, corner_radius=0.1,
                                      fill_color="#EF476F", fill_opacity=1), 4).move_to(P(0.7, 0)))
    horn.move_to(P((x0 + x1) / 2 + 2.9, cy)).rotate(math.radians(ang))
    hlab = PR.txt("HORN", 22, color=ink()).move_to(P((x0 + x1) / 2 + 2.9, cy - 1.15))
    g.add(house, motor, g1, g2, glab, pot, plab, horn, hlab)
    g.add(caption("A motor, gears, and a sensor that knows its exact angle", box))
    return g


def servo_dial(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """A big 0–180° dial. The horn rotates to the angle in ``ctx['angle']`` (degrees), with 0, 90 and 180 labelled.
    Narrated practice angles (30°, 60°) are highlighted when active; 0/90/180 stay on the scale."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#FFFDF6"))
    ttl = title("EXACT ANGLE", box, size=42)
    # park the title at the top-left so 60°/90° labels stay clear
    ttl.move_to(P(x0 + ttl.width / 2 + 0.45, y1 - 0.55))
    g.add(ttl)
    def _ang():
        if ctx.get("angle") is not None:
            return float(ctx["angle"])
        marks = [(ctx[k], d) for k, d in (("t0", 0), ("t30", 30), ("t60", 60), ("t90", 90), ("t180", 180))
                 if ctx.get(k) is not None]
        marks.sort()
        if not marks:
            return 0.0
        if t <= marks[0][0]:
            return 0.0
        for i in range(len(marks) - 1):
            if t < marks[i + 1][0]:
                u = clamp01((t - marks[i][0]) / max(0.35, marks[i + 1][0] - marks[i][0]))
                return marks[i][1] + (marks[i + 1][1] - marks[i][1]) * ease_in_out(u)
        return marks[-1][1]
    ang = _ang()
    if ctx.get("spoken") is None:
        if ctx.get("t60") is not None and t >= ctx["t60"]:
            ctx = {**ctx, "spoken": 60}
        elif ctx.get("t30") is not None and t >= ctx["t30"]:
            ctx = {**ctx, "spoken": 30}
    # Dial sits lower so the 90° label can live OUTSIDE the ring at the top, clear of the title.
    cx, cy = (x0 + x1) / 2 + 0.35, (y0 + y1) / 2 - 0.35
    r = 2.15
    # 0° = right (east), 90° = TOP, 180° = left — true servo-dial positions
    def pt(d, rr=r):
        a = math.radians(d)
        return P(cx + rr * math.cos(a), cy + rr * math.sin(a))
    dial = Annulus(inner_radius=r - 0.16, outer_radius=r + 0.16, fill_color="#EEF2F7", fill_opacity=1,
                   stroke_width=0).move_to(P(cx, cy))
    ticks = VGroup()
    spoken = ctx.get("spoken")  # 30 or 60: highlighted ticks only; the number lives in the big readout
    for d in range(0, 181, 10):
        long = d in (0, 90, 180)
        mid = d in (30, 60)
        hot = mid and spoken == d
        p0, p1 = pt(d, r - (0.32 if long or mid else 0.14)), pt(d, r + (0.42 if mid else 0.28 if long else 0.16))
        ticks.add(Line(p0, p1, stroke_width=10 if long else 8 if mid else 3,
                       color="#E76F51" if mid else ink()))
        if d in (0, 90, 180):
            lab = PR.txt(f"{d}°", 40, color="#6C4AB6", font="Luckiest Guy", stroke=4)
            lab.move_to(pt(d, r + 0.78))  # all three fixed labels sit outside the ring
            ticks.add(lab)
    # horn
    horn = VGroup(_o(Circle(0.32, fill_color="#EF476F", fill_opacity=1), 6),
                  _o(RoundedRectangle(width=r - 0.15, height=0.32, corner_radius=0.12,
                                      fill_color="#EF476F", fill_opacity=1), 5).shift(RIGHT * ((r - 0.15) / 2)))
    horn.move_to(P(cx, cy)).rotate(math.radians(ang), about_point=P(cx, cy))
    readout = _o(RoundedRectangle(width=2.0, height=0.78, corner_radius=0.16, fill_color="#1E1633", fill_opacity=1), 4)
    rt = PR.txt(f"{ang:.0f}°", 48, color="#FFD166", font="Luckiest Guy", stroke=3)
    readout.move_to(P(cx, cy - 0.7))
    rt.move_to(readout)
    face = _o(Circle(r - 0.18, fill_color="#FFFFFF", fill_opacity=1), 6).move_to(P(cx, cy))
    g.add(dial, face, ticks, horn, readout, rt)
    g.add(caption(ctx.get("subtitle") or "The horn turns exactly as far as the brain tells it", box))
    return g


def servo_head(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """How Bolt uses a servo: a sensor head / turret that turns to an exact angle."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#F4FBFF"), title("HOW BOLT USES A SERVO", box, size=48))
    ang = 25 * math.sin(1.2 * t)   # gentle scan
    # body
    body = _o(RoundedRectangle(width=3.4, height=2.4, corner_radius=0.8, fill_color="#2EC4B6", fill_opacity=1), 8)
    body.move_to(P(0, -0.55))
    screen = _o(RoundedRectangle(width=2.5, height=1.15, corner_radius=0.4, fill_color="#1B263B", fill_opacity=1), 6)
    screen.move_to(P(0, -0.15))
    # turret / sensor head on a servo
    servo = _o(RoundedRectangle(width=0.9, height=0.45, corner_radius=0.08, fill_color="#FFD166", fill_opacity=1), 5)
    servo.move_to(P(0, 0.85))
    sl = PR.txt("SERVO", 22, color=ink(), font="Luckiest Guy", stroke=3).move_to(servo.get_center() + RIGHT * 1.15)
    head = VGroup(
        _o(Circle(0.55, fill_color="#4CC9F0", fill_opacity=1), 6),
        Rectangle(width=0.7, height=0.22, fill_color="#1B263B", fill_opacity=1, stroke_width=0).move_to(P(0.45, 0)),
    )
    head.move_to(P(0, 1.55)).rotate(math.radians(ang), about_point=P(0, 0.85))
    arc = Arc(radius=1.15, start_angle=math.radians(70), angle=math.radians(40), color="#6C4AB6", stroke_width=6)
    arc.move_to(P(0, 1.55) + UP * 0.2)
    art = VGroup(body, screen, servo, sl, head, arc)
    g.add(_fit(art, box, top=1.2, bottom=1.2))
    g.add(caption("A servo turns his sensor head to an exact angle", box))
    return g


# ------------------------------------------------------------------------------------------ echo as illustration + quiz


def sensor_range(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """A 0–3 m range bar: in range vs out of range, timed to the narration."""
    g = VGroup(board(box, "#F4FBFF"), title("SENSOR RANGE", box))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bar_w = min(10.0, x1 - x0 - 2.0)
    bar = _o(RoundedRectangle(width=bar_w, height=0.7, corner_radius=0.2, fill_color="#EEF2F7", fill_opacity=1), 5)
    bar.move_to(P(cx, cy))
    # 0 .. 3 m ticks
    ticks = VGroup()
    for i, lab in enumerate(("0 m", "1 m", "2 m", "3 m")):
        x = cx - bar_w / 2 + bar_w * (i / 3)
        ticks.add(Line(P(x, cy - 0.45), P(x, cy + 0.45), stroke_width=4, color=ink()))
        ticks.add(PR.txt(lab, 28, color=ink(), font="Luckiest Guy", stroke=3).move_to(P(x, cy - 1.0)))
    oor_t = ctx.get("oor")
    out = bool(oor_t is not None and t >= oor_t)
    # in-range fill 0-3m; a pip at ~1.2 m then jumps past 3 m
    u = 0.4 + 0.0
    if out:
        pip_x = cx + bar_w / 2 + 0.7
        tag = "OUT OF RANGE"
        col = "#E76F51"
    else:
        pip_x = cx - bar_w / 2 + bar_w * (1.2 / 3)
        tag = "IN RANGE"
        col = "#06D6A0"
    pulse = 1.0 + 0.18 * math.sin(3.4 * t)
    pip = _o(Circle(0.28 * pulse, fill_color=col, fill_opacity=1), 5).move_to(P(pip_x, cy))
    g.add(bar, ticks, pip, caption(tag, box, color=col))
    return g


def quiz_question(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """Quiz with picture-card answer choices (sensor, wheel, battery) and a short question."""
    x0, y0, x1, y1 = box
    q = ctx.get("question") or "Which part of a robot measures distance?"
    # drop the leading "Here's your question." so the cards have room
    q = q.replace("Here's your question. ", "").replace("Here's your question.", "").strip() or q
    g = VGroup(board(box, "#F8F1FF"), title("QUIZ TIME!", box))
    qx = PR.txt(q, 40, color=ink(), font="Fredoka", weight="BOLD", stroke=3)
    if qx.width > (x1 - x0) - 1.0:
        qx.scale(((x1 - x0) - 1.0) / qx.width)
    qx.move_to(P((x0 + x1) / 2, y1 - 1.25))
    g.add(qx)

    def card(art, label, at):
        back = _o(RoundedRectangle(width=3.5, height=3.3, corner_radius=0.25, fill_color="#FFFFFF", fill_opacity=1), 6)
        back.move_to(at)
        a = art.copy()
        a.scale(min(2.2 / max(a.width, 0.01), 1.7 / max(a.height, 0.01)))
        a.move_to(at + UP * 0.25)
        lab = PR.txt(label, 34, color=ink(), font="Fredoka", weight="BOLD", stroke=2).move_to(at + DOWN * 1.22)
        return VGroup(back, a, lab)

    # sensor picture
    sens = VGroup(_o(RoundedRectangle(width=1.4, height=1.05, corner_radius=0.3, fill_color="#2EC4B6", fill_opacity=1), 5),
                  _o(Circle(0.28, fill_color="#1B263B", fill_opacity=1), 3).move_to(P(-0.28, 0)),
                  _o(Circle(0.28, fill_color="#1B263B", fill_opacity=1), 3).move_to(P(0.28, 0)))
    wheel = VGroup(_o(Circle(0.7, fill_color="#2B2B2B", fill_opacity=1), 6),
                   _o(Circle(0.22, fill_color="#FFD166", fill_opacity=1), 4))
    for i in range(6):
        a = i * PI / 3 + 0.8 * t
        wheel.add(Line(P(0, 0), P(0.58 * math.cos(a), 0.58 * math.sin(a)), stroke_width=5, color="#FFD166"))
    batt = PR.battery(0.7, charging=False).scale(1.6)
    cy = (y0 + y1) / 2 - 0.35
    gap = 3.9
    mid = (x0 + x1) / 2
    for i, (art, lab, at) in enumerate(((sens, "SENSOR", P(mid - gap, cy)),
                                        (wheel, "WHEEL", P(mid, cy)),
                                        (batt, "BATTERY", P(mid + gap, cy)))):
        c = card(art, lab, at)
        c.shift(UP * (0.10 * math.sin(2.2 * t + i * 1.1)))
        g.add(c)
    g.add(caption("Think about it, and say your answer out loud!", box))
    return g


# wrap existing visuals at illustration size (imported lazily to avoid a cycle)
def _adapt(name: str):
    def fn(t, ctx, box=ILLUSTRATION_BOX):
        from robotics101.cartoon import visuals as V
        return V.VISUALS[name][0](t, ctx, box)
    return fn


EXPLAINERS = {
    "example_toaster": (lambda t, c, box=ILLUSTRATION_BOX: one_example(t, {**c, "kind": "toaster"}, box),
                        ("illustration",)),
    "example_vacuum": (lambda t, c, box=ILLUSTRATION_BOX: one_example(t, {**c, "kind": "vacuum",
                        "label": c.get("label") or "Robot vacuum"}, box), ("illustration",)),
    "example_arm": (lambda t, c, box=ILLUSTRATION_BOX: one_example(t, {**c, "kind": "arm",
                     "label": c.get("label") or "Factory arm"}, box), ("illustration",)),
    "example_rover": (lambda t, c, box=ILLUSTRATION_BOX: one_example(t, {**c, "kind": "rover",
                       "label": c.get("label") or "Space rover"}, box), ("illustration",)),
    "part_structure": (lambda t, c, box=ILLUSTRATION_BOX: checkup_part(t, {**c, "part": "structure"}, box),
                       ("illustration",)),
    "part_sensors": (lambda t, c, box=ILLUSTRATION_BOX: checkup_part(t, {**c, "part": "sensors"}, box),
                     ("illustration",)),
    "part_actuators": (lambda t, c, box=ILLUSTRATION_BOX: checkup_part(t, {**c, "part": "actuators"}, box),
                       ("illustration",)),
    "part_power": (lambda t, c, box=ILLUSTRATION_BOX: checkup_part(t, {**c, "part": "power"}, box),
                   ("illustration",)),
    "part_controller": (lambda t, c, box=ILLUSTRATION_BOX: checkup_part(t, {**c, "part": "controller"}, box),
                        ("illustration",)),
    "the_rule": (the_rule, ("illustration",)),
    "rule_test": (rule_test, ("illustration",)),
    "servo_cutaway": (servo_cutaway, ("illustration",)),
    "servo_dial": (servo_dial, ("illustration",)),
    "servo_head": (servo_head, ("illustration",)),
    "quiz_question": (quiz_question, ("illustration",)),
    "sensor_range": (sensor_range, ("illustration",)),
}

__all__ = ["EXPLAINERS", "one_example", "checkup_part", "the_rule", "rule_test", "servo_cutaway", "servo_dial",
           "servo_head", "quiz_question", "sensor_range", "ILLUSTRATION_BOX"]
