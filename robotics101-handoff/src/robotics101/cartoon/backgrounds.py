"""Section backgrounds (M05.5): a library of themed sets drawn in code, with palette variants.

Every episode section gets its own background (``episode.resolve_backgrounds`` auto-assigns one per section when the
spec doesn't name it, and adjacent sections never share a theme). All themes keep the shared stage geometry from
``sets`` (floor line at ``FLOOR_Y``, characters on ``GROUND``, the wall socket at ``SOCKET_POS``), so staging,
props, rulers, the caption band and the acting work are unaffected by which background is drawn.

Themes are static VGroups, built once per (theme, palette, variant) and cached.
"""

from __future__ import annotations

import math
from functools import lru_cache

import numpy as np
from manim import (LEFT, RIGHT, UP, Arc, Circle, Line, Polygon, Rectangle, RoundedRectangle, Square, Triangle,
                   VGroup)

from robotics101.cartoon import BACKGROUND_THEMES
from robotics101.cartoon.sets import FLOOR_Y, SOCKET_POS, garage, ink

W, H = 14.4, 8.2
TOP = H / 2


def P(x: float, y: float) -> np.ndarray:
    return np.array([x, y, 0.0])


def _o(m, w=5):
    return m.set_stroke(ink(), w)


def _rect(x0, y0, x1, y1, color, opacity=1.0, stroke=0):
    r = Rectangle(width=x1 - x0, height=y1 - y0, fill_color=color, fill_opacity=opacity, stroke_width=0)
    r.move_to(P((x0 + x1) / 2, (y0 + y1) / 2))
    return _o(r, stroke) if stroke else r


def _room(wall: str, floor: str, trim: str, floor_lines: str | None = None, perspective: bool = True) -> list:
    """Wall + floor + skirting + floor line in the shared stage geometry."""
    parts = [_rect(-W / 2, -H / 2, W / 2, H / 2, wall), _rect(-W / 2, -H / 2, W / 2, FLOOR_Y, floor)]
    if floor_lines:
        if perspective:
            parts += [Line(P(x, FLOOR_Y), P(x * 1.6, -4.1), stroke_width=2, color=floor_lines)
                      for x in np.arange(-6, 7, 2.0)]
        else:
            parts += [Line(P(-W / 2, y), P(W / 2, y), stroke_width=2, color=floor_lines)
                      for y in (FLOOR_Y - 0.5, FLOOR_Y - 1.2)]
    parts += [_rect(-W / 2, FLOOR_Y, W / 2, FLOOR_Y + 0.18, trim),
              Line(LEFT * 7.2, RIGHT * 7.2, stroke_width=8, color=ink()).shift(UP * FLOOR_Y)]
    return parts


def _socket(face: str = "#FFFFFF") -> VGroup:
    s = _o(RoundedRectangle(width=0.35, height=0.5, corner_radius=0.06, fill_color=face, fill_opacity=1), 3)
    s.move_to(SOCKET_POS)
    s.add(*[Line(SOCKET_POS + P(x, 0.1), SOCKET_POS + P(x, -0.05), stroke_width=4, color=ink()) for x in (-0.07, 0.07)])
    return s


# ------------------------------------------------------------------------------------------ themes

