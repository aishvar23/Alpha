"""Primitive-geometry robot drawings shared by templates (no external assets).

Every function returns a VGroup roughly 2 units tall centred on the origin; callers
scale/position it. Named sub-parts are attached as attributes where templates need them.
"""

from __future__ import annotations

from manim import (
    DOWN,
    LEFT,
    RIGHT,
    UP,
    Circle,
    Dot,
    Line,
    Polygon,
    Rectangle,
    RoundedRectangle,
    VGroup,
)

from robotics101.animation.manim_templates._base import ACCENT, BG, FG, GOOD, METAL, MUTED, PANEL, WARN


def _box(w, h, color=METAL, fill=PANEL, r=0.12, sw=3):
    return RoundedRectangle(width=w, height=h, corner_radius=r, color=color, stroke_width=sw,
                            fill_color=fill, fill_opacity=1)


def vacuum_robot() -> VGroup:
    """Robot vacuum seen from the side: low puck body, bumper sensor, wheels."""
    body = _box(2.4, 0.7, r=0.3)
    top = _box(1.0, 0.18, color=ACCENT, fill=ACCENT, r=0.08).next_to(body, UP, buff=0)
    bumper = Line(body.get_corner(UP + RIGHT) + DOWN * 0.15, body.get_corner(DOWN + RIGHT) + UP * 0.15,
                  color=ACCENT, stroke_width=6).shift(RIGHT * 0.06)
    w1 = Circle(0.2, color=FG, fill_color=BG, fill_opacity=1, stroke_width=3).move_to(body.get_bottom() + LEFT * 0.7)
    w2 = w1.copy().move_to(body.get_bottom() + RIGHT * 0.7)
    brush = Line(LEFT * 0.35, RIGHT * 0.35, color=WARN, stroke_width=5).next_to(body, DOWN, buff=0.04)
    return VGroup(body, top, bumper, w1, w2, brush).move_to([0, 0, 0])


def factory_arm() -> VGroup:
    """Industrial arm: base, two links, gripper."""
    base = _box(1.4, 0.35, r=0.06).shift(DOWN * 1.0)
    j0 = Dot(base.get_top() + UP * 0.1, radius=0.14, color=WARN)
    elbow = j0.get_center() + [0.55, 1.05, 0]
    wrist = elbow + [0.95, -0.25, 0]
    l1 = Line(j0.get_center(), elbow, color=METAL, stroke_width=16)
    l2 = Line(elbow, wrist, color=METAL, stroke_width=12)
    j1 = Dot(elbow, radius=0.13, color=WARN)
    j2 = Dot(wrist, radius=0.1, color=WARN)
    g1 = Line(wrist, wrist + [0.3, 0.18, 0], color=FG, stroke_width=6)
    g2 = Line(wrist, wrist + [0.3, -0.18, 0], color=FG, stroke_width=6)
    return VGroup(base, l1, l2, j0, j1, j2, g1, g2).move_to([0, 0, 0])


def mobile_rover() -> VGroup:
    """Four-wheeled rover with mast and sensor head."""
    body = _box(2.0, 0.7, r=0.1)
    wheels = VGroup(*[Circle(0.28, color=FG, fill_color=BG, fill_opacity=1, stroke_width=3)
                      .move_to(body.get_bottom() + RIGHT * x) for x in (-0.7, 0.0, 0.7)])
    mast = Line(body.get_top() + LEFT * 0.4, body.get_top() + LEFT * 0.4 + UP * 0.6, color=METAL, stroke_width=6)
    head = _box(0.6, 0.3, color=ACCENT, r=0.06).move_to(mast.get_end() + UP * 0.1)
    eye = Dot(head.get_right() + LEFT * 0.12, radius=0.06, color=ACCENT)
    antenna = Line(body.get_top() + RIGHT * 0.6, body.get_top() + RIGHT * 0.75 + UP * 0.45, color=MUTED, stroke_width=3)
    return VGroup(body, wheels, mast, head, eye, antenna).move_to([0, 0, 0])


