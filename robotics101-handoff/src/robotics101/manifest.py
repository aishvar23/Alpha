"""SHA-256 artifact manifest for an episode bundle (M01.5).

``manifest.json`` lists every artifact with its bundle-relative path, SHA-256, size and (for media) an
ffprobe summary. ``finalVideoSha256`` is the hash a future human approval must bind to; the bundle is
always ``publish.status = "not_published"`` here — nothing in M01 publishes or uploads.

The QA reports are hashed into the manifest *after* QA ran (QA itself verifies every other entry), so
``verify_manifest`` skips the ``qa_report`` role by default to avoid a circular dependency.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from robotics101.media import MediaError, sha256_file, summarize

MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = "robotics101.manifest/1"
SELF_REFERENTIAL_ROLES = frozenset({"qa_report"})
MEDIA_SUFFIXES = {".mp4", ".wav"}


def new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"


def collect_artifacts(out_dir: Path, scene_ids: list[str]) -> list[tuple[str, str, str | None]]:
    """(relative path, role, sceneId) for every artifact the pipeline is expected to have produced."""
    items: list[tuple[str, str, str | None]] = [("episode.json", "spec", None), ("timing.json", "timing", None)]
    for sid in scene_ids:
        items.append((f"audio/{sid}.wav", "narration_audio", sid))
    for sid in scene_ids:
        items.append((f"scenes/{sid}.mp4", "scene_video", sid))
    for sid in scene_ids:
        items.append((f"clips/{sid}.mp4", "scene_clip", sid))
    items += [("final.mp4", "final_video", None), ("captions.srt", "captions", None),
              ("compose.json", "compose_report", None)]
    if (Path(out_dir) / "scenes" / "render-report.json").is_file():
        items.append(("scenes/render-report.json", "render_report", None))
    return items


def artifact_entry(out_dir: Path, rel: str, role: str, scene_id: str | None, probe: bool = True) -> dict:
    p = Path(out_dir) / rel
    entry: dict = {"path": rel, "role": role}
    if scene_id:
        entry["sceneId"] = scene_id
    entry["bytes"] = p.stat().st_size
    entry["sha256"] = sha256_file(p)
    if probe and p.suffix in MEDIA_SUFFIXES:
        try:
            entry["media"] = summarize(p).to_dict()
        except MediaError as e:
            entry["media"] = {"error": str(e)}
    return entry


def build_manifest(out_dir: Path, spec: dict, profile: str, timing: dict, *, run_id: str,
                   tool_versions: dict, probe: bool = True) -> dict:
    """Hash every artifact (missing ones raise FileNotFoundError: a manifest must be complete)."""
    out_dir = Path(out_dir)
    scene_ids = [s["sceneId"] for s in sorted(spec["scenes"], key=lambda s: s["sequence"])]
    missing = [rel for rel, _, _ in collect_artifacts(out_dir, scene_ids) if not (out_dir / rel).is_file()]
    if missing:
        raise FileNotFoundError(f"cannot build manifest, missing artifacts: {missing}")
    artifacts = [artifact_entry(out_dir, rel, role, sid, probe) for rel, role, sid in collect_artifacts(out_dir, scene_ids)]
    final = next(a for a in artifacts if a["role"] == "final_video")
    spec_entry = next(a for a in artifacts if a["role"] == "spec")
    synthetic = any(s.get("is_synthetic_placeholder") for s in timing.get("scenes", []))
    return {
        "schemaVersion": SCHEMA_VERSION,
        "episodeId": spec["episodeId"],
        "title": spec.get("title"),
        "runId": run_id,
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "profile": profile,
        "specSha256": spec_entry["sha256"],
        "finalVideoSha256": final["sha256"],
        "finalVideo": {"path": final["path"], "bytes": final["bytes"], "media": final.get("media")},
        "tts": {"provider": timing.get("provider"), "labels": timing.get("providerLabels", []),
                "isSyntheticPlaceholder": synthetic},
        "toolVersions": tool_versions,
        "publish": {"status": "not_published", "requiresApprovalOfSha256": final["sha256"]},
        "qa": None,
        "artifacts": artifacts,
    }


def attach_qa(manifest: dict, out_dir: Path, qa_status: str, report_paths: list[str]) -> dict:
    """Add/replace the QA report entries (hashed after QA wrote them) and the QA status."""
    manifest["artifacts"] = [a for a in manifest["artifacts"] if a["role"] not in SELF_REFERENTIAL_ROLES]
    entries = [artifact_entry(out_dir, rel, "qa_report", None, probe=False) for rel in report_paths]
    manifest["artifacts"] += entries
    manifest["qa"] = {"status": qa_status, "reports": {e["path"]: e["sha256"] for e in entries}}
    return manifest


def write_manifest(out_dir: Path, manifest: dict) -> Path:
    path = Path(out_dir) / MANIFEST_NAME
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_manifest(out_dir: Path) -> dict:
    return json.loads((Path(out_dir) / MANIFEST_NAME).read_text(encoding="utf-8"))


def verify_manifest(out_dir: Path, manifest: dict | None = None,
                    skip_roles: frozenset[str] = SELF_REFERENTIAL_ROLES) -> list[str]:
    """Problems (empty == every listed artifact exists with the recorded size and SHA-256)."""
    out_dir = Path(out_dir)
    manifest = manifest if manifest is not None else load_manifest(out_dir)
    problems: list[str] = []
    root = out_dir.resolve()
    by_role: dict[str, str] = {}
    for a in manifest.get("artifacts", []):
        rel = a.get("path", "")
        p = (out_dir / rel).resolve()
        if Path(rel).is_absolute() or root not in p.parents:
            problems.append(f"{rel}: path escapes the bundle")
            continue
        if a.get("role") in ("final_video", "spec"):
            by_role[a["role"]] = a.get("sha256", "")
        if a.get("role") in skip_roles:
            continue
        if not p.is_file():
            problems.append(f"{rel}: missing")
            continue
        size = p.stat().st_size
        if size != a.get("bytes"):
            problems.append(f"{rel}: size {size} != manifest {a.get('bytes')}")
        digest = sha256_file(p)
        if digest != a.get("sha256"):
            problems.append(f"{rel}: sha256 {digest[:12]}… != manifest {str(a.get('sha256'))[:12]}…")
    final = by_role.get("final_video")
    if not final:
        problems.append("manifest lists no final_video artifact")
    else:
        if manifest.get("finalVideoSha256") != final:
            problems.append("finalVideoSha256 does not match the final_video artifact hash")
        pub = manifest.get("publish") or {}
        if pub.get("requiresApprovalOfSha256") != final:
            problems.append("publish.requiresApprovalOfSha256 does not match the final video hash")
        if pub.get("status") != "not_published":
            problems.append(f"publish.status is {pub.get('status')!r}; M01 bundles must be 'not_published'")
    if by_role.get("spec") and manifest.get("specSha256") != by_role["spec"]:
        problems.append("specSha256 does not match the spec artifact hash")
    return problems
