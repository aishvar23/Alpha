"""Cartoon thumbnail (M02.8): a staged 1280x720 key art frame drawn with the rigs (not a grabbed video frame).

Bolt mid-bonk against the box pile with stars, Maya laughing, Nib hovering, the series logo and the episode
title. Deterministic (same inputs -> same PNG).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from manim import VGroup
from PIL import Image

from robotics101.cartoon import props as PR
from robotics101.cartoon.render2d import frame_rgb
from robotics101.cartoon.rigs import Pose, build
from robotics101.cartoon.sets import GROUND, garage

W, H = 1280, 720


def thumbnail_mobjects(title: str) -> list:
    def place(cid, pose, x, y=0.0, k=1.0):
        return build(cid, pose).scale(k, about_point=np.zeros(3)).shift(np.array([x, GROUND + y, 0]))
    bolt = place("bolt", Pose(expression="dizzy", facing=1, lean=-0.18, arm_l=70, arm_r=110, extras=("stars",)), 0.9,
                 k=0.92)
    maya = place("maya", Pose(expression="laugh", facing=1, arm_r=150, arm_l=40), -5.3, k=0.85)
    nib = place("nib", Pose(expression="surprised", facing=-1, arm_l=90, prop=0.8), 5.15, PR.PILE_H - 0.02, k=1.15)
    pile = PR.box_pile(5.0)
    bonk = PR.sfx_text("BONK!", "#EF476F", 0.5, PR.P(3.1, 0.75), angle=0.2, size=120)
    logo = PR.txt("ROBOTICS 101", 96, color="#FF6B9A", font="Luckiest Guy", weight="NORMAL", stroke=7)
    logo.move_to(PR.P(0, 3.3))
    sub = PR.txt(title, 54)
    if sub.width > 11.5:
        sub = PR.wrap(title, 48, 11.5)
    sub_panel = VGroup(PR.RoundedRectangle(width=sub.width + 0.7, height=sub.height + 0.35, corner_radius=0.25,
                                           fill_color="#FFFFFF", fill_opacity=1).set_stroke(PR.ink(), 7), sub)
    sub.move_to(sub_panel[0])
    sub_panel.move_to(PR.P(0, 2.0))
    return [garage(), pile, maya, bolt, nib, bonk, logo, sub_panel]


def make_cartoon_thumbnail(out_png: Path, title: str) -> Path:
    img = frame_rgb(thumbnail_mobjects(title), W, H, "#FFE8C2")
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(img).save(out_png, optimize=False)
    return out_png
