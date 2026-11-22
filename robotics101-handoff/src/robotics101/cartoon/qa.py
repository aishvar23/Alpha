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