def studio(pal: dict) -> VGroup:
    """TV studio: curtains, a marquee of bulbs and a stage floor (the cast intro)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"])
    parts += [Circle(0.05, fill_color="#FFFFFF", fill_opacity=0.55, stroke_width=0).move_to(P(x, y))
              for x in np.arange(-6.5, 7, 1.3) for y in np.arange(-1.0, 3.9, 1.1) if (round(x * 10) + round(y * 10)) % 3 == 0]
    for side in (-1, 1):
        x_out, x_in = side * 7.2, side * 5.6
        cur = Polygon(P(x_out, TOP), P(x_in, TOP), P(side * 6.1, 1.0), P(x_in + side * 0.2, FLOOR_Y),
                      P(x_out, FLOOR_Y), fill_color=pal["accent"], fill_opacity=1)
        folds = VGroup(*[Line(P(x_out - side * k, TOP), P(x_out - side * k * 0.9, FLOOR_Y), stroke_width=3,
                              color=pal["accent2"]) for k in (0.4, 0.8, 1.2)])
        parts += [_o(cur, 5), folds]
    valance = _rect(-W / 2, TOP - 0.55, W / 2, TOP, pal["accent"], stroke=5)
    scallops = VGroup(*[_o(Arc(radius=0.36, start_angle=math.pi, angle=math.pi, fill_color=pal["accent"],
                                fill_opacity=1), 4).move_to(P(x, TOP - 0.7)) for x in np.arange(-6.6, 7, 0.72)])
    bulbs = VGroup(*[Circle(0.09, fill_color="#FFE66D", fill_opacity=1, stroke_color=ink(), stroke_width=2)
                     .move_to(P(x, TOP - 1.25)) for x in np.arange(-4.6, 4.7, 0.6)])
    parts += [valance, scallops, bulbs, _socket()]
    return VGroup(*parts)


def museum(pal: dict) -> VGroup:
    """Robot museum: framed robot portraits on a gallery wall, a velvet rope and plinths."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"])
    parts.append(_rect(-W / 2, 0.6, W / 2, 0.75, pal["accent2"]))           # picture rail
    for x, kind in ((-5.0, "bot"), (-1.9, "arm"), (1.9, "rover"), (5.0, "bot")):
        frame = _o(RoundedRectangle(width=2.0, height=1.6, corner_radius=0.08, fill_color=pal["accent"],
                                    fill_opacity=1), 6).move_to(P(x, 2.3))
        mat = _rect(x - 0.78, 1.68, x + 0.78, 2.92, "#FFFDF6")
        g = VGroup(frame, mat)
        c = pal["art"]
        if kind == "bot":
            g.add(_o(RoundedRectangle(width=0.7, height=0.55, corner_radius=0.1, fill_color=c, fill_opacity=1), 3)
                  .move_to(P(x, 2.42)), _o(Rectangle(width=0.5, height=0.3, fill_color=c, fill_opacity=1), 3)
                  .move_to(P(x, 1.98)), Line(P(x, 2.7), P(x, 2.85), stroke_width=3, color=ink()))
        elif kind == "arm":
            g.add(Line(P(x - 0.4, 1.85), P(x - 0.1, 2.5), stroke_width=7, color=c),
                  Line(P(x - 0.1, 2.5), P(x + 0.4, 2.3), stroke_width=7, color=c),
                  _rect(x - 0.55, 1.78, x - 0.25, 1.9, ink()))
        else:
            g.add(_o(RoundedRectangle(width=0.9, height=0.35, corner_radius=0.08, fill_color=c, fill_opacity=1), 3)
                  .move_to(P(x, 2.15)), *[_o(Circle(0.11, fill_color=ink(), fill_opacity=1), 2)
                                           .move_to(P(x + dx, 1.92)) for dx in (-0.3, 0, 0.3)])
        parts.append(g)
    for x in (-6.3, 6.3):
        parts += [_o(_rect(x - 0.45, FLOOR_Y, x + 0.45, FLOOR_Y + 1.1, pal["trim"]), 4),
                  _o(_rect(x - 0.6, FLOOR_Y + 1.1, x + 0.6, FLOOR_Y + 1.25, pal["accent2"]), 4)]
    parts.append(_socket())
    return VGroup(*parts)


