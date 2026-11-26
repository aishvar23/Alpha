"""Shared golden-frame helper for kit primitives / the gap placeholder (same rules as the rig model sheets)."""

import os
from pathlib import Path

import numpy as np
import pytest

GOLDEN = Path(__file__).parent / "golden" / "kit"
SIZE = (960, 540)
MAX_CHANGED_PX = 60
UPDATE = os.environ.get("ROBOTICS101_UPDATE_GOLDEN") == "1"


def frame(name: str, ctx: dict, t: float, layout: str = "illustration"):
    from manim import VGroup
    from robotics101.cartoon import visuals as VZ
    box = VZ.default_box(layout)
    return VGroup(VZ.backdrop(layout, t), VZ.visual(name)(t, ctx, box))


def _load(p: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)


def assert_golden(mob, key: str, tmp_path: Path) -> Path:
    from robotics101.cartoon.model_sheet import render_png
    out = render_png(mob, tmp_path / f"{key}.png", *SIZE)
    golden = GOLDEN / f"{key}-{SIZE[0]}.png"
    if UPDATE or not golden.exists():
        if not UPDATE:
            pytest.fail(f"missing golden {golden}; run with ROBOTICS101_UPDATE_GOLDEN=1 and review the PNGs")
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_bytes(out.read_bytes())
    a, b = _load(out), _load(golden)
    assert a.shape == b.shape
    diff = np.abs(a - b)
    changed = int((diff.max(axis=2) > 48).sum())
    assert changed <= MAX_CHANGED_PX and diff.mean() < 0.05, \
        f"{key}: {changed} px changed (mean {diff.mean():.3f}) — review the frame, then re-bless"
    return out


def moving(name: str, ctx: dict, t0: float, t1: float, layout: str = "illustration") -> float:
    """Mean absolute pixel difference between two frames of the visual alone (animation evidence)."""
    from manim import VGroup
    from robotics101.cartoon import visuals as VZ
    from robotics101.cartoon.model_sheet import render_png
    import tempfile
    box = VZ.default_box(layout)
    with tempfile.TemporaryDirectory() as d:
        a = render_png(VGroup(VZ.visual(name)(t0, ctx, box)), Path(d) / "a.png", 480, 270)
        b = render_png(VGroup(VZ.visual(name)(t1, ctx, box)), Path(d) / "b.png", 480, 270)
        return float(np.abs(_load(a) - _load(b)).mean())