def generic_robot() -> VGroup:
    """Fallback icon for example names without a dedicated drawing."""
    body = _box(1.1, 1.0)
    head = _box(0.8, 0.55, color=ACCENT).next_to(body, UP, buff=0.08)
    eyes = VGroup(Dot(radius=0.07, color=ACCENT), Dot(radius=0.07, color=ACCENT)).arrange(RIGHT, buff=0.25).move_to(head)
    legs = VGroup(*[Line(UP * 0, DOWN * 0.4, color=METAL, stroke_width=8).move_to(body.get_bottom() + RIGHT * x + DOWN * 0.2)
                    for x in (-0.3, 0.3)])
    return VGroup(body, head, eyes, legs).move_to([0, 0, 0])


def icon_for_example(name: str) -> VGroup:
    key = name.lower()
    if "vacuum" in key or "clean" in key:
        return vacuum_robot()
    if "arm" in key or "factory" in key or "industrial" in key:
        return factory_arm()
    if "rover" in key or "mobile" in key or "car" in key or "drone" in key:
        return mobile_rover()
    return generic_robot()


def anatomy_robot() -> VGroup:
    """Simple mobile robot used by robot_anatomy, with anchor points for each part.

    Attribute ``anchors`` maps a canonical part name to (highlight mobject, anchor mobject, direction).
    """
    chassis = _box(3.0, 1.6, r=0.15)
    battery = _box(0.9, 0.5, color=GOOD, fill=BG, r=0.05).move_to(chassis.get_center() + LEFT * 0.75 + DOWN * 0.3)
    batt_tip = Rectangle(width=0.08, height=0.2, color=GOOD, fill_color=GOOD, fill_opacity=1).next_to(battery, RIGHT, buff=0)
    plus = Line(LEFT * 0.1, RIGHT * 0.1, color=GOOD, stroke_width=4).move_to(battery)
    plus_v = Line(DOWN * 0.1, UP * 0.1, color=GOOD, stroke_width=4).move_to(battery)
    chip = _box(0.7, 0.55, color=WARN, fill=BG, r=0.04).move_to(chassis.get_center() + RIGHT * 0.7 + UP * 0.25)
    pins = VGroup(*[Line(UP * 0, DOWN * 0.12, color=WARN, stroke_width=3).move_to(chip.get_bottom() + RIGHT * x + DOWN * 0.06)
                    for x in (-0.2, 0.0, 0.2)])
    wheels = VGroup(*[Circle(0.42, color=FG, fill_color=BG, fill_opacity=1, stroke_width=4)
                      .move_to(chassis.get_bottom() + RIGHT * x) for x in (-1.0, 1.0)])
    hubs = VGroup(*[Dot(w.get_center(), radius=0.08, color=METAL) for w in wheels])
    mast = Line(chassis.get_top() + RIGHT * 0.9, chassis.get_top() + RIGHT * 0.9 + UP * 0.5, color=METAL, stroke_width=6)
    sensor = _box(0.7, 0.36, color=ACCENT, r=0.08).move_to(mast.get_end() + UP * 0.12)
    lenses = VGroup(Dot(radius=0.07, color=ACCENT), Dot(radius=0.07, color=ACCENT)).arrange(RIGHT, buff=0.18).move_to(sensor)
    beam = Polygon(sensor.get_right(), sensor.get_right() + [0.8, 0.25, 0], sensor.get_right() + [0.8, -0.25, 0],
                   color=ACCENT, stroke_width=0, fill_color=ACCENT, fill_opacity=0.25)
    robot = VGroup(chassis, battery, batt_tip, plus, plus_v, chip, pins, wheels, hubs, mast, sensor, lenses, beam)
    # (mobject to highlight, mobject whose critical point the arrow targets, direction).
    # Points are resolved at use time so they stay correct after the robot is scaled/moved.
    robot.anchors = {
        "structure": (chassis, chassis, UP + LEFT),
        "sensors": (VGroup(sensor, lenses, beam), sensor, UP),
        "actuators": (VGroup(wheels, hubs), wheels[0], LEFT),
        "power": (VGroup(battery, batt_tip, plus, plus_v), battery, LEFT),
        "controller": (VGroup(chip, pins), chip, RIGHT),
    }
    return robot


ANATOMY_ALIASES = {
    "structure": "structure", "body": "structure", "chassis": "structure", "frame": "structure",
    "sensors": "sensors", "sensor": "sensors", "camera": "sensors",
    "actuators": "actuators", "actuator": "actuators", "motors": "actuators", "wheels": "actuators",
    "power": "power", "battery": "power", "power source": "power",
    "controller": "controller", "brain": "controller", "computer": "controller", "microcontroller": "controller",
}
