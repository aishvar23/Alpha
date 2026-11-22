"""robot_anatomy: a primitive robot drawing; each requested part is highlighted and labelled in turn."""

from __future__ import annotations

from manim import DOWN, LEFT, RIGHT, UP, Arrow, Create, FadeIn, Indicate, VGroup

from robotics101.animation.manim_templates._base import (
    BODY_SIZE, FG, WARN, TemplateScene, content_box, wrapped_text,
)
from robotics101.animation.manim_templates._shapes import ANATOMY_ALIASES, anatomy_robot


class RobotAnatomyScene(TemplateScene):
    TEMPLATE = "robot_anatomy"
    NOMINAL_SECONDS = 14.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        parts: list[str] = self.params["parts"]

        robot = anatomy_robot()
        robot.scale_to_fit_height(min(3.6, (top - bottom) * 0.62))
        robot.move_to([0, (top + bottom) / 2 - 0.1, 0])
        self.anim(Create(robot), seconds=2.0)

        col_w = (right - left) / 2 - robot.width / 2 - 0.5
        # Generic anchors for unknown part names: spread along the robot outline.
        generic = [robot.get_corner(UP + LEFT), robot.get_corner(UP + RIGHT), robot.get_corner(DOWN + LEFT),
                   robot.get_corner(DOWN + RIGHT), robot.get_left(), robot.get_right(), robot.get_top(), robot.get_bottom()]
        resolved = []
        for i, name in enumerate(parts):
            canon = ANATOMY_ALIASES.get(name.strip().lower())
            if canon:
                target, anchor, direction = robot.anchors[canon]
                point = anchor.get_critical_point(direction)
            else:
                target, point = None, generic[i % len(generic)]
            resolved.append((name, target, point))
        # Each label goes on the side of its anchor; within a column, slots follow anchor height so
        # arrows don't cross. Balance columns if one side would get more than half (rounded up).
        cx = robot.get_center()[0]
        order = sorted(range(len(parts)), key=lambda i: resolved[i][2][0])
        n_left = sum(1 for _, _, p in resolved if p[0] < cx)
        n_left = min(max(n_left, len(parts) // 2), (len(parts) + 1) // 2)
        side_of = {i: (k < n_left) for k, i in enumerate(order)}
        slot_of = {}
        for side in (True, False):
            members = sorted([i for i in range(len(parts)) if side_of[i] == side], key=lambda i: -resolved[i][2][1])
            n = len(members)
            for k, i in enumerate(members):
                slot_of[i] = top - 0.5 - k * ((top - bottom - 1.0) / max(n - 1, 1)) if n > 1 else (top + bottom) / 2

        per_part = 12.0 / len(parts)
        for i, (name, target, point) in enumerate(resolved):
            side_left = side_of[i]
            y = slot_of[i]
            label = wrapped_text(name.capitalize(), col_w, size=BODY_SIZE, color=FG, max_lines=2)
            if side_left:
                label.move_to([left + label.width / 2 + 0.1, y, 0])
                start = label.get_right() + RIGHT * 0.15
            else:
                label.move_to([right - label.width / 2 - 0.1, y, 0])
                start = label.get_left() + LEFT * 0.15
            arrow = Arrow(start, point, buff=0.08, color=WARN, stroke_width=4,
                          max_tip_length_to_length_ratio=0.12)
            anims = [FadeIn(label, shift=(RIGHT if side_left else LEFT) * 0.2), Create(arrow)]
            if target is not None:
                anims.append(Indicate(target, color=WARN, scale_factor=1.08))
            self.anim(*anims, seconds=per_part * 0.6)
            self.pause(per_part * 0.4)