def lab_bench(pal: dict) -> VGroup:
    """Robot clinic / lab: tiled wall, a back bench with beakers and a heartbeat monitor (the robot check-up)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"], perspective=False)
    parts += [Line(P(x, FLOOR_Y + 0.18), P(x, TOP), stroke_width=2, color=pal["grid"]) for x in np.arange(-7, 7.2, 0.8)]
    parts += [Line(P(-W / 2, y), P(W / 2, y), stroke_width=2, color=pal["grid"]) for y in np.arange(FLOOR_Y + 0.8, TOP, 0.8)]
    bench = _o(_rect(-7.3, 0.9, 1.2, 1.15, pal["accent2"]), 5)
    parts.append(bench)
    for x, h, c in ((-6.0, 0.7, "#4CC9F0"), (-5.3, 0.5, "#06D6A0"), (-4.6, 0.85, "#F72585"), (-0.6, 0.6, "#FFD166")):
        flask = Polygon(P(x - 0.1, 1.15 + h), P(x + 0.1, 1.15 + h), P(x + 0.28, 1.15), P(x - 0.28, 1.15),
                        fill_color=c, fill_opacity=0.9)
        parts.append(_o(flask, 3))
    mon = _o(RoundedRectangle(width=2.5, height=1.7, corner_radius=0.15, fill_color="#1B1B3A", fill_opacity=1), 6) \
        .move_to(P(-2.6, 2.3))
    beat = [P(-3.6, 2.2), P(-3.0, 2.2), P(-2.8, 2.75), P(-2.55, 1.7), P(-2.35, 2.45), P(-2.2, 2.2), P(-1.6, 2.2)]
    heart = VGroup(*[Line(a, b, stroke_width=5, color="#7CFFCB") for a, b in zip(beat, beat[1:])])
    cross = VGroup(_rect(-0.25 + 0.9, 3.0, 0.25 + 0.9, 3.5, pal["accent"]), _rect(0.4, 3.15, 1.4, 3.35, pal["accent"]))
    parts += [mon, heart, cross, _socket()]
    return VGroup(*parts)


def sound_lab(pal: dict) -> VGroup:
    """Sound lab: acoustic-foam wall, big speaker cones and ripple rings (sensors: ping!)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"])
    for i, x in enumerate(np.arange(-6.8, 7, 0.8)):
        for j, y in enumerate(np.arange(FLOOR_Y + 0.6, TOP, 0.8)):
            up = (i + j) % 2 == 0
            tri = Triangle(fill_color=pal["foam"], fill_opacity=1, stroke_width=0).scale(0.33)
            parts.append(tri.rotate(0 if up else math.pi).move_to(P(x, y)))
    for x in (-5.6, 5.6):
        cab = _o(RoundedRectangle(width=1.5, height=2.6, corner_radius=0.15, fill_color=pal["accent2"],
                                  fill_opacity=1), 6).move_to(P(x, FLOOR_Y + 1.3))
        cones = VGroup(*[VGroup(_o(Circle(r, fill_color="#2B2140", fill_opacity=1), 4),
                                Circle(r * 0.35, fill_color=pal["accent"], fill_opacity=1, stroke_width=0))
                         .move_to(P(x, FLOOR_Y + y)) for r, y in ((0.5, 0.85), (0.32, 2.0))])
        parts += [cab, cones]
    rings = VGroup(*[Arc(radius=r, start_angle=-0.6, angle=1.2, stroke_width=6, color=pal["accent"])
                     .move_to(P(-1.2 + r * 0.5, 2.6)) for r in (0.4, 0.8, 1.2)])
    parts += [rings, _socket()]
    return VGroup(*parts)


def control_room(pal: dict) -> VGroup:
    """Robot brain control room: panelled wall, blinking console lights and a gauge (the rule)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"], perspective=False)
    for x in np.arange(-6.6, 7, 2.2):
        parts.append(_o(RoundedRectangle(width=2.0, height=3.6, corner_radius=0.12, fill_color=pal["panel"],
                                         fill_opacity=1), 3).move_to(P(x, FLOOR_Y + 2.5)))
    cols = ("#EF476F", "#FFD166", "#06D6A0", "#4CC9F0")
    for k, x in enumerate(np.arange(-6.9, 7, 0.45)):
        parts.append(Circle(0.08, fill_color=cols[k % 4], fill_opacity=1, stroke_color=ink(), stroke_width=2)
                     .move_to(P(x, FLOOR_Y + 0.55 + 0.25 * (k % 2))))
    gauge = VGroup(_o(Circle(0.6, fill_color="#FFFDF6", fill_opacity=1), 5),
                   Arc(radius=0.45, start_angle=math.pi * 0.15, angle=math.pi * 0.7, stroke_width=8, color="#06D6A0"),
                   Line(P(0, 0), P(0.3, 0.32), stroke_width=5, color=ink())).move_to(P(-5.5, 3.0))
    wires = VGroup(*[Line(P(x, TOP), P(x, TOP - 0.5), stroke_width=6, color=pal["accent"]) for x in (-2.6, -2.3, 2.4)])
    parts += [gauge, wires, _socket()]
    return VGroup(*parts)


def blueprint(pal: dict) -> VGroup:
    """Servo blueprint: grid-paper wall with white line drawings of gears and a servo (actuators)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"], perspective=False)
    parts += [Line(P(x, FLOOR_Y + 0.18), P(x, TOP), stroke_width=1.5, color=pal["grid"]) for x in np.arange(-7, 7.2, 0.5)]
    parts += [Line(P(-W / 2, y), P(W / 2, y), stroke_width=1.5, color=pal["grid"]) for y in np.arange(FLOOR_Y + 0.5, TOP, 0.5)]
    ink_w = pal["draw"]

    def gear(cx, cy, r, teeth):
        g = VGroup(Circle(r, stroke_color=ink_w, stroke_width=4).move_to(P(cx, cy)),
                   Circle(r * 0.3, stroke_color=ink_w, stroke_width=4).move_to(P(cx, cy)))
        for k in range(teeth):
            a = 2 * math.pi * k / teeth
            g.add(Square(side_length=r * 0.32, stroke_color=ink_w, stroke_width=4).rotate(a)
                  .move_to(P(cx, cy) + 1.12 * r * np.array([math.cos(a), math.sin(a), 0])))
        return g
    parts += [gear(-5.2, 2.4, 0.75, 10), gear(-4.0, 1.4, 0.45, 8), gear(5.4, 2.7, 0.6, 9)]
    servo = VGroup(Rectangle(width=2.2, height=1.1, stroke_color=ink_w, stroke_width=4).move_to(P(0.9, 2.6)),
                   Circle(0.3, stroke_color=ink_w, stroke_width=4).move_to(P(0.2, 2.6)),
                   Line(P(0.2, 2.6), P(-0.6, 3.3), stroke_width=6, color=ink_w),
                   Arc(radius=1.0, start_angle=math.pi * 0.55, angle=math.pi * 0.4, stroke_width=3, color=ink_w)
                   .move_arc_center_to(P(0.2, 2.6)),
                   Line(P(-0.2, 1.8), P(2.0, 1.8), stroke_width=3, color=ink_w),
                   Line(P(-0.2, 1.7), P(-0.2, 1.9), stroke_width=3, color=ink_w),
                   Line(P(2.0, 1.7), P(2.0, 1.9), stroke_width=3, color=ink_w))
    parts += [servo, _socket(pal["trim"])]
    return VGroup(*parts)


