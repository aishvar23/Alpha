"""recap_quiz: Sense / Decide / Act recap bullets, then the closing question."""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, Circle, FadeIn, RoundedRectangle, VGroup, Write

from robotics101.animation.manim_templates._base import (
    ACCENT, BG, BODY_SIZE, FG, GOOD, LABEL_SIZE, MUTED, PANEL, WARN, TemplateScene, content_box, text,
    wrapped_text,
)

RECAP = [
    ("Sense", "sensors measure the world around the robot", ACCENT),
    ("Decide", "the controller applies simple rules", WARN),
    ("Act", "actuators turn decisions into movement", GOOD),
]


class RecapQuizScene(TemplateScene):
    TEMPLATE = "recap_quiz"
    NOMINAL_SECONDS = 9.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        width = right - left

        heads = [text(h, BODY_SIZE + 4, c, "BOLD") for h, _, c in RECAP]
        head_w = max(h.width for h in heads)
        body_w = width - 0.64 - 0.35 - head_w - 0.4
        rows = VGroup()
        for i, ((_, body, color), head_t) in enumerate(zip(RECAP, heads), start=1):
            badge = VGroup(Circle(0.32, color=color, fill_color=BG, fill_opacity=1, stroke_width=4),
                           text(str(i), BODY_SIZE, color, "BOLD"))
            body_t = wrapped_text(body, body_w, size=BODY_SIZE, color=FG, max_lines=1, align="left")
            # fixed columns: badge | head | body
            head_t.next_to(badge, RIGHT, buff=0.35)
            body_t.move_to(head_t, aligned_edge=LEFT).shift(RIGHT * (head_w + 0.4))
            body_t.align_to(head_t, DOWN)
            rows.add(VGroup(badge, head_t, body_t))
        rows.arrange(DOWN, buff=0.38, aligned_edge=LEFT)
        rows.move_to([0, top - 0.25 - rows.height / 2, 0])
        for r in rows:
            self.anim(FadeIn(r, shift=RIGHT * 0.3), seconds=0.9)
            self.pause(0.4)

        q_area_top = rows.get_bottom()[1] - 0.45
        heading = text("Quick question", LABEL_SIZE + 2, ACCENT, "BOLD")
        question = wrapped_text(self.params["question"], width - 1.2, size=BODY_SIZE + 4, color=FG, max_lines=3)
        inner = VGroup(heading, question).arrange(DOWN, buff=0.3)
        panel = RoundedRectangle(width=width, height=min(inner.height + 0.7, q_area_top - bottom),
                                 corner_radius=0.2, color=ACCENT, stroke_width=3, fill_color=PANEL, fill_opacity=1)
        if inner.height > panel.height - 0.3:
            inner.scale_to_fit_height(panel.height - 0.3)
        panel.move_to([0, q_area_top - panel.height / 2, 0])
        inner.move_to(panel)
        self.anim(FadeIn(panel), FadeIn(heading, shift=DOWN * 0.1), seconds=0.8)
        self.anim(Write(question), seconds=1.6)
        hint = text("Pause the video and answer before the next episode!", LABEL_SIZE, MUTED)
        if hint.width > width:
            hint.scale_to_fit_width(width)
        hint.move_to([0, bottom + 0.2, 0])
        if hint.get_top()[1] < panel.get_bottom()[1] - 0.1:
            self.anim(FadeIn(hint, shift=UP * 0.15), seconds=0.8)
