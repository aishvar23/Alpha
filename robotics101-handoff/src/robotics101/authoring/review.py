"""Human review points R1/R2/R3 and their hash-bound approvals (PLAN-authoring §7).

A packet ``review/R1.json`` / ``review/R2.json`` lists the reviewed artifacts with their SHA-256; R2 also records
the R1 packet hash, so any change to an R1 artifact voids R1 *and* R2. An approval record
``review/R1.approval.json`` = ``{point, approvedSha256 (packet hash), reviewer, decision, timestamp, notes}`` is
checked with the semantics of ``publish/youtube_stub.check_approval``:
missing | invalid | not_approved | sha_mismatch | approved. R3 is the existing ``approval.json`` bound to the final
video. Approvals come from the owner's own words relayed by Grok Bot — this module never writes one by itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from robotics101.authoring.schemas import canonical, errors, sha256_bytes, sha256_file

POINTS = {
    "R1": ("outline.json", "facts.json", "sources.json"),
    "R2": ("episode.source.json", "visual_bindings.json", "visual_gaps.json", "authoring_report.json"),
}
STATUSES = ("missing", "invalid", "not_approved", "sha_mismatch", "stale_chain", "approved")


def packet(run_dir: Path, point: str) -> dict:
    run_dir = Path(run_dir)
    if point not in POINTS:
        raise ValueError(f"unknown review point {point!r} (R1, R2; R3 is approval.json on the final video)")
    arts = {}
    for name in POINTS[point]:
        p = run_dir / name
        if not p.is_file():
            raise FileNotFoundError(f"{point} packet needs {name} in {run_dir}")
        arts[name] = sha256_file(p)
    doc = {"point": point, "runId": run_dir.name, "artifacts": arts, "previous": None}
    if point == "R2":
        doc["previous"] = {"point": "R1", "packetSha256": packet_sha256(packet(run_dir, "R1"))}
    return doc


def packet_sha256(doc: dict) -> str:
    return sha256_bytes(canonical(doc))


def write_packet(run_dir: Path, point: str) -> tuple[Path, str]:
    doc = packet(run_dir, point)
    path = Path(run_dir) / "review" / f"{point}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical(doc))
    return path, packet_sha256(doc)


def approval_path(run_dir: Path, point: str) -> Path:
    return Path(run_dir) / "review" / f"{point}.approval.json"


def check_review(run_dir: Path, point: str) -> dict:
    """Status of one review point against the *current* artifacts (re-hashed now)."""
    run_dir = Path(run_dir)
    try:
        cur = packet_sha256(packet(run_dir, point))
    except FileNotFoundError as e:
        return {"point": point, "status": "missing", "message": str(e)}
    path = approval_path(run_dir, point)
    if not path.is_file():
        return {"point": point, "status": "missing", "packetSha256": cur,
                "message": f"no {path.name}; the owner must approve packet {cur}"}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        doc = None
    errs = errors("review_approval", doc) if isinstance(doc, dict) else ["not a JSON object"]
    if errs or doc.get("point") != point:
        return {"point": point, "status": "invalid", "message": "; ".join(errs) or f"point {doc.get('point')!r}"}
    if doc["decision"] != "approved":
        return {"point": point, "status": "not_approved", "reviewer": doc["reviewer"],
                "message": f"decision is {doc['decision']!r}"}
    if doc["approvedSha256"] != cur:
        return {"point": point, "status": "sha_mismatch", "reviewer": doc["reviewer"], "packetSha256": cur,
                "approvedSha256": doc["approvedSha256"],
                "message": "an artifact changed since this review was approved"}
    if point == "R2":
        r1 = check_review(run_dir, "R1")
        if r1["status"] != "approved":
            return {"point": point, "status": "stale_chain", "message": f"R1 is {r1['status']}: an R1 change voids R2"}
    return {"point": point, "status": "approved", "reviewer": doc["reviewer"], "timestamp": doc["timestamp"],
            "packetSha256": cur}


def check_r3(bundle_dir: Path) -> dict:
    from robotics101.publish.youtube_stub import check_approval
    final = Path(bundle_dir) / "final.mp4"
    if not final.is_file():
        return {"point": "R3", "status": "missing", "message": "no final.mp4"}
    return {"point": "R3", **check_approval(bundle_dir, sha256_file(final))}


def render_allowed(run_dir: Path, allow_draft: bool = False) -> tuple[bool, str]:
    """``render`` of an authored spec needs R1 + R2 at current hashes; ``--allow-unapproved-draft`` → draft."""
    r1, r2 = check_review(run_dir, "R1"), check_review(run_dir, "R2")
    if r1["status"] == r2["status"] == "approved":
        return True, "approved"
    if allow_draft:
        return True, "draft"
    return False, f"R1 {r1['status']}, R2 {r2['status']}"


__all__ = ["POINTS", "STATUSES", "approval_path", "check_r3", "check_review", "packet", "packet_sha256",
           "render_allowed", "write_packet"]
