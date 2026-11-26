"""A4: the ``visual_gap`` placeholder — unmistakably not a finished visual (hazard stripes, "VISUAL COMING SOON",
the gap id and what must be shown). Always animated (stripes scroll, sign bobs) so it never reads as a frozen frame,
but QA ``authoring.visual_gaps`` fails any bundle that shows it and publish/R3 refuse it."""

from __future__ import annotations

import math

from manim import Polygon, Rectangle, RoundedRectangle, VGroup

from robotics101.cartoon import props as PR
from robotics101.cartoon.kit.common import GAP, outline

P = PR.P
STRIPE_A, STRIPE_B = "#FFD23F", "#222222"
HEADLINE = "VISUAL COMING SOON"


def _clip(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman clip of a convex polygon to the rectangle (deterministic, pure Python)."""
    def cut(pts, inside, inter):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / ((b[0] - a[0]) or 1e-9))

    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / ((b[1] - a[1]) or 1e-9), yc)
    pts = list(poly)
    for inside, inter in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)),
                          (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        pts = cut(pts, inside, inter) if pts else pts
    return pts


def _stripes(x0, y0, x1, y1, t: float, w: float = 0.55) -> VGroup:
    g = VGroup(Rectangle(width=x1 - x0, height=y1 - y0, fill_color=STRIPE_A, fill_opacity=1, stroke_width=0)
               .move_to(P((x0 + x1) / 2, (y0 + y1) / 2)))
    h = y1 - y0
    x = x0 - h - 2 * w + (0.6 * t) % (2 * w)
    while x < x1:
        pts = _clip([(x, y0), (x + w, y0), (x + w + h, y1), (x + h, y1)], x0, y0, x1, y1)
        if len(pts) >= 3:
            g.add(Polygon(*[P(px, py) for px, py in pts], fill_color=STRIPE_B, fill_opacity=1, stroke_width=0))
        x += 2 * w
    return g


def visual_gap(t: float, ctx: dict, box=None) -> VGroup:
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX
    x0, y0, x1, y1 = box or ILLUSTRATION_BOX
    g = VGroup(_stripes(x0, y0, x1, y1, t))
    bob = 0.06 * math.sin(2.4 * t)
    sw, sh = (x1 - x0) * 0.78, (y1 - y0) * 0.66
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2 + bob
    sign = outline(RoundedRectangle(width=sw, height=sh, corner_radius=0.2, fill_color="#FFFFFF", fill_opacity=1), 6)
    g.add(sign.move_to(P(cx, cy)))
    head = PR.txt(HEADLINE, 56, color="#D62828", font="Luckiest Guy", weight="NORMAL")
    head.scale(min(1.0, (sw - 0.6) / max(head.width, 0.01)))
    g.add(head.move_to(P(cx, cy + sh * 0.28)))
    what = (ctx.get("what") or "").strip()
    if what:
        body = PR.wrap(what, 30, sw - 0.8)
        body.scale(min(1.0, (sh * 0.38) / max(body.height, 0.01)))
        g.add(body.move_to(P(cx, cy - sh * 0.02)))
    tag = PR.txt(f"PLACEHOLDER  {ctx.get('gapId', 'gap-??')}", 24, color="#555555")
    g.add(tag.move_to(P(cx, cy - sh * 0.38)))
    return g


GAP["visual_gap"] = {"fn": visual_gap}

__all__ = ["HEADLINE", "visual_gap"]
