"""Wide teaching visuals for illustration / solo shots (M05.1).

A visual is ``fn(t, ctx) -> VGroup`` (pure in ``t``, deterministic) drawn inside a ``box`` given in world
coordinates ``(x0, y0, x1, y1)``; ``ctx`` carries times taken from the scene (word / sfx times) so the art syncs
with the dialogue. ``VISUALS[name] = (fn, layouts)``; ``concept_<icon>`` is the generic fallback for any explanatory
line (the scene's concept icon, big and animated).

Layout boxes keep everything above the caption band (``layout.CONTENT_FLOOR_Y``).
"""

from __future__ import annotations

import math

import numpy as np
from manim import PI, Arc, Circle, Line, Polygon, Rectangle, RoundedRectangle, Star, VGroup

from robotics101.cartoon import props as PR
from robotics101.cartoon.layout import CONTENT_FLOOR_Y, FRAME_H, FRAME_W, FRAME_X, FRAME_Y
from robotics101.cartoon.motion import bump, clamp01, ease_out
from robotics101.cartoon.sets import ink
from robotics101.cartoon.vignettes import KINDS, vignette

P = PR.P
ILLUSTRATION_BOX = (-6.65, CONTENT_FLOOR_Y + 0.1, 6.65, 3.85)       # full-bleed board (above the caption band)
SOLO_BOX = (-2.0, CONTENT_FLOOR_Y + 0.15, 6.8, 3.55)                # wide visual right of the solo character
SOLO_X = -4.75                                                      # solo character stands left, facing the visual
BACKDROPS = {"illustration": "#FFF1D0", "solo": "#E9F7FF"}


def _o(m, w=5):
    return m.set_stroke(ink(), w)


def _u(t: float, a: float | None, d: float = 0.45) -> float:
    return 0.0 if a is None else clamp01((t - a) / d)


def backdrop(layout: str, t: float) -> VGroup:
    """Full-frame, softly animated backdrop for a shot (covers the stage completely)."""
    col = BACKDROPS.get(layout, "#FFF1D0")
    bg = Rectangle(width=FRAME_W + 0.2, height=FRAME_H + 0.2, fill_color=col, fill_opacity=1, stroke_width=0)
    dots = VGroup(*[Circle(0.09, fill_color="#FFFFFF", fill_opacity=0.7, stroke_width=0)
                    .move_to(P(-7.4 + 1.1 * i + 0.25 * math.sin(0.6 * t + j), -4.3 + 1.1 * j + (0.18 * t) % 1.1))
                    for i in range(14) for j in range(9) if (i + j) % 2 == 0])
    dots.decor = True                                  # decoration: may run under the caption band
    return VGroup(bg, dots)


def board(box, color: str = "#FFFFFF") -> RoundedRectangle:
    x0, y0, x1, y1 = box
    return _o(RoundedRectangle(width=x1 - x0, height=y1 - y0, corner_radius=0.35, fill_color=color,
                               fill_opacity=1), 7).move_to(P((x0 + x1) / 2, (y0 + y1) / 2))


# ------------------------------------------------------------------------------------------ robot families

