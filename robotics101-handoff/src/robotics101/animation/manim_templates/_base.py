"""Shared style, text layout and exact-duration timing for all Manim templates."""

from __future__ import annotations

import json
import os
from typing import Any

from manim import (
    DOWN,
    LEFT,
    ORIGIN,
    RIGHT,
    UP,
    Line,
    Scene,
    Text,
    VGroup,
    config,
)

from robotics101.animation.manim_templates import JOB_ENV
from robotics101.animation.timing import animation_speed, frames_for, target_frames
from robotics101.templates.registry import get_template

# ---------------------------------------------------------------- style
BG = "#101826"
FG = "#E8EEF6"
MUTED = "#9AA8BC"
ACCENT = "#4FC3F7"      # cyan: titles, sensor beams
GOOD = "#7BD88F"        # green: keep going / ok
WARN = "#FFB454"        # amber: highlights
ALERT = "#FF6B6B"       # red: detected / stop
METAL = "#7F8EA3"
PANEL = "#1C2738"
FONT = "Inter"

TITLE_SIZE = 40
BODY_SIZE = 30
LABEL_SIZE = 26
MIN_FONT_SIZE = 24      # manim font_size 24 ~= 42 px glyph box / 33 px cap height at 1080p

MARGIN = 0.45           # scene units kept clear at every frame edge (~60 px at 1080p)
TITLE_ZONE_BOTTOM = 2.75  # content must stay below this y


def frame_half_w() -> float:
    return config.frame_width / 2


def frame_half_h() -> float:
    return config.frame_height / 2


def content_box() -> tuple[float, float, float, float]:
    """(left, right, bottom, top) of the content area below the title."""
    return (-frame_half_w() + MARGIN, frame_half_w() - MARGIN, -frame_half_h() + MARGIN, TITLE_ZONE_BOTTOM)


def text(s: str, size: float = BODY_SIZE, color: str = FG, weight: str = "NORMAL") -> Text:
    """Single-line Text whose bounding box spans the font's full ascender..descender height.

    Invisible '|' strut glyphs at both ends give every text of the same size an identical
    vertical extent, so texts arranged in a row share a baseline ("range" vs "Measured").
    """
    t = Text(f"|{s}|", font=FONT, font_size=size, color=color, weight=weight)
    for strut in (t[0], t[-1]):
        strut.set_fill(opacity=0).set_stroke(opacity=0, width=0)
    return t


def wrapped_text(s: str, max_width: float, size: float = BODY_SIZE, color: str = FG,
                 max_lines: int = 3, align: str = "center", weight: str = "NORMAL",
                 line_gap: float = 0.12) -> VGroup:
    """Greedy word-wrap ``s`` into at most ``max_lines`` lines no wider than ``max_width``.

    If the text cannot fit, the font shrinks step-wise down to MIN_FONT_SIZE; at the
    minimum size the group is finally scaled to fit (and that is logged by the caller's
    frame check if it ever happens).
    """
    words = s.split()
    fs = size
    while True:
        lines: list[str] = []
        cur = ""
        for w in words:
            cand = f"{cur} {w}".strip()
            if cur and text(cand, fs).width > max_width:
                lines.append(cur)
                cur = w
            else:
                cur = cand
        if cur:
            lines.append(cur)
        too_wide = any(text(ln, fs).width > max_width for ln in lines)
        if (len(lines) <= max_lines and not too_wide) or fs <= MIN_FONT_SIZE:
            break
        fs = max(MIN_FONT_SIZE, fs - 2)
    group = VGroup(*[text(ln, fs, color, weight) for ln in lines])
    edge = {"center": ORIGIN, "left": LEFT}[align]
    group.arrange(DOWN, buff=line_gap, aligned_edge=edge)
    if group.width > max_width:
        group.scale_to_fit_width(max_width)
    return group


