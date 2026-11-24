"""M05.3 acting: an emotion-pose library + the script rules that pick poses, listener reactions and celebrations.

Pure Python (no Manim) so the schema validator can use the names. A pose is ``fn(u) -> overrides`` over its own
duration (``u`` 0..1, envelope included) using Pose channels: ``dy`` (hop height, world units), ``lean`` (rad),
``squash`` (multiplier), ``arm_l``/``arm_r`` (degrees, absolute, blended in), ``head_tilt`` (rad), ``brow``
(-1..1 extra brow raise), ``expression`` (rig expression while the pose plays) and ``extras``.

Script cues (episode schema): a line may carry ``pose`` (the speaker's emotion pose) and ``react`` (what the
listeners do). When omitted they are chosen automatically from the line's ``emotion`` and text (``auto_pose`` /
``auto_react``), deterministically, so every episode acts without extra authoring.
"""

from __future__ import annotations

import hashlib
import math


def _c(u: float) -> float:
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def _bump(u: float) -> float:
    return math.sin(math.pi * _c(u))


def _env(u: float, a: float = 0.12, r: float = 0.25) -> float:
    """Attack / release envelope 0 -> 1 -> 0."""
    u = _c(u)
    return min(1.0, u / a if a else 1.0, (1 - u) / r if r else 1.0)


def _hop(u: float, h: float) -> dict:
    """Anticipation squash, stretched take-off, parabola, landing squash (cartoon hop)."""
    if u < 0.2:
        return {"squash": 1 - 0.18 * _bump(u / 0.4), "dy": 0.0}
    if u < 0.75:
        v = (u - 0.2) / 0.55
        return {"dy": h * 4 * v * (1 - v), "squash": 1 + 0.14 * (1 - abs(2 * v - 1))}
    v = (u - 0.75) / 0.25
    return {"squash": 1 - 0.2 * _bump(v), "dy": 0.0}


def surprised(u: float) -> dict:
    """Jump back: squash, pop up stretched with arms flung up, brows way up, settle."""
    o = _hop(min(1.0, u / 0.55), 0.35)
    e = _env(u, 0.05, 0.3)
    return {**o, "lean": -0.16 * e, "arm_l": 20 + 130 * e, "arm_r": 20 + 120 * e, "brow": 1.0 * e,
            "head_tilt": -0.06 * e, "expression": "surprised" if u < 0.85 else None}


def giggle(u: float) -> dict:
    """Shoulders shake, little bounces, lean back and forth, one hand to the mouth."""
    e = _env(u, 0.1, 0.25)
    shake = math.sin(2 * math.pi * 7 * u)
    return {"squash": 1 + 0.05 * e * shake, "dy": 0.05 * e * abs(math.sin(2 * math.pi * 3.5 * u)),
            "lean": 0.1 * e * math.sin(2 * math.pi * 1.5 * u) - 0.05 * e, "arm_r": 20 + 120 * e,
            "arm_l": 20 + 25 * e, "head_tilt": 0.12 * e * math.sin(2 * math.pi * 1.5 * u + 1.0),
            "brow": 0.4 * e, "expression": "laugh"}


def proud(u: float) -> dict:
    """Chest out, lean back, chin up, hands on hips (arms akimbo), a small up-bounce."""
    e = _env(u, 0.18, 0.3)
    return {"lean": -0.12 * e, "squash": 1 + 0.06 * e, "dy": 0.08 * _bump(u / 0.35), "arm_l": 20 + 35 * e,
            "arm_r": 20 + 35 * e, "head_tilt": -0.1 * e, "brow": -0.2 * e, "extras": ("sparkle",) if u > 0.2 else ()}


def excited(u: float) -> dict:
    """Two bouncy hops with arms up."""
    v = (u * 2) % 1.0
    o = _hop(v, 0.32)
    e = _env(u, 0.08, 0.15)
    return {**o, "arm_l": 20 + 110 * e, "arm_r": 20 + 125 * e, "brow": 0.6 * e,
            "head_tilt": 0.08 * e * math.sin(2 * math.pi * 2 * u)}


def thinking(u: float) -> dict:
    """Hand to chin, head tilted, eyes up, slow sway."""
    e = _env(u, 0.2, 0.25)
    return {"arm_r": 20 + 115 * e, "head_tilt": 0.16 * e, "lean": 0.04 * e * math.sin(2 * math.pi * u),
            "brow": 0.3 * e, "squash": 1 - 0.02 * e}


