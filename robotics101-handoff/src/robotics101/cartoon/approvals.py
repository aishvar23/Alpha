"""M05.8 scene locks: review goes scene by scene, and a full episode is only stitched from approved scenes.

A scene's **content hash** covers everything that decides what the scene looks and sounds like:

* ``inputsSha256`` — the expanded scene spec, the scene's voice timeline (line texts, ElevenLabs cache keys, beat
  and word timings) and the render plan the renderer recorded in ``scenes.json`` (shots and their windows,
  concept cards, background, keepouts, illustration regions, cut-aways);
* ``codeSha256`` — the cartoon renderer sources + character registry (drawing code; QA / preview / lock modules
  are excluded because they never change a frame).

``contentSha256 = sha256(inputsSha256 + codeSha256)``. The approval file (default
``approvals/<episodeId>/scene_approvals.json``) records per scene: content hash, the two parts, the preview clip's
decoded-frame MD5, the approval time (UTC) and who approved. Stitching refuses unless every scene of the episode is
approved and its content hash still matches (``--allow-unapproved`` is the explicit dev override). If only the
code changed and a fresh preview's frames are byte-identical to the approved preview, the approval carries over
(the renderer change didn't touch that scene).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APPROVALS_SCHEMA = "robotics101.scene_approvals/1"
CODE_DIR = Path(__file__).resolve().parent
REGISTRY = ROOT / "characters" / "registry.json"
_PLAN_KEYS = ("template", "frames", "duration_s", "background", "keepouts", "illustrations", "facts", "cutaways",
              "enterAt")


class SceneLockError(RuntimeError):
    pass


def _canon(x) -> bytes:
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# measurement / bookkeeping modules that never change a rendered frame (QA, previews, locks)
CODE_EXCLUDE = {"qa.py", "preview.py", "approvals.py", "lint.py"}


def code_sha256() -> str:
    h = hashlib.sha256()
    for p in sorted(CODE_DIR.glob("*.py")):
        if p.name in CODE_EXCLUDE:
            continue
        h.update(p.name.encode())
        h.update(p.read_bytes())
    for p in sorted((CODE_DIR / "kit").glob("*.py")):            # A4-A6: the visual kit draws frames too
        h.update(f"kit/{p.name}".encode())
        h.update(p.read_bytes())
    if REGISTRY.is_file():
        h.update(REGISTRY.read_bytes())
    return h.hexdigest()


def _timing_view(ts: dict, voice_dir: Path | None) -> dict:
    beats = []
    for b in ts["beats"]:
        e = {k: v for k, v in b.items() if k not in ("wav", "words")}
        if b.get("words") and voice_dir is not None and (Path(voice_dir) / b["words"]).is_file():
            e["wordsSha256"] = _sha((Path(voice_dir) / b["words"]).read_bytes())
        beats.append(e)
    return {"sceneId": ts["sceneId"], "duration": ts["scene_duration_s"], "beats": beats}


def _plan_view(report: dict) -> dict:
    out = {k: report.get(k) for k in _PLAN_KEYS}
    cut = []
    for c in out.get("cutaways") or []:
        cut.append({k: v for k, v in c.items() if k != "clip"})
    out["cutaways"] = cut
    return out


def scene_hashes(spec_scene: dict, timing_scene: dict, scene_report: dict, voice_dir: Path | None = None,
                 code: str | None = None) -> dict:
    inputs = _sha(_canon({"spec": spec_scene, "timing": _timing_view(timing_scene, voice_dir),
                          "plan": _plan_view(scene_report)}))
    code = code or code_sha256()
    return {"inputsSha256": inputs, "codeSha256": code, "contentSha256": _sha((inputs + code).encode())}


def bundle_scene_hashes(out_dir: Path, only: list[str] | None = None) -> dict[str, dict]:
    out_dir = Path(out_dir)
    spec = json.loads((out_dir / "episode.json").read_text(encoding="utf-8"))
    timing = json.loads((out_dir / "timing.json").read_text(encoding="utf-8"))
    sj = json.loads((out_dir / "scenes.json").read_text(encoding="utf-8"))
    by_spec = {s["sceneId"]: s for s in spec["scenes"]}
    by_rep = {s["sceneId"]: s for s in sj["scenes"]}
    code = code_sha256()
    res = {}
    for ts in timing["scenes"]:
        sid = ts["sceneId"]
        if (only and sid not in only) or sid not in by_rep:
            continue
        res[sid] = scene_hashes(by_spec[sid], ts, by_rep[sid], out_dir, code)
    return res


def default_path(episode_id: str) -> Path:
    return ROOT / "approvals" / episode_id / "scene_approvals.json"


def load(path: Path, episode_id: str | None = None) -> dict:
    path = Path(path)
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        doc = {"schemaVersion": APPROVALS_SCHEMA, "episodeId": episode_id, "scenes": {}}
    doc.setdefault("scenes", {})
    return doc


def save(path: Path, doc: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def approve(path: Path, episode_id: str, scene_id: str, hashes: dict, *, frames_md5: str | None = None,
            preview_sha256: str | None = None, by: str = "owner", note: str | None = None,
            now: datetime | None = None) -> dict:
    doc = load(path, episode_id)
    if doc.get("episodeId") not in (None, episode_id):
        raise SceneLockError(f"{path} belongs to episode {doc['episodeId']}, not {episode_id}")
    doc["episodeId"] = episode_id
    rec = {**hashes, "approvedAt": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
           "approvedBy": by}
    if frames_md5:
        rec["previewFramesMd5"] = frames_md5
    if preview_sha256:
        rec["previewSha256"] = preview_sha256
    if note:
        rec["note"] = note
    doc["scenes"][scene_id] = rec
    save(path, doc)
    return rec


def stitch_problems(approvals: dict, current: dict[str, dict], scene_ids: list[str]) -> list[str]:
    """Why the episode can't be stitched: a scene without an approval or whose content hash changed."""
    out = []
    recs = approvals.get("scenes") or {}
    for sid in scene_ids:
        rec = recs.get(sid)
        if rec is None:
            out.append(f"{sid}: not approved")
            continue
        cur = current.get(sid)
        if cur is None:
            out.append(f"{sid}: not rendered")
            continue
        if rec.get("contentSha256") != cur["contentSha256"]:
            what = [k[:-6] for k in ("inputsSha256", "codeSha256") if rec.get(k) != cur.get(k)]
            out.append(f"{sid}: changed since approval ({', '.join(what) or 'content'}; approved "
                       f"{rec.get('approvedAt')}) — re-preview and re-approve")
    return out


def require_approved(approvals_path: Path, current: dict[str, dict], scene_ids: list[str]) -> None:
    probs = stitch_problems(load(approvals_path), current, scene_ids)
    if probs:
        raise SceneLockError("refusing to stitch the episode: " + "; ".join(probs)
                             + f" (approvals: {approvals_path}; dev override: --allow-unapproved)")


def carry_over(path: Path, scene_id: str, hashes: dict, frames_md5: str | None) -> bool:
    """Code-only change with byte-identical preview frames keeps the approval (refreshes its hash)."""
    doc = load(path)
    rec = (doc.get("scenes") or {}).get(scene_id)
    if not rec or not frames_md5 or rec.get("contentSha256") == hashes["contentSha256"]:
        return False
    if rec.get("inputsSha256") == hashes["inputsSha256"] and rec.get("previewFramesMd5") == frames_md5:
        rec.update(hashes)
        rec["carriedOverAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save(path, doc)
        return True
    return False


__all__ = ["APPROVALS_SCHEMA", "SceneLockError", "approve", "bundle_scene_hashes", "carry_over", "code_sha256",
           "default_path", "load", "require_approved", "save", "scene_hashes", "stitch_problems"]
