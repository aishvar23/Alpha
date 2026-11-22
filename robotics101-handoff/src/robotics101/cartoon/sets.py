"""Sets (M02.5): backgrounds drawn in code, one static VGroup per set, built once per scene render.

Stage conventions shared with the scene engine: frame is 14.22 x 8 units centred on 0; characters stand on
``GROUND`` (their feet); the floor line sits slightly above it so characters read as standing *on* the floor.
Distances in teaching demos use ``METER`` screen units per metre.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, Circle, Line, Polygon, Rectangle, RoundedRectangle, Text, VGroup

from robotics101.cartoon.rigs import style

GROUND = -2.55
FLOOR_Y = GROUND + 0.5
METER = 2.2
WALL, WALL_STRIPE, FLOOR = "#FFE8C2", "#FFDDA8", "#B5838D"


def ink() -> str:
    return style("bolt").ink


def _o(m, w=6):
    return m.set_stroke(ink(), w)


@lru_cache(maxsize=8)
def garage(variant: str = "default") -> VGroup:
    """The garage workshop. ``variant`` hides pieces that a scene replaces with props (e.g. 'no_shelf')."""
    wall = Rectangle(width=14.4, height=8.2, fill_color=WALL, fill_opacity=1, stroke_width=0)
    stripes = VGroup(*[Rectangle(width=0.6, height=8.2, fill_color=WALL_STRIPE, fill_opacity=1, stroke_width=0)
                       .shift(RIGHT * x) for x in np.arange(-7.5, 8, 1.2)])
    floor = Rectangle(width=14.4, height=4.1 + FLOOR_Y, fill_color=FLOOR, fill_opacity=1, stroke_width=0)
    floor.move_to(np.array([0, (-4.1 + FLOOR_Y) / 2, 0]))
    boards = VGroup(*[Line(np.array([x, FLOOR_Y, 0]), np.array([x * 1.6, -4.1, 0]), stroke_width=2,
                           color="#A0717B") for x in np.arange(-6, 7, 2.0)])
    floor_line = Line(LEFT * 7.2, RIGHT * 7.2, stroke_width=8, color=ink()).shift(UP * FLOOR_Y)
    skirting = Rectangle(width=14.4, height=0.18, fill_color="#E9C46A", fill_opacity=1, stroke_width=0) \
        .move_to(np.array([0, FLOOR_Y + 0.09, 0]))
    parts = [wall, stripes, floor, boards, skirting, floor_line]
    window = _o(RoundedRectangle(width=2.6, height=1.9, corner_radius=0.2, fill_color="#9BF6FF", fill_opacity=1)) \
        .move_to(np.array([-4.9, 2.35, 0]))
    sun = Circle(0.38, fill_color="#FFE66D", fill_opacity=1, stroke_width=0) \
        .move_to(window.get_center() + np.array([0.55, 0.3, 0]))
    cloud = VGroup(*[Circle(r, fill_color="#FFFFFF", fill_opacity=1, stroke_width=0).move_to(
        window.get_center() + np.array([x, y, 0])) for x, y, r in ((-0.6, -0.35, 0.22), (-0.35, -0.3, 0.28),
                                                                    (-0.08, -0.38, 0.2))])
    cross = VGroup(Line(window.get_top(), window.get_bottom()), Line(window.get_left(), window.get_right())) \
        .set_stroke(ink(), 6)
    parts += [window, sun, cloud, cross]
    if variant != "no_shelf":
        shelf = _o(Rectangle(width=3.2, height=0.18, fill_color="#8D5524", fill_opacity=1), 4) \
            .move_to(np.array([4.6, 1.55, 0]))
        jars = VGroup(*[_o(RoundedRectangle(width=0.5, height=h, corner_radius=0.1, fill_color=c, fill_opacity=1), 4)
                        .next_to(shelf, UP, buff=0).shift(RIGHT * x)
                        for x, h, c in ((-1.1, 0.7, "#06D6A0"), (-0.4, 0.5, "#EF476F"), (0.4, 0.9, "#118AB2"),
                                        (1.1, 0.6, "#FFD166"))])
        parts += [shelf, jars]
    pegboard = _o(RoundedRectangle(width=2.4, height=1.5, corner_radius=0.1, fill_color="#DDB892", fill_opacity=1),
                  4).move_to(np.array([-1.4, 2.5, 0]))
    holes = VGroup(*[Circle(0.04, fill_color="#9C6644", fill_opacity=1, stroke_width=0).move_to(
        pegboard.get_center() + np.array([x, y, 0])) for x in np.linspace(-1.0, 1.0, 7) for y in (-0.5, 0, 0.5)])
    wrench = VGroup(Line(np.array([-0.3, -0.3, 0]), np.array([0.3, 0.3, 0]), stroke_width=10, color="#8D99AE"),
                    Circle(0.12, stroke_color="#8D99AE", stroke_width=8).move_to(np.array([0.36, 0.36, 0]))) \
        .move_to(pegboard.get_center() + LEFT * 0.5)
    hammer = VGroup(Line(np.array([0, -0.35, 0]), np.array([0, 0.25, 0]), stroke_width=9, color="#9C6644"),
                    _o(Rectangle(width=0.45, height=0.16, fill_color="#8D99AE", fill_opacity=1), 3)
                    .move_to(np.array([0, 0.3, 0]))).move_to(pegboard.get_center() + RIGHT * 0.5)
    if variant != "no_pegboard":
        parts += [pegboard, holes, wrench, hammer]
    socket = _o(RoundedRectangle(width=0.35, height=0.5, corner_radius=0.06, fill_color="#FFFFFF", fill_opacity=1),
                3).move_to(np.array([-6.5, FLOOR_Y + 0.8, 0]))
    socket.add(*[Line(socket.get_center() + np.array([x, 0.1, 0]), socket.get_center() + np.array([x, -0.05, 0]),
                      stroke_width=4, color=ink()) for x in (-0.07, 0.07)])
    parts.append(socket)
    return VGroup(*parts)


SOCKET_POS = np.array([-6.5, FLOOR_Y + 0.8, 0])


def door(x: float = -3.0) -> VGroup:
    """Side door in the back wall (scene 7's victory-spin bonk)."""
    frame = _o(Rectangle(width=1.7, height=3.4, fill_color="#9C6644", fill_opacity=1), 6)
    frame.move_to(np.array([x, FLOOR_Y + 1.7, 0]))
    panel = VGroup(*[_o(RoundedRectangle(width=1.1, height=1.2, corner_radius=0.08, fill_color="#B07D56",
                                         fill_opacity=1), 3).move_to(frame.get_center() + UP * y) for y in (0.8, -0.7)])
    knob = Circle(0.09, fill_color="#FFD166", fill_opacity=1, stroke_color=ink(), stroke_width=3) \
        .move_to(frame.get_center() + RIGHT * 0.55 + DOWN * 0.1)
    return VGroup(frame, panel, knob)
