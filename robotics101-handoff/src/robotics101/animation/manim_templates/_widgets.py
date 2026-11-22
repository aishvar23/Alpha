"""Small LaTeX-free widgets (manim's NumberLine/DecimalNumber need LaTeX, so we draw our own)."""

from __future__ import annotations

from manim import DOWN, Line, VGroup

from robotics101.animation.manim_templates._base import LABEL_SIZE, MUTED, text


def fmt_m(x: float) -> str:
    """Metres with 1-2 decimals: 3 -> '3.0 m', 1.25 -> '1.25 m'."""
    s = f"{x:.2f}".rstrip("0")
    if s.endswith("."):
        s += "0"
    return f"{s} m"


def ruler(x0: float, x1: float, y: float, max_value: float, step: float, color: str = MUTED,
          label_every: int = 1) -> VGroup:
    """Horizontal axis from x0 (value 0) to x1 (value max_value) with ticks every ``step`` and Text labels."""
    axis = Line([x0, y, 0], [x1, y, 0], color=color, stroke_width=3)
    ticks, labels = VGroup(), VGroup()
    n = int(round(max_value / step + 1e-9))
    for i in range(n + 1):
        v = min(i * step, max_value)
        x = x0 + (x1 - x0) * v / max_value
        ticks.add(Line([x, y + 0.12, 0], [x, y - 0.12, 0], color=color, stroke_width=3))
        if i % label_every == 0 or i == n:
            labels.add(text(fmt_m(v), LABEL_SIZE, color).next_to([x, y - 0.12, 0], DOWN, buff=0.12))
    return VGroup(axis, ticks, labels)
