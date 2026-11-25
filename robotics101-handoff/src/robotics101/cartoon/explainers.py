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


def title(text: str, box, y_off: float = 0.0, size: int = 64, t: float | None = None) -> VGroup:
    x0, y0, x1, y1 = box
    bob = 0.05 * math.sin(2 * PI * 0.8 * t) if t is not None else 0.0
    lab = PR.txt(text, size, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL", stroke=5)
    if lab.width > (x1 - x0) - 0.6:
        lab.scale(((x1 - x0) - 0.6) / lab.width)
    return lab.move_to(P((x0 + x1) / 2, y1 - 0.48 + y_off + bob))


def live_board(box, t: float, color: str = "#FFFFFF") -> VGroup:
    """Flush teaching board. Motion lives on the art (idle loops, title bob, glows), never a
    board-wide sheen — a traveling bar read as a smudge across the illustration (M05.7)."""
    return VGroup(board(box, color))


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


def _rover_full(t: float, area, ctx: dict | None = None) -> VGroup:
    """M05.8: the space rover visibly DRIVES across a Martian slope: it rolls left to right over the shot, its
    wheels turn with the ground speed, dust puffs kick up behind it and it leaves twin tracks."""
    ctx = ctx or {}
    x0, y0, x1, y1 = area
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    g = VGroup(Rectangle(width=w, height=h, fill_color="#FFE5D9", fill_opacity=1, stroke_width=0).move_to(P(cx, cy)))
    g.add(_o(Circle(0.7, fill_color="#F4A261", fill_opacity=1), 4).move_to(P(x1 - 1.8, y1 - 1.1)))
    for rx, ry, rr in ((x0 + 2.2, y1 - 1.6, 0.12), (x0 + 5.5, y1 - 0.9, 0.08), (cx + 1.4, y1 - 1.4, 0.1)):
        g.add(Circle(rr, fill_color="#FFFFFF", fill_opacity=0.9, stroke_width=0).move_to(P(rx, ry)))

    def gy(x):
        return y0 + 0.42 * h + 0.35 * math.sin((x - x0) * 0.42)
    xs = np.linspace(x0, x1, 64)
    g.add(Polygon(*([P(x, gy(x)) for x in xs] + [P(x1, y0), P(x0, y0)]), fill_color="#E76F51", fill_opacity=1,
                  stroke_color=ink(), stroke_width=4))
    for kx in (0.12, 0.31, 0.58, 0.83):                         # rocks (fixed: the rover moves past them)
        rx = x0 + kx * w
        g.add(_o(Ellipse(width=0.55, height=0.3, fill_color="#9C4A3A", fill_opacity=1), 3).move_to(P(rx, gy(rx) - 0.35)))
    t0, t1 = ctx.get("t0"), ctx.get("t1") or (ctx.get("shot") or {}).get("end")
    if t0 is None or t1 is None or t1 - t0 < 0.5:
        u = (t / 6.0) % 1.0
    else:
        u = clamp01((t - t0) / (t1 - t0))
    start_x, end_x = x0 + 2.6, x1 - 2.6
    rx0 = start_x + (end_x - start_x) * u
    speed = (end_x - start_x) / max(0.5, (t1 - t0) if t0 is not None and t1 is not None else 6.0)
    # tracks: twin dashed ruts from the start to the rover's rear wheel
    for k in range(int(max(0.0, rx0 - 1.6 - start_x + 1.6) / 0.32)):
        tx = start_x - 1.6 + k * 0.32
        if tx > rx0 - 1.6:
            break
        g.add(Line(P(tx, gy(tx) - 0.06), P(tx + 0.18, gy(tx + 0.18) - 0.06), stroke_width=5, color="#7A3328"))
    yb, yf = gy(rx0 - 0.7), gy(rx0 + 0.7)
    tilt = math.atan2(yf - yb, 1.4)
    wr = 0.55
    bump_y = 0.04 * math.sin(t * 22.0)                          # suspension jiggle while rolling
    body = _o(RoundedRectangle(width=3.8, height=1.25, corner_radius=0.28, fill_color="#F4F1DE", fill_opacity=1), 8)
    mast = Line(P(0.85, 0.55), P(0.85, 1.85), stroke_width=12, color=ink())
    cam = _o(Rectangle(width=0.95, height=0.52, fill_color="#2EC4B6", fill_opacity=1), 5).move_to(P(0.85, 2.1))
    panel = _o(Rectangle(width=1.9, height=0.26, fill_color="#118AB2", fill_opacity=1), 4).move_to(P(-0.45, 0.75))
    wheels = VGroup()
    spin = -(rx0 - start_x) / wr                                # rolling without slipping
    for wx in (-1.35, 0.0, 1.35):
        wh = VGroup(_o(Circle(wr, fill_color="#45505E", fill_opacity=1), 6))
        for j in range(3):
            a = spin + j * PI / 3
            wh.add(Line(P(-wr * math.cos(a), -wr * math.sin(a)), P(wr * math.cos(a), wr * math.sin(a)),
                        stroke_width=6, color="#FFFFFF"))
        wheels.add(wh.move_to(P(wx, -0.85)))
    rv = VGroup(body.shift(UP * bump_y), mast.shift(UP * bump_y), cam.shift(UP * bump_y), panel.shift(UP * bump_y),
                wheels).rotate(tilt, about_point=P(0, -0.85))
    rv.move_to(P(rx0, (yb + yf) / 2 + 0.95))
    # dust: puffs spawn behind the rear wheel and drift back / up as they fade
    for k in range(6):
        age = ((t * 3.0) + k / 6) % 1.0
        px = rx0 - 1.9 - age * 1.2
        py = gy(rx0 - 1.9) + 0.1 + age * 0.7
        g.add(Circle(0.16 + 0.32 * age, fill_color="#D9A38B", fill_opacity=0.75 * (1 - age),
                     stroke_width=0).move_to(P(px, py)))
    # speed lines
    for k in range(3):
        ly = (yb + yf) / 2 + 0.6 + k * 0.42
        g.add(Line(P(rx0 - 2.6 - 0.3 * k, ly), P(rx0 - 2.05 - 0.3 * k, ly), stroke_width=5, color=ink(),
                   stroke_opacity=0.5 + 0.3 * math.sin(10 * t + k)))
    g.add(rv)
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


# M05.8 middle-ground scale for the one-example family frames: the example sits in a framed scene ("diorama")
# that spans ~55-70% of the frame (width and height), centred between the title and the caption, with breathing
# room on every side; never edge-to-edge (M05.6 was too zoomed in) and never a small inset (M05.5).
SUBJECT_SHARE = (0.55, 0.70)
FRAME_W, FRAME_H = 14.222, 8.0
SUBJECT_W, SUBJECT_H = 0.64 * FRAME_W, 0.57 * FRAME_H


def subject_box(box=ILLUSTRATION_BOX) -> tuple[float, float, float, float]:
    """World corners of the framed example scene inside a teaching box."""
    x0, y0, x1, y1 = box
    top = y1 - 0.98                                  # below the title
    bottom = y0 + 1.0                                # above the caption
    h = min(SUBJECT_H, top - bottom)
    cy = (top + bottom) / 2
    cx = (x0 + x1) / 2
    return (cx - SUBJECT_W / 2, cy - h / 2, cx + SUBJECT_W / 2, cy + h / 2)


def subject_share(box=ILLUSTRATION_BOX) -> dict:
    sx0, sy0, sx1, sy1 = subject_box(box)
    return {"width": round((sx1 - sx0) / FRAME_W, 3), "height": round((sy1 - sy0) / FRAME_H, 3),
            "marginX": round((sx0 + FRAME_W / 2) / FRAME_W, 3)}


def _in_panel(art: VGroup, panel) -> VGroup:
    """Scale full-bleed art (drawn for the old teaching box) into the diorama panel."""
    px0, py0, px1, py1 = panel
    art.scale(min((px1 - px0) / max(art.width, 0.01), (py1 - py0) / max(art.height, 0.01)))
    return art.move_to(P((px0 + px1) / 2, (py0 + py1) / 2))


def one_example(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """One example, full screen: a framed animated scene at the middle-ground scale and its name. Never a grid
    of several examples."""
    kind = (ctx.get("kind") or ctx.get("example") or "robot").lower()
    label = ctx.get("label") or kind.replace("_", " ").title()
    sub = ctx.get("subtitle") or ""
    g = VGroup(live_board(box, t, "#FFFDF6"))
    panel = subject_box(box)
    px0, py0, px1, py1 = panel
    full = _art_box(box, top=0.0, bottom=0.0, pad=0.0)          # the art's native canvas (old full-bleed box)
    frame = _o(RoundedRectangle(width=px1 - px0, height=py1 - py0, corner_radius=0.25, fill_opacity=0), 8)
    frame.move_to(P((px0 + px1) / 2, (py0 + py1) / 2))
    shadow = RoundedRectangle(width=px1 - px0, height=py1 - py0, corner_radius=0.25, fill_color="#E8E1CF",
                              fill_opacity=1, stroke_width=0).move_to(P((px0 + px1) / 2 + 0.12, (py0 + py1) / 2 - 0.12))
    if kind == "toaster":
        sub = sub or "Not a robot — it doesn't think"
        art = VGroup(Rectangle(width=full[2] - full[0], height=full[3] - full[1], fill_color="#FFF1D6",
                               fill_opacity=1, stroke_width=0).move_to(P((full[0] + full[2]) / 2, (full[1] + full[3]) / 2)))
        art.add(Rectangle(width=full[2] - full[0], height=1.6, fill_color="#C68B59", fill_opacity=1, stroke_width=0)
                .move_to(P((full[0] + full[2]) / 2, full[1] + 0.8)))
        toaster = _toaster_art(t).scale(1.55).move_to(P((full[0] + full[2]) / 2, full[1] + 1.6 + 1.45))
        art.add(toaster)
    elif "vacuum" in kind:
        art = _vacuum_full(t, full)
    elif kind in ("arm", "factory_arm") or "arm" in kind:
        art = _arm_full(t, full)
    elif "rover" in kind:
        art = _rover_full(t, full, ctx)
    elif kind in KINDS:
        art = _fit(vignette(kind, t), box)
    else:
        art = _fit(PR.icon(kind), box)
    g.add(shadow, _in_panel(art, panel), frame)
    g.add(title(label.upper() + "!", box, t=t))
    g.add(caption(sub or label, box))
    g.subject_box = panel
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
    """A wide robot frame that gently assembles, with parts highlighted in turn.

    Motion is *inside* the group (a traveling sheen, growing ribs, cycling rivets) so it still
    reads after ``checkup_part`` fits the art to the teaching box (a uniform scale pulse would
    be undone by ``_fit``).
    """
    body = _o(RoundedRectangle(width=5.6, height=3.1, corner_radius=0.9, fill_color="#2EC4B6", fill_opacity=1), 8)
    ribs = VGroup()
    for i, x in enumerate((-1.5, 0.0, 1.5)):
        grow = 0.55 + 0.45 * abs(math.sin(1.3 * t + i * 0.8))
        ribs.add(Line(P(x, -1.2 * grow), P(x, 1.2 * grow), stroke_width=8, color="#1B7A72"))
    span = 1.4 + 0.8 * abs(math.sin(1.1 * t + 0.4))
    ribs.add(Line(P(-span, 0), P(span, 0), stroke_width=8, color="#1B7A72"))
    u = (0.35 * t) % 1.0
    sheen = Rectangle(width=0.75, height=2.9, fill_color="#FFFFFF", fill_opacity=0.34, stroke_width=0)
    sheen.move_to(P(-2.5 + 5.0 * u, 0)).rotate(0.18)
    riv = VGroup()
    corners = ((-1.85, 0.95), (1.85, 0.95), (1.85, -0.95), (-1.85, -0.95))
    hi = int((t * 1.4) % 4)
    for i, (x, y) in enumerate(corners):
        on = i == hi
        tw = 0.18 + (0.10 if on else 0.0) + 0.03 * math.sin(3.1 * t + i)
        riv.add(Circle(tw, fill_color="#FFD166" if on else ink(), fill_opacity=1, stroke_width=0).move_to(P(x, y)))
    return VGroup(body, sheen, ribs, riv, PR.txt("FRAME", 52, color="#FFFFFF", font="Luckiest Guy", stroke=3))


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
    g = VGroup(live_board(box, t, "#F4FBFF"), title((ctx.get("label") or part).upper(), box, t=t))
    art = _part_power(t, ctx) if part == "power" else _PART_ART.get(part, _part_structure)(t)
    g.add(_fit(art, box, margin=0.2, top=1.05, bottom=1.0))
    g.add(caption(_PART_SUB.get(part, part), box))
    return g


# ------------------------------------------------------------------------------------------ the Rule + rematch

def the_rule(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    x0, y0, x1, y1 = box
    g = VGroup(live_board(box, t, "#F7FFF4"), title("THE RULE", box, t=t))
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
    g = VGroup(live_board(box, t, "#EAF7FF"), title("LET'S TEST THE RULE", box, t=t))
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
    g = VGroup(live_board(box, t, "#F4F7FF"), title("WHAT IS A SERVO?", box, t=t))
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
    """A big 0–180° dial. The horn eases to the spoken angle (30°, then 60°) and keeps a small idle wobble
    at holds so the board never freezes. 0, 90 and 180 stay labelled on the scale."""
    x0, y0, x1, y1 = box
    g = VGroup(live_board(box, t, "#FFFDF6"))
    if ctx.get("title", "EXACT ANGLE"):
        ttl = title(ctx.get("title", "EXACT ANGLE"), box, size=42, t=t)
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
    target = _ang()
    # Subtle idle wobble at holds; keep it small during an ease so the horn still tracks the line.
    marks = [(ctx[k], d) for k, d in (("t0", 0), ("t30", 30), ("t60", 60), ("t90", 90), ("t180", 180))
             if ctx.get(k) is not None]
    marks.sort()
    easing = False
    if ctx.get("angle") is None and len(marks) >= 2:
        for i in range(len(marks) - 1):
            if marks[i][0] < t < marks[i + 1][0]:
                easing = True
                break
    wobble = (2.0 if easing else 8.0) * math.sin(3.7 * t) if ctx.get("wobble", True) else 0.0
    ang = target + wobble
    if ctx.get("spoken") is None:
        if ctx.get("t60") is not None and t >= ctx["t60"]:
            ctx = {**ctx, "spoken": 60}
        elif ctx.get("t30") is not None and t >= ctx["t30"]:
            ctx = {**ctx, "spoken": 30}
    # Dial sits lower so the 90° label can live OUTSIDE the ring at the top, clear of the title.
    cx, cy = (x0 + x1) / 2 + float(ctx.get("dx", 0.35)), (y0 + y1) / 2 - float(ctx.get("dy", 0.35))
    r = float(ctx.get("radius", 2.15))
    # 0° = right (east), 90° = TOP, 180° = left — true servo-dial positions
    def pt(d, rr=r):
        a = math.radians(d)
        return P(cx + rr * math.cos(a), cy + rr * math.sin(a))
    dial = Annulus(inner_radius=r - 0.16, outer_radius=r + 0.16, fill_color="#EEF2F7", fill_opacity=1,
                   stroke_width=0).move_to(P(cx, cy))
    ticks = VGroup()
    spoken = ctx.get("spoken")  # 30 or 60: highlighted ticks; numbers sit outside the ring with 0/90/180
    for d in range(0, 181, 10):
        long = d in (0, 90, 180)
        mid = d in (30, 60)
        hot = mid and spoken == d
        p0, p1 = pt(d, r - (0.32 if long or mid else 0.14)), pt(d, r + (0.42 if mid else 0.28 if long else 0.16))
        ticks.add(Line(p0, p1, stroke_width=10 if long else 8 if mid else 3,
                       color="#E76F51" if mid else ink()))
        if d in (0, 90, 180):
            lab = PR.txt(f"{d}°", 40, color="#6C4AB6", font="Luckiest Guy", stroke=4)
            lab.move_to(pt(d, r + 0.78))  # fixed labels sit outside the ring
            ticks.add(lab)
        elif d in (30, 60):
            # spoken practice angles: outside the ring, along the tick, slightly smaller so 60° stays
            # clear of 90° at the top and 30° stays clear of 0° on the right
            lab = PR.txt(f"{d}°", 32, color="#E76F51", font="Luckiest Guy", stroke=4)
            lab.move_to(pt(d, r + 0.92))
            if hot:
                # pulse the spoken target label (active element only — never a bar across the art)
                lab.scale(1.0 + 0.10 * math.sin(3.7 * t))
            ticks.add(lab)
    # horn
    horn = VGroup(_o(Circle(0.32, fill_color="#EF476F", fill_opacity=1), 6),
                  _o(RoundedRectangle(width=r - 0.15, height=0.32, corner_radius=0.12,
                                      fill_color="#EF476F", fill_opacity=1), 5).shift(RIGHT * ((r - 0.15) / 2)))
    horn.move_to(P(cx, cy)).rotate(math.radians(ang), about_point=P(cx, cy))
    readout = _o(RoundedRectangle(width=2.0, height=0.78, corner_radius=0.16, fill_color="#1E1633", fill_opacity=1), 4)
    rt = PR.txt(f"{target:.0f}°", 48, color="#FFD166", font="Luckiest Guy", stroke=3)
    readout.move_to(P(cx, cy - 0.7))
    rt.move_to(readout)
    face = _o(Circle(r - 0.18, fill_color="#FFFFFF", fill_opacity=1), 6).move_to(P(cx, cy))
    # a bright tick at the live horn angle so the wobble (and the ease) reads clearly
    tip = pt(ang, r + 0.12)
    pulse = 0.5 + 0.5 * math.sin(3.7 * t)
    halo = Circle(0.58 + 0.22 * pulse, fill_color="#FFD166", fill_opacity=0.40 + 0.25 * pulse,
                  stroke_width=0).move_to(tip)
    glow = Circle(0.32 + 0.14 * pulse, fill_color="#EF476F", fill_opacity=0.95, stroke_width=0).move_to(tip)
    g.add(dial, face, ticks, horn, halo, glow, readout, rt)
    g.add(caption(ctx.get("subtitle") or "The horn turns exactly as far as the brain tells it", box))
    return g


def servo_head(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """How Bolt uses a servo: a sensor head / turret that turns to an exact angle."""
    x0, y0, x1, y1 = box
    g = VGroup(live_board(box, t, "#F4FBFF"), title("HOW BOLT USES A SERVO", box, size=48, t=t))
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


def _bolt_with_arm(pose, ang: float, height: float, at) -> VGroup:
    """Bolt's real rig with his right arm on servo angle ``ang`` (0 = straight forward, 90 = up), facing right,
    scaled to ``height`` with his feet at ``at``."""
    from robotics101.cartoon.rigs import build
    g = build("bolt", pose.with_(arm_r=90.0 + ang, facing=1))
    parts = g.parts
    k = height / max(g.height, 0.01)
    g.scale(k)
    g.shift(np.array([at[0], at[1], 0]) - np.array([g.get_center()[0], g.get_bottom()[1], 0]))
    g.parts = parts
    return g


def _angle_fan(center, ang: float, radius: float, color: str, label: bool = True, size: int = 34) -> VGroup:
    """Filled wedge from 0 deg (forward) to ``ang`` at a joint, with a 0 deg reference line and the angle label."""
    from manim import VMobject
    n = max(2, int(abs(ang) / 3) + 2)
    pts = [center] + [center + radius * P(math.cos(math.radians(ang * j / (n - 1))),
                                          math.sin(math.radians(ang * j / (n - 1)))) for j in range(n)] + [center]
    fan = VMobject().set_points_as_corners(pts).set_fill(color, 0.35).set_stroke(color, 4)
    ref = Line(center, center + RIGHT * (radius + 0.25), stroke_width=4, color=ink()).set_stroke(opacity=0.55)
    g = VGroup(fan, ref)
    if label:
        mid = math.radians(max(ang, 8) / 2)
        g.add(PR.txt(f"{ang:.0f}°", size, color="#E76F51", font="Luckiest Guy", stroke=4)
              .move_to(center + (radius + 0.55) * P(math.cos(mid), math.sin(mid))))
    return g


def servo_split(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """M05.8 split screen: LEFT = Bolt raising his arm on the servo track (the angle wedge drawn at his shoulder),
    RIGHT = the servo dial at the very same angle (no idle wobble, so they can never disagree). A yellow '=' badge
    joins the two numbers."""
    from robotics101.cartoon.rigs import Pose
    from robotics101.cartoon.scenes import servo_angle
    x0, y0, x1, y1 = box
    mid = (x0 + x1) / 2
    ang = servo_angle(ctx.get("track") or [], t)
    g = VGroup(live_board(box, t, "#FFFDF6"))
    left = (x0, y0, mid - 0.05, y1)
    right = (mid + 0.05, y0, x1, y1)
    g.add(Rectangle(width=mid - x0, height=y1 - y0, fill_color="#EAF7FF", fill_opacity=1, stroke_width=0)
          .move_to(P((x0 + mid) / 2, (y0 + y1) / 2)))
    g.add(Line(P(mid, y0 + 0.2), P(mid, y1 - 0.2), stroke_width=8, color="#6C4AB6"))
    hl = PR.txt("BOLT'S ARM", 40, color="#6C4AB6", font="Luckiest Guy", stroke=4)
    hl.move_to(P((x0 + mid) / 2, y1 - 0.5 + 0.04 * math.sin(2 * PI * 0.8 * t)))
    g.add(hl)
    perf = ctx.get("perf")
    pose = perf.state(t).pose if perf is not None else Pose(expression="happy")
    h = (y1 - y0) * 0.55
    bolt = _bolt_with_arm(pose.with_(lean=0.0), ang, h, ((x0 + mid) / 2 - 1.0, y0 + 0.95))
    sh = bolt.parts["arm_r"].get_start()
    g.add(_angle_fan(sh, ang, 1.85, "#FFD166", size=40), bolt)
    hand = bolt.parts["arm_r"].get_end()
    clap = ctx.get("clap")
    if clap is not None and clap <= t < clap + 0.9:
        u = (t - clap) / 0.9
        star = PR.sfx_text("HIGH-FIVE!", "#06D6A0", u, hand + P(-0.2, 0.9), size=56)
        burst = VGroup(*[Line(hand + 0.35 * P(math.cos(a), math.sin(a)), hand + (0.6 + 0.4 * u) * P(math.cos(a), math.sin(a)),
                              stroke_width=8, color="#FFD166") for a in np.linspace(0, 2 * PI, 9)[:-1]])
        g.add(burst, star)
    # right half: the dial at the same angle
    hr = PR.txt("SERVO DIAL", 40, color="#6C4AB6", font="Luckiest Guy", stroke=4)
    hr.move_to(P((mid + x1) / 2, y1 - 0.5 + 0.04 * math.sin(2 * PI * 0.8 * t)))
    g.add(servo_dial(t, {"angle": ang, "wobble": False, "title": "", "radius": 1.75, "dx": 0.0, "dy": 0.55,
                         "spoken": 60 if ang >= 45 else 30 if ang >= 15 else None,
                         "subtitle": "Same angle, same moment"}, (right[0], right[1], right[2], right[3] - 0.2)))
    g.add(hr)
    bc = P(mid, (y0 + y1) / 2 + 0.2)
    badge = _o(Circle(0.42, fill_color="#FFD166", fill_opacity=1), 5).move_to(bc)
    g.add(badge, *[Line(bc + P(-0.2, dy), bc + P(0.2, dy), stroke_width=9, color=ink()) for dy in (0.09, -0.09)])
    return g


def servo_cause(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """M05.8 'How Bolt uses a servo' as cause -> effect, left to right: (1) the brain sends '60°', (2) the signal
    travels down the wire, (3) the servo in Bolt's shoulder turns, (4) his arm moves by exactly that angle. The
    step strip at the top lights the current step."""
    from robotics101.cartoon.rigs import Pose
    x0, y0, x1, y1 = box
    goal = float(ctx.get("goal", 60))
    t0 = float(ctx.get("t0", 0.0))
    send = float(ctx.get("send", t0 + 0.4))
    end = float(ctx.get("end", send + 3.0))
    span = max(1.6, end - send)
    a_sig, b_sig = send + 0.25 * span, send + 0.55 * span          # signal travels
    b_turn = send + 0.9 * span                                     # servo + arm reach the goal
    step = 0 if t < send else 1 if t < a_sig else 2 if t < b_sig else 3
    g = VGroup(live_board(box, t, "#F4FBFF"), title("HOW BOLT USES A SERVO", box, size=46, t=t))
    labels = ["BRAIN SAYS " + f"{goal:.0f}°", "SIGNAL", "SERVO TURNS", "ARM MOVES " + f"{goal:.0f}°"]
    sx = np.linspace(x0 + 2.0, x1 - 2.0, 4)
    for k, (lab, cx) in enumerate(zip(labels, sx)):
        on = k + 1 == step or (k == 3 and t >= b_sig)
        done = k + 1 < step
        chip = _o(RoundedRectangle(width=3.0, height=0.62, corner_radius=0.25,
                                   fill_color="#FFD166" if on else "#C8F7E1" if done else "#FFFFFF", fill_opacity=1), 4)
        chip.move_to(P(cx, y1 - 1.25))
        if on:
            chip.scale(1.0 + 0.05 * math.sin(6 * t))
        g.add(chip, PR.txt(f"{k + 1}. {lab}", 22, color=ink(), font="Luckiest Guy", stroke=2).move_to(chip))
        if k < 3:
            g.add(PR.txt("→", 30, color="#6C4AB6").move_to(P((cx + sx[k + 1]) / 2, y1 - 1.25)))
    # brain (controller chip) on the left with its command bubble
    bx, by = x0 + 2.0, (y0 + y1) / 2 - 0.35
    brain = _o(RoundedRectangle(width=2.0, height=1.6, corner_radius=0.2, fill_color="#1E1633", fill_opacity=1), 5)
    brain.move_to(P(bx, by))
    for j in range(5):
        g.add(Line(P(bx - 0.8 + 0.4 * j, by + 0.8), P(bx - 0.8 + 0.4 * j, by + 1.0), stroke_width=5, color="#9AA5B1"))
        g.add(Line(P(bx - 0.8 + 0.4 * j, by - 0.8), P(bx - 0.8 + 0.4 * j, by - 1.0), stroke_width=5, color="#9AA5B1"))
    glow = 0.5 + 0.5 * math.sin(5 * t)
    g.add(brain, PR.txt("BRAIN", 30, color="#06D6A0", font="Luckiest Guy", stroke=2).move_to(brain))
    if t >= send:
        u = ease_out(_u(t, send, 0.4))
        bub = _o(RoundedRectangle(width=1.7, height=0.95, corner_radius=0.3, fill_color="#FFFFFF", fill_opacity=1), 5)
        bub.move_to(P(bx + 2.25, by + 1.05))
        tail = _o(Polygon(P(bx + 1.45, by + 0.85), P(bx + 1.45, by + 1.2), P(bx + 1.0, by + 0.65),
                          fill_color="#FFFFFF", fill_opacity=1), 5)
        num = PR.txt(f"{goal:.0f}°", 44, color="#E76F51", font="Luckiest Guy", stroke=3).move_to(bub)
        bg = VGroup(tail, bub, num).scale(max(0.05, u), about_point=P(bx + 1.0, by + 0.65))
        if step == 1:
            bg.scale(1.0 + 0.06 * math.sin(8 * t), about_point=P(bx + 1.0, by + 0.65))
        g.add(bg)
    # Bolt on the right, servo at his shoulder
    ang = 0.0 if t < b_sig else goal * ease_in_out(clamp01((t - b_sig) / max(0.3, b_turn - b_sig)))
    pose = Pose(expression="happy", blink=1.0 if (t % 3.1) < 0.12 else 0.0, glow=0.5 + 0.5 * glow)
    # Bolt (antenna included) stays below the step strip so the wire can pass over his head under the chips
    bolt = _bolt_with_arm(pose, ang, min((y1 - y0) * 0.6, (y1 - 2.15) - (y0 + 0.95)), (x1 - 4.4, y0 + 0.95))
    shp = bolt.parts["arm_r"].get_start()
    # the wire runs from the brain, over Bolt's head, down to the servo in his shoulder (never across his face)
    top_y = bolt.get_top()[1] + 0.2
    w_pts = [brain.get_right() + RIGHT * 0.05, P(bolt.get_left()[0] - 0.4, by), P(bolt.get_left()[0] - 0.4, top_y),
             P(shp[0] + 0.25, top_y), P(shp[0] + 0.25, shp[1] + 0.3)]
    seg = [float(np.linalg.norm(w_pts[k + 1] - w_pts[k])) for k in range(len(w_pts) - 1)]

    def along(u):
        d = u * sum(seg)
        for k, L in enumerate(seg):
            if d <= L or k == len(seg) - 1:
                return w_pts[k] + (w_pts[k + 1] - w_pts[k]) * clamp01(d / max(L, 1e-6))
            d -= L
    from manim import VMobject
    g.add(VMobject().set_points_as_corners(w_pts).set_stroke("#9AA5B1", 8))
    g.add(_angle_fan(shp, ang, 1.9, "#FFD166", label=t >= b_sig, size=40), bolt)
    servo = _o(RoundedRectangle(width=0.62, height=0.46, corner_radius=0.08, fill_color="#FFD166", fill_opacity=1), 4)
    servo.move_to(shp)
    horn = Line(shp, shp + 0.32 * P(math.cos(math.radians(ang)), math.sin(math.radians(ang))), stroke_width=7,
                color="#EF476F")
    lab = PR.txt("SERVO", 22, color=ink(), font="Luckiest Guy", stroke=2)
    chip = _o(RoundedRectangle(width=lab.width + 0.3, height=0.42, corner_radius=0.12, fill_color="#FFFFFF",
                               fill_opacity=1), 3)
    lab_at = shp + P(1.15, -0.55)
    g.add(servo, horn, chip.move_to(lab_at), lab.move_to(lab_at),
          Line(lab_at + LEFT * (chip.width / 2), shp + P(0.3, -0.15), stroke_width=3, color=ink()))
    if a_sig <= t < b_sig + 0.2:
        u = clamp01((t - a_sig) / max(0.2, b_sig - a_sig))
        pos = along(ease_in_out(u))
        g.add(Circle(0.28 + 0.06 * math.sin(14 * t), fill_color="#FFD166", fill_opacity=1, stroke_width=4,
                     stroke_color=ink()).move_to(pos),
              PR.txt(f"{goal:.0f}°", 24, color=ink(), font="Luckiest Guy", stroke=2).move_to(pos + UP * 0.5))
    elif t >= b_sig + 0.2:      # after the move: a soft pulse keeps flowing so the board never freezes
        u = ((t - b_sig) * 0.5) % 1.0
        g.add(Circle(0.14, fill_color="#FFD166", fill_opacity=0.8, stroke_width=0).move_to(along(u)))
    g.add(caption("The brain says how far. The servo turns exactly that far.", box))
    return g


# ------------------------------------------------------------------------------------------ echo as illustration + quiz


def _nib_icon(t: float, h: float = 1.0) -> VGroup:
    """Nib himself (the real rig, small), propeller spinning, so the range frames show *him*, not a dot."""
    from robotics101.cartoon.rigs import Pose, build
    g = build("nib", Pose(prop=t * 18.0, gaze=(-0.8, 0.0), facing=-1, expression="happy"))
    return g.scale(h / max(g.height, 0.01))


def _range_scene(t: float, ctx: dict, box, out: bool) -> VGroup:
    """M05.8 shared drawing for the two range frames: Bolt's eye-like distance sensor on the left sends waves
    that fade out at the 3 m edge of a green detection zone; Nib hovers at his real distance."""
    x0, y0, x1, y1 = box
    rng = float(ctx.get("range") or 3.0)
    g = VGroup(live_board(box, t, "#F4FBFF"))
    g.add(title("OUT OF RANGE!" if out else "SENSOR RANGE: 3 METERS", box, t=t, size=56))
    cy = (y0 + y1) / 2 + 0.45
    sx = x0 + 1.25                                   # sensor
    bar0, bar1 = sx + 0.9, x1 - 2.6                  # 0 m .. 3 m
    per_m = (bar1 - bar0) / rng
    # detection zone (grows in at the start of the frame, then breathes)
    grow = ease_out(_u(t, ctx.get("t0"), 0.9)) if ctx.get("t0") is not None else 1.0
    zone_w = max(0.05, (bar1 - bar0) * grow)
    zone = Rectangle(width=zone_w, height=2.3, fill_color="#06D6A0", fill_opacity=0.16 + 0.04 * math.sin(2.4 * t),
                     stroke_width=0).move_to(P(bar0 + zone_w / 2, cy))
    g.add(zone)
    edge = Line(P(bar1, cy - 1.3), P(bar1, cy + 1.3), stroke_width=8, color="#E76F51" if out else "#06D6A0")
    g.add(edge)
    # ground ruler with metre ticks
    ry = cy - 1.55
    g.add(Line(P(bar0, ry), P(x1 - 0.6, ry), stroke_width=6, color=ink()))
    for m in range(0, int(rng) + 2):
        x = bar0 + m * per_m
        if x > x1 - 0.5:
            break
        g.add(Line(P(x, ry - 0.18), P(x, ry + 0.18), stroke_width=5, color=ink()))
        g.add(PR.txt(f"{m} m", 30, color=ink(), font="Luckiest Guy", stroke=3).move_to(P(x, ry - 0.42)))
    # sensor "eye"
    eye = VGroup(_o(RoundedRectangle(width=1.3, height=1.0, corner_radius=0.3, fill_color="#2EC4B6", fill_opacity=1), 6),
                 _o(Circle(0.24, fill_color="#1B263B", fill_opacity=1), 3).move_to(P(-0.27, 0)),
                 _o(Circle(0.24, fill_color="#1B263B", fill_opacity=1), 3).move_to(P(0.27, 0)))
    g.add(eye.move_to(P(sx, cy)))
    # waves travel out and fade at the range edge (never past it)
    for k in range(4):
        ph = ((t * 0.9) + k / 4) % 1.0
        wx = bar0 + ph * (bar1 - bar0)
        rad = 0.35 + 1.1 * ph
        op = max(0.0, 1.0 - ph) * 0.9
        g.add(Arc(radius=rad, start_angle=-0.6, angle=1.2, color="#118AB2", stroke_width=7,
                  stroke_opacity=op).move_to(P(wx, cy)))
    # Nib at his distance
    nib_m = float(ctx.get("nibMeters") or (3.6 if out else 1.2))
    if out:
        nib_m = max(nib_m, rng + 0.6)
    nx = bar0 + nib_m * per_m
    nx = min(nx, x1 - 0.8)
    bob = 0.12 * math.sin(2.6 * t)
    nib = _nib_icon(t, 1.25).move_to(P(nx, cy + 0.15 + bob))
    g.add(nib)
    dist = PR.txt(f"{nib_m:g} m", 34, color="#E76F51" if out else "#118AB2", font="Luckiest Guy", stroke=3)
    g.add(dist.move_to(P(nx, cy + 1.25 + bob)))
    if out:
        q = PR.txt("?", 72, color="#E76F51", font="Luckiest Guy", stroke=4)
        g.add(q.move_to(P(sx + 0.95, cy + 1.0)).scale(1.0 + 0.12 * math.sin(4.0 * t)))
        g.add(caption("Farther than 3 m: the sensor can't see him", box, color="#E76F51"))
    else:
        chk = PR.txt("IN RANGE", 30, color="#06D6A0", font="Luckiest Guy", stroke=3)
        g.add(chk.move_to(P(nx, cy - 0.95 + bob)))
        g.add(caption("The sensor measures things up to 3 meters away", box, color=ink()))
    return g


def sensor_range(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """M05.8: "measures things up to 3 m": the green detection zone with Nib inside it (in range)."""
    return _range_scene(t, ctx, box, out=False)


def sensor_out_of_range(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """M05.8: "farther than 3 m, out of range": Nib beyond the zone edge, the waves stop at 3 m."""
    return _range_scene(t, ctx, box, out=True)


def quiz_question(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """Quiz with picture-card answer choices (sensor, wheel, battery) and a short question."""
    x0, y0, x1, y1 = box
    q = ctx.get("question") or "Which part of a robot measures distance?"
    # drop the leading "Here's your question." so the cards have room
    q = q.replace("Here's your question. ", "").replace("Here's your question.", "").strip() or q
    g = VGroup(live_board(box, t, "#F8F1FF"), title("QUIZ TIME!", box, t=t))
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
    "servo_split": (servo_split, ("illustration",)),
    "servo_cause": (servo_cause, ("illustration",)),
    "quiz_question": (quiz_question, ("illustration",)),
    "sensor_range": (sensor_range, ("illustration",)),
    "sensor_out_of_range": (sensor_out_of_range, ("illustration",)),
}

__all__ = ["EXPLAINERS", "SUBJECT_SHARE", "subject_box", "subject_share", "one_example", "checkup_part", "the_rule", "rule_test", "servo_cutaway", "servo_dial",
           "servo_head", "servo_split", "servo_cause", "quiz_question", "sensor_range", "sensor_out_of_range", "ILLUSTRATION_BOX"]