# ---------------------------------------------------------------- scene base
class TemplateScene(Scene):
    """Base class: loads the scene job, draws the title, runs ``build()``, pads to exact length.

    Templates script ``NOMINAL_SECONDS`` of animation using ``self.anim()`` / ``self.pause()``
    (which quantise every segment to whole frames). The pad hold after ``build()`` makes the
    clip exactly ``target_frames(duration, fps)`` frames long.
    """

    TEMPLATE = ""
    NOMINAL_SECONDS = 10.0

    def setup(self) -> None:
        job_path = os.environ.get(JOB_ENV)
        if not job_path:
            raise RuntimeError(f"{JOB_ENV} is not set; render via `robotics101 render-scenes`")
        with open(job_path, encoding="utf-8") as f:
            job = json.load(f)
        if job.get("template") != self.TEMPLATE:
            raise RuntimeError(f"job template {job.get('template')!r} != scene template {self.TEMPLATE!r}")
        spec = get_template("manim", self.TEMPLATE)
        errors = spec.validate_params(job["params"]) if spec else ["unknown template"]
        if errors:  # defence in depth: the host validated already
            raise RuntimeError(f"invalid parameters for {self.TEMPLATE}: {errors}")
        self.job: dict[str, Any] = job
        self.params: dict[str, Any] = job["params"]
        self.fps = int(round(config.frame_rate))
        self.duration_s = float(job["durationSeconds"])
        self.speed = animation_speed(self.duration_s, self.NOMINAL_SECONDS)
        self.camera.background_color = BG

    # -- frame-exact timing helpers
    def _frames_written(self) -> int:
        return int(round(self.renderer.time * self.fps))

    def anim(self, *animations, seconds: float = 1.0, **kwargs) -> None:
        """Play animations for ``seconds`` (scaled by ``self.speed``), quantised to whole frames."""
        n = frames_for(seconds * self.speed, self.fps)
        # np.arange(0, (n-0.5)/fps, 1/fps) yields exactly n frames
        self.play(*animations, run_time=(n - 0.5) / self.fps, **kwargs)

    def pause(self, seconds: float) -> None:
        """Static hold for ``seconds`` (scaled), quantised to whole frames (frozen frame)."""
        self._hold_frames(frames_for(seconds * self.speed, self.fps))

    def _hold_frames(self, n: int) -> None:
        if n > 0:
            # freeze_current_frame writes int(duration*fps) frames -> n exactly
            self.wait((n + 0.5) / self.fps, frozen_frame=True)

    def add_title(self) -> VGroup:
        title = wrapped_text(self.job.get("title", ""), max_width=config.frame_width - 2 * MARGIN,
                             size=TITLE_SIZE, color=ACCENT, max_lines=1, weight="BOLD")
        title.to_edge(UP, buff=MARGIN)
        rule = Line(LEFT * (frame_half_w() - MARGIN), RIGHT * (frame_half_w() - MARGIN),
                    color=MUTED, stroke_width=2).next_to(title, DOWN, buff=0.18)
        group = VGroup(title, rule)
        self.add(group)
        return group

    def build(self) -> None:  # pragma: no cover - implemented by templates
        raise NotImplementedError

    def construct(self) -> None:
        self.add_title()
        self.build()
        self._assert_in_frame()
        target = target_frames(self.duration_s, self.fps)
        written = self._frames_written()
        if written > target:
            raise RuntimeError(f"{self.TEMPLATE}: animation used {written} frames, more than the "
                               f"scheduled {target} ({self.duration_s}s @ {self.fps}fps)")
        self._hold_frames(target - written)
        final = self._frames_written()
        if final != target:
            raise RuntimeError(f"{self.TEMPLATE}: wrote {final} frames, expected {target}")

    def _assert_in_frame(self) -> None:
        hw, hh = frame_half_w() - 0.05, frame_half_h() - 0.05
        for m in self.mobjects:
            if m.width == 0 and m.height == 0:
                continue
            if m.get_left()[0] < -hw or m.get_right()[0] > hw or m.get_bottom()[1] < -hh or m.get_top()[1] > hh:
                raise RuntimeError(f"{self.TEMPLATE}: {type(m).__name__} extends outside the frame "
                                   f"(x {m.get_left()[0]:.2f}..{m.get_right()[0]:.2f}, "
                                   f"y {m.get_bottom()[1]:.2f}..{m.get_top()[1]:.2f})")