def worried(u: float) -> dict:
    """Shrink, arms pulled in, brows up, a nervous shiver."""
    e = _env(u, 0.12, 0.3)
    return {"squash": 1 - 0.07 * e, "lean": 0.035 * e * math.sin(2 * math.pi * 9 * u), "arm_l": 20 + 45 * e,
            "arm_r": 20 + 45 * e, "brow": 0.8 * e, "head_tilt": -0.05 * e}


def curious(u: float) -> dict:
    """Head tilt + lean in (questions, listening)."""
    e = _env(u, 0.2, 0.3)
    return {"head_tilt": 0.18 * e, "lean": 0.07 * e, "brow": 0.5 * e}


def nod(u: float) -> dict:
    """Big agreeing nods (bob + tilt)."""
    e = _env(u, 0.1, 0.2)
    s = math.sin(2 * math.pi * 3 * u)
    return {"head_tilt": 0.1 * e * s, "squash": 1 - 0.05 * e * max(0.0, s), "dy": 0.03 * e * abs(s)}


def talk_bounce(u: float) -> dict:
    """Friendly emphasis for neutral lines: a bounce, brows up, a side tilt."""
    e = _env(u, 0.12, 0.35)
    return {"dy": 0.1 * _bump(u / 0.4), "squash": 1 + 0.05 * _bump(u / 0.4) - 0.05 * _bump((u - 0.4) / 0.2),
            "brow": 0.5 * e, "head_tilt": 0.1 * e * math.sin(math.pi * u)}


def celebrate(u: float) -> dict:
    """Dance: hop on the beat, arms pump alternately, hips sway."""
    v = (u * 3) % 1.0
    o = _hop(v, 0.28)
    e = _env(u, 0.06, 0.12)
    s = math.sin(2 * math.pi * 3 * u)
    return {**o, "lean": 0.16 * e * s, "arm_l": 20 + e * (90 + 60 * s), "arm_r": 20 + e * (90 - 60 * s),
            "head_tilt": 0.12 * e * s, "brow": 0.6 * e, "extras": ("sparkle",) if 0.2 < u < 0.9 else ()}


POSES = {
    #  name          (seconds, fn,         rig expression family)
    "surprised": (1.1, surprised),
    "giggle": (1.5, giggle),
    "proud": (1.6, proud),
    "excited": (1.2, excited),
    "thinking": (1.8, thinking),
    "worried": (1.4, worried),
    "curious": (1.4, curious),
    "nod": (1.0, nod),
    "talk_bounce": (1.0, talk_bounce),
    "celebrate": (2.0, celebrate),
}
POSE_NAMES = tuple(POSES)
EMOTION_POSES = ("surprised", "giggle", "proud", "excited", "thinking", "worried", "celebrate")
EMOTION_TO_POSE = {"surprised": "surprised", "laugh": "giggle", "proud": "proud", "worried": "worried",
                   "thinking": "thinking", "sleepy": "worried"}
REACTIONS = {"giggle": ("giggle", 0.6), "surprised": ("surprised", 0.5), "excited": ("excited", 0.5),
             "proud": ("nod", 0.8), "worried": ("worried", 0.6), "celebrate": ("celebrate", 0.7)}
CELEBRATION_CUES = {"victory_sting", "chant_beat", "title_sting"}      # music beats everybody dances to
CELEBRATION_SFX = {"sparkle", "ding", "clap"}                         # the last speaker celebrates


def _h(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def auto_pose(line: dict) -> str:
    """Emotion pose for a line without an authored ``pose``: from its emotion, else from the text."""
    if line.get("pose"):
        return line["pose"]
    emo, text = line.get("emotion") or "", line.get("text", "")
    if emo in EMOTION_TO_POSE:
        return EMOTION_TO_POSE[emo]
    if text.rstrip().endswith("?"):
        return "curious"
    if "!" in text and len(text) <= 48:
        return "excited"
    return ("talk_bounce", "nod")[_h(text) % 2]


def auto_react(line: dict, pose: str) -> tuple[str, float] | None:
    """Listener reaction to a line (authored ``react`` wins), with a gain (< 1: smaller than the speaker's)."""
    if line.get("react"):
        return line["react"], 0.8
    if pose in REACTIONS:
        return REACTIONS[pose]
    return ("curious", 0.7) if _h(line.get("text", "") + "react") % 3 == 0 else None


def pose_duration(name: str) -> float:
    return POSES[name][0]


def pose_fn(name: str):
    return POSES[name][1]


__all__ = ["CELEBRATION_CUES", "CELEBRATION_SFX", "EMOTION_POSES", "POSES", "POSE_NAMES", "auto_pose",
           "auto_react", "pose_duration", "pose_fn"]