def test_track(pal: dict) -> VGroup:
    """Outdoor test track: sky, sun, hills, a fence and an asphalt track with lane dashes (the rematch)."""
    sky = [_rect(-W / 2, y0, W / 2, y1, c) for (y0, y1), c in zip(((1.6, TOP), (0.4, 1.6), (FLOOR_Y, 0.4)), pal["sky"])]
    parts = sky
    parts.append(_o(Circle(0.55, fill_color=pal["sun"], fill_opacity=1), 4).move_to(P(5.6, 3.0)))
    for x, y, r in ((-4.8, 3.1, 0.35), (-4.3, 3.2, 0.45), (-3.8, 3.05, 0.32), (1.6, 2.7, 0.3), (2.0, 2.8, 0.38)):
        parts.append(Circle(r, fill_color="#FFFFFF", fill_opacity=0.95, stroke_width=0).move_to(P(x, y)))
    parts.append(_o(Polygon(P(-7.3, FLOOR_Y), P(-4.5, 1.2), P(-1.5, FLOOR_Y + 0.4), P(2.0, 0.9), P(5.0, FLOOR_Y + 0.3),
                            P(7.3, 1.0), P(7.3, FLOOR_Y), fill_color=pal["hill"], fill_opacity=1), 4))
    parts += [_o(_rect(x - 0.06, FLOOR_Y + 0.05, x + 0.06, FLOOR_Y + 0.9, pal["fence"]), 2) for x in np.arange(-6.9, 7.1, 0.9)]
    parts += [_o(_rect(-W / 2, FLOOR_Y + y, W / 2, FLOOR_Y + y + 0.1, pal["fence"]), 2) for y in (0.35, 0.7)]
    parts.append(_rect(-W / 2, -H / 2, W / 2, FLOOR_Y, pal["floor"]))
    parts += [_rect(x, FLOOR_Y - 1.0, x + 0.8, FLOOR_Y - 0.9, "#FFFFFF", 0.85) for x in np.arange(-7.0, 7.2, 1.6)]
    for x in (-6.4, 6.6):
        cone = _o(Polygon(P(x - 0.3, FLOOR_Y + 0.02), P(x + 0.3, FLOOR_Y + 0.02), P(x, FLOOR_Y + 0.8),
                          fill_color="#FF8C42", fill_opacity=1), 3)
        parts += [cone, _rect(x - 0.17, FLOOR_Y + 0.3, x + 0.17, FLOOR_Y + 0.4, "#FFFFFF")]
    post = _o(_rect(SOCKET_POS[0] - 0.3, FLOOR_Y, SOCKET_POS[0] + 0.3, SOCKET_POS[1] + 0.45, pal["trim"]), 4)
    parts += [_rect(-W / 2, FLOOR_Y, W / 2, FLOOR_Y + 0.08, pal["trim"]),
              Line(LEFT * 7.2, RIGHT * 7.2, stroke_width=8, color=ink()).shift(UP * FLOOR_Y), post, _socket()]
    return VGroup(*parts)


