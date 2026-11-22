"""Model sheets (M02.3): every expression, mouth shape and key pose of each rig, rendered to PNG.

The sheets are the visual contract for the cast: reviewers check them once per rig version, and golden-image
tests (tests/test_rigs.py) compare low-resolution renders against ``tests/golden/`` so a rig change can't slip
through unnoticed. Rendering is a single still per sheet via Manim's Cairo camera (no video, no LaTeX).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, Camera, Line, Mobject, Text, VGroup, tempconfig

from robotics101.cartoon.rigs import MOUTH_SHAPES, RIG_VERSION, Pose, build, style

BG = "#FFF4E0"
FONT, TITLE_FONT = "Fredoka", "Luckiest Guy"
SHEETS = ("cast", "bolt", "maya", "nib")
HEAD_PARTS = {"bolt": ("screen", "cheeks", "eyes", "mouth"),
              "maya": ("puffs", "ears", "head", "cheeks", "eyes", "brows", "nose", "mouth", "band", "goggles"),
              "nib": ("body", "belly", "wing", "eye", "beak", "mast", "prop", "hub")}
POSES = {
    "bolt": [("blink", Pose(blink=1.0)), ("wave", Pose(arm_r=160, arm_l=30)), ("cheer", Pose(arm_l=165, arm_r=165)),
             ("squash", Pose(squash=0.8)), ("stretch", Pose(squash=1.18, expression="surprised")),
             ("lean", Pose(lean=0.2, arm_l=60, arm_r=60)), ("face left", Pose(facing=-1)),
             ("look up", Pose(gaze=(0.6, 1.0), expression="surprised"))],
    "maya": [("blink", Pose(expression="happy", blink=1.0)), ("wave", Pose(expression="grin", arm_r=165)),
             ("point", Pose(expression="happy", arm_r=95)), ("cheer", Pose(expression="laugh", arm_l=160, arm_r=160)),
             ("squash", Pose(expression="happy", squash=0.85)), ("stretch", Pose(expression="surprised", squash=1.12)),
             ("face left", Pose(expression="grin", facing=-1)),
             ("look down", Pose(expression="thinking", gaze=(-0.4, -1.0)))],
    "nib": [("blink", Pose(blink=1.0, expression="surprised")), ("flap up", Pose(arm_l=80)),
            ("flap down", Pose(arm_l=-30)), ("beep", Pose(mouth="D")), ("prop spin", Pose(prop=1.2)),
            ("squash", Pose(squash=0.75)), ("face left", Pose(facing=-1)), ("heart", Pose(extras=("heart",)))],
}


def _label(text: str, size: int = 22) -> Text:
    return Text(text, font=FONT, weight="BOLD", font_size=size, color=style("bolt").ink)


X0, X1 = -6.0, 6.9


def _row(items: list[tuple[str, Mobject]], *, max_h: float, ground: float | None = None,
         center: float | None = None) -> VGroup:
    """Lay items out evenly; one uniform scale per row (keeps relative sizes); labels under each item."""
    tallest = max(m.height for _, m in items)
    widest = max(m.width for _, m in items)
    n = len(items)
    k = min(max_h / tallest, 0.92 * (X1 - X0) / n / widest)
    row = VGroup()
    for i, (name, mob) in enumerate(items):
        mob.scale(k)
        x = X0 + (X1 - X0) * (i + 0.5) / n
        if ground is not None:
            mob.shift(np.array([x - mob.get_center()[0], ground - mob.get_bottom()[1], 0]))
        else:
            mob.move_to(np.array([x, center, 0]))
        base = ground if ground is not None else mob.get_bottom()[1]
        row.add(mob, _label(name, 20).move_to(np.array([x, base - 0.2, 0])))
    return row


def _section(text: str, y: float) -> Text:
    lbl = _label(text, 20)
    return lbl.move_to(np.array([-7.0 + lbl.width / 2, y, 0]))


def sheet(name: str) -> VGroup:
    ink = style("bolt").ink
    if name == "cast":
        title = Text("ROBOTICS 101 — cast lineup", font=TITLE_FONT, font_size=56, color="#FF6B9A") \
            .set_stroke(ink, 2, background=True).to_edge(UP, buff=0.35)
        ground = Line(LEFT * 7, RIGHT * 7, color=ink, stroke_width=4).shift(DOWN * 2.6)
        chars = VGroup(build("maya", Pose(expression="grin", arm_r=150)), build("bolt", Pose(arm_l=40, arm_r=140)),
                       build("nib", Pose(expression="happy")))
        xs = (-3.6, 0.2, 3.6)
        for c, x in zip(chars, xs):
            c.shift(np.array([x, -2.6, 0]))
        names = VGroup(*[_label(f"{n} ({h:.1f} u)", 26).move_to(np.array([x, -3.05, 0]))
                         for n, x, h in zip(("Maya", "Bolt", "Nib"), xs, [c.height for c in chars])])
        foot = _label(f"rig v{RIG_VERSION} · ground line = y 0 for every rig", 20).to_edge(DOWN, buff=0.15)
        return VGroup(title, ground, chars, names, foot)
    st = style(name)
    title = Text(f"{name.upper()} — model sheet (rig v{RIG_VERSION})", font=TITLE_FONT, font_size=40,
                 color=st.palette.get("body", st.palette.get("hoodie"))).set_stroke(ink, 2, background=True) \
        .to_edge(UP, buff=0.15)
    exprs = [(e, build(name, Pose(expression=e))) for e in st.expressions]
    heads = []
    base = st.expressions[0]
    for m in MOUTH_SHAPES:
        g = build(name, Pose(expression=base, mouth=m))
        heads.append((m, VGroup(*[g.parts[k] for k in HEAD_PARTS[name]])))
    poses = [(lbl, build(name, p)) for lbl, p in POSES[name]]
    return VGroup(title,
                  _section("expressions", 3.0), _row(exprs, max_h=2.15, ground=0.75),
                  _section("mouths (Rhubarb A–H, X = rest)", 0.3), _row(heads, max_h=0.85, center=-0.45),
                  _section("poses", -1.2), _row(poses, max_h=1.95, ground=-3.55))


def render_png(mob: Mobject, path: Path, width: int = 1920, height: int = 1080, background: str = BG) -> Path:
    from PIL import Image

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempconfig({"pixel_width": width, "pixel_height": height, "frame_width": 14.222222222222221,
                     "frame_height": 8.0, "background_color": background, "disable_caching": True}):
        cam = Camera(background_color=background)
        cam.capture_mobjects([mob])
        img = cam.get_image()
        img = img if isinstance(img, Image.Image) else Image.fromarray(np.asarray(img))
        img.convert("RGB").save(path)
    return path


def render_sheets(out_dir: Path, width: int = 1920, height: int = 1080, names=SHEETS) -> list[Path]:
    return [render_png(sheet(n), Path(out_dir) / f"model-sheet-{n}.png", width, height) for n in names]
