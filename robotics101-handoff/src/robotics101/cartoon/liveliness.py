"""M03.3 "nobody is ever static": analytic pose-track motion check.

Every on-stage character is reduced, per frame, to a handful of key points in 1080p pixels (body centre, head top,
both hands, eyes incl. gaze/blink, mouth opening). A character is *static* while none of its key points moves more
than ``STATIC_PX`` from where it was at the start of the run. Frames where the character is hidden (presence < 0.5),
covered by a transition / concept card, or replaced by a robot-cam cutaway don't count (they reset the run)."""

from __future__ import annotations

import math

PX_PER_UNIT = 1080 / 8.0          # 135 px per world unit at 1080p
STATIC_PX = 6.0
MAX_STATIC_S = 1.0
MOUTH_OPEN = {"X": 0.0, "A": 0.1, "B": 0.35, "C": 0.7, "D": 1.0, "E": 0.6, "F": 0.3, "G": 0.3, "H": 0.5}


def key_points(state, height: float) -> list[tuple[float, float]]:
    """Key points (px) of a FrameState for a character of nominal ``height`` world units."""
    p, h = state.pose, height
    cx, cy = state.x, state.y + 0.45 * h
    hx = cx + math.sin(p.lean) * p.facing * h * 0.55 * p.squash
    hy = state.y + h * p.squash * math.cos(p.lean)
    pts = [(cx, cy), (hx, hy)]
    for a, side in ((p.arm_l, -1), (p.arm_r, 1)):
        r = math.radians(a)
        pts.append((cx + side * 0.25 * h + side * 0.3 * h * math.sin(r), cy + 0.1 * h - 0.3 * h * math.cos(r)))
    ey = hy - 0.18 * h
    pts.append((hx + p.gaze[0] * 0.06 * h, ey + p.gaze[1] * 0.06 * h - p.blink * 0.05 * h))
    pts.append((hx, ey - 0.12 * h - MOUTH_OPEN.get(str(p.mouth), 0.3) * 0.05 * h))
    return [(x * PX_PER_UNIT, y * PX_PER_UNIT) for x, y in pts]


def static_runs(tracks: list[list[tuple[float, float]] | None], fps: int = 30,
                threshold_px: float = STATIC_PX) -> tuple[float, int]:
    """Longest static run (seconds, start frame). ``None`` entries are excluded frames (they reset the run)."""
    best, best_at, anchor, start = 0, 0, None, 0
    for i, pts in enumerate(tracks + [None]):
        if pts is not None and anchor is not None and max(
                math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(pts, anchor)) < threshold_px:
            continue
        if anchor is not None and i - start > best:
            best, best_at = i - start, start
        anchor, start = pts, i
    return best / fps, best_at


def scene_liveliness(sc, presence_fn, heights: dict[str, float], scales: dict[str, float], fps: int = 30) -> dict:
    """Per character: longest static run (s) and where, over the scene's analysable frames."""
    k = max(1, round(sc.trans_half * fps))
    excluded = []
    for c in getattr(sc, "concepts", []) or []:
        excluded.append((c["start"], c["end"]))
    for c in sc.cutaways:
        excluded.append((c["start"], c["end"]))
    out = {}
    for cid, perf in sc.perf.items():
        if cid not in sc.cast:
            continue
        tracks = []
        for n in range(sc.n_frames):
            t = n / fps
            if ((sc.trans_in and n < k) or (sc.trans_out and n >= sc.n_frames - k)
                    or any(a <= t < b for a, b in excluded) or presence_fn(sc, t).get(cid, 0.0) < 0.5
                    or t < sc.enter_at.get(cid, 0.0)
                    or any(sh["start"] <= t < sh["end"] and sh.get("character") != cid
                           for sh in getattr(sc, "shots", []) or [])):        # M05.1: hidden behind a shot
                tracks.append(None)
                continue
            tracks.append(key_points(perf.state(t), heights[cid] * perf.scale / scales[cid]))
        s, at = static_runs(tracks, fps)
        out[cid] = {"longestStaticS": round(s, 3), "at": round(at / fps, 2),
                    "frames": sum(1 for x in tracks if x is not None)}
    return out
