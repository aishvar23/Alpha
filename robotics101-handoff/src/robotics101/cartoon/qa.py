"""Cartoon bundle QA (M02.8): final media, captions, dialogue, scenes (presence, lip sync), teaching facts,
robot-cam, mix + licences, manifest integrity incl. character registry fingerprint and drawing version,
voice identity, audience, thumbnail."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from robotics101.cartoon import CARTOON_SCHEMA_VERSIONS
from robotics101.animation.render import PROFILES
from robotics101.media import find_ffmpeg, summarize
from robotics101.qa import QaReport, _check_captions, _check_final

FPS = 30
PRESENCE_MIN = 0.8
LIPSYNC_MEAN_MIN, LIPSYNC_LINE_MIN = 0.9, 0.6


def _load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


CUT_MAX_DIFF = 4.0          # mean |grey| change across a scene boundary (both frames fully covered)
COVER_MIN_DIFF = 10.0       # the cover must actually appear (vs the frame one half-transition earlier)
CARD_MIN_S = 2.0


def boundaries(timing: dict) -> list[tuple[str, int]]:
    out, n = [], 0
    for s in timing["scenes"]:
        if n:
            out.append((s["sceneId"], n))
        n += round(s["scene_duration_s"] * FPS)
    return out


def check_transitions(rep, out_dir: Path, spec: dict, timing: dict, half_s: float) -> None:
    """M03.2: no hard cuts — every scene boundary is covered by a transition (identical fully-covered frames on both
    sides, and the cover visibly arrives), unless the spec asks for an explicit ``cut`` (warning)."""
    from robotics101.cartoon import vision
    video = Path(out_dir) / "final.mp4"
    style = {s["sceneId"]: s.get("transitionIn") for s in spec["scenes"]}
    k = max(1, round(half_s * FPS))
    bad, cuts, rows = [], [], []
    for sid, b in boundaries(timing):
        if style.get(sid) == "cut":
            cuts.append(sid)
            continue
        if not style.get(sid):
            bad.append(f"{sid}: no transition")
            continue
        f = vision.frames_at(video, [b - 1 - k, b - 1, b, b + k + 2])
        across, arrive = vision.diff(f[b - 1], f[b]), vision.diff(f[b - 1 - k], f[b - 1])
        reveal = vision.diff(f[b], f[b + k + 2])
        rows.append({"scene": sid, "style": style[sid], "frame": b, "across": round(across, 2),
                     "arrive": round(arrive, 2), "reveal": round(reveal, 2)})
        if across > CUT_MAX_DIFF or arrive < COVER_MIN_DIFF or reveal < COVER_MIN_DIFF:
            bad.append(f"{sid} ({style[sid]}) at frame {b}: across {across:.1f}, cover {arrive:.1f}, reveal {reveal:.1f}")
    rep.hard("transitions.no_hard_cuts", not bad,
             f"{len(rows)} scene boundaries covered by transitions ({', '.join(sorted({r['style'] for r in rows}))})"
             if not bad else "; ".join(bad), rows)
    if cuts:
        rep.soft("transitions.explicit_cuts", False, f"hard cuts requested by the spec into {cuts}")


def check_concepts(rep, out_dir: Path, spec: dict, by: dict, timing: dict) -> None:
    """M03.2: every concept marker has an animated title card that plays (>= 2 s) before the concept is taught."""
    from robotics101.cartoon import vision
    video = Path(out_dir) / "final.mp4"
    starts, n = {}, 0
    for s in timing["scenes"]:
        starts[s["sceneId"]] = n
        n += round(s["scene_duration_s"] * FPS)
    want = [(s["sceneId"], c) for s in spec["scenes"] for c in (s.get("concepts") or [])]
    if not want:
        rep.soft("concepts.cards", False, "the episode declares no concept markers (scene `concepts`)")
        return
    bad, rows = [], []
    for sid, c in want:
        card = next((x for x in ((by.get(sid) or {}).get("facts") or {}).get("conceptCards", []) if x["id"] == c["id"]),
                    None)
        if card is None:
            bad.append(f"{c['id']}: no card in {sid}")
            continue
        dur = card["end"] - card["start"]
        f0 = starts[sid]
        mid, after = f0 + round((card["start"] + card["end"]) / 2 * FPS), f0 + round((card["end"] + 0.4) * FPS)
        fr = vision.frames_at(video, [mid, after])
        shown = vision.diff(fr[mid], fr[after])
        rows.append({"concept": c["id"], "scene": sid, "start": card["start"], "end": card["end"],
                     "teachStart": card["teachStart"], "visibleDiff": round(shown, 1)})
        if card["title"] != c["title"]:
            bad.append(f"{c['id']}: card title {card['title']!r} != {c['title']!r}")
        if dur < CARD_MIN_S:
            bad.append(f"{c['id']}: card only {dur:.1f}s")
        if card["end"] > card["teachStart"] + 0.05:
            bad.append(f"{c['id']}: card still up when teaching starts ({card['end']} > {card['teachStart']})")
        if shown < COVER_MIN_DIFF:
            bad.append(f"{c['id']}: card not visible in final.mp4 (diff {shown:.1f})")
    rep.hard("concepts.cards", not bad, f"{len(rows)} concept title cards before teaching: "
             + (", ".join(r["concept"] for r in rows) if not bad else "; ".join(bad)), rows)


STATIC_MAX_S = 1.0
HOLD_MAX_S = 2.0            # M03.4: no illustration / whole frame may sit still longer than this
HOLD_W, HOLD_H = 384, 216
HOLD_PIX_DELTA, HOLD_PIX_COUNT = 10, 30      # full frame: "moving" = ≥ 30 px changed by > 10 grey levels
REGION_MIN_DIFF = 1.0                        # illustration region: mean |grey| change vs the run's first frame


def hold_runs(video: Path, timing: dict, by: dict, half_s: float = 0.4) -> dict:
    """Stream ``video`` once (small grey frames) and measure the longest near-zero-motion run of the whole frame and
    of every registered illustration region (scenes.json ``illustrations``)."""
    import numpy as np

    from robotics101.cartoon.vision import stream_gray
    regions, off = [], 0
    for s in timing["scenes"]:
        n = round(s["scene_duration_s"] * FPS)
        for il in (by.get(s["sceneId"]) or {}).get("illustrations", []):
            x0, y0, x1, y1 = il["box"]
            a = off + round(il["start"] * FPS)
            b = min(off + round(il["end"] * FPS), off + n - round(half_s * FPS))   # out-transition covers the end
            regions.append({"id": f"{s['sceneId']}/{il['id']}", "a": a, "b": b,
                            "sl": (slice(max(0, int(y0 * HOLD_H)), int(y1 * HOLD_H)),
                                   slice(max(0, int(x0 * HOLD_W)), int(x1 * HOLD_W))),
                            "anchor": None, "start": a, "best": 0, "at": a})
        off += n
    full = {"anchor": None, "start": 0, "best": 0, "at": 0}
    i = -1
    for i, f in enumerate(stream_gray(video, HOLD_W, HOLD_H)):
        f16 = f.astype(np.int16)
        if full["anchor"] is None or int((np.abs(f16 - full["anchor"]) > HOLD_PIX_DELTA).sum()) >= HOLD_PIX_COUNT:
            if i - full["start"] > full["best"]:
                full["best"], full["at"] = i - full["start"], full["start"]
            full["anchor"], full["start"] = f16, i
        for r in regions:
            if not r["a"] <= i < r["b"]:
                continue
            crop = f16[r["sl"]]
            if r["anchor"] is None or float(np.abs(crop - r["anchor"]).mean()) >= REGION_MIN_DIFF:
                if r["anchor"] is not None and i - r["start"] > r["best"]:
                    r["best"], r["at"] = i - r["start"], r["start"]
                r["anchor"], r["start"] = crop, i
    end = i + 1
    if end - full["start"] > full["best"]:
        full["best"], full["at"] = end - full["start"], full["start"]
    for r in regions:
        stop = min(r["b"], end)
        if r["anchor"] is not None and stop - r["start"] > r["best"]:
            r["best"], r["at"] = stop - r["start"], r["start"]
    return {"frames": end, "fullFrame": {"longestHoldS": round(full["best"] / FPS, 3), "at": round(full["at"] / FPS, 2)},
            "regions": {r["id"]: {"longestHoldS": round(r["best"] / FPS, 3), "at": round(r["at"] / FPS, 2),
                                  "seconds": round((r["b"] - r["a"]) / FPS, 2)} for r in regions}}


def check_static_holds(rep, out_dir: Path, spec: dict, timing: dict, by: dict, half_s: float) -> None:
    """M03.4: every registered illustration (animated robot families) keeps moving and the picture never freezes:
    hard ``illustrations.animated`` and ``video.no_long_holds`` (≤ 2 s near-zero motion)."""
    res = hold_runs(out_dir / "final.mp4", timing, by, half_s)
    (out_dir / "qa").mkdir(exist_ok=True)
    (out_dir / "qa" / "static_holds.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    ff = res["fullFrame"]
    rep.hard("video.no_long_holds", ff["longestHoldS"] <= HOLD_MAX_S,
             f"longest near-still stretch of the whole picture {ff['longestHoldS']:.2f} s at {ff['at']} s "
             f"(≤ {HOLD_MAX_S} s)", ff["longestHoldS"])
    regs = res["regions"]
    fam = any(s["template"] == "cartoon_robot_family" for s in spec["scenes"])
    bad = {k: v for k, v in regs.items() if v["longestHoldS"] > HOLD_MAX_S}
    rep.hard("illustrations.animated", (bool(regs) or not fam) and not bad,
             f"{len(regs)} animated illustration region(s); longest still "
             f"{max((v['longestHoldS'] for v in regs.values()), default=0):.2f} s (≤ {HOLD_MAX_S} s); "
             f"static: {bad or 'none'}", {k: v["longestHoldS"] for k, v in regs.items()})


def check_liveliness(rep, by: dict) -> None:
    """M03.3: nobody is ever static — per character, the longest pose-track run with no key point moving more than
    6 px (1080p) must stay ≤ 1 s (frames under transitions/cards/cutaways or off stage excluded)."""
    measured = {sid: r["liveliness"] for sid, r in by.items() if "liveliness" in r}
    if not measured:
        rep.soft("characters.alive", False, "no pose-track liveliness data in scenes.json (pre-M03.3 render)")
        return
    worst, bad = {}, []
    for sid, d in measured.items():
        for cid, v in d.items():
            s = v.get("longestStaticS", 0.0)
            if s > worst.get(cid, (-1, ""))[0]:
                worst[cid] = (s, f"{sid}@{v.get('at')}s")
            if s > STATIC_MAX_S:
                bad.append(f"{cid} {s:.2f}s in {sid} at {v.get('at')}s")
    missing = sorted(set(by) - set(measured))
    rep.hard("characters.alive", not bad and not missing,
             f"longest static run per character {({c: f'{w[0]:.2f}s ({w[1]})' for c, w in worst.items()})} "
             f"(≤ {STATIC_MAX_S} s); static: {bad or 'none'}; unmeasured scenes: {missing or 'none'}",
             {c: w[0] for c, w in worst.items()})


def check_shots(rep, spec: dict, timing: dict, by: dict) -> None:
    """M05.1 / M05.6 illustration-first layouts: every explanatory line is inside an illustration/solo shot;
    illustration visuals cover >= 60% of the frame and solo visuals >= 35%; a teaching visual may not share the
    frame with a full-size character (corner cameo <= 8%) and must itself cover >= 60%."""
    from robotics101.cartoon.layout import (CORNER_MAX_AREA, ILLUSTRATION_MIN_AREA, MAX_CHARACTERS, MIN_CHARACTERS,
                                            SOLO_MIN_AREA)
    from robotics101.cartoon.visuals import is_teaching_visual
    tim = {s["sceneId"]: s for s in timing["scenes"]}
    bad, rows, n_explain = [], [], 0
    for sc in spec["scenes"]:
        sid = sc["sceneId"]
        shots = ((by.get(sid) or {}).get("facts") or {}).get("shots") or []
        for sh in shots:
            lay, n = sh["layout"], len(sh.get("characters") or [])
            need = ILLUSTRATION_MIN_AREA if lay == "illustration" else SOLO_MIN_AREA
            rows.append({"scene": sid, "layout": lay, "visual": sh.get("visual"), "areaShare": sh.get("areaShare"),
                         "characters": [c["id"] for c in sh.get("characters") or []],
                         "start": sh["start"], "end": sh["end"]})
            if (sh.get("areaShare") or 0) < need:
                bad.append(f"{sid} {lay} visual covers {sh.get('areaShare')} of the frame (< {need})")
            if not MIN_CHARACTERS.get(lay, 0) <= n <= MAX_CHARACTERS.get(lay, 9):
                bad.append(f"{sid} {lay} shot has {n} characters")
            if lay == "illustration" and any(c.get("area", 0) > CORNER_MAX_AREA for c in sh.get("characters") or []):
                bad.append(f"{sid} illustration corner character too big")
            if is_teaching_visual(sh.get("visual")):
                if (sh.get("areaShare") or 0) < ILLUSTRATION_MIN_AREA:
                    bad.append(f"{sid} teaching visual {sh.get('visual')} covers {sh.get('areaShare')} "
                               f"of the frame (< {ILLUSTRATION_MIN_AREA})")
                if any(c.get("area", 0) > CORNER_MAX_AREA for c in sh.get("characters") or []):
                    bad.append(f"{sid} teaching visual {sh.get('visual')} shares the frame with a full-size character")
        beats = {b["index"]: b for b in (tim.get(sid) or {}).get("beats", [])}
        for i, b in enumerate(sc["beats"]):
            if b["type"] != "line" or not b.get("explain"):
                continue
            n_explain += 1
            tb = beats.get(i)
            if tb is None:
                bad.append(f"{sid}#{i}: explanatory line missing from timing")
                continue
            if not any(sh["layout"] in ("illustration", "solo") and sh["start"] <= tb["start_s"] + 0.05
                       and tb["end_s"] - 0.05 <= sh["end"] for sh in shots):
                bad.append(f"{sid}#{i}: explanatory line not shown in an illustration/solo shot")
    if not rows and not n_explain:
        rep.soft("layout.illustration_first", False, "no explanatory beats / illustration or solo shots in the episode")
        return
    rep.hard("layout.illustration_first", not bad,
             f"{n_explain} explanatory lines in {len(rows)} illustration/solo shots "
             f"({', '.join(f'{r['scene']}:{r['layout']}/{r['visual']} {r['areaShare']:.0%}' for r in rows)}); "
             f"problems: {bad or 'none'}", rows)



def check_one_example_per_frame(rep, spec: dict, timing: dict, by: dict) -> None:
    """M05.6: each teaching example has its own frame; two example illustrations are never on screen at once,
    and a multi-example grid (``robot_families``) is not used."""
    from robotics101.cartoon.visuals import is_example_visual
    bad, rows = [], []
    for sc in spec["scenes"]:
        sid = sc["sceneId"]
        shots = ((by.get(sid) or {}).get("facts") or {}).get("shots") or sc.get("shots") or []
        examples = []
        for sh in shots:
            vis = sh.get("visual") or ""
            if vis == "robot_families":
                bad.append(f"{sid}: robot_families grid shows several examples on one frame")
            if is_example_visual(vis) or sh.get("example"):
                examples.append(sh)
                rows.append({"scene": sid, "example": sh.get("example") or vis, "visual": vis,
                             "start": sh.get("start"), "end": sh.get("end")})
        # authored / expanded beat examples must each have a shot
        for i, b in enumerate(sc.get("beats") or []):
            for ex in b.get("examples") or []:
                if not any((sh.get("example") == ex["id"]) or sh.get("visual") == ex.get("visual") for sh in shots):
                    bad.append(f"{sid}: example {ex['id']} has no frame of its own")
        for i, a in enumerate(examples):
            for b in examples[i + 1:]:
                a0, a1 = a.get("start"), a.get("end")
                b0, b1 = b.get("start"), b.get("end")
                if a0 is None or b0 is None:
                    if a.get("fromBeat") == b.get("fromBeat") and not (a.get("untilWord") or b.get("atWord")):
                        bad.append(f"{sid}: examples {a.get('example')} and {b.get('example')} share a beat with no split")
                    continue
                if a0 < b1 and b0 < a1:
                    bad.append(f"{sid}: {a.get('example') or a.get('visual')} and {b.get('example') or b.get('visual')} "
                               f"visible together ({a0}–{a1} overlaps {b0}–{b1})")
    rep.hard("layout.one_example_per_frame", not bad,
             f"{len(rows)} one-example frames; problems: {bad or 'none'}", rows)


def check_clutter(rep, spec: dict, by: dict) -> None:
    """M05.6: explainer / illustration frames stay uncluttered — the teaching visual dominates, at most one small
    cameo, and no pile of overlapping extras."""
    from robotics101.cartoon.layout import CLUTTER_MAX_COVER, CLUTTER_MAX_ITEMS, CORNER_MAX_AREA, ILLUSTRATION_MIN_AREA
    from robotics101.cartoon.visuals import is_teaching_visual
    bad, rows = [], []
    for sc in spec["scenes"]:
        sid = sc["sceneId"]
        shots = ((by.get(sid) or {}).get("facts") or {}).get("shots") or []
        illustrations = (by.get(sid) or {}).get("illustrations") or []
        for sh in shots:
            if sh.get("layout") != "illustration" and not is_teaching_visual(sh.get("visual")):
                continue
            chars = sh.get("characters") or []
            mid = ((sh.get("start") or 0) + (sh.get("end") or 0)) / 2
            visible_il = [i for i in illustrations if i.get("start", 0) <= mid < i.get("end", 0)]
            n = len(chars) + max(0, len(visible_il))
            rows.append({"scene": sid, "visual": sh.get("visual"), "items": n, "areaShare": sh.get("areaShare")})
            if (sh.get("areaShare") or 1) < ILLUSTRATION_MIN_AREA:
                bad.append(f"{sid} {sh.get('visual')} is cluttered / too small ({sh.get('areaShare')})")
            if any(c.get("area", 0) > CORNER_MAX_AREA for c in chars):
                bad.append(f"{sid} {sh.get('visual')} has a full-size character on the explainer")
            if n > CLUTTER_MAX_ITEMS:
                bad.append(f"{sid} {sh.get('visual')} has {n} overlapping items (max {CLUTTER_MAX_ITEMS})")
            if (sh.get("areaShare") or 0) > CLUTTER_MAX_COVER and len(chars) > 1:
                bad.append(f"{sid} {sh.get('visual')} coverage is overcrowded")
    if not rows:
        rep.soft("layout.clutter", True, "no explainer frames to score for clutter")
        return
    rep.hard("layout.clutter", not bad, f"{len(rows)} explainer frames; problems: {bad or 'none'}", rows)


def check_acting(rep, spec: dict, by: dict) -> None:
    """M05.3 acting: per scene and on-stage character, motion energy (mean key-point speed) above the threshold and
    still share ≤ 30 %; every speaking character plays ≥ 3 distinct emotion poses over the episode and an emotion
    pose in every scene where it speaks; at least one celebration (soft)."""
    from robotics101.cartoon.acting import EMOTION_POSES
    from robotics101.cartoon.liveliness import (ENERGY_MIN_BY_CHARACTER, ENERGY_MIN_PX_S, MIN_DISTINCT_EMOTION_POSES,
                                                STILL_SHARE_MAX)
    measured = {sid: r["acting"] for sid, r in by.items() if "acting" in r}
    if not measured:
        rep.soft("characters.acting", False, "no acting metrics in scenes.json (pre-M05.3 render)")
        return
    bad, low = [], {}
    speakers: dict[str, set] = {}
    for sc in spec["scenes"]:
        for b in sc["beats"]:
            if b["type"] == "line":
                speakers.setdefault(b["speaker"], set()).add(sc["sceneId"])
    used: dict[str, set] = {}
    for sid, d in measured.items():
        for cid, v in d.items():
            need = ENERGY_MIN_BY_CHARACTER.get(cid, ENERGY_MIN_PX_S)
            if v.get("frames", 0) and v["energy"] < need:
                bad.append(f"{cid} energy {v['energy']} px/s < {need} in {sid}")
            if v.get("frames", 0) and v["stillShare"] > STILL_SHARE_MAX:
                bad.append(f"{cid} still {v['stillShare']:.0%} of the time in {sid}")
            if v["energy"] < low.get(cid, (1e9, ""))[0]:
                low[cid] = (v["energy"], sid)
            used.setdefault(cid, set()).update(v.get("poses", []))
            if sid in speakers.get(cid, set()) and not v.get("poseCount"):
                bad.append(f"{cid} speaks in {sid} without an emotion pose")
    for cid in speakers:
        emo = used.get(cid, set()) & set(EMOTION_POSES)
        if cid in {c for d in measured.values() for c in d} and len(emo) < MIN_DISTINCT_EMOTION_POSES:
            bad.append(f"{cid} plays only {sorted(emo)} (< {MIN_DISTINCT_EMOTION_POSES} distinct emotion poses)")
    missing = sorted(set(by) - set(measured))
    rep.hard("characters.acting", not bad and not missing,
             f"lowest motion energy per character { {c: f'{e} px/s ({s})' for c, (e, s) in low.items()} } "
             f"(≥ {ENERGY_MIN_PX_S}, Nib ≥ {ENERGY_MIN_BY_CHARACTER.get('nib')}); still share ≤ {STILL_SHARE_MAX:.0%}; "
             f"emotion poses used { {c: sorted(v & set(EMOTION_POSES)) for c, v in used.items()} }; problems: "
             f"{bad or 'none'}; unmeasured scenes: {missing or 'none'}",
             {c: e for c, (e, _) in low.items()})
    rep.soft("characters.celebrate", any("celebrate" in v for v in used.values()),
             "a celebration / dance beat plays somewhere in the episode")


def check_caption_band(rep, by: dict) -> None:
    """M05.2: the bottom caption band is reserved for subtitles — no character, teaching visual, readout or prop
    geometry (measured at render time on sampled frames) reaches into it beyond a few anti-aliased pixels."""
    from robotics101.cartoon.layout import BAND_OVERLAP_TOL, CAPTION_BAND
    measured = {sid: r["captionBand"] for sid, r in by.items() if "captionBand" in r}
    if not measured:
        rep.soft("layout.caption_band", False, "no caption-band measurements in scenes.json (pre-M05.2 render)")
        return
    bad = [f"{sid}: {o['what']} {o['maxIntrusion'] * 1080:.0f}px@1080 from {o['first']}s ({o['n']} samples)"
           for sid, r in measured.items() for o in r.get("offenders", []) if o["maxIntrusion"] > BAND_OVERLAP_TOL]
    missing = sorted(set(by) - set(measured))
    worst = max((r["maxIntrusion"] for r in measured.values()), default=0.0)
    rep.hard("layout.caption_band", not bad and not missing,
             f"bottom {CAPTION_BAND:.0%} reserved for captions; {sum(r['samples'] for r in measured.values())} "
             f"sampled frames, worst content intrusion {worst * 1080:.1f}px@1080 (tolerance "
             f"{BAND_OVERLAP_TOL * 1080:.0f}px); offenders: {bad or 'none'}; unmeasured scenes: {missing or 'none'}",
             round(worst, 4))


SUB_COVER_TOL = 0.05
SUB_COLOR_DIST = 70.0         # RGB distance to the speaker colour that counts as "subtitle text" pixels
SUB_MIN_TEXT_FRAC = 0.04      # share of the cue box covered by speaker-coloured text in the final video
SUB_SAMPLES = 16
SUB_ONE_LINE_MIN = 0.7        # M05.2: most cues should be a single line


def check_subtitles(rep, out_dir: Path, spec: dict, timing: dict, video_s: float | None) -> None:
    """M03.5: burned-in kid subtitles cover all dialogue, stay in the safe area, ≤ 2 lines, legible size, avoid the
    registered teaching visuals, and are really in final.mp4 (speaker-coloured text inside each sampled cue box)."""
    from robotics101.cartoon.subtitles import MAX_LINES, MIN_EM_PX, SAFE, settings
    st = settings(spec)
    doc = _load(out_dir / "subtitles.json")
    comp = _load(out_dir / "compose.json") or {}
    if not st["burnIn"]:
        rep.soft("subtitles.burned", False, "burned-in subtitles disabled by the spec (subtitles.burnIn false)")
        return
    burned = bool(doc and doc.get("burnIn") and (comp.get("subtitles") or {}).get("burnedIn")
                  and (out_dir / "subtitles.ass").is_file())
    if not rep.hard("subtitles.burned", burned, "subtitles.ass written and burned in at compose "
                    f"({(comp.get('subtitles') or {}).get('cues', 0)} cues)"):
        return
    cues = doc["cues"]
    by_line: dict = {}
    for c in cues:
        by_line.setdefault((c["sceneId"], c["lineIndex"]), []).append(c)
    missing = []
    for s in timing["scenes"]:
        t0 = float(s.get("scene_start_s", 0.0))
        for b in s["beats"]:
            if b["type"] != "line":
                continue
            cs = sorted(by_line.get((s["sceneId"], int(b.get("index", 0))), []), key=lambda c: c["start"])
            a, z = t0 + b["start_s"], t0 + b["end_s"]
            ok = bool(cs) and cs[0]["start"] <= a + SUB_COVER_TOL and cs[-1]["end"] >= z - SUB_COVER_TOL and all(
                n["start"] - p["end"] <= SUB_COVER_TOL for p, n in zip(cs, cs[1:]))
            if not ok:
                missing.append(f"{s['sceneId']}#{b.get('index')}")
    n_lines = sum(1 for s in timing["scenes"] for b in s["beats"] if b["type"] == "line")
    rep.hard("subtitles.coverage", not missing and n_lines > 0,
             f"{n_lines - len(missing)}/{n_lines} dialogue lines covered by {len(cues)} cues; missing: "
             f"{missing or 'none'}", len(missing))
    W, H = doc["frame"]
    lo_x, lo_y, hi_x, hi_y = W * SAFE, H * SAFE, W * (1 - SAFE), H * (1 - SAFE)
    out_safe = [f"{c['sceneId']}#{c['lineIndex']}" for c in cues
                if not (c["box"][0] >= lo_x and c["box"][1] >= lo_y and c["box"][2] <= hi_x and c["box"][3] <= hi_y)]
    too_long = [f"{c['sceneId']}#{c['lineIndex']}" for c in cues if len(c["lines"]) > MAX_LINES]
    sj = _load(out_dir / "scenes.json") or {"scenes": []}
    kos = {r["sceneId"]: r.get("keepouts", []) for r in sj["scenes"]}
    starts = {s["sceneId"]: float(s.get("scene_start_s", 0.0)) for s in timing["scenes"]}
    clash = []
    for c in cues:
        t0 = starts.get(c["sceneId"], 0.0)
        for k in kos.get(c["sceneId"], []):
            kb = [k["box"][0] * W, k["box"][1] * H, k["box"][2] * W, k["box"][3] * H]
            for what, b in (("", c["box"]), ("panel", c.get("panel"))):
                if b and (k["start"] < c["end"] - t0 and c["start"] - t0 < k["end"] and b[0] < kb[2]
                          and kb[0] < b[2] and b[1] < kb[3] and kb[1] < b[3]):
                    clash.append(f"{c['sceneId']}#{c['lineIndex']}{'(' + what + ')' if what else ''}~{k['id']}")
    # M05.2: every cue sits on its compact caption box inside the reserved caption band
    bare = [f"{c['sceneId']}#{c['lineIndex']}" for c in cues if not c.get("panel")]
    band = doc.get("captionBand")
    off_band = [f"{c['sceneId']}#{c['lineIndex']}" for c in cues if band and (
        c.get("placement") != "band" or (c.get("panel") or c["box"])[1] < band[1] or c["box"][3] > band[3])]
    if not band:
        off_band = ["subtitles.json has no captionBand (pre-M05.2 layout)"]
    em = doc.get("emPx", 0) * (1080 / H)
    one = sum(1 for c in cues if len(c["lines"]) == 1)
    rep.hard("subtitles.layout", not out_safe and not too_long and not clash and not bare and not off_band
             and em >= MIN_EM_PX,
             f"font {doc.get('font')} em {doc.get('emPx')} px @ {W}x{H} (≥ {MIN_EM_PX}); outside safe area: "
             f"{out_safe or 'none'}; > {MAX_LINES} lines: {too_long or 'none'}; covering teaching visuals: "
             f"{clash or 'none'}; without caption box: {bare or 'none'}; outside the caption band "
             f"{band}: {off_band or 'none'}; one-line cues {one}/{len(cues)}")
    rep.soft("subtitles.compact", cues and one / len(cues) >= SUB_ONE_LINE_MIN,
             f"{one}/{len(cues)} cues on one line (≥ {SUB_ONE_LINE_MIN:.0%} preferred; max {MAX_LINES})",
             round(one / max(1, len(cues)), 3))
    if not video_s:
        return
    from robotics101.cartoon.vision import frame_rgb_at
    step = max(1, len(cues) // SUB_SAMPLES)
    sample = cues[::step][:SUB_SAMPLES]
    weak = []
    fracs = []
    for c in sample:
        n = round((c["start"] + c["end"]) / 2 * FPS)
        img = frame_rgb_at(out_dir / "final.mp4", n)
        h, w = img.shape[:2]
        x0, y0, x1, y1 = (round(c["box"][0] * w / W), round(c["box"][1] * h / H), round(c["box"][2] * w / W),
                          round(c["box"][3] * h / H))
        crop = img[y0:y1, x0:x1].astype(float)
        col = [int(c["color"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        frac = float((((crop - col) ** 2).sum(axis=2) ** 0.5 < SUB_COLOR_DIST).mean()) if crop.size else 0.0
        fracs.append(frac)
        if frac < SUB_MIN_TEXT_FRAC:
            weak.append(f"{c['sceneId']}#{c['lineIndex']}@{(c['start'] + c['end']) / 2:.1f}s ({frac:.3f})")
    rep.hard("subtitles.visible", not weak,
             f"{len(sample)} cues sampled in final.mp4; speaker-coloured text share in the cue box min "
             f"{min(fracs, default=0):.3f} (≥ {SUB_MIN_TEXT_FRAC}); weak: {weak or 'none'}", round(min(fracs, default=0), 3))


SECTION_SWATCH_MIN = 10.0     # M05.5: adjacent sections' background swatches must differ by ≥ this (0..255 mean)


def check_section_backgrounds(rep, spec: dict, by: dict) -> None:
    """M05.5 ``scenes.section_backgrounds`` (hard): every scene records the section background it drew; consecutive
    scenes of one section share it, and adjacent sections differ in theme AND in drawn colours (swatch distance)."""
    from robotics101.cartoon.backgrounds import swatch_distance
    order = [s["sceneId"] for s in spec["scenes"]]
    missing = [sid for sid in order if not (by.get(sid) or {}).get("background")]
    groups: list[dict] = []
    bad = []
    for sid in order:
        b = (by.get(sid) or {}).get("background")
        if not b:
            continue
        if groups and groups[-1]["section"] == b.get("section"):
            g = groups[-1]
            if (b["theme"], b.get("palette")) != (g["theme"], g["palette"]):
                bad.append(f"{sid}: background {b['theme']}/{b.get('palette')} differs inside section {g['section']!r}")
            g["scenes"].append(sid)
            continue
        groups.append({"section": b.get("section"), "theme": b["theme"], "palette": b.get("palette"),
                       "swatch": b.get("swatch"), "scenes": [sid]})
    for a, b in zip(groups, groups[1:]):
        d = swatch_distance(a["swatch"], b["swatch"]) if a.get("swatch") and b.get("swatch") else 0.0
        if a["theme"] == b["theme"]:
            bad.append(f"{a['section']} → {b['section']}: same theme {a['theme']!r}")
        elif d < SECTION_SWATCH_MIN:
            bad.append(f"{a['section']} → {b['section']}: backgrounds look alike (swatch Δ {d:.1f} < {SECTION_SWATCH_MIN})")
    rows = [{"section": g["section"], "theme": g["theme"], "palette": g["palette"], "scenes": g["scenes"]} for g in groups]
    rep.hard("scenes.section_backgrounds", not bad and not missing and len(groups) >= 1,
             f"{len(groups)} sections, backgrounds " + ", ".join(f"{g['section']}={g['theme']}/{g['palette']}" for g in groups)
             + f"; adjacent clashes: {bad or 'none'}; unrecorded scenes: {missing or 'none'}", rows)


def card_kickers(spec: dict, by: dict) -> list[dict]:
    """Every shown kicker in episode order: concept-card kickers and section banners (M05.5)."""
    out = []
    for sc in spec["scenes"]:
        f = (by.get(sc["sceneId"]) or {}).get("facts") or {}
        items = [(c.get("start", 0.0), "card", c.get("id"), c.get("kicker")) for c in f.get("conceptCards") or []]
        if f.get("sectionBanner"):
            b = f["sectionBanner"]
            items.append((b.get("start", 0.0), "banner", sc["sceneId"], b.get("kicker")))
        out += [{"scene": sc["sceneId"], "kind": k, "id": i, "kicker": kk} for _, k, i, kk in sorted(items) if kk]
    return out


def check_kicker_variety(rep, spec: dict, by: dict) -> None:
    """M05.5 ``cards.kicker_variety`` (hard): no two cards/banners share a kicker (case-insensitive) — the old single
    'NEW IDEA!' on every card read as a bug; ``cards.kicker_adjacent`` (soft): consecutive cards never repeat one."""
    ks = card_kickers(spec, by)
    norm = [" ".join(k["kicker"].split()).casefold() for k in ks]
    dup = sorted({k["kicker"] for k, n in zip(ks, norm) if norm.count(n) > 1})
    rep.hard("cards.kicker_variety", not dup,
             f"{len(ks)} kickers: " + (", ".join(f"{k['scene']}={k['kicker']!r}" for k in ks) or "none")
             + f"; repeated: {dup or 'none'}", [k["kicker"] for k in ks])
    adj = [f"{a['scene']}→{b['scene']} {a['kicker']!r}" for a, b, na, nb in zip(ks, ks[1:], norm, norm[1:]) if na == nb]
    rep.soft("cards.kicker_adjacent", not adj, f"adjacent repeated kickers: {adj or 'none'}", adj)


def check_intro(rep, spec: dict, by: dict) -> None:
    """M03.1: the generated cast intro is present (unless the spec turns it off) and introduces every main registry
    character of the episode cast: on stage (presence), nameplate with the registry display name, and a voiced line
    that says the name while the plate is up."""
    from robotics101.cartoon.episode import INTRO_TEMPLATE, intro_settings, main_characters
    from robotics101.characters import load_registry
    cfg = intro_settings(spec)
    scenes = [s for s in spec["scenes"] if s["template"] == INTRO_TEMPLATE]
    if not cfg["enabled"]:
        rep.soft("intro.present", not scenes, "character intro disabled by the spec (intro.enabled = false)")
        return
    want_at = 1 if (cfg["position"] == "after_cold_open" and spec["scenes"][0]["template"] == "cartoon_cold_open") else 0
    ok = len(scenes) == 1 and spec["scenes"][want_at]["template"] == INTRO_TEMPLATE and scenes[0]["sceneId"] in by
    if not rep.hard("intro.present", ok, f"cast intro scene at position {want_at + 1} ({cfg['position']}), rendered"):
        return
    reg = load_registry()
    r = by[scenes[0]["sceneId"]]
    got = {x["id"]: x for x in (r.get("facts") or {}).get("introduced", [])}
    pres = r.get("minPresence") or {}
    bad = []
    for cid in main_characters(reg, spec["characters"]):
        ch, x = reg.get(cid), got.get(cid)
        if x is None:
            bad.append(f"{cid}: not introduced")
            continue
        if x.get("name") != ch.displayName:
            bad.append(f"{cid}: nameplate {x.get('name')!r} != registry {ch.displayName!r}")
        p0, p1 = x.get("plate") or (0, 0)
        if p1 - p0 < 1.5:
            bad.append(f"{cid}: nameplate only {p1 - p0:.1f}s")
        if not x.get("line") or ch.displayName.lower() not in x["line"].lower():
            bad.append(f"{cid}: intro line does not say the name")
        elif not (p0 - 0.5 <= (x.get("lineStart") or -1) <= p1):
            bad.append(f"{cid}: name line not spoken while the plate is up")
        if pres.get(cid, 0) < PRESENCE_MIN:
            bad.append(f"{cid}: on screen {pres.get(cid, 0):.2f} < {PRESENCE_MIN}")
    rep.hard("intro.cast", not bad, "every main character on stage, nameplate (registry name) + named in a line: "
             + ("; ".join(bad) if bad else ", ".join(f"{k}={v['name']}" for k, v in got.items())))


def run_cartoon_qa(out_dir: Path, profile_name: str = "full") -> QaReport:
    from robotics101.cartoon.audio import check_mix
    from robotics101.cartoon.rigs import RIG_VERSION
    from robotics101.characters import load_registry
    from robotics101.manifest import verify_manifest
    from robotics101.voice.qa import check_dialogue

    out_dir = Path(out_dir)
    profile = PROFILES[profile_name]
    ffmpeg, ffprobe = find_ffmpeg()
    spec = _load(out_dir / "episode.json")
    rep = QaReport((spec or {}).get("episodeId"), profile_name, str(out_dir))
    if not rep.hard("bundle.spec", spec is not None and spec.get("schemaVersion") in CARTOON_SCHEMA_VERSIONS,
                    "episode.json is a cartoon (1.1/1.2) spec"):
        return rep
    timing = check_dialogue(rep, out_dir)
    if timing is None:
        return rep
    frames = [round(s["scene_duration_s"] * FPS) for s in timing["scenes"]]
    video_s = _check_final(rep, out_dir, ffmpeg, ffprobe, profile, sum(frames) / FPS, sum(frames))
    _check_captions(rep, out_dir, video_s)

    # scenes
    sj = _load(out_dir / "scenes.json") or {"scenes": []}
    by = {s["sceneId"]: s for s in sj["scenes"]}
    tmpl = {s["sceneId"]: s["template"] for s in spec["scenes"]}
    agree_all = []
    for s, n in zip(timing["scenes"], frames):
        sid = s["sceneId"]
        r = by.get(sid)
        row = {"sceneId": sid, "sequence": s["sequence"], "template": tmpl.get(sid), "engine": "cartoon", "duration_s": s["scene_duration_s"], "frames": n,
               "speech_coverage": s.get("speech_coverage"), "flags": []}
        rep.scenes.append(row)
        mp4 = out_dir / "scenes" / f"{sid}.mp4"
        if not rep.hard(f"scene.{sid}.video", mp4.is_file() and r is not None, f"scenes/{sid}.mp4 + render report"):
            continue
        v = summarize(mp4, ffprobe, count_frames=True).video or {}
        rep.hard(f"scene.{sid}.frames", v.get("frames") == n and (v.get("width"), v.get("height")) ==
                 (profile.width, profile.height), f"{v.get('frames')} frames {v.get('width')}x{v.get('height')} "
                 f"(timing {n})")
        pres = r.get("minPresence", {})
        rep.hard(f"scene.{sid}.presence", pres and min(pres.values()) >= PRESENCE_MIN,
                 f"min on-screen fraction {pres} (≥ {PRESENCE_MIN})", pres)
        ag = list((r.get("lipsyncAgreement") or {}).values())
        agree_all += ag
        row["lipsync_mean"] = round(sum(ag) / len(ag), 3) if ag else None
        row["presence"] = pres
    if agree_all:
        mean = sum(agree_all) / len(agree_all)
        low = [k for r in by.values() for k, a in (r.get("lipsyncAgreement") or {}).items() if a < LIPSYNC_LINE_MIN]
        rep.soft("lipsync.agreement", mean >= LIPSYNC_MEAN_MIN and not low,
                 f"mean mouth-open-while-voiced {mean:.3f} (≥ {LIPSYNC_MEAN_MIN}); lines < {LIPSYNC_LINE_MIN}: "
                 f"{low or 'none'}", round(mean, 3))

    check_intro(rep, spec, by)
    check_section_backgrounds(rep, spec, by)
    check_kicker_variety(rep, spec, by)
    check_liveliness(rep, by)
    check_shots(rep, spec, timing, by)
    check_one_example_per_frame(rep, spec, timing, by)
    check_clutter(rep, spec, by)
    check_caption_band(rep, by)
    check_acting(rep, spec, by)
    if video_s:
        check_transitions(rep, out_dir, spec, timing, float(sj.get("transitionHalfSeconds", 0.4)))
        check_concepts(rep, out_dir, spec, by, timing)
        check_static_holds(rep, out_dir, spec, timing, by, float(sj.get("transitionHalfSeconds", 0.4)))
    check_subtitles(rep, out_dir, spec, timing, video_s)

    # teaching facts (what is drawn on screen vs the spec)
    sp = {s["template"]: s.get("parameters", {}) for s in spec["scenes"]}
    facts = {r["template"]: r.get("facts", {}) for r in by.values()}
    thr = {p["thresholdMeters"] for p in sp.values() if "thresholdMeters" in p}
    rep.hard("facts.threshold_consistent", len(thr) == 1, f"threshold(s) in spec: {sorted(thr)}")
    t = next(iter(thr)) if len(thr) == 1 else None
    rb, rm = facts.get("cartoon_rule_board", {}), facts.get("cartoon_obstacle_rematch", {})
    rep.hard("facts.rule_board", rb.get("thresholdMeters") == t and rb.get("stopReading", 9) < (t or 0)
             and rb.get("readings") == sp.get("cartoon_rule_board", {}).get("readings"),
             f"rule board: threshold {rb.get('thresholdMeters')}, readings {rb.get('readings')}, stop at "
             f"{rb.get('stopReading')} m")
    rep.hard("facts.rematch_stop", rm.get("thresholdMeters") == t and 0 < rm.get("stopReading", 9) < (t or 0)
             and 0 < rm.get("stopDistance", 9) < (t or 0),
             f"rematch stops at {rm.get('stopReading')} m (true {rm.get('stopDistance', 0):.3f} m) < {t} m, no contact")
    cut = (by.get(next((s["sceneId"] for s in spec["scenes"] if s["template"] == "cartoon_obstacle_rematch"), ""), {})
           .get("cutaways") or [])
    rep.hard("facts.robotcam", bool(cut) and all((out_dir / c["clip"]).is_file() for c in cut),
             f"robot-cam cutaway in the rematch: {[(c['start'], c['end']) for c in cut]}")
    ping = facts.get("cartoon_sensor_ping", {})
    pp = sp.get("cartoon_sensor_ping", {})
    rep.hard("facts.sensor", ping.get("rangeMeters") == pp.get("rangeMeters") and
             ping.get("nibMeters") == pp.get("obstacleDistanceMeters"),
             f"sensor range {ping.get('rangeMeters')} m, Nib at {ping.get('nibMeters')} m")
    sv, svp = facts.get("cartoon_servo_highfive", {}), sp.get("cartoon_servo_highfive", {})
    rep.hard("facts.servo", sv.get("endAngle") == svp.get("endAngleDegrees") and
             sv.get("missAngle") == svp.get("missAngleDegrees"), f"servo {sv}")
    q = facts.get("cartoon_recap_chant", {}).get("question")
    rep.hard("facts.quiz", bool(q) and q == sp.get("cartoon_recap_chant", {}).get("question"), f"quiz card: {q!r}")

    # mix + licences
    lic = _load(out_dir / "licenses.json")
    rep.hard("assets.licenses_present", lic is not None, "licenses.json in bundle")
    mix = check_mix(rep, out_dir, timing, lic)
    rep.final["mix"] = mix
    if lic and shutil.which("fc-list"):
        fams = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
        missing = [f["family"] for f in lic.get("fonts", []) if f["family"] not in fams]
        rep.soft("assets.fonts_installed", not missing, f"fonts installed: missing {missing or 'none'}")

    # manifest + character registry fingerprint / drawing version
    man = _load(out_dir / "manifest.json")
    if rep.hard("manifest.present", man is not None, "manifest.json present"):
        problems = verify_manifest(out_dir, man)
        rep.hard("manifest.integrity", not problems, "every artifact matches its size + SHA-256" if not problems
                 else "; ".join(problems[:5]))
        reg = load_registry()
        cr = man.get("characterRegistry") or {}
        rep.hard("manifest.registry", cr.get("sha256") == reg.sha256 == timing.get("registrySha256"),
                 f"registry sha256 {str(cr.get('sha256'))[:12]}… (current {reg.sha256[:12]}…, voiced with "
                 f"{str(timing.get('registrySha256'))[:12]}…)")
        rep.hard("manifest.drawing_version", cr.get("drawingVersion") == RIG_VERSION and
                 cr.get("rigVersion") == reg.rig_version,
                 f"rig/drawing version {cr.get('rigVersion')}/{cr.get('drawingVersion')} (code {RIG_VERSION})")
        aud = (man.get("audience") or {}).get("madeForKids")
        rep.hard("audience.declared", aud is True and (spec.get("publishing") or {}).get("madeForKids") is True,
                 f"madeForKids {aud} (spec and manifest)")

    # voice identity: one provider, each speaker's configured voice
    reg = load_registry()
    prov = timing.get("provider")
    bad = []
    for cid, v in (timing.get("voices") or {}).items():
        cfg = (reg.get(cid).voice or {}).get(prov) or {}
        want = cfg.get("voiceId") or cfg.get("voice")
        got = v.get("voiceId") or v.get("voice")
        if v.get("provider") != prov or (want and got != want):
            bad.append(f"{cid}: {got} (registry {want})")
    speakers = {b["speaker"] for s in timing["scenes"] for b in s["beats"] if b["type"] == "line"}
    rep.hard("voice.identity", not bad and speakers <= set(timing.get("voices") or {}),
             f"{prov}: " + (", ".join(f"{c}={(timing['voices'][c].get('voiceId') or timing['voices'][c].get('voice'))}"
                                     for c in sorted(timing.get("voices") or {})) if not bad else "; ".join(bad)))

    thumb = out_dir / "thumbnail.png"
    tv = summarize(thumb, ffprobe).video if thumb.is_file() else None
    rep.hard("thumbnail", bool(tv) and (tv["width"], tv["height"]) == (1280, 720), "thumbnail.png 1280x720")
    rep.soft("profile.publishable", profile_name == "full", f"profile {profile_name}")
    return rep
