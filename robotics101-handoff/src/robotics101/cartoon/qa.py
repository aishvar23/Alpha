"""Cartoon bundle QA (M02.8): final media, captions, dialogue, scenes (presence, lip sync), teaching facts,
robot-cam, mix + licences, manifest integrity incl. character registry fingerprint and drawing version,
voice identity, audience, thumbnail."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

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
    if not rep.hard("bundle.spec", spec is not None and spec.get("schemaVersion") == "1.1",
                    "episode.json is a cartoon (1.1) spec"):
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
    check_liveliness(rep, by)
    if video_s:
        check_transitions(rep, out_dir, spec, timing, float(sj.get("transitionHalfSeconds", 0.4)))
        check_concepts(rep, out_dir, spec, by, timing)
        check_static_holds(rep, out_dir, spec, timing, by, float(sj.get("transitionHalfSeconds", 0.4)))

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
