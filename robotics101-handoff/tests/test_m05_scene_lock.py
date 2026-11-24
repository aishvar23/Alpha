"""M05.8: single-scene previews and scene locks (approval file + stitch gate)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from robotics101 import cli
from robotics101.cartoon import approvals as A
from robotics101.cartoon import pipeline as P
from robotics101.cartoon import preview as PV

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


def _scene(text="Hello there."):
    spec = {"sceneId": "scene-002", "template": "cartoon_robot_family", "beats": [{"type": "line", "text": text}]}
    timing = {"sceneId": "scene-002", "scene_duration_s": 3.0,
              "beats": [{"index": 0, "type": "line", "text": text, "cacheKey": "k1", "start_s": 0.4, "end_s": 2.0}]}
    report = {"template": "cartoon_robot_family", "frames": 90, "duration_s": 3.0,
              "facts": {"shots": [{"visual": "example_toaster", "start": 0.3, "end": 2.3}]}}
    return spec, timing, report


def test_content_hash_is_deterministic_and_tracks_inputs_and_code():
    spec, timing, rep = _scene()
    a = A.scene_hashes(spec, timing, rep, code="c1")
    assert a == A.scene_hashes(spec, timing, rep, code="c1")
    b = A.scene_hashes(*_scene("Hello there!")[:2], rep, code="c1")
    assert b["inputsSha256"] != a["inputsSha256"] and b["codeSha256"] == a["codeSha256"]
    rep2 = json.loads(json.dumps(rep))
    rep2["facts"]["shots"][0]["end"] = 2.9               # a re-timed shot is a different scene
    assert A.scene_hashes(spec, timing, rep2, code="c1")["inputsSha256"] != a["inputsSha256"]
    c = A.scene_hashes(spec, timing, rep, code="c2")
    assert c["inputsSha256"] == a["inputsSha256"] and c["contentSha256"] != a["contentSha256"]


def test_code_fingerprint_ignores_qa_and_lock_modules():
    assert {"qa.py", "preview.py", "approvals.py"} <= A.CODE_EXCLUDE
    assert "scenes.py" not in A.CODE_EXCLUDE and "explainers.py" not in A.CODE_EXCLUDE


def test_approval_file_records_hash_and_date_and_stitch_gate(tmp_path):
    path = tmp_path / "scene_approvals.json"
    spec, timing, rep = _scene()
    h = A.scene_hashes(spec, timing, rep, code="c1")
    with pytest.raises(A.SceneLockError, match="not approved"):
        A.require_approved(path, {"scene-002": h}, ["scene-002"])
    when = datetime(2026, 11, 24, 20, 0, tzinfo=timezone.utc)
    rec = A.approve(path, "ep-001", "scene-002", h, frames_md5="abc", by="owner", now=when)
    doc = json.loads(path.read_text())
    assert doc["schemaVersion"] == A.APPROVALS_SCHEMA and doc["episodeId"] == "ep-001"
    assert doc["scenes"]["scene-002"]["contentSha256"] == h["contentSha256"] == rec["contentSha256"]
    assert doc["scenes"]["scene-002"]["approvedAt"] == "2026-11-24T20:00:00+00:00"
    A.require_approved(path, {"scene-002": h}, ["scene-002"])          # approved + unchanged: ok
    changed = A.scene_hashes(*_scene("Changed line.")[:2], rep, code="c1")
    with pytest.raises(A.SceneLockError, match="changed since approval \\(inputs"):
        A.require_approved(path, {"scene-002": changed}, ["scene-002"])
    probs = A.stitch_problems(A.load(path), {"scene-002": h}, ["scene-002", "scene-003"])
    assert probs == ["scene-003: not approved"]
    with pytest.raises(A.SceneLockError):
        A.approve(path, "ep-999", "scene-002", h)                       # file belongs to another episode


def test_code_only_change_with_identical_frames_carries_the_approval(tmp_path):
    path = tmp_path / "a.json"
    spec, timing, rep = _scene()
    old = A.scene_hashes(spec, timing, rep, code="c1")
    A.approve(path, "ep-001", "scene-002", old, frames_md5="same")
    new = A.scene_hashes(spec, timing, rep, code="c2")
    assert not A.carry_over(path, "scene-002", new, "different")      # pixels changed: re-approve
    assert A.carry_over(path, "scene-002", new, "same")
    A.require_approved(path, {"scene-002": new}, ["scene-002"])
    other = A.scene_hashes(*_scene("New words.")[:2], rep, code="c2")
    assert not A.carry_over(path, "scene-002", other, "same")         # inputs changed: never carried


def test_full_stitch_refuses_unapproved_scenes_before_rendering(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "default_path", lambda eid: tmp_path / "none.json")
    with pytest.raises(P.CartoonPipelineError, match="scenes not approved") as e:
        P.render_cartoon_episode(CARTOON, tmp_path / "o", tts="fixture", size="854x480", log=lambda m: None)
    assert e.value.code == 6
    assert not (tmp_path / "o" / "timing.json").exists()               # nothing voiced or rendered


def test_cli_override_flag_reaches_the_pipeline(tmp_path, monkeypatch):
    seen = {}

    def fake(episode, out, tts="auto", size="", log=print, **kw):
        seen.update(kw)
        raise P.CartoonPipelineError("stop", 7)
    monkeypatch.setattr(P, "render_cartoon_episode", fake)
    assert cli.main(["render", str(CARTOON), "--out", str(tmp_path), "--allow-unapproved"]) == 7
    assert seen["allow_unapproved"] is True


def test_cli_scene_preview_routing_and_flag_checks(tmp_path, monkeypatch, capsys):
    assert cli.main(["render", str(CARTOON), "--out", str(tmp_path), "--scene", "scene-002"]) != 0
    assert "--preview" in capsys.readouterr().err
    seen = {}

    def fake(episode, out, ids, tts="auto", approvals_path=None, log=print):
        seen.update(ids=ids, tts=tts)
        return {sid: {"clip": f"{out}/scenes/{sid}-preview.mp4", "duration": 1.0,
                      "qa": {"status": "PASS", "checks": [{"id": "sync.visual_narration", "status": "pass"}]}}
                for sid in ids}
    monkeypatch.setattr(PV, "render_scene_previews", fake)
    rc = cli.main(["render", str(CARTOON), "--out", str(tmp_path), "--scene", "scene-002", "--scene", "scene-003",
                   "--preview", "--tts", "elevenlabs"])
    assert rc == 0 and seen == {"ids": ["scene-002", "scene-003"], "tts": "elevenlabs"}
    assert "scene-003-preview.mp4" in capsys.readouterr().out


def test_preview_refuses_any_billable_synthesis(tmp_path, monkeypatch):
    from robotics101.voice import dialogue as D
    monkeypatch.setattr(D, "cost_summary", lambda plans, backend: {"lines": 2, "cachedLines": 1, "charsTotal": 40,
                                                                   "billableChars": 20, "provider": "x"})
    with pytest.raises(PV.PreviewError, match="cached audio only"):
        PV.render_scene_previews(CARTOON, tmp_path, ["scene-002"], tts="fixture", log=lambda m: None)
    assert not (tmp_path / "timing.json").exists()


def test_preview_rejects_unknown_scene(tmp_path):
    with pytest.raises(P.CartoonPipelineError, match="unknown scene"):
        PV.render_scene_previews(CARTOON, tmp_path, ["scene-999"], tts="fixture", log=lambda m: None)


def test_scene_offsets_follow_the_composed_timeline():
    t = {"scenes": [{"sceneId": "a", "scene_duration_s": 1.01}, {"sceneId": "b", "scene_duration_s": 2.0}]}
    off = PV.scene_offsets(t)
    assert off["a"] == (0.0, 1.0) and off["b"] == (1.0, 2.0)


def test_approve_from_preview_requires_matching_preview(tmp_path, monkeypatch):
    with pytest.raises(PV.PreviewError, match="no preview"):
        PV.approve_from_preview(tmp_path, "scene-002")
    (tmp_path / "scenes").mkdir()
    (tmp_path / "episode.json").write_text(json.dumps({"episodeId": "ep-001"}))
    rec = {"hashes": {"inputsSha256": "i", "codeSha256": "c", "contentSha256": "x"}, "previewFramesMd5": "m"}
    (tmp_path / "scenes" / "scene-002-preview.json").write_text(json.dumps(rec))
    monkeypatch.setattr(A, "bundle_scene_hashes", lambda out, only=None: {"scene-002": {**rec["hashes"], "contentSha256": "y"}})
    with pytest.raises(PV.PreviewError, match="changed since its preview"):
        PV.approve_from_preview(tmp_path, "scene-002", approvals_path=tmp_path / "a.json")
    monkeypatch.setattr(A, "bundle_scene_hashes", lambda out, only=None: {"scene-002": rec["hashes"]})
    out = PV.approve_from_preview(tmp_path, "scene-002", by="tester", approvals_path=tmp_path / "a.json")
    assert out["approvedBy"] == "tester" and out["previewFramesMd5"] == "m"
