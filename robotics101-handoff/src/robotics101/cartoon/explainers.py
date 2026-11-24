"""Full-screen teaching visuals (M05.6): one example or idea per illustration frame.

Each visual is ``fn(t, ctx, box) -> VGroup``, drawn inside ``box`` (world corners) above the caption band.
They are registered on ``visuals.VISUALS`` and used as illustration-only shots (no full-size characters).
"""

from __future__ import annotations

import math

import numpy as np
from manim import (DOWN, LEFT, PI, RIGHT, UP, Annulus, Arc, Circle, Line, Polygon, Rectangle, RoundedRectangle,
                   Square, Star, VGroup)

from robotics101.cartoon import props as PR
from robotics101.cartoon.layout import CONTENT_FLOOR_Y
from robotics101.cartoon.motion import bump, clamp01, ease_in_out, ease_out
from robotics101.cartoon.sets import ink
from robotics101.cartoon.vignettes import KINDS, vignette

P = PR.P
ILLUSTRATION_BOX = (-6.65, CONTENT_FLOOR_Y + 0.1, 6.65, 3.85)


def _o(m, w=5):
    return m.set_stroke(ink(), w)


def _u(t: float, a: float | None, d: float = 0.45) -> float:
    return 0.0 if a is None else clamp01((t - a) / d)


def board(box, color: str = "#FFFFFF") -> RoundedRectangle:
    x0, y0, x1, y1 = box
    return _o(RoundedRectangle(width=x1 - x0, height=y1 - y0, corner_radius=0.35, fill_color=color,
                               fill_opacity=1), 7).move_to(P((x0 + x1) / 2, (y0 + y1) / 2))


