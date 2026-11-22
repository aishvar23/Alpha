"""robot_intro: title card, then each example robot drawn from primitives with its label."""

from __future__ import annotations

from manim import DOWN, UP, FadeIn, FadeOut, GrowFromCenter, LaggedStart, VGroup, Write

from robotics101.animation.manim_templates._base import (
    ACCENT, BODY_SIZE, FG, LABEL_SIZE, MUTED, TemplateScene, content_box, wrapped_text,
)
from robotics101.animation.manim_templates._shapes import icon_for_example

DEFAULT_EXAMPLES = ["vacuum", "factory arm", "mobile rover"]


class RobotIntroScene(TemplateScene):
    TEMPLATE = "robot_intro"
    NOMINAL_SECONDS = 11.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        width = right - left
        examples = self.params.get("examples") or DEFAULT_EXAMPLES

        # -- title card
        ep_title = wrapped_text(self.job.get("episodeTitle") or "Robotics 101", width * 0.9, size=64,
                                color=FG, max_lines=2, weight="BOLD")
        series = wrapped_text(f"Robotics 101 · Episode {self.job.get('episodeNumber', '')}".strip(" ·"),
                              width * 0.9, size=BODY_SIZE, color=ACCENT, max_lines=1)
        card = VGroup(ep_title, series).arrange(DOWN, buff=0.4).move_to([0, (top + bottom) / 2, 0])
        self.anim(Write(ep_title), seconds=1.5)
        self.anim(FadeIn(series, shift=UP * 0.2), seconds=0.8)
        self.pause(1.7)
        self.anim(FadeOut(card), seconds=0.6)

        # -- examples row: icon above label, equal cells
        n = len(examples)
        cell = width / n
        icon_h = min(1.9, cell * 0.55)
        cells = []
        for i, name in enumerate(examples):
            icon = icon_for_example(name)
            icon.scale_to_fit_height(icon_h)
            if icon.width > cell * 0.8:
                icon.scale_to_fit_width(cell * 0.8)
            label = wrapped_text(name, cell * 0.88, size=BODY_SIZE, color=FG, max_lines=2)
            x = left + cell * (i + 0.5)
            icon.move_to([x, 0.55, 0])
            label.next_to(icon, DOWN, buff=0.35).set_x(x)
            # keep label tops aligned across cells
            label.align_to([0, 0.55 - icon_h / 2 - 0.35, 0], UP)
            cells.append(VGroup(icon, label))
        for c in cells:
            self.anim(GrowFromCenter(c[0]), FadeIn(c[1], shift=UP * 0.15), seconds=1.2)
            self.pause(0.5)

        tagline = wrapped_text("Robots come in many shapes — not just humanoids.", width, size=LABEL_SIZE + 2,
                               color=MUTED, max_lines=2)
        tagline.move_to([0, bottom + 0.55, 0])
        self.anim(LaggedStart(FadeIn(tagline, shift=UP * 0.2)), seconds=1.0)