def robot_families(t: float, ctx: dict, box=ILLUSTRATION_BOX) -> VGroup:
    """Full-screen 'robot family' illustration: one big animated vignette panel per example, each popping in as it
    is named (``ctx['reveal']``), with a bouncing title."""
    x0, y0, x1, y1 = box
    examples = ctx.get("examples") or ["vacuum", "arm", "rover"]
    reveal = ctx.get("reveal") or [None] * len(examples)
    g = VGroup(board(box, "#FFFDF6"))
    title = PR.txt("MEET THE ROBOT FAMILY!", 56, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL", stroke=4)
    title.move_to(P((x0 + x1) / 2, y1 - 0.5 + 0.06 * math.sin(2 * PI * 0.8 * t)))
    g.add(title)
    n = len(examples)
    gap = 0.3
    pw = (x1 - x0 - 0.6 - gap * (n - 1)) / n
    ph = (y1 - 1.15) - (y0 + 0.75)
    colors = ("#E0FBFC", "#FFE5EC", "#E9FFE0", "#FFF3B0")
    for i, (name, r) in enumerate(zip(examples, reveal)):
        cx = x0 + 0.3 + pw / 2 + i * (pw + gap)
        cy = y0 + 0.75 + ph / 2
        k = _u(t, r)
        frame = _o(RoundedRectangle(width=pw, height=ph, corner_radius=0.25, fill_color=colors[i % len(colors)],
                                    fill_opacity=1), 6).move_to(P(cx, cy))
        if k <= 0:
            q = PR.txt("?", 120, color="#C9B8F0", font="Luckiest Guy", weight="NORMAL")
            q.move_to(P(cx, cy + 0.08 * math.sin(3 * t + i)))
            g.add(frame.set_fill(opacity=0.55), q)
            continue
        art = vignette(name, t) if name in KINDS else PR.icon(name)
        art.scale(min((pw - 0.3) / art.width, (ph - 0.3) / art.height)).move_to(P(cx, cy))
        label = PR.txt(name.upper(), 40, color=ink()).move_to(P(cx, y0 + 0.4))
        tile = VGroup(frame, art, label)
        g.add(tile.scale(PR.pop(k), about_point=P(cx, cy)))
    return g


def family_tile_boxes(ctx: dict, box=ILLUSTRATION_BOX) -> list[tuple[float, float, float, float]]:
    """World boxes of the animated vignettes (for the static-hold QA)."""
    x0, y0, x1, y1 = box
    n = len(ctx.get("examples") or ["vacuum", "arm", "rover"])
    gap = 0.3
    pw = (x1 - x0 - 0.6 - gap * (n - 1)) / n
    ph = (y1 - 1.15) - (y0 + 0.75)
    out = []
    for i in range(n):
        cx = x0 + 0.3 + pw / 2 + i * (pw + gap)
        cy = y0 + 0.75 + ph / 2
        out.append((cx, cy, pw - 0.3, ph - 0.3))
    return out


# ------------------------------------------------------------------------------------------ echo diagram

def _bat(at: np.ndarray, t: float, k: float) -> VGroup:
    flap = 0.25 * math.sin(2 * PI * 3 * t)
    wing_l = Polygon(P(0, 0), P(-0.5, 0.25 + flap), P(-0.95, 0.1 + flap), P(-0.7, -0.05), P(-0.45, -0.15),
                     fill_color="#4A3B6B", fill_opacity=1)
    wing_r = wing_l.copy().stretch(-1, 0, about_point=P(0, 0))
    body = VGroup(_o(wing_l, 3), _o(wing_r, 3),
                  _o(Circle(0.2, fill_color="#4A3B6B", fill_opacity=1), 3),
                  Circle(0.045, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0).move_to(P(0.08, 0.05)),
                  Circle(0.045, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0).move_to(P(-0.08, 0.05)))
    return body.scale(1.3 * PR.pop(k)).move_to(at + P(0, 0.12 * math.sin(2 * PI * 0.9 * t)))


def echo_diagram(t: float, ctx: dict, box=SOLO_BOX) -> VGroup:
    """Sound-wave diagram: a sensor sends a ping, it bounces off a wall and the echo comes back. The first ping is
    synced to the scene's ``ping`` sfx, later pings loop; a 'faster echo = closer' strip and a bat appear on cue."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#FFFFFF"))
    head = PR.txt("HOW A DISTANCE SENSOR WORKS", 40, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL")
    g.add(head.move_to(P((x0 + x1) / 2, y1 - 0.42)))
    cy = (y0 + y1) / 2 + 0.25
    sx, wx = x0 + 1.15, x1 - 1.1
    sensor = VGroup(_o(RoundedRectangle(width=1.1, height=0.75, corner_radius=0.12, fill_color="#2EC4B6",
                                        fill_opacity=1), 5),
                    *[_o(Circle(0.22, fill_color="#DDE3EA", fill_opacity=1), 4).move_to(P(dx, 0)) for dx in (-0.25, 0.25)])
    g.add(sensor.move_to(P(sx, cy)))
    wall = VGroup(_o(Rectangle(width=0.7, height=2.6, fill_color="#E76F51", fill_opacity=1), 5),
                  *[Line(P(-0.35, y), P(0.35, y), stroke_width=3, color="#B4513A") for y in (-0.65, 0.0, 0.65)])
    g.add(wall.move_to(P(wx, cy)))
    reach = wx - 0.35 - (sx + 0.55)
    ping0 = ctx.get("ping")
    period = 2.4
    tt = t - (ping0 if ping0 is not None else 0.0)
    if tt >= 0:
        u = (tt % period) / period
        if u < 0.42:
            g.add(PR.ping_waves(P(sx + 0.55, cy), u / 0.42, reach / 1.6).scale(1.6, about_point=P(sx + 0.55, cy)))
        elif u < 0.84:
            g.add(PR.ping_waves(P(sx + 0.55, cy), (u - 0.42) / 0.42, reach / 1.6, back=True)
                  .scale(1.6, about_point=P(sx + 0.55, cy)))
        if u < 0.2:
            g.add(PR.txt("PING!", 44, color="#4CC9F0", font="Luckiest Guy", weight="NORMAL", stroke=3)
                  .move_to(P(sx + 0.1, cy + 1.05)).scale(1 + 0.15 * bump(u / 0.2)))
        elif 0.7 < u < 0.95:
            g.add(PR.txt("echo!", 40, color="#F72585", font="Luckiest Guy", weight="NORMAL", stroke=3)
                  .move_to(P(sx + 1.6, cy + 1.05)))
    # distance arrow + 'faster echo = closer'
    ay = y0 + 0.95
    arr = VGroup(Line(P(sx + 0.6, ay), P(wx - 0.4, ay), stroke_width=6, color=ink()),
                 Polygon(P(wx - 0.4, ay + 0.15), P(wx - 0.4, ay - 0.15), P(wx - 0.15, ay), fill_color=ink(),
                         fill_opacity=1, stroke_width=0),
                 Polygon(P(sx + 0.6, ay + 0.15), P(sx + 0.6, ay - 0.15), P(sx + 0.35, ay), fill_color=ink(),
                         fill_opacity=1, stroke_width=0))
    g.add(arr, PR.txt("distance", 30, color=ink()).move_to(P((sx + wx) / 2, ay + 0.3)))
    k = _u(t, ctx.get("faster"))
    if k > 0:
        strip = VGroup(_o(RoundedRectangle(width=6.2, height=0.62, corner_radius=0.3, fill_color="#FFD166",
                                           fill_opacity=1), 4),
                       PR.txt("faster echo = closer!", 34, color=ink()))
        strip[1].move_to(strip[0])
        g.add(strip.move_to(P((x0 + x1) / 2, y0 + 0.38)).scale(PR.pop(k)))
    kb = _u(t, ctx.get("bats"))
    if kb > 0:
        g.add(_bat(P(x1 - 1.9, y1 - 1.25), t, kb))
    return g


# ------------------------------------------------------------------------------------------ sense think act

def sense_think_act(t: float, ctx: dict, box=SOLO_BOX) -> VGroup:
    """SENSE -> THINK -> ACT loop with icons; each step lights up as it is said (``ctx['sense'|'think'|'act']``)."""
    x0, y0, x1, y1 = box
    g = VGroup(board(box, "#FFFFFF"))
    g.add(PR.txt("HOW YOUR ROBOT BRAIN WORKS", 40, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL")
          .move_to(P((x0 + x1) / 2, y1 - 0.42)))
    thr = ctx.get("threshold")
    steps = [("SENSE", "#4CC9F0", "measure\ndistance"),
             ("THINK", "#FFD166", f"closer than\n{thr:g} m?" if thr else "check\nthe rule"),
             ("ACT", "#06D6A0", "stop\nand turn")]
    times = [ctx.get(n.lower()) for n, _, _ in steps]
    active = max((i for i, a in enumerate(times) if a is not None and t >= a), default=-1)
    w = (x1 - x0 - 1.0) / 3
    cy = (y0 + y1) / 2 + 0.1
    for i, (name, col, sub) in enumerate(steps):
        cx = x0 + 0.5 + w * (i + 0.5)
        on = i <= active
        pulse = 1 + (0.08 * abs(math.sin(PI * 1.6 * t)) if i == active else 0.0)
        c = _o(Circle(0.95, fill_color=col if on else "#F1F1F1", fill_opacity=1), 6).move_to(P(cx, cy + 0.3))
        lab = PR.txt(name, 36, color=ink() if on else "#9A8C98").move_to(c)
        cap = VGroup(*[PR.txt(line, 26, color=ink() if on else "#9A8C98") for line in sub.split("\n")]) \
            .arrange(np.array([0.0, -1.0, 0.0]), buff=0.08).move_to(P(cx, cy - 1.25))
        g.add(VGroup(c, lab).scale(pulse, about_point=P(cx, cy + 0.3)), cap)
        if i < 2:
            ax = cx + w / 2
            g.add(Polygon(P(ax - 0.28, cy + 0.5), P(ax - 0.28, cy + 0.1), P(ax + 0.12, cy + 0.3), fill_color=ink(),
                          fill_opacity=1, stroke_width=0))
    return g


# ------------------------------------------------------------------------------------------ generic concept

def concept_visual(icon: str):
    def fn(t: float, ctx: dict, box=SOLO_BOX) -> VGroup:
        x0, y0, x1, y1 = box
        g = VGroup(board(box, "#FFFFFF"))
        if ctx.get("title"):
            g.add(PR.txt(ctx["title"].upper(), 40, color="#6C4AB6", font="Luckiest Guy", weight="NORMAL")
                  .move_to(P((x0 + x1) / 2, y1 - 0.42)))
        art = PR.concept_icon(icon, t)
        art.scale(min((x1 - x0 - 1.5) / max(art.width, 0.01), (y1 - y0 - 1.6) / max(art.height, 0.01)))
        g.add(art.move_to(P((x0 + x1) / 2, (y0 + y1) / 2 - 0.2)))
        return g
    return fn


VISUALS = {"robot_families": (robot_families, ("illustration", "solo")),
           "echo_diagram": (echo_diagram, ("solo", "illustration")),
           "sense_think_act": (sense_think_act, ("solo", "illustration"))}


def visual(name: str):
    if name in VISUALS:
        return VISUALS[name][0]
    if name.startswith("concept_"):
        return concept_visual(name[len("concept_"):])
    raise ValueError(f"unknown shot visual {name!r}; known: {sorted(VISUALS)} or concept_<icon>")


def default_box(layout: str) -> tuple[float, float, float, float]:
    return ILLUSTRATION_BOX if layout == "illustration" else SOLO_BOX


__all__ = ["ILLUSTRATION_BOX", "SOLO_BOX", "SOLO_X", "VISUALS", "backdrop", "default_box", "visual",
           "family_tile_boxes", "FRAME_X", "FRAME_Y", "ease_out"]
