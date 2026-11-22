"""sense_think_act: Sense -> Think -> Act loop, the threshold rule, and a reading crossing the threshold."""

from __future__ import annotations

import math

from manim import (
    DOWN, RIGHT, UP, Arrow, CurvedArrow, Create, FadeIn, Indicate, Line, RoundedRectangle, Triangle, ValueTracker,
    VGroup, Write, always_redraw,
)

from robotics101.animation.manim_templates._base import (
    ACCENT, ALERT, BODY_SIZE, FG, GOOD, LABEL_SIZE, MUTED, PANEL, WARN, TemplateScene, content_box, text,
    wrapped_text,
)
from robotics101.animation.manim_templates._widgets import fmt_m
from robotics101.geometry import STOP_AND_TURN, reading_sweep, threshold_decision


STAGES = [("Sense", "read distance", ACCENT), ("Think", "apply the rule", WARN), ("Act", "drive the motors", GOOD)]
DECISION_TEXT = {STOP_AND_TURN: "STOP & TURN", "KEEP_GOING": "KEEP GOING"}


class SenseThinkActScene(TemplateScene):
    TEMPLATE = "sense_think_act"
    NOMINAL_SECONDS = 13.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        thr = float(self.params["thresholdMeters"])
        start, end = reading_sweep(thr)

        # -- loop boxes
        boxes = VGroup()
        for name, sub, color in STAGES:
            r = RoundedRectangle(width=3.0, height=1.25, corner_radius=0.18, color=color, stroke_width=4,
                                 fill_color=PANEL, fill_opacity=1)
            lbl = VGroup(text(name, BODY_SIZE + 4, color, "BOLD"), text(sub, LABEL_SIZE, MUTED)).arrange(DOWN, buff=0.1)
            lbl.move_to(r)
            boxes.add(VGroup(r, lbl))
        boxes.arrange(RIGHT, buff=1.1).move_to([0, top - 1.05, 0])
        arrows = VGroup(*[Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), buff=0.1, color=FG, stroke_width=5)
                          for i in range(2)])
        loop = CurvedArrow(boxes[2].get_bottom() + DOWN * 0.05, boxes[0].get_bottom() + DOWN * 0.05,
                           angle=-0.55, color=MUTED, stroke_width=4)
        for i in range(3):
            self.anim(FadeIn(boxes[i], shift=UP * 0.2), *( [Create(arrows[i - 1])] if i else [] ), seconds=0.8)
        self.anim(Create(loop), seconds=0.8)

        # -- the rule
        rule = text(f"if distance < {fmt_m(thr)}:  stop & turn", BODY_SIZE + 2, FG)
        rule.move_to([0, loop.get_bottom()[1] - 0.45, 0])
        self.anim(Write(rule), seconds=1.2)

        # -- reading on a scale with the threshold marked
        line_y = rule.get_bottom()[1] - 0.85
        x0, x1 = left + 1.0, right - 1.0
        vmax = math.ceil(start * 1.1 / 0.5) * 0.5   # round scale end (e.g. 2.0 m) so it can be labelled

        def vx(v: float) -> float:
            return x0 + (x1 - x0) * v / vmax

        scale = Line([x0, line_y, 0], [x1, line_y, 0], color=MUTED, stroke_width=4)
        zero = text("0 m", LABEL_SIZE, MUTED).next_to(scale.get_start(), DOWN, buff=0.15)
        end_lbl = text(fmt_m(vmax), LABEL_SIZE, MUTED).next_to(scale.get_end(), DOWN, buff=0.15)
        thr_tick = Line([vx(thr), line_y + 0.35, 0], [vx(thr), line_y - 0.35, 0], color=ALERT, stroke_width=5)
        thr_lbl = text(f"threshold {fmt_m(thr)}", LABEL_SIZE, ALERT).next_to(thr_tick, DOWN, buff=0.1)
        if thr_lbl.get_left()[0] < zero.get_right()[0] + 0.2:
            thr_lbl.next_to(zero, RIGHT, buff=0.3)
        danger = Line([x0, line_y, 0], [vx(thr), line_y, 0], color=ALERT, stroke_width=8)
        self.anim(Create(scale), FadeIn(zero), FadeIn(end_lbl), Create(danger), Create(thr_tick), FadeIn(thr_lbl), seconds=1.0)

        reading = ValueTracker(start)

        def marker():
            v = reading.get_value()
            tri = Triangle(color=FG, fill_color=FG, fill_opacity=1).scale(0.14).rotate(3.14159265)
            tri.move_to([vx(v), line_y + 0.3, 0])
            return tri

        def readout():
            v = reading.get_value()
            d = threshold_decision(v, thr)
            col = ALERT if d == STOP_AND_TURN else GOOD
            g = VGroup(text(f"distance = {fmt_m(v)}", BODY_SIZE, FG),
                       text("→", BODY_SIZE, MUTED),
                       text(DECISION_TEXT[d], BODY_SIZE + 2, col, "BOLD")).arrange(RIGHT, buff=0.35)
            return g.move_to([0, bottom + 0.4, 0])

        mk, ro = always_redraw(marker), always_redraw(readout)
        self.anim(FadeIn(mk), FadeIn(ro), seconds=0.6)
        self.pause(0.8)
        mid = (start + thr) / 2
        self.anim(reading.animate.set_value(mid), Indicate(boxes[0], color=ACCENT, scale_factor=1.05), seconds=2.0)
        self.anim(reading.animate.set_value(end), Indicate(boxes[1], color=WARN, scale_factor=1.05), seconds=2.0)
        self.anim(Indicate(boxes[2], color=ALERT, scale_factor=1.08), Indicate(rule, color=ALERT), seconds=1.2)
        # freeze final state as static mobjects so holds don't re-run updaters
        mk.clear_updaters()
        ro.clear_updaters()
