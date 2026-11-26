"""Shared kit plumbing: registry, cue/param resolution, drawing helpers (PLAN-authoring §5.3 common rules)."""

from __future__ import annotations

import math
import re

from manim import Line, Polygon, RoundedRectangle, VGroup

from robotics101.cartoon import props as PR
from robotics101.cartoon.motion import clamp01
from robotics101.cartoon.sets import ink

P = PR.P
PRIMITIVES: dict[str, dict] = {}       # name -> {"fn", "cueKeys", "layouts"}; filled by the primitive modules
GAP: dict[str, dict] = {}              # "visual_gap" -> {"fn"}
LABEL_MAX = 18                         # §5.3: labels <= 18 chars (Fredoka)
TITLE_COLOR = "#6C4AB6"
PALETTE = ["#4CC9F0", "#FFD166", "#06D6A0", "#EF476F", "#9B5DE5", "#F78C6B"]


def register(name: str, fn, cue_keys: tuple[str, ...] = (), layouts: tuple[str, ...] = ("illustration", "solo")):
    PRIMITIVES[name] = {"fn": fn, "cueKeys": tuple(cue_keys), "layouts": tuple(layouts)}
    return fn


def visual(name: str):
    """Drawing function for ``kit_<primitive>`` or ``visual_gap``."""
    if name in GAP:
        return GAP[name]["fn"]
    prim = name[len("kit_"):] if name.startswith("kit_") else name
    if prim not in PRIMITIVES:
        raise ValueError(f"unknown kit primitive {prim!r}; known: {sorted(PRIMITIVES)}")
    return PRIMITIVES[prim]["fn"]


# ------------------------------------------------------------------ params / cues

PARAM_REF = re.compile(r"^\$([A-Za-z][A-Za-z0-9_]*)$")


def resolve_params(value, scene_params: dict):
    """Replace ``"$name"`` strings (anywhere in the params tree) by the scene parameter ``name``."""
    if isinstance(value, str):
        m = PARAM_REF.match(value)
        if m:
            if m.group(1) not in scene_params:
                raise KeyError(f"unresolved kit parameter ${m.group(1)}")
            return scene_params[m.group(1)]
        return value
    if isinstance(value, list):
        return [resolve_params(v, scene_params) for v in value]
    if isinstance(value, dict):
        return {k: resolve_params(v, scene_params) for k, v in value.items()}
    return value


def param_refs(value) -> list[str]:
    if isinstance(value, str):
        m = PARAM_REF.match(value)
        return [m.group(1)] if m else []
    if isinstance(value, list):
        return [r for v in value for r in param_refs(v)]
    if isinstance(value, dict):
        return [r for v in value.values() for r in param_refs(v)]
    return []


def cue_list(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v or [])


def cue_time(sc, sh: dict, cue: str) -> float | None:
    """Scene time of ``word:<w>`` (first covered line containing it) or ``sfx:<id>`` (first covered beat)."""
    from robotics101.cartoon.scenes import word_time_in_line
    kind, _, val = cue.partition(":")
    beats = sc.beats[sh["fromBeat"]:sh["toBeat"] + 1]
    for b in beats:
        if kind == "word" and b.get("type") == "line":
            t = word_time_in_line(sc.voice_dir, b, val)
            if t is not None:
                return float(t)
        if kind == "sfx" and b.get("type") == "sfx" and b.get("id") == val:
            return float(b["start_s"])
    return None


def context(sc, sh: dict) -> dict:
    """Shot context for a kit / gap shot: resolved params, cue times (sorted lists per cue key), shot window."""
    if sh.get("visual") == "visual_gap":
        g = sh.get("gap") or {}
        return {"gapId": g.get("gapId", "gap-??"), "what": g.get("what", ""), "t0": sh["start"]}
    kit = sh.get("kit") or {}
    params = resolve_params(kit.get("params") or {}, dict(sc.params))
    t0, t1 = sh["start"] + 0.35, max(sh["start"] + 0.5, sh["end"] - 0.4)
    cues = {}
    for key, val in sorted((kit.get("cues") or {}).items()):
        ts = [cue_time(sc, sh, c) for c in cue_list(val)]
        cues[key] = [round(t, 3) for t in ts if t is not None]
    return {"params": params, "cues": cues, "title": kit.get("title"), "t0": round(t0, 3), "t1": round(t1, 3)}


