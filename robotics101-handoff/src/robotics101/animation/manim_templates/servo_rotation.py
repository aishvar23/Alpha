"""servo_rotation: servo body with a horn/arm rotating from startAngleDegrees to endAngleDegrees.

Angle convention (see robotics101.geometry): 0 deg = arm pointing right, 90 deg = up, 180 deg = left.
The arm tip is computed by ``servo_arm_endpoint`` every frame, so the drawing matches the angles exactly.
"""

from __future__ import annotations

import math

from manim import (
    DEGREES, DOWN, LEFT, RIGHT, UP, Arc, Circle, Create, DashedLine, Dot, FadeIn, Line, RoundedRectangle,
    ValueTracker, VGroup, Write, always_redraw,
)

from robotics101.animation.manim_templates._base import (
    ACCENT, BG, BODY_SIZE, FG, GOOD, LABEL_SIZE, METAL, MUTED, PANEL, WARN, TemplateScene, content_box, text,
)
from robotics101.geometry import servo_arm_endpoint

ARM_LEN = 2.5
ARC_R = 0.95
SCALE_R = 2.95


def fmt_deg(a: float) -> str:
    return f"{a:.0f}°" if abs(a - round(a)) < 0.05 else f"{a:.1f}°"


class ServoRotationScene(TemplateScene):
    TEMPLATE = "servo_rotation"
    NOMINAL_SECONDS = 10.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        a0 = float(self.params["startAngleDegrees"])
        a1 = float(self.params["endAngleDegrees"])
        pivot = (-1.6, bottom + 1.55)
        P = [pivot[0], pivot[1], 0]

        def pt(angle: float, r: float):
            x, y = servo_arm_endpoint(angle, r, pivot)
            return [x, y, 0]

        body = RoundedRectangle(width=2.2, height=1.2, corner_radius=0.1, color=METAL, stroke_width=3,
                                fill_color=PANEL, fill_opacity=1).move_to([pivot[0], pivot[1] - 0.75, 0])
        tabs = VGroup(*[RoundedRectangle(width=0.45, height=0.25, corner_radius=0.04, color=METAL, stroke_width=3,
                                         fill_color=PANEL, fill_opacity=1).next_to(body, side, buff=0).shift(UP * 0.3)
                        for side in (LEFT, RIGHT)])
        servo_lbl = text("servo", LABEL_SIZE, MUTED).move_to(body)
        self.anim(FadeIn(body), FadeIn(tabs), FadeIn(servo_lbl), seconds=1.0)

        # protractor scale: semicircle with ticks every 15 deg, labels every 45 deg
        scale = Arc(radius=SCALE_R, start_angle=0, angle=math.pi, arc_center=P, color=MUTED, stroke_width=2)
        ticks, labels = VGroup(), VGroup()
        for a in range(0, 181, 15):
            ticks.add(Line(pt(a, SCALE_R - (0.18 if a % 45 else 0.3)), pt(a, SCALE_R), color=MUTED, stroke_width=2))
            if a % 45 == 0:
                labels.add(text(f"{a}°", LABEL_SIZE, MUTED).move_to(pt(a, SCALE_R + 0.42)))
        self.anim(Create(scale), Create(ticks), FadeIn(labels), seconds=1.2)

        start_ref = DashedLine(P, pt(a0, ARM_LEN), color=MUTED, stroke_width=3)
        target_ref = DashedLine(P, pt(a1, ARM_LEN + 0.25), color=WARN, stroke_width=3)
        angle = ValueTracker(a0)

        def arm():
            a = angle.get_value()
            tip = pt(a, ARM_LEN)
            bar = Line(P, tip, color=FG, stroke_width=14)
            end = Dot(tip, radius=0.11, color=FG)
            return VGroup(bar, end)

        def sweep():
            a = angle.get_value()
            if abs(a - a0) < 1e-6:
                return VGroup()
            return Arc(radius=ARC_R, start_angle=a0 * DEGREES, angle=(a - a0) * DEGREES, arc_center=P,
                       color=ACCENT, stroke_width=6)

        def readout():
            a = angle.get_value()
            g = VGroup(text("angle", LABEL_SIZE, MUTED), text(fmt_deg(a), 56, ACCENT, "BOLD")).arrange(DOWN, buff=0.15)
            return g.move_to([right - 2.0, (top + bottom) / 2 + 0.6, 0])

        horn = VGroup(Circle(0.32, color=WARN, fill_color=BG, fill_opacity=1, stroke_width=4).move_to(P),
                      Dot(P, radius=0.08, color=WARN))
        arm_m, sweep_m, ro = always_redraw(arm), always_redraw(sweep), always_redraw(readout)
        self.add(sweep_m)
        self.anim(Create(start_ref), FadeIn(arm_m), FadeIn(horn), FadeIn(ro), seconds=1.0)
        self.bring_to_front(horn)

        info = VGroup(text(f"start: {fmt_deg(a0)}", BODY_SIZE, MUTED),
                      text(f"target: {fmt_deg(a1)}", BODY_SIZE, WARN)).arrange(DOWN, buff=0.2, aligned_edge=LEFT)
        info.move_to([right - 2.0, (top + bottom) / 2 - 1.2, 0])
        self.anim(Create(target_ref), Write(info), seconds=1.2)
        self.bring_to_front(arm_m, horn)
        self.pause(0.6)
        self.anim(angle.animate.set_value(a1), seconds=3.0)
        reached = text("target reached", BODY_SIZE, GOOD).next_to(info, DOWN, buff=0.35).align_to(info, LEFT)
        self.anim(FadeIn(reached, shift=UP * 0.15), seconds=0.8)
        for m in (arm_m, sweep_m, ro):
            m.clear_updaters()
        self.final_angle = angle.get_value()