def quiz_stage(pal: dict) -> VGroup:
    """Quiz-show stage: sunburst rays, a bulb-lit arch and a shiny floor (recap and quiz)."""
    parts = _room(pal["wall"], pal["floor"], pal["trim"], pal["lines"])
    c = P(0, 0.4)
    for k in range(16):
        a0, a1 = 2 * math.pi * k / 16, 2 * math.pi * (k + 0.5) / 16
        parts.append(Polygon(c, c + 12 * np.array([math.cos(a0), math.sin(a0), 0]),
                             c + 12 * np.array([math.cos(a1), math.sin(a1), 0]),
                             fill_color=pal["ray"], fill_opacity=1, stroke_width=0))
    parts = parts[:1] + parts[len(parts) - 16:] + parts[1:len(parts) - 16]       # rays on the wall, behind the floor
    arch = Arc(radius=5.6, start_angle=math.pi * 0.06, angle=math.pi * 0.88, stroke_width=26, color=pal["accent"])
    arch.move_arc_center_to(P(0, FLOOR_Y - 1.0))
    bulbs = VGroup(*[Circle(0.1, fill_color="#FFE66D", fill_opacity=1, stroke_color=ink(), stroke_width=2)
                     .move_to(P(0, FLOOR_Y - 1.0) + 5.6 * np.array([math.cos(a), math.sin(a), 0]))
                     for a in np.linspace(math.pi * 0.08, math.pi * 0.92, 19)])
    stars = VGroup(*[Polygon(*[P(x, y) + (0.22 if i % 2 == 0 else 0.09) * np.array(
        [math.cos(math.pi / 2 + i * math.pi / 5), math.sin(math.pi / 2 + i * math.pi / 5), 0]) for i in range(10)],
        fill_color="#FFFFFF", fill_opacity=0.9, stroke_width=0) for x, y in ((-6.2, 3.2), (6.1, 3.4), (-3.1, 3.6), (3.4, 3.1))])
    parts += [arch, bulbs, stars, _socket()]
    return VGroup(*parts)


def workshop(pal: dict, variant: str = "default") -> VGroup:
    """The original garage workshop (M02.5), recoloured by palette (the default 'sunny' palette is unchanged)."""
    g = garage(variant).copy()
    if pal.get("tint"):
        g[0].set_fill(pal["wall"])
        g[1].set_fill(pal["stripe"])
        g[2].set_fill(pal["floor"])
    return g


