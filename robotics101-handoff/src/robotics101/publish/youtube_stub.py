"""YouTube publisher **stub** — dry run only (M01.6).

What it does: reads a rendered bundle (``manifest.json``, ``final.mp4``, ``captions.srt``, ``thumbnail.png``,
``qa_report.json``, ``compose.json``, ``episode.json``), re-hashes ``final.mp4`` and builds exactly what a
future uploader would send (``snippet`` / ``status`` metadata, caption and thumbnail file refs, chapters),
plus every reason it would refuse today. Writes ``<out>/publish_plan.json``.

What it never does: import any Google/YouTube/OAuth library, open a socket, read credentials, or upload.
A real upload is not implemented (M06) and is refused unconditionally. When it exists, it must require
``approval.json`` from the owner that binds to the exact SHA-256 of ``final.mp4`` (checked here already):

    {"approvedSha256": "<sha256 of final.mp4>", "reviewer": "<name>", "decision": "approved",
     "timestamp": "<ISO-8601>"}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from robotics101.manifest import MANIFEST_NAME, verify_manifest
from robotics101.media import sha256_file

PLAN_NAME = "publish_plan.json"
APPROVAL_NAME = "approval.json"
PLAN_SCHEMA = "robotics101.publish_plan/1"
SERIES = "Robotics 101"
CATEGORY_EDUCATION = "27"
TITLE_MAX, DESCRIPTION_MAX, TAGS_MAX_CHARS = 100, 5000, 500
REAL_UPLOAD_REFUSAL = ("real upload not implemented (M06); requires owner approval bound to the final video "
                       "SHA-256. Nothing was uploaded. Use --dry-run to write publish_plan.json.")
BASE_TAGS = ["robotics", "robotics 101", "robots for beginners", "introduction to robotics", "STEM", "education"]
TEMPLATE_TAGS = {
    "robot_anatomy": "robot parts",
    "sensor_range": "distance sensor",
    "sense_think_act": "sense think act",
    "servo_rotation": "servo motor",
    "mobile_robot_avoidance": "obstacle avoidance",
    "recap_quiz": "robotics quiz",
}


class PublishRefused(RuntimeError):
    """The bundle cannot even be planned (missing files, hash mismatch, tampered manifest)."""


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _clean(s: str) -> str:
    # YouTube rejects '<' and '>' in titles/descriptions
    return s.replace("<", "‹").replace(">", "›")


def _ts(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def build_title(spec: dict) -> str:
    n = spec.get("episodeNumber")
    t = spec.get("title") or spec.get("episodeId", "Untitled")
    title = f"{SERIES} · Ep. {n}: {t}" if n else f"{SERIES}: {t}"
    return _clean(title)[:TITLE_MAX]


def build_chapters(spec: dict, compose: dict | None) -> list[dict]:
    titles = {s["sceneId"]: s.get("title", s["sceneId"]) for s in spec.get("scenes", [])}
    segs = (compose or {}).get("segments") or []
    return [{"start_s": round(float(seg["start_s"]), 3), "timestamp": _ts(float(seg["start_s"])),
             "title": _clean(titles.get(seg["sceneId"], seg["sceneId"]))} for seg in segs]


def chapters_valid(chapters: list[dict]) -> bool:
    """YouTube auto-chapters: first at 0:00, at least 3, each at least 10 s long."""
    if len(chapters) < 3 or chapters[0]["start_s"] != 0:
        return False
    starts = [c["start_s"] for c in chapters]
    return all(b - a >= 10 for a, b in zip(starts, starts[1:]))


def build_description(spec: dict, chapters: list[dict], synthetic_voice: bool) -> str:
    lines = [f"{SERIES}, episode {spec.get('episodeNumber', '?')}: {spec.get('title', '')}", ""]
    objectives = spec.get("learningObjectives") or []
    if objectives:
        lines += ["In this episode you will learn to:"] + [f"• {o}" for o in objectives] + [""]
    if chapters:
        lines += ["Chapters:"] + [f"{c['timestamp']} {c['title']}" for c in chapters] + [""]
    if synthetic_voice:
        lines += ["Narration: synthetic text-to-speech placeholder voice.", ""]
    lines += ["Animations generated with Manim and Blender."]
    return _clean("\n".join(lines))[:DESCRIPTION_MAX]


def build_tags(spec: dict) -> list[str]:
    tags = list(BASE_TAGS)
    for s in sorted(spec.get("scenes", []), key=lambda s: s.get("sequence", 0)):
        t = TEMPLATE_TAGS.get(s.get("template"))
        if t and t not in tags:
            tags.append(t)
    out, total = [], 0
    for t in tags:
        if total + len(t) > TAGS_MAX_CHARS:
            break
        out.append(t)
        total += len(t)
    return out


def check_approval(out_dir: Path, final_sha256: str) -> dict:
    """Status of ``approval.json``: missing | invalid | not_approved | sha_mismatch | approved."""
    path = Path(out_dir) / APPROVAL_NAME
    if not path.is_file():
        return {"file": APPROVAL_NAME, "status": "missing",
                "message": f"no {APPROVAL_NAME}; the owner must approve this exact video (sha256 {final_sha256})"}
    doc = _load(path)
    required = ("approvedSha256", "reviewer", "decision", "timestamp")
    if not isinstance(doc, dict) or any(not isinstance(doc.get(k), str) or not doc.get(k) for k in required):
        return {"file": APPROVAL_NAME, "status": "invalid",
                "message": f"{APPROVAL_NAME} must be a JSON object with non-empty string fields {list(required)}"}
    if doc["decision"] != "approved":
        return {"file": APPROVAL_NAME, "status": "not_approved", "reviewer": doc["reviewer"],
                "message": f"decision is {doc['decision']!r}, not 'approved'"}
    if doc["approvedSha256"] != final_sha256:
        return {"file": APPROVAL_NAME, "status": "sha_mismatch", "reviewer": doc["reviewer"],
                "approvedSha256": doc["approvedSha256"],
                "message": "approval is for a different video (final.mp4 changed since it was approved)"}
    return {"file": APPROVAL_NAME, "status": "approved", "reviewer": doc["reviewer"], "timestamp": doc["timestamp"],
            "approvedSha256": doc["approvedSha256"], "message": "approved for this exact final.mp4"}


def _file_ref(out_dir: Path, name: str) -> dict | None:
    p = Path(out_dir) / name
    return {"file": name, "bytes": p.stat().st_size, "sha256": sha256_file(p)} if p.is_file() else None


def build_publish_plan(out_dir: Path) -> dict:
    """Everything a future uploader would send + why it would refuse. Raises PublishRefused on integrity errors."""
    out_dir = Path(out_dir)
    manifest = _load(out_dir / MANIFEST_NAME)
    spec = _load(out_dir / "episode.json")
    final = out_dir / "final.mp4"
    if manifest is None or spec is None or not final.is_file():
        raise PublishRefused(f"{out_dir} is not a rendered bundle (need {MANIFEST_NAME}, episode.json, final.mp4)")
    actual = sha256_file(final)
    if actual != manifest.get("finalVideoSha256"):
        raise PublishRefused(f"final.mp4 sha256 {actual} does not match manifest finalVideoSha256 "
                             f"{manifest.get('finalVideoSha256')} — the video changed after QA; re-render/re-QA")
    problems = verify_manifest(out_dir, manifest)
    if problems:
        raise PublishRefused("manifest verification failed: " + "; ".join(problems[:5]))

    qa = _load(out_dir / "qa_report.json") or {}
    compose = _load(out_dir / "compose.json")
    synthetic = bool((manifest.get("tts") or {}).get("isSyntheticPlaceholder"))
    chapters = build_chapters(spec, compose)
    approval = check_approval(out_dir, actual)
    media = (manifest.get("finalVideo") or {}).get("media") or {}

    made_for_kids = (spec.get("publishing") or {}).get("madeForKids")
    blockers = [REAL_UPLOAD_REFUSAL]
    if made_for_kids is None:
        blockers.append("audience not declared: set publishing.madeForKids in the episode spec")
    qa_status = qa.get("status")
    if qa_status is None:
        blockers.append("no qa_report.json")
    elif qa_status == "FAIL":
        blockers.append("QA status FAIL")
    elif qa.get("warnings"):
        blockers.append(f"QA {qa_status}: {len(qa['warnings'])} warning(s) need explicit human sign-off "
                        f"({', '.join(sorted({w['id'].split('.')[0] for w in qa['warnings']}))})")
    if manifest.get("profile") != "full":
        blockers.append(f"profile {manifest.get('profile')!r} is not publishable (render with --profile full)")
    if approval["status"] != "approved":
        blockers.append(f"approval {approval['status']}: {approval['message']}")
    if synthetic:
        blockers.append("narration is a synthetic placeholder voice (owner decision pending on production voice)")

    return {
        "schemaVersion": PLAN_SCHEMA,
        "mode": "dry_run",
        "target": "youtube",
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "networkCalls": 0,
        "uploaded": False,
        "wouldUpload": False,
        "blockers": blockers,
        "episodeId": spec.get("episodeId"),
        "runId": manifest.get("runId"),
        "video": {"file": "final.mp4", "sha256": actual, "bytes": final.stat().st_size,
                  "matchesManifest": True, "durationSeconds": media.get("duration_s"),
                  "resolution": f"{(media.get('video') or {}).get('width')}x{(media.get('video') or {}).get('height')}"},
        "snippet": {"title": build_title(spec), "description": build_description(spec, chapters, synthetic),
                    "tags": build_tags(spec), "categoryId": CATEGORY_EDUCATION,
                    "defaultLanguage": "en", "defaultAudioLanguage": "en"},
        "status": {"privacyStatus": "private", "embeddable": True, "license": "youtube",
                   "containsSyntheticMedia": synthetic,
                   "selfDeclaredMadeForKids": made_for_kids,
                   "_notes": ("madeForKids from the episode spec (publishing.madeForKids; owner decision)"
                              if made_for_kids is not None else
                              "selfDeclaredMadeForKids must be set by the owner before any real upload")},
        "captions": dict(_file_ref(out_dir, "captions.srt") or {"file": None}, language="en", name="English"),
        "thumbnail": _file_ref(out_dir, "thumbnail.png"),
        "chapters": chapters,
        "chaptersValidForYouTube": chapters_valid(chapters),
        "qa": {"status": qa_status, "warnings": len(qa.get("warnings") or []),
               "hardFailures": len(qa.get("failures") or [])},
        "approval": approval,
        "manifestPublish": manifest.get("publish"),
    }


def dry_run(out_dir: Path) -> dict:
    plan = build_publish_plan(out_dir)
    (Path(out_dir) / PLAN_NAME).write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return plan


def refuse_real_upload() -> str:
    return REAL_UPLOAD_REFUSAL


__all__ = ["APPROVAL_NAME", "PLAN_NAME", "PublishRefused", "build_publish_plan", "check_approval", "dry_run",
           "refuse_real_upload"]
