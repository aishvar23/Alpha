"""Props, overlays and lettering (M02.5). Every function is pure: (parameters, progress 0..1) -> VGroup.

Text objects are expensive to lay out (Pango), so ``txt`` caches each distinct (string, font, size, colour) and
hands out copies. Progress arguments let the scene engine animate a prop from any frame time independently.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from manim import (DOWN, LEFT, PI, RIGHT, UP, Arc, Circle, CubicBezier, Dot, Ellipse, Line, Polygon, Rectangle,
                   RoundedRectangle, Square, Star, Text, Triangle, VGroup, VMobject)

from robotics101.cartoon.motion import bump, clamp01, ease_out, ease_out_back
from robotics101.cartoon.sets import FLOOR_Y, GROUND, METER, ink

BOX_W, BOX_H, TOP_W, TOP_H = 1.9, 1.25, 1.2, 0.8
PILE_H = BOX_H + TOP_H
ALERT, OK_GREEN, CHALK = "#EF476F", "#06D6A0", "#F8F9FA"


def _o(m, w=6):
    return m.set_stroke(ink(), w)


def P(x: float, y: float) -> np.ndarray:
    return np.array([x, y, 0.0])


@lru_cache(maxsize=1024)
def _txt(s: str, font: str, size: int, color: str, weight: str, stroke: float):
    t = Text(s, font=font, font_size=size, color=color, weight=weight)
    if stroke:
        t.set_stroke(ink(), stroke, background=True)
    return t


def txt(s: str, size: int = 32, color: str | None = None, font: str = "Fredoka", weight: str = "BOLD",
        stroke: float = 0.0) -> Text:
    return _txt(s, font, size, color or ink(), weight, stroke).copy()


def wrap(s: str, size: int, max_w: float, color: str | None = None) -> VGroup:
    """Greedy word wrap into centred lines no wider than ``max_w`` (when a single word allows)."""
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and txt(trial, size, color).width > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return VGroup(*[txt(line, size, color) for line in lines]).arrange(DOWN, buff=0.12)


def pop(u: float) -> float:
    """Scale curve for things that pop in: 0 -> overshoot -> 1."""
    return 0.001 + max(0.0, ease_out_back(clamp01(u)))


# ------------------------------------------------------------------------------------------ boxes / toaster

def box_pile(x: float) -> VGroup:
    base = _o(RoundedRectangle(width=BOX_W, height=BOX_H, corner_radius=0.08, fill_color="#E76F51", fill_opacity=1))
    base.move_to(P(x, GROUND + BOX_H / 2))
    tape = Rectangle(width=0.3, height=BOX_H, fill_color="#F4A261", fill_opacity=1, stroke_width=0).move_to(base)
    lbl = txt("BOXES", 26, font="Luckiest Guy", weight="NORMAL").move_to(base.get_center() + DOWN * 0.15)
    top = _o(RoundedRectangle(width=TOP_W, height=TOP_H, corner_radius=0.06, fill_color="#F4A261", fill_opacity=1))
    top.move_to(P(x - 0.15, GROUND + BOX_H + TOP_H / 2))
    arrow = txt("THIS SIDE UP ↑", 12).move_to(top)
    return VGroup(base, tape, lbl, top, arrow)


def toaster(x: float, pop_u: float = 0.0) -> VGroup:
    table = VGroup(_o(Rectangle(width=1.8, height=0.14, fill_color="#8D5524", fill_opacity=1), 4)
                   .move_to(P(x, GROUND + 1.25)),
                   *[Line(P(x + dx, GROUND + 1.2), P(x + dx, GROUND), stroke_width=8, color=ink())
                     for dx in (-0.7, 0.7)])
    h = 0.2 + 0.9 * bump(clamp01(pop_u)) if 0 < pop_u < 1 else (0.2 if pop_u <= 0 else 0.25)
    toast = _o(RoundedRectangle(width=0.55, height=0.6, corner_radius=0.12, fill_color="#E9C46A", fill_opacity=1), 4)
    toast.move_to(P(x, GROUND + 1.32 + 0.55 + h))
    if pop_u >= 1:
        toast.set_fill("#6F4518")                       # "very crispy toast"
    body = _o(RoundedRectangle(width=1.2, height=0.85, corner_radius=0.25, fill_color="#C0C0C8", fill_opacity=1))
    body.move_to(P(x, GROUND + 1.32 + 0.43))
    slot = Rectangle(width=0.7, height=0.06, fill_color=ink(), fill_opacity=1, stroke_width=0) \
        .move_to(body.get_top() + DOWN * 0.08)
    lever = _o(Rectangle(width=0.1, height=0.3, fill_color="#FF9F1C", fill_opacity=1), 3) \
        .move_to(body.get_right() + RIGHT * 0.05 + DOWN * (0.05 if pop_u <= 0 else -0.15))
    return VGroup(table, toast, body, slot, lever)


# ------------------------------------------------------------------------------------------ icons + album

def icon(kind: str) -> VGroup:
    k = kind.lower()
    if "vacuum" in k:
        disc = _o(Circle(0.55, fill_color="#8D99AE", fill_opacity=1), 5)
        return VGroup(disc, _o(Circle(0.22, fill_color="#2EC4B6", fill_opacity=1), 4),
                      Dot(P(0.3, 0.25), 0.07, color=OK_GREEN), *[Line(P(-0.2, -0.55), P(-0.45 + 0.25 * i, -0.75),
                                                                       stroke_width=3, color=ink()) for i in range(3)])
    if "arm" in k:
        base = _o(Rectangle(width=0.9, height=0.25, fill_color="#45505E", fill_opacity=1), 4).move_to(P(0, -0.6))
        l1 = Line(P(-0.2, -0.45), P(0.15, 0.25), stroke_width=16, color="#FF9F1C")
        l2 = Line(P(0.15, 0.25), P(0.6, 0.05), stroke_width=12, color="#FF9F1C")
        joints = VGroup(*[_o(Circle(0.09, fill_color="#FFE66D", fill_opacity=1), 3).move_to(p)
                          for p in (P(-0.2, -0.45), P(0.15, 0.25))])
        grip = VGroup(Line(P(0.6, 0.05), P(0.75, 0.18), stroke_width=6, color=ink()),
                      Line(P(0.6, 0.05), P(0.75, -0.08), stroke_width=6, color=ink()))
        return VGroup(base, l1, l2, joints, grip)
    if "rover" in k:
        body = _o(RoundedRectangle(width=1.0, height=0.4, corner_radius=0.1, fill_color="#F4F1DE", fill_opacity=1), 4)
        wheels = VGroup(*[_o(Circle(0.14, fill_color="#45505E", fill_opacity=1), 3).move_to(P(x, -0.32))
                          for x in (-0.38, 0, 0.38)])
        mast = Line(P(0.25, 0.2), P(0.25, 0.55), stroke_width=5, color=ink())
        cam = _o(Rectangle(width=0.25, height=0.14, fill_color="#2EC4B6", fill_opacity=1), 3).move_to(P(0.25, 0.6))
        panel = _o(Rectangle(width=0.5, height=0.08, fill_color="#118AB2", fill_opacity=1), 2).move_to(P(-0.2, 0.26))
        planet = Arc(radius=2.2, start_angle=PI / 2 - 0.35, angle=0.7, stroke_width=4, color="#E76F51") \
            .move_to(P(0, -0.5))
        return VGroup(planet, body, wheels, mast, cam, panel)
    return VGroup(_o(Square(0.9, fill_color="#FFD166", fill_opacity=1)), txt("?", 40))


def album(examples: list[str], reveal: list[float], open_u: float = 1.0) -> VGroup:
    """'Robot family album': a card with one tile per example; each tile pops in with its reveal progress."""
    n = len(examples)
    w = 2.1 * n + 0.6
    card = _o(RoundedRectangle(width=w, height=2.9, corner_radius=0.25, fill_color="#FFFFFF", fill_opacity=1))
    head = txt("ROBOT FAMILY ALBUM", 26, color="#6C4AB6").move_to(card.get_top() + DOWN * 0.35)
    g = VGroup(card, head)
    for i, (name, r) in enumerate(zip(examples, reveal)):
        if r <= 0:
            continue
        cx = -w / 2 + 0.3 + 2.1 * (i + 0.5)
        frame = _o(RoundedRectangle(width=1.8, height=1.7, corner_radius=0.15, fill_color="#E0FBFC", fill_opacity=1), 4)
        tile = VGroup(frame.move_to(P(cx, 0.05)), icon(name).scale(0.95).move_to(P(cx, 0.1)),
                      txt(name, 20).move_to(P(cx, -1.05)))
        g.add(tile.scale(pop(r), about_point=P(cx, 0.0)))
    return g.scale(max(0.001, ease_out(open_u)))


# ------------------------------------------------------------------------------------------ check-up

def checklist(parts: list[str], ticks: list[float]) -> VGroup:
    card = _o(RoundedRectangle(width=3.5, height=0.6 + 0.55 * len(parts), corner_radius=0.2, fill_color="#FFFFFF",
                               fill_opacity=1))
    g = VGroup(card, txt("ROBOT CHECK-UP", 24, color="#6C4AB6").move_to(card.get_top() + DOWN * 0.3))
    for i, (name, t) in enumerate(zip(parts, ticks)):
        y = card.get_top()[1] - 0.8 - 0.55 * i
        boxm = _o(Square(0.32, fill_color="#FFFFFF", fill_opacity=1), 3).move_to(P(-1.35, y))
        label = txt(name.capitalize(), 24, color=ink() if t > 0 else "#9A8C98")
        label.move_to(P(-1.05 + label.width / 2, y))
        g.add(boxm, label)
        if t > 0:
            tick = VMobject(stroke_color=OK_GREEN, stroke_width=8).set_points_as_corners(
                [P(-1.47, y + 0.02), P(-1.37, y - 0.1), P(-1.17, y + 0.16)])
            g.add(tick.scale(pop(t), about_point=P(-1.35, y)))
    return g


def battery(level: float, charging: bool = False) -> VGroup:
    shell = _o(RoundedRectangle(width=1.0, height=0.45, corner_radius=0.08, fill_color="#FFFFFF", fill_opacity=1), 4)
    tip = Rectangle(width=0.08, height=0.2, fill_color=ink(), fill_opacity=1, stroke_width=0) \
        .next_to(shell, RIGHT, buff=0)
    lv = clamp01(level)
    color = ALERT if lv < 0.3 else "#FFD166" if lv < 0.7 else OK_GREEN
    fill = Rectangle(width=max(0.02, 0.86 * lv), height=0.31, fill_color=color, fill_opacity=1, stroke_width=0)
    fill.move_to(shell.get_left() + RIGHT * (0.07 + fill.width / 2))
    g = VGroup(shell, tip, fill)
    if charging:
        g.add(Polygon(P(0.05, 0.2), P(-0.12, -0.02), P(0.0, -0.02), P(-0.05, -0.2), P(0.12, 0.04), P(0.0, 0.04),
                      fill_color="#FFE66D", fill_opacity=1, stroke_color=ink(), stroke_width=2).move_to(shell))
    return g


def cable(a: np.ndarray, b: np.ndarray, u: float = 1.0) -> VGroup:
    u = clamp01(u)
    end = a + (b - a) * ease_out(u)
    sag = P(0, -0.8 * (1 - abs(0.5 - u)))
    c = CubicBezier(a, a + (end - a) / 3 + sag, a + 2 * (end - a) / 3 + sag, end).set_stroke("#45505E", 8)
    plug = _o(Rectangle(width=0.22, height=0.16, fill_color="#FFD166", fill_opacity=1), 3).move_to(end)
    return VGroup(c, plug)


def glow_outline(mob, u: float = 1.0, color: str = "#FFE66D") -> VGroup:
    """Pulsing highlight around a rig part (copy of its outline, thick and bright)."""
    k = 0.5 + 0.5 * math.sin(2 * math.pi * 2 * u)
    g = mob.copy()
    g.set_fill(opacity=0)
    g.set_stroke(color, 16 + 10 * k, opacity=0.55 + 0.35 * k)
    return VGroup(g)


def part_label(text: str, at: np.ndarray, u: float) -> VGroup:
    t = txt(text, 26, color="#FFFFFF")
    pill = RoundedRectangle(width=t.width + 0.4, height=t.height + 0.25, corner_radius=0.2, fill_color="#6C4AB6",
                            fill_opacity=1).set_stroke(ink(), 4)
    return VGroup(pill, t).move_to(at).scale(pop(u * 2.5), about_point=at)


# ------------------------------------------------------------------------------------------ sensor demo

def ping_waves(origin: np.ndarray, u: float, reach: float, back: bool = False, color: str = "#4CC9F0") -> VGroup:
    """Ultrasonic 'ping': three arcs travelling ``reach`` units to the right (or back for the echo)."""
    g = VGroup()
    for k in range(3):
        v = clamp01(u * 1.3 - 0.15 * k)
        if v <= 0 or v >= 1:
            continue
        d = reach * (v if not back else 1 - v)
        r = 0.3 + 0.25 * d / max(reach, 1e-6) + 0.2
        arc = Arc(radius=r, start_angle=-0.6, angle=1.2, stroke_width=7, color=color if not back else "#F72585")
        arc.set_stroke(opacity=1 - 0.6 * v)
        g.add(arc.move_to(origin + RIGHT * (0.1 + d)))
    return g


def ruler(x0: float, meters: float, y: float = FLOOR_Y - 0.85, step: float = 0.5, danger: float | None = None,
          highlight: float | None = None) -> VGroup:
    """Floor tape measure starting at ``x0`` (0 m) and running right, ticks every ``step`` m."""
    length = meters * METER
    tape = _o(Rectangle(width=length, height=0.32, fill_color="#FFD166", fill_opacity=1), 3) \
        .move_to(P(x0 + length / 2, y))
    g = VGroup(tape)
    if danger:
        g.add(Rectangle(width=danger * METER, height=0.32, fill_color=ALERT, fill_opacity=0.55, stroke_width=0)
              .move_to(P(x0 + danger * METER / 2, y)))
    n = int(round(meters / step))
    for i in range(n + 1):
        m = i * step
        x = x0 + m * METER
        major = abs(m - round(m)) < 1e-6
        g.add(Line(P(x, y + 0.16), P(x, y + (-0.05 if major else 0.05)), stroke_width=3, color=ink()))
        if major or step >= 0.5:
            g.add(txt(f"{m:g} m", 16).move_to(P(x, y - 0.3)))
    if highlight is not None:
        x = x0 + highlight * METER
        g.add(Triangle(fill_color=ALERT, fill_opacity=1, stroke_color=ink(), stroke_width=3).scale(0.13)
              .rotate(PI).move_to(P(x, y + 0.32)))
    return g


def ruler_rev(x_face: float, meters: float, **kw) -> VGroup:
    """Tape measure whose 0 m is at an obstacle face and which counts up to the LEFT (distance-to-obstacle)."""
    g = ruler(0.0, meters, **kw)
    labels = [m for m in g if isinstance(m, Text)]
    g.stretch(-1, 0, about_point=P(0, 0))
    for lb in labels:                                  # un-mirror the text
        lb.stretch(-1, 0)
    return g.shift(RIGHT * x_face)


def range_zone(x0: float, meters: float, u: float = 1.0, y_mid: float = GROUND + 1.6, h: float = 2.6) -> VGroup:
    w = meters * METER * ease_out(u)
    zone = Rectangle(width=max(0.01, w), height=h, fill_color="#4CC9F0", fill_opacity=0.16, stroke_width=0)
    zone.move_to(P(x0 + w / 2, y_mid))
    edge = Line(P(x0 + w, y_mid - h / 2), P(x0 + w, y_mid + h / 2), stroke_width=4, color="#4CC9F0")
    edge.set_stroke(opacity=0.9)
    lab = txt(f"sensor range {meters:g} m", 22, color="#118AB2").move_to(P(x0 + w - 1.3, y_mid + h / 2 + 0.25))
    return VGroup(zone, edge, lab) if u >= 1 else VGroup(zone, edge)


def readout(lines: list[tuple[str, str]], at: np.ndarray, u: float = 1.0) -> VGroup:
    """HUD panel: list of (text, colour) rows."""
    rows = VGroup(*[txt(s, 28, color=c) for s, c in lines]).arrange(DOWN, aligned_edge=LEFT, buff=0.12)
    panel = RoundedRectangle(width=rows.width + 0.5, height=rows.height + 0.4, corner_radius=0.2,
                             fill_color="#1B1B3A", fill_opacity=0.92).set_stroke(ink(), 5)
    g = VGroup(panel, rows.move_to(panel)).move_to(at)
    return g.scale(pop(u * 3), about_point=at)


def tag(text: str, at: np.ndarray, color: str = ALERT, size: int = 26) -> VGroup:
    t = txt(text, size, color="#FFFFFF")
    pill = RoundedRectangle(width=t.width + 0.35, height=t.height + 0.22, corner_radius=0.18, fill_color=color,
                            fill_opacity=1).set_stroke(ink(), 3)
    return VGroup(pill, t).move_to(at)


# ------------------------------------------------------------------------------------------ rule board

def chalkboard(rule_words: list[str], u: float, at: np.ndarray = P(-0.6, 2.1), width: float = 7.2) -> VGroup:
    board = RoundedRectangle(width=width, height=2.0, corner_radius=0.12, fill_color="#2D6A4F", fill_opacity=1)
    board.set_stroke("#8D5524", 14).move_to(at)
    head = txt("THE RULE", 22, color="#FFD166").move_to(board.get_top() + DOWN * 0.3)
    n = len(rule_words)
    shown = int(math.ceil(clamp01(u) * n)) if u > 0 else 0
    g = VGroup(board, head)
    if shown:
        line = txt(" ".join(rule_words[:shown]), 34, color=CHALK)
        full = txt(" ".join(rule_words), 34, color=CHALK)
        fit = min(1.0, (width - 0.6) / full.width)
        line.scale(fit)
        full.scale(fit)
        line.move_to(board.get_center() + DOWN * 0.15).align_to(full.move_to(board.get_center() + DOWN * 0.15), LEFT)
        g.add(line)
    return g


def stc_chips(active: str | None, at: np.ndarray = P(0, 3.45)) -> VGroup:
    g = VGroup()
    for i, name in enumerate(("SENSE", "THINK", "ACT")):
        on = active == name
        t = txt(name, 26, color="#FFFFFF" if on else ink())
        pill = RoundedRectangle(width=1.9, height=0.55, corner_radius=0.27,
                                fill_color={"SENSE": "#4CC9F0", "THINK": "#FFD166", "ACT": OK_GREEN}[name] if on
                                else "#FFFFFF", fill_opacity=1).set_stroke(ink(), 4 if on else 2)
        chip = VGroup(pill, t.move_to(pill)).move_to(at + RIGHT * (i - 1) * 2.4)
        if on:
            chip.scale(1.12)
        g.add(chip)
        if i < 2:
            g.add(txt("→", 30).move_to(at + RIGHT * ((i - 1) * 2.4 + 1.2)))
    return g


# ------------------------------------------------------------------------------------------ servo

def protractor(center: np.ndarray, angle_deg: float, facing: int = 1, radius: float = 1.5,
               target: float | None = None) -> VGroup:
    """Quarter-circle gauge at the shoulder: 0° = arm straight forward, 90° = straight up."""
    s = facing
    fan = VMobject().set_points_as_corners([center] + [center + radius * P(s * math.cos(math.radians(a)),
                                                                           math.sin(math.radians(a)))
                                                       for a in range(0, 91, 5)] + [center])
    fan.set_fill("#FFFFFF", 0.75).set_stroke(ink(), 3)
    g = VGroup(fan)
    for a in (0, 30, 60, 90):
        d = P(s * math.cos(math.radians(a)), math.sin(math.radians(a)))
        g.add(Line(center + d * radius * 0.85, center + d * radius, stroke_width=3, color=ink()))
        g.add(txt(f"{a}°", 16).move_to(center + d * (radius + 0.25)))
    if target is not None:
        d = P(s * math.cos(math.radians(target)), math.sin(math.radians(target)))
        g.add(Line(center, center + d * radius, stroke_width=4, color=OK_GREEN).set_stroke(opacity=0.8))
    d = P(s * math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg)))
    g.add(Line(center, center + d * radius * 0.95, stroke_width=7, color=ALERT))
    g.add(tag(f"{angle_deg:.0f}°", center + P(s * 0.1, -0.45), color="#6C4AB6", size=24))
    return g


# ------------------------------------------------------------------------------------------ lettering / cards

SFX_WORDS = {"bonk": ("BONK!", ALERT), "boing": ("BOING!", "#7209B7"), "pop": ("POP!", "#FF9F1C"),
             "toaster_pop": ("POP!", "#FF9F1C"), "skid": ("SKREEE!", "#F77F00"), "clap": ("CLAP!", "#06D6A0"),
             "whoosh": ("WHOOSH!", "#118AB2"), "ping": ("PING!", "#4CC9F0"), "ding": ("DING!", "#FFD166"),
             "zoom": ("ZOOM!", "#F72585"), "charge": ("BZZT!", "#FFD166")}


def sfx_text(word: str, color: str, u: float, at: np.ndarray, angle: float = 0.15, size: int = 88) -> VGroup:
    if u <= 0 or u >= 1:
        return VGroup()
    t = txt(word, size, color=color, font="Bangers", weight="NORMAL", stroke=5)
    k = pop(u / 0.3) * (1 + 0.06 * math.sin(20 * u))
    g = VGroup(t).rotate(angle).move_to(at).scale(k)
    if u > 0.8:
        g.set_opacity((1 - u) / 0.2)
    return g


def speech_bubble(text: str, tail_to: np.ndarray, u: float, at: np.ndarray, size: int = 30) -> VGroup:
    if u <= 0 or u >= 1:
        return VGroup()
    t = txt(text, size)
    body = RoundedRectangle(width=t.width + 0.5, height=t.height + 0.4, corner_radius=0.3, fill_color="#FFFFFF",
                            fill_opacity=1).set_stroke(ink(), 5).move_to(at)
    base = body.get_bottom()
    tail = Polygon(base + LEFT * 0.2 + UP * 0.05, base + RIGHT * 0.2 + UP * 0.05, tail_to, fill_color="#FFFFFF",
                   fill_opacity=1).set_stroke(ink(), 5)
    cover = Rectangle(width=0.38, height=0.1, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0) \
        .move_to(base + UP * 0.05)
    return VGroup(tail, body, cover, t.move_to(body)).scale(pop(u / 0.15), about_point=at)


def title_card(u: float, subtitle: str = "with Bolt, Maya & Nib") -> VGroup:
    if u <= 0 or u >= 1:
        return VGroup()
    burst = Star(16, outer_radius=4.2, inner_radius=3.2, fill_color="#FFD166", fill_opacity=1, stroke_color=ink(),
                 stroke_width=6).rotate(u * 0.6)
    title = txt("ROBOTICS 101", 120, color="#FF6B9A", font="Luckiest Guy", weight="NORMAL", stroke=6)
    sub = txt(subtitle, 40).next_to(title, DOWN, buff=0.2)
    g = VGroup(burst, title, sub)
    k = pop(u / 0.25)
    if u > 0.85:
        k *= max(0.001, 1 - (u - 0.85) / 0.15)
    return g.scale(k)


def card(title: str, body: str, u: float, at: np.ndarray = P(0, 2.2), width: float = 9.5) -> VGroup:
    if u <= 0:
        return VGroup()
    head = txt(title, 30, color="#6C4AB6")
    text = wrap(body, 40, width - 0.6)
    if text.width > width - 0.6:
        text.scale((width - 0.6) / text.width)
    panel = RoundedRectangle(width=width, height=head.height + text.height + 0.9, corner_radius=0.3,
                             fill_color="#FFFFFF", fill_opacity=1).set_stroke(ink(), 6)
    VGroup(head, text).arrange(DOWN, buff=0.25).move_to(panel)
    return VGroup(panel, head, text).move_to(at).scale(pop(u * 3), about_point=at)


def chant_word(word: str, color: str, u: float, at: np.ndarray) -> VGroup:
    return sfx_text(word, color, u, at, angle=0.0, size=130)


# ------------------------------------------------------------------------------------------ top-down inset

def top_down_inset(robot_xy: tuple[float, float], heading_deg: float, threshold_m: float, obstacle_x_m: float,
                   path: list[tuple[float, float]], at: np.ndarray = P(4.75, 2.45), status: str = "") -> VGroup:
    """Mini-map (metres, top view): obstacle wall, threshold band, robot triangle + heading, driven path."""
    W, H, k = 4.2, 2.6, 1.0                      # inset units; 1 m = k*... scaled below
    panel = RoundedRectangle(width=W, height=H, corner_radius=0.18, fill_color="#F8F9FA", fill_opacity=0.97)
    panel.set_stroke(ink(), 5).move_to(at)
    scale = 1.05                                  # inset units per metre
    origin = at + P(-W / 2 + 0.45, -H / 2 + 0.55)

    def m2p(x, y):
        return origin + P(x * scale, y * scale)
    wall = Rectangle(width=0.22, height=H - 0.5, fill_color="#E76F51", fill_opacity=1, stroke_width=0) \
        .move_to(m2p(obstacle_x_m, 0) + P(0.11, (H - 0.5) / 2 - 0.3))
    band = Rectangle(width=threshold_m * scale, height=H - 0.5, fill_color=ALERT, fill_opacity=0.18, stroke_width=0) \
        .move_to(m2p(obstacle_x_m - threshold_m / 2, 0) + P(0, (H - 0.5) / 2 - 0.3))
    g = VGroup(panel, band, wall, txt("top view", 16).move_to(panel.get_top() + DOWN * 0.2),
               txt(f"{threshold_m:g} m", 14, color=ALERT).move_to(m2p(obstacle_x_m - threshold_m / 2, -0.25)))
    if len(path) >= 2:
        g.add(VMobject(stroke_color="#4CC9F0", stroke_width=4).set_points_as_corners([m2p(*p) for p in path]))
    tri = Triangle(fill_color="#2EC4B6", fill_opacity=1, stroke_color=ink(), stroke_width=3).scale(0.16)
    tri.rotate(math.radians(heading_deg - 90)).move_to(m2p(*robot_xy))
    g.add(tri)
    if status:
        g.add(txt(status, 18, color=ALERT if "STOP" in status else ink()).move_to(panel.get_bottom() + UP * 0.2))
    return g