def staged(ctx: dict, key: str, n: int) -> list[float]:
    """``n`` reveal times for cue ``key``: the cue times first, then evenly spread over the rest of the shot (so every
    element still appears and the board keeps moving even with fewer cues than elements)."""
    got = list(ctx.get("cues", {}).get(key) or [])
    t0, t1 = float(ctx.get("t0", 0.0)), float(ctx.get("t1", 4.0))
    out = []
    for i in range(n):
        if i < len(got):
            out.append(got[i])
        else:
            last = out[-1] if out else t0
            rest = n - i
            out.append(last + max(0.35, (t1 - last) / (rest + 1)))
    return out


# ------------------------------------------------------------------ drawing helpers

def u(t: float, a: float | None, d: float = 0.45) -> float:
    return 0.0 if a is None else clamp01((t - a) / d)


def outline(m, w: float = 5):
    return m.set_stroke(ink(), w)


def label(s: str, size: int = 30, color: str | None = None):
    return PR.txt(str(s)[:LABEL_MAX], size, color=color)


def title(box, text: str | None, t: float):
    x0, y0, x1, y1 = box
    if not text:
        return VGroup()
    head = PR.txt(text.upper()[:40], 40, color=TITLE_COLOR, font="Luckiest Guy", weight="NORMAL")
    head.scale(min(1.0, (x1 - x0 - 0.6) / max(head.width, 0.01)))
    return head.move_to(P((x0 + x1) / 2, y1 - 0.42 + 0.03 * math.sin(2.2 * t)))


def content_box(box, has_title: bool):
    x0, y0, x1, y1 = box
    return (x0 + 0.35, y0 + 0.25, x1 - 0.35, y1 - (0.95 if has_title else 0.3))


def chip(text: str, w: float, h: float, color: str, size: int = 30, k: float = 1.0):
    body = outline(RoundedRectangle(width=w, height=h, corner_radius=min(0.25, h / 3), fill_color=color,
                                    fill_opacity=1), 4)
    lab = label(text, size)
    lab.scale(min(1.0, (w - 0.25) / max(lab.width, 0.01), (h - 0.15) / max(lab.height, 0.01)))
    g = VGroup(body, lab.move_to(body.get_center()))
    if k != 1.0:
        g.scale(max(k, 0.001))
    return g


def arrow(a, b, color: str | None = None, w: float = 6, tip: float = 0.22):
    import numpy as np
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    d = b - a
    n = float(np.linalg.norm(d)) or 1.0
    d /= n
    p = np.array([-d[1], d[0], 0.0])
    col = color or ink()
    shaft = Line(a, b - d * tip * 0.9, stroke_color=col, stroke_width=w)
    head = Polygon(b, b - d * tip + p * tip * 0.6, b - d * tip - p * tip * 0.6, fill_color=col, fill_opacity=1,
                   stroke_width=0)
    return VGroup(shaft, head)


def check_mark(at, size: float = 0.35, color: str = "#06D6A0"):
    import numpy as np
    at = np.array(at, dtype=float)
    return VGroup(Line(at + np.array([-size, 0, 0]), at + np.array([-size * 0.35, -size * 0.6, 0]),
                       stroke_color=color, stroke_width=10),
                  Line(at + np.array([-size * 0.35, -size * 0.6, 0]), at + np.array([size, size * 0.7, 0]),
                       stroke_color=color, stroke_width=10))


__all__ = ["GAP", "LABEL_MAX", "PALETTE", "PRIMITIVES", "arrow", "check_mark", "chip", "content_box", "context",
           "cue_list", "cue_time", "label", "outline", "param_refs", "register", "resolve_params", "staged", "title",
           "u", "visual"]
