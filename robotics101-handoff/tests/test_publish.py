"""M01.6: YouTube publisher stub (dry run only) + thumbnail."""

import ast
import json
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

from robotics101.cli import main
from robotics101.compose.thumbnail import make_thumbnail, pick_thumbnail_time, thumbnail_filter, thumbnail_title
from robotics101.media import sha256_file, summarize
from robotics101.publish import PLAN_NAME, PublishRefused, build_publish_plan, check_approval, dry_run

ROOT = Path(__file__).resolve().parents[1]
HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")


def make_bundle(root: Path, spec: dict, *, profile: str = "full", qa_status: str = "PASS_WITH_WARNINGS") -> Path:
    """Minimal bundle the stub can plan: final.mp4 (bytes only), episode.json, compose.json, manifest, QA."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "final.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 8)
    (root / "episode.json").write_text(json.dumps(spec), encoding="utf-8")
    (root / "captions.srt").write_text("1\n00:00:00,500 --> 00:00:02,000\nHello.\n", encoding="utf-8")
    t, segs = 0.0, []
    for s in sorted(spec["scenes"], key=lambda s: s["sequence"]):
        d = float(s["durationTargetSeconds"])
        segs.append({"sceneId": s["sceneId"], "start_s": t, "end_s": t + d})
        t += d
    (root / "compose.json").write_text(json.dumps({"segments": segs}), encoding="utf-8")
    (root / "qa_report.json").write_text(json.dumps({
        "status": qa_status, "warnings": [{"id": "tts.production_voice"}], "failures": []}), encoding="utf-8")
    final_sha, spec_sha = sha256_file(root / "final.mp4"), sha256_file(root / "episode.json")
    manifest = {
        "schemaVersion": "robotics101.manifest/1", "episodeId": spec["episodeId"], "runId": "run-test",
        "profile": profile, "specSha256": spec_sha, "finalVideoSha256": final_sha,
        "finalVideo": {"path": "final.mp4", "media": {"duration_s": t, "video": {"width": 1920, "height": 1080}}},
        "tts": {"provider": "espeak", "isSyntheticPlaceholder": True},
        "publish": {"status": "not_published", "requiresApprovalOfSha256": final_sha},
        "artifacts": [
            {"path": "episode.json", "role": "spec", "bytes": (root / "episode.json").stat().st_size, "sha256": spec_sha},
            {"path": "final.mp4", "role": "final_video", "bytes": (root / "final.mp4").stat().st_size,
             "sha256": final_sha},
        ],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def approve(root: Path, sha: str | None = None, decision: str = "approved") -> None:
    (root / "approval.json").write_text(json.dumps({
        "approvedSha256": sha or sha256_file(root / "final.mp4"), "reviewer": "owner",
        "decision": decision, "timestamp": "2026-11-22T20:00:00Z"}), encoding="utf-8")


def test_dry_run_writes_plan_with_metadata_and_blockers(spec, tmp_path):
    b = make_bundle(tmp_path / "b", spec)
    plan = dry_run(b)
    on_disk = json.loads((b / PLAN_NAME).read_text())
    assert on_disk["video"]["sha256"] == plan["video"]["sha256"] == sha256_file(b / "final.mp4")
    assert plan["mode"] == "dry_run" and plan["uploaded"] is False and plan["wouldUpload"] is False
    assert plan["networkCalls"] == 0
    assert plan["snippet"]["title"] == "Robotics 101 · Ep. 1: What Is a Robot?"
    assert len(plan["snippet"]["title"]) <= 100 and "<" not in plan["snippet"]["description"]
    assert plan["snippet"]["categoryId"] == "27" and "robotics" in plan["snippet"]["tags"]
    assert sum(len(t) for t in plan["snippet"]["tags"]) <= 500
    assert plan["status"]["privacyStatus"] == "private" and plan["status"]["containsSyntheticMedia"] is True
    assert plan["captions"]["file"] == "captions.srt" and plan["thumbnail"] is None
    assert [c["timestamp"] for c in plan["chapters"]][:2] == ["0:00", "0:30"]
    assert plan["chaptersValidForYouTube"] is True
    assert "0:00 Intro: robots in everyday life" in plan["snippet"]["description"]
    assert plan["approval"]["status"] == "missing"
    assert any("not implemented (M06)" in x for x in plan["blockers"])
    assert any(x.startswith("approval missing") for x in plan["blockers"])


def test_approval_states(spec, tmp_path):
    b = make_bundle(tmp_path / "b", spec)
    sha = sha256_file(b / "final.mp4")
    assert check_approval(b, sha)["status"] == "missing"
    (b / "approval.json").write_text("{not json", encoding="utf-8")
    assert check_approval(b, sha)["status"] == "invalid"
    approve(b, decision="rejected")
    assert check_approval(b, sha)["status"] == "not_approved"
    approve(b, sha="0" * 64)
    assert check_approval(b, sha)["status"] == "sha_mismatch"
    approve(b)
    assert check_approval(b, sha)["status"] == "approved"
    plan = build_publish_plan(b)
    # even fully approved, the stub never uploads
    assert plan["approval"]["status"] == "approved" and plan["wouldUpload"] is False and plan["uploaded"] is False
    assert not any(x.startswith("approval") for x in plan["blockers"])


def test_one_byte_change_in_final_invalidates_bundle_and_approval(spec, tmp_path):
    b = make_bundle(tmp_path / "b", spec)
    approve(b)
    data = bytearray((b / "final.mp4").read_bytes())
    data[100] ^= 1
    (b / "final.mp4").write_bytes(bytes(data))
    with pytest.raises(PublishRefused, match="does not match manifest"):
        build_publish_plan(b)
    assert check_approval(b, sha256_file(b / "final.mp4"))["status"] == "sha_mismatch"
    assert main(["publish", str(b), "--dry-run"]) == 6
    assert not (b / PLAN_NAME).exists()


def test_tampered_publish_state_refused(spec, tmp_path):
    b = make_bundle(tmp_path / "b", spec)
    m = json.loads((b / "manifest.json").read_text())
    m["publish"]["status"] = "published"
    (b / "manifest.json").write_text(json.dumps(m))
    with pytest.raises(PublishRefused, match="not_published"):
        build_publish_plan(b)


def test_preview_and_qa_fail_are_blockers(spec, tmp_path):
    plan = build_publish_plan(make_bundle(tmp_path / "p", spec, profile="preview", qa_status="FAIL"))
    assert "QA status FAIL" in plan["blockers"]
    assert any("not publishable" in x for x in plan["blockers"])


def test_cli_without_dry_run_refuses_and_writes_nothing(spec, tmp_path, capsys):
    b = make_bundle(tmp_path / "b", spec)
    approve(b)
    assert main(["publish", str(b)]) == 6
    assert "real upload not implemented (M06)" in capsys.readouterr().err
    assert not (b / PLAN_NAME).exists()


def test_cli_dry_run_ok_and_missing_bundle(spec, tmp_path, capsys):
    b = make_bundle(tmp_path / "b", spec)
    assert main(["publish", str(b), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "nothing uploaded" in out and (b / PLAN_NAME).is_file()
    assert main(["publish", str(tmp_path / "nope"), "--dry-run"]) == 2
    (tmp_path / "empty").mkdir()
    assert main(["publish", str(tmp_path / "empty"), "--dry-run"]) == 6


def test_dry_run_makes_no_network_calls(spec, tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access attempted")
    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    dry_run(make_bundle(tmp_path / "b", spec))


def test_publish_package_imports_no_network_or_google_libs():
    banned = {"socket", "urllib", "http", "requests", "httpx", "google", "googleapiclient", "oauth2client",
              "google_auth_oauthlib", "ssl", "aiohttp"}
    for py in (ROOT / "src" / "robotics101" / "publish").glob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in banned, (py.name, n)


# ---------------------------------------------------------------- thumbnail

def test_thumbnail_time_prefers_blender_scene(spec):
    segs, t = [], 0.0
    for s in spec["scenes"]:
        segs.append({"sceneId": s["sceneId"], "start_s": t, "end_s": t + s["durationTargetSeconds"]})
        t += s["durationTargetSeconds"]
    assert pick_thumbnail_time(spec, segs) == 240.0          # scene-006 starts at 230 s
    for s in spec["scenes"]:
        s["engine"] = "manim"
    assert pick_thumbnail_time(spec, segs) == 150.0
    assert thumbnail_title(spec) == "Ep. 1: What Is a Robot?"
    vf = thumbnail_filter("It's 50%: ok", "/f/Inter.ttf")
    assert "scale=1280:720" in vf and "drawtext" in vf and "\\:" in vf and "\\%" in vf
    assert "drawtext" not in thumbnail_filter("x", None)


@needs_ffmpeg
def test_make_thumbnail_real(tmp_path):
    src = tmp_path / "v.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30:duration=2",
                    "-pix_fmt", "yuv420p", str(src)], check=True)
    png = make_thumbnail(src, tmp_path / "thumbnail.png", "Ep. 1: What Is a Robot?", 1.0)
    v = summarize(png).video
    assert (v["width"], v["height"]) == (1280, 720)


def test_made_for_kids_comes_from_spec(spec, tmp_path):
    plan = build_publish_plan(make_bundle(tmp_path / "a", spec))       # v1.0 spec: undeclared audience
    assert plan["status"]["selfDeclaredMadeForKids"] is None
    assert any(x.startswith("audience not declared") for x in plan["blockers"])
    cartoon = json.loads((Path(__file__).resolve().parents[1] / "examples" / "episode-001-cartoon.json").read_text())
    plan = build_publish_plan(make_bundle(tmp_path / "b", cartoon))
    assert plan["status"]["selfDeclaredMadeForKids"] is True
    assert not any(x.startswith("audience not declared") for x in plan["blockers"])
    assert plan["wouldUpload"] is False and plan["networkCalls"] == 0
