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
    tilt = p.lean + getattr(p, "head_tilt", 0.0) * 0.6         # M05.3 head tilt moves the head point too
    hx = cx + math.sin(tilt) * p.facing * h * 0.55 * p.squash
    hy = state.y + h * p.squash * math.cos(tilt)
    pts = [(cx, cy), (hx, hy)]
    for a, side in ((p.arm_l, -1), (p.arm_r, 1)):
        r = math.radians(a)
        pts.append((cx + side * 0.25 * h + side * 0.3 * h * math.sin(r), cy + 0.1 * h - 0.3 * h * math.cos(r)))
    ey = hy - 0.18 * h
    pts.append((hx + p.gaze[0] * 0.06 * h, ey + p.gaze[1] * 0.06 * h - p.blink * 0.05 * h))
    pts.append((hx, ey - 0.12 * h - MOUTH_OPEN.get(str(p.mouth), 0.3) * 0.05 * h))
    # M05.3 secondary parts: antenna / mast tip and hair, brows
    sec = getattr(p, "antenna", 0.0) * 0.18 * h, getattr(p, "hair", 0.0) * 0.03 * h
    pts.append((hx + sec[0] * p.facing, hy + 0.12 * h + sec[1]))
    pts.append((hx, ey + 0.08 * h + getattr(p, "brow", 0.0) * 0.025 * h))
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


# ------------------------------------------------------------------------------------------ M05.3 acting metrics

ENERGY_MIN_PX_S = 75.0       # mean key-point speed (1080p px/s) per on-stage character (M03.6 rig: Bolt 63-80)
ENERGY_MIN_BY_CHARACTER = {"nib": 40.0}      # tiny Nib covers fewer pixels for the same acting
MIN_DISTINCT_EMOTION_POSES = 3               # per speaking character over the episode
STILL_WINDOW_S = 0.5         # a moment is "still" when nothing moved > STILL_PX within this window
STILL_PX = 10.0
STILL_SHARE_MAX = 0.3        # no character may be still for more than 30 % of its screen time


def acting_metrics(tracks: list, fps: int = 30) -> dict:
    """Motion energy (mean key-point speed) and still share from per-frame key-point tracks (None = excluded)."""
    speeds, still, n = [], 0, 0
    w = max(1, round(STILL_WINDOW_S * fps))
    for i, pts in enumerate(tracks):
        if pts is None:
            continue
        prev = tracks[i - 1] if i else None
        if prev is not None:
            speeds.append(sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(pts, prev)) / len(pts) * fps)
        win = [x for x in tracks[max(0, i - w):i + 1] if x is not None]
        if len(win) > w // 2:
            n += 1
            ref = win[0]
            if max(math.hypot(a[0] - b[0], a[1] - b[1]) for x in win for a, b in zip(x, ref)) < STILL_PX:
                still += 1
    return {"energy": round(sum(speeds) / len(speeds), 1) if speeds else 0.0,
            "stillShare": round(still / n, 3) if n else 0.0, "frames": n}


def scene_acting(sc, presence_fn, heights: dict[str, float], scales: dict[str, float], fps: int = 30) -> dict:
    """Per on-stage character: motion energy, still share and the emotion poses it played (M05.3 QA)."""
    k = max(1, round(sc.trans_half * fps))
    excluded = [(c["start"], c["end"]) for c in getattr(sc, "concepts", []) or []] + \
        [(c["start"], c["end"]) for c in sc.cutaways]
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
                           for sh in getattr(sc, "shots", []) or [])):
                tracks.append(None)
                continue
            tracks.append(key_points(perf.state(t), heights[cid] * perf.scale / scales[cid]))
        m = acting_metrics(tracks, fps)
        own = [a for a in perf.poses if float(a.arg or 1) >= 0.75]
        m["poses"] = sorted({a.name for a in own})
        m["poseCount"] = len(own)
        m["reactions"] = sum(1 for a in perf.poses if float(a.arg or 1) < 0.75)
        out[cid] = m
    return out
