"""Estimated episode timeline before any voice/render (PLAN-authoring §6.2).

Same rules and constants as ``voice.dialogue`` (lead-in, gaps, anchored sfx, action/music costs, tail), except a
line lasts ``words / wps`` (default ``DIALOGUE_WPS`` 2.6 words/s) instead of its audio length. Produces a
``timing.json``-shaped dict so the engagement gate runs identically on the estimate and on the real timing.
"""

from __future__ import annotations

import math

from robotics101.voice.dialogue import (ACTION_DEFAULT_S, ACTION_SECONDS, ECHO_DELAY_S, FPS, GAP_SAME_S,
                                        GAP_SWITCH_S, LEAD_IN_S, MUSIC_ADVANCE_S, SFX_ADVANCE_S, SFX_AT_END,
                                        SFX_SECONDS, TAIL_S)


def _r(x: float) -> float:
    return round(x, 3)


def words(text: str) -> int:
    return len([w for w in text.replace("—", " ").split() if any(c.isalnum() for c in w)])


def estimate_timing(spec: dict, wps: float = 2.6) -> dict:
    scenes_out, t0 = [], 0.0
    for scene in sorted(spec["scenes"], key=lambda s: s.get("sequence", 0)):
        beats = scene.get("beats", [])
        line_idx = [i for i, b in enumerate(beats) if b["type"] == "line"]
        t, out, anchor, last_ping = LEAD_IN_S, [], None, None
        for i, b in enumerate(beats):
            kind, e = b["type"], {"index": i, "type": b["type"]}
            if kind == "line":
                dur = max(0.6, words(b["text"]) / wps)
                nxt = next((j for j in line_idx if j > i), None)
                gap = GAP_SAME_S if nxt is not None and beats[nxt]["speaker"] == b["speaker"] else GAP_SWITCH_S
                e.update(speaker=b["speaker"], text=b["text"], emotion=b.get("emotion"), action=b.get("action"),
                         pose=b.get("pose"), react=b.get("react"), start_s=_r(t), end_s=_r(t + dur))
                t += dur + gap
            elif kind == "action":
                d = float(b.get("seconds") or ACTION_SECONDS.get(b["do"].split(":")[0], ACTION_DEFAULT_S))
                e.update(who=b["who"], do=b["do"], start_s=_r(t), end_s=_r(t + d))
                t += d
            elif kind == "sfx":
                sid = b["id"]
                snd = SFX_SECONDS.get(sid, SFX_ADVANCE_S)
                if anchor is not None or (sid == "echo" and last_ping is not None):
                    if sid == "echo":
                        at = (last_ping if last_ping is not None else anchor["start_s"]) + ECHO_DELAY_S
                    elif sid in SFX_AT_END:
                        at = anchor["end_s"]
                    else:
                        at = anchor["start_s"]
                    e.update(id=sid, start_s=_r(at), end_s=_r(at + snd))
                else:
                    e.update(id=sid, start_s=_r(t), end_s=_r(t + snd))
                    t += SFX_ADVANCE_S
                if sid == "ping":
                    last_ping = e["start_s"]
            elif kind == "music":
                d = MUSIC_ADVANCE_S.get(b["cue"], 0.0)
                e.update(cue=b["cue"], start_s=_r(t), end_s=_r(t + d))
                t += d
            elif kind == "pause":
                e.update(start_s=_r(t), end_s=_r(t + float(b["seconds"])))
                t += float(b["seconds"])
            out.append(e)
            if kind == "action":
                anchor = e
            elif kind != "sfx":
                anchor, last_ping = None, None
        last = max([e["end_s"] for e in out] + [LEAD_IN_S])
        dur = round(math.ceil(round((last + TAIL_S) * FPS, 6)) / FPS, 6)
        scenes_out.append({"sceneId": scene["sceneId"], "sequence": scene.get("sequence"), "scene_start_s": _r(t0),
                           "scene_end_s": _r(t0 + dur), "scene_duration_s": dur, "beats": out,
                           "target_duration_s": scene.get("durationTargetSeconds")})
        t0 += dur
    return {"schemaVersion": "robotics101.timing.estimate/1", "estimated": True, "wps": wps,
            "totalDurationSeconds": _r(t0), "scenes": scenes_out}


__all__ = ["estimate_timing", "words"]