def title(text: str, box, y_off: float = 0.0, size: int = 52) -> VGroup:
    x0, y0, x1, y1 = box
    t = PR.txt(text, size, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL", stroke=4)
    if t.width > (x1 - x0) - 0.8:
        t.scale(((x1 - x0) - 0.8) / t.width)
    return t.move_to(P((x0 + x1) / 2, y1 - 0.55 + y_off))


def caption(text: str, box, size: int = 36, color: str = ink()) -> VGroup:
    x0, y0, x1, y1 = box
    t = PR.txt(text, size, color=color, font="Fredoka", weight="BOLD", stroke=3)
    if t.width > (x1 - x0) - 1.0:
        t.scale(((x1 - x0) - 1.0) / t.width)
    return t.move_to(P((x0 + x1) / 2, y0 + 0.55))


def _fit(art: VGroup, box, margin: float = 0.7, top: float = 1.15, bottom: float = 1.15) -> VGroup:
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


def one_example(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """One example, full screen: a large animated illustration and its name. Never a grid of several examples."""
    kind = (ctx.get("kind") or ctx.get("example") or "robot").lower()
    label = ctx.get("label") or kind.replace("_", " ").title()
    sub = ctx.get("subtitle") or ""
    g = VGroup(board(box, "#FFFDF6"), title(label.upper() + "!", box))
    if kind == "toaster":
        art = _toaster_art(t)
        sub = sub or "Not a robot — it doesn't think"
    elif kind in KINDS:
        art = vignette(kind, t)
    else:
        art = PR.icon(kind)
    g.add(_fit(art, box))
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
    body = _o(RoundedRectangle(width=3.2, height=2.6, corner_radius=0.8, fill_color="#2EC4B6", fill_opacity=1), 8)
    riv = VGroup(*[Circle(0.1, fill_color=ink(), fill_opacity=1, stroke_width=0).move_to(P(x, y))
                   for x, y in ((-1.0, 0.7), (1.0, 0.7), (-1.0, -0.7), (1.0, -0.7))])
    return VGroup(body, riv, PR.txt("FRAME", 40, color="#FFFFFF", font="Luckiest Guy", stroke=3))


def _part_sensors(t: float) -> VGroup:
    eye = _o(Circle(0.85, fill_color="#1B263B", fill_opacity=1), 7)
    pupil = Circle(0.35, fill_color="#7CFFCB", fill_opacity=1, stroke_width=0).move_to(P(0.12 * math.sin(t), 0.05))
    waves = VGroup(*[Arc(radius=1.3 + 0.35 * i, start_angle=-0.4, angle=0.8, color="#4CC9F0",
                         stroke_width=6).move_to(P(1.1, 0)) for i in range(3)])
    waves.set_opacity(0.4 + 0.4 * abs(math.sin(2 * t)))
    return VGroup(waves, eye, pupil)


def _part_actuators(t: float) -> VGroup:
    a = 20 + 50 * abs(math.sin(t))
    wheel = _o(Circle(0.7, fill_color="#333333", fill_opacity=1), 6).move_to(P(-1.6, -0.3))
    Circle(0.15, fill_color="#FFD166", fill_opacity=1, stroke_width=0).move_to(wheel)
    arm = Line(P(0.4, 0.2), P(0.4 + 1.6 * math.cos(math.radians(90 - a)), 0.2 + 1.6 * math.sin(math.radians(90 - a))),
               stroke_width=18, color=ink())
    hand = _o(Circle(0.28, fill_color="#FFD166", fill_opacity=1), 4).move_to(arm.get_end())
    return VGroup(wheel, Circle(0.15, fill_color="#FFD166", fill_opacity=1, stroke_width=0).move_to(P(-1.6, -0.3)),
                  arm, hand)


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
    chip = _o(RoundedRectangle(width=2.6, height=2.0, corner_radius=0.2, fill_color="#22223B", fill_opacity=1), 7)
    pins = VGroup(*[Rectangle(width=0.12, height=0.35, fill_color="#C0C0C8", fill_opacity=1, stroke_width=0)
                    .move_to(P(x, y)) for x in np.linspace(-1.0, 1.0, 6) for y in (1.15, -1.15)])
    glow = Circle(0.55 + 0.08 * math.sin(3 * t), fill_color="#7CFFCB", fill_opacity=0.25, stroke_width=0)
    brain = PR.txt("CPU", 64, color="#7CFFCB", font="Luckiest Guy", stroke=3)
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
    g.add(_fit(art, box, top=1.2, bottom=1.2))
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
    robot = _o(RoundedRectangle(width=1.4, height=1.2, corner_radius=0.4, fill_color="#2EC4B6", fill_opacity=1), 6)
    robot.move_to(P(x0 + 2.0, gy + 0.7))
    arr = VGroup(Line(P(x0 + 2.9, gy + 1.3), P(mark_x - 0.35, gy + 1.3), stroke_width=8, color="#06D6A0"),
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
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 - 0.15
    r = 2.35
    # 0° = right (east), 90° = up, 180° = left, matching a servo horn
    def pt(d, rr=r):
        a = math.radians(d)
        return P(cx + rr * math.cos(a), cy + rr * math.sin(a))
    arc = Arc(radius=r, start_angle=0, angle=PI, color=ink(), stroke_width=10).move_to(P(cx, cy + 0.0))
    # reposition: manim Arc is centered on its arc midpoint; draw with move of circle center
    dial = Annulus(inner_radius=r - 0.18, outer_radius=r + 0.18, fill_color="#EEF2F7", fill_opacity=1,
                   stroke_width=0).move_to(P(cx, cy))
    # only the top half looks like a 180° gauge: cover the bottom with the board colour via a clip of ticks 0..180
    ticks = VGroup()
    spoken = ctx.get("spoken")  # 30 or 60 when the line names it (highlighted)
    for d in range(0, 181, 10):
        long = d in (0, 90, 180)
        mid = d in (30, 60)
        p0, p1 = pt(d, r - (0.28 if long or mid else 0.14)), pt(d, r + 0.28)
        ticks.add(Line(p0, p1, stroke_width=7 if long else 5 if mid else 3,
                       color="#E76F51" if mid and spoken == d else ink()))
        if d in (0, 30, 60, 90, 180):
            hot = mid and spoken == d
            lab = PR.txt(f"{d}°", 34 if long or hot else 28,
                         color="#E76F51" if mid else "#6C4AB6", font="Luckiest Guy", stroke=3)
            # 90° sits inside the dial so it never collides with the title
            lab.move_to(pt(d, r - 0.58 if d == 90 else r + 0.62))
            ticks.add(lab)
    # horn
    horn = VGroup(_o(Circle(0.32, fill_color="#EF476F", fill_opacity=1), 6),
                  _o(RoundedRectangle(width=r - 0.15, height=0.32, corner_radius=0.12,
                                      fill_color="#EF476F", fill_opacity=1), 5).shift(RIGHT * ((r - 0.15) / 2)))
    horn.move_to(P(cx, cy)).rotate(math.radians(ang), about_point=P(cx, cy))
    # readout lives inside the lower half of the dial face, clear of the caption
    readout = _o(RoundedRectangle(width=1.9, height=0.7, corner_radius=0.16, fill_color="#1E1633", fill_opacity=1), 4)
    rt = PR.txt(f"{ang:.0f}°", 44, color="#FFD166", font="Luckiest Guy", stroke=3)
    readout.move_to(P(cx, cy - 0.85))
    rt.move_to(readout)
    # hide the unused bottom of the annulus with a white half? keep full circle as a clean dial face
    face = _o(Circle(r - 0.2, fill_color="#FFFFFF", fill_opacity=1), 6).move_to(P(cx, cy))
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
    pip = _o(Circle(0.28, fill_color=col, fill_opacity=1), 5).move_to(P(pip_x, cy))
    g.add(bar, ticks, pip, caption(tag, box, color=col))
    return g


def quiz_question(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    x0, y0, x1, y1 = box
    q = ctx.get("question") or "Which part of a robot measures distance?"
    g = VGroup(board(box, "#F8F1FF"), title("QUIZ TIME!", box))
    card = _o(RoundedRectangle(width=min(11.0, x1 - x0 - 1.2), height=2.6, corner_radius=0.4,
                               fill_color="#FFFFFF", fill_opacity=1), 8)
    card.move_to(P((x0 + x1) / 2, (y0 + y1) / 2 + 0.1))
    tx = PR.txt(q, 42, color=ink(), font="Fredoka", weight="BOLD", stroke=3)
    if tx.width > card.width - 0.8:
        tx.scale((card.width - 0.8) / tx.width)
    g.add(card, tx.move_to(card))
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