THEMES = {
    "workshop": (workshop, {
        "sunny": {},
        "evening": {"tint": True, "wall": "#F6D6C8", "stripe": "#EFC3B2", "floor": "#8E6C8A"},
    }),
    "studio": (studio, {
        "violet": {"wall": "#3D2C6B", "floor": "#C9844D", "trim": "#8E5B2F", "lines": "#A86F3E",
                   "accent": "#D7263D", "accent2": "#A51C30"},
        "teal": {"wall": "#1F4E5F", "floor": "#C9844D", "trim": "#8E5B2F", "lines": "#A86F3E",
                 "accent": "#6C4AB6", "accent2": "#4E3591"},
    }),
    "museum": (museum, {
        "mint": {"wall": "#D8F3DC", "floor": "#B08968", "trim": "#E6CCB2", "lines": "#9C7656",
                 "accent": "#C9A227", "accent2": "#7F5539", "art": "#2EC4B6"},
        "rose": {"wall": "#FFE5EC", "floor": "#A98467", "trim": "#EDE0D4", "lines": "#8C6A50",
                 "accent": "#B08D57", "accent2": "#6F4E37", "art": "#F15BB5"},
    }),
    "lab_bench": (lab_bench, {
        "clinic": {"wall": "#E0FBFC", "floor": "#9DB4C0", "trim": "#5C6B73", "lines": "#7D939E", "grid": "#C2E7EC",
                   "accent": "#EF476F", "accent2": "#FFFFFF"},
        "lilac": {"wall": "#EDE7F6", "floor": "#9A8FB5", "trim": "#5E548E", "lines": "#857AA6", "grid": "#D9CEF0",
                  "accent": "#EF476F", "accent2": "#FFFFFF"},
    }),
    "sound_lab": (sound_lab, {
        "ocean": {"wall": "#2B4C7E", "foam": "#3A63A0", "floor": "#567EBB", "trim": "#1B2F4F", "lines": "#466BA6",
                  "accent": "#4CC9F0", "accent2": "#1B1B3A"},
        "sunset": {"wall": "#7A3B69", "foam": "#93497F", "floor": "#B5838D", "trim": "#4A2040", "lines": "#A0717B",
                   "accent": "#FFD166", "accent2": "#2B2140"},
    }),
    "control_room": (control_room, {
        "night": {"wall": "#22305B", "panel": "#2E4172", "floor": "#4F5D75", "trim": "#16213E", "lines": "#5E6C86",
                  "accent": "#F72585"},
        "steel": {"wall": "#5C677D", "panel": "#7D8597", "floor": "#33415C", "trim": "#1E2A3D", "lines": "#44536E",
                  "accent": "#FFD166"},
    }),
    "blueprint": (blueprint, {
        "classic": {"wall": "#1D4E89", "grid": "#3A6EA5", "draw": "#E0F4FF", "floor": "#14365E", "trim": "#0D2647",
                    "lines": "#2A5A8F"},
        "teal": {"wall": "#0B6E79", "grid": "#2A8C96", "draw": "#E8FFFB", "floor": "#08525A", "trim": "#053A40",
                 "lines": "#1E7A84"},
    }),
    "test_track": (test_track, {
        "day": {"sky": ("#8ED1FC", "#B5E3FF", "#DDF3FF"), "sun": "#FFE66D", "hill": "#80B918", "fence": "#FFFFFF",
                "floor": "#6C757D", "trim": "#495057"},
        "dusk": {"sky": ("#F4A261", "#F6BD8A", "#FAD9B5"), "sun": "#FFF3B0", "hill": "#588157", "fence": "#FFF8E7",
                 "floor": "#5A5F66", "trim": "#3E4247"},
    }),
    "quiz_stage": (quiz_stage, {
        "gold": {"wall": "#6C4AB6", "ray": "#7B5CC4", "floor": "#2B2140", "trim": "#FFD166", "lines": "#3D3058",
                 "accent": "#F72585"},
        "aqua": {"wall": "#0081A7", "ray": "#0094BD", "floor": "#1B1B3A", "trim": "#FFD166", "lines": "#2B2B55",
                 "accent": "#FF8C42"},
    }),
}
THEME_NAMES = tuple(THEMES)
DEFAULT_THEME = "workshop"


def palettes(theme: str) -> tuple[str, ...]:
    return tuple(THEMES[theme][1])


@lru_cache(maxsize=32)
def backdrop(theme: str = DEFAULT_THEME, palette: str | None = None, variant: str = "default") -> VGroup:
    """The static background VGroup for a (theme, palette); ``variant`` only applies to the workshop."""
    if theme not in THEMES:
        raise ValueError(f"unknown background theme {theme!r}; choose from {THEME_NAMES}")
    fn, pals = THEMES[theme]
    palette = palette or next(iter(pals))
    if palette not in pals:
        raise ValueError(f"unknown palette {palette!r} for {theme}; choose from {tuple(pals)}")
    return fn(pals[palette], variant) if theme == "workshop" else fn(pals[palette])


def signature(theme: str, palette: str | None = None, w: int = 48, h: int = 27) -> np.ndarray:
    """Small RGB thumbnail of the drawn background (QA: adjacent sections must look different, not just be named
    differently)."""
    from robotics101.cartoon.render2d import frame_rgb
    return frame_rgb([backdrop(theme, palette)], w, h, "#000000")[..., :3].astype(np.float32)


def swatch(theme: str, palette: str | None = None) -> list[list[int]]:
    """Mean RGB of a 4x3 grid over the drawn background (12 colours) for the scenes.json record."""
    a = signature(theme, palette, 48, 27)
    cells = [a[r * 9:(r + 1) * 9, c * 12:(c + 1) * 12].reshape(-1, 3).mean(0) for r in range(3) for c in range(4)]
    return [[int(round(v)) for v in cell] for cell in cells]


def swatch_distance(a: list, b: list) -> float:
    """Mean absolute per-channel difference (0..255) between two swatches."""
    return float(np.abs(np.array(a, dtype=float) - np.array(b, dtype=float)).mean())


__all__ = ["DEFAULT_THEME", "swatch", "swatch_distance", "THEMES", "THEME_NAMES", "backdrop", "palettes", "signature"]
