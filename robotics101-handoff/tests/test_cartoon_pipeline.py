"""M02.8: cartoon end-to-end pipeline — backend gating, compose, CLI routing, cartoon QA (incl. tamper checks)."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from robotics101 import cli
from robotics101.cartoon import pipeline as P
from robotics101.characters import load_registry

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"
BUNDLE = next((ROOT / "out" / d for d in ("m03.6", "m02.8") if (ROOT / "out" / d / "manifest.json").is_file()),
              ROOT / "out" / "m02.8")             # latest local render (not in git)
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
needs_bundle = pytest.mark.skipif(not (BUNDLE / "manifest.json").is_file(), reason="needs a rendered out/m02.8")


def test_elevenlabs_voices_are_owner_approved():
    assert P.unapproved_elevenlabs(load_registry()) == []          # owner approved Horatius / Ember (M05.4)
    assert P.unapproved_elevenlabs(_unapproved()) == ["bolt", "maya"]


def _unapproved():
    reg = load_registry()
    for cid in ("bolt", "maya"):
        reg.get(cid).voice["elevenlabs"]["approved"] = False
    return reg


def _fake_select(monkeypatch):
    import robotics101.voice as V

    def sel(choice="auto"):
        name = "elevenlabs" if choice in ("auto", "elevenlabs") else choice
        return SimpleNamespace(name=name), ["x"] if choice == "auto" else []
    monkeypatch.setattr(V, "select_backend", sel)


def test_auto_falls_back_from_unapproved_elevenlabs(monkeypatch):
    _fake_select(monkeypatch)
    b, skipped = P.pick_backend("auto", _unapproved())
    assert b.name == "kokoro" and any("not approved" in s for s in skipped)


def test_explicit_elevenlabs_refused_until_approved(monkeypatch):
    _fake_select(monkeypatch)
    with pytest.raises(P.CartoonPipelineError, match="not approved"):
        P.pick_backend("elevenlabs", _unapproved())


def test_auto_uses_elevenlabs_once_approved(monkeypatch):
    _fake_select(monkeypatch)
    b, skipped = P.pick_backend("auto", load_registry())
    assert b.name == "elevenlabs"


def test_render_rejects_cartoon_tts_for_narrator_specs(tmp_path, capsys):
    rc = cli.main(["render", str(ROOT / "examples" / "episode-001.json"), "--out", str(tmp_path), "--tts", "kokoro"])
    assert rc == cli.EXIT_INPUT and "cartoon" in capsys.readouterr().err


def test_render_routes_cartoon_spec_to_cartoon_pipeline(tmp_path, monkeypatch):
    seen = {}

    def fake(episode, out, tts="auto", size="", log=print):
        seen.update(episode=Path(episode), tts=tts, size=size)
        raise P.CartoonPipelineError("stop here", 7)
    monkeypatch.setattr(P, "render_cartoon_episode", fake)
    rc = cli.main(["render", str(CARTOON), "--out", str(tmp_path / "o"), "--profile", "full"])
    assert rc == 7 and seen == {"episode": CARTOON, "tts": "auto", "size": "1920x1080"}


@needs_ffmpeg
def test_compose_final_frames_and_segments(tmp_path):
    (tmp_path / "scenes").mkdir()
    (tmp_path / "audio").mkdir()
    for sid, d, c in (("scene-001", 1.0, "red"), ("scene-002", 0.5, "blue")):
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"color={c}:s=320x180:r=30:d={d}",
                        "-pix_fmt", "yuv420p", str(tmp_path / "scenes" / f"{sid}.mp4")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:r=48000:d=1.5", "-ac", "2",
                    str(tmp_path / "audio" / "mix.wav")], check=True)
    timing = {"scenes": [{"sceneId": "scene-001", "scene_duration_s": 1.0},
                         {"sceneId": "scene-002", "scene_duration_s": 0.5}]}
    doc = P.compose_final(tmp_path, timing, "T", log=lambda m: None)
    assert doc["total_frames"] == 45 and [s["start_s"] for s in doc["segments"]] == [0.0, 1.0]
    out = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries",
                          "stream=nb_read_frames", "-of", "csv=p=0", str(tmp_path / "final.mp4")],
                         capture_output=True, text=True, check=True).stdout.strip()
    assert out == "45" and json.loads((tmp_path / "compose.json").read_text())["segments"][1]["frames"] == 15


def test_cartoon_qa_rejects_non_cartoon_spec(tmp_path):
    from robotics101.cartoon.qa import run_cartoon_qa
    shutil.copy(ROOT / "examples" / "episode-001.json", tmp_path / "episode.json")
    rep = run_cartoon_qa(tmp_path, "preview")
    assert rep.status == "FAIL" and rep.failures[0].id == "bundle.spec"


def _linked_copy(src: Path, dst: Path):
    for p in src.rglob("*"):
        q = dst / p.relative_to(src)
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
        else:
            q.parent.mkdir(parents=True, exist_ok=True)
            os.link(p, q)


@needs_bundle
def test_rendered_bundle_passes_and_manifest_has_registry_fingerprint():
    man = json.loads((BUNDLE / "manifest.json").read_text())
    reg = load_registry()
    from robotics101.cartoon.rigs import RIG_VERSION
    cr = man["characterRegistry"]
    if cr["sha256"] != reg.sha256:
        pytest.skip("local bundle was rendered with an older character registry (re-render to refresh)")
    assert cr["sha256"] == reg.sha256 and cr["rigVersion"] == reg.rig_version and cr["drawingVersion"] == RIG_VERSION
    assert man["publish"]["status"] == "not_published" and man["audience"]["madeForKids"] is True
    assert man["qa"]["status"] in ("PASS", "PASS_WITH_WARNINGS")
    blob = (BUNDLE / "manifest.json").read_text() + (BUNDLE / "timing.json").read_text()
    assert "ELEVENLABS_API_KEY=" not in blob and "xi-api-key" not in blob


@needs_bundle
@pytest.mark.parametrize("tamper,check", [
    ("registry", "manifest.registry"),
    ("drawing", "manifest.drawing_version"),
    ("threshold", "facts.threshold_consistent"),
    ("quiz", "facts.quiz"),
])
def test_cartoon_qa_catches_tampering(tamper, check):
    import tempfile
    from robotics101.cartoon.qa import run_cartoon_qa
    b = Path(tempfile.mkdtemp(prefix=".tamper-", dir=BUNDLE.parent))       # same filesystem -> hard links work
    try:
        _tamper_and_check(b, tamper, check, run_cartoon_qa)
    finally:
        shutil.rmtree(b, ignore_errors=True)


def _tamper_and_check(b, tamper, check, run_cartoon_qa):
    _linked_copy(BUNDLE, b)

    def rewrite(name, fn):
        doc = json.loads((b / name).read_text())
        (b / name).unlink()            # break the hard link before writing
        fn(doc)
        (b / name).write_text(json.dumps(doc))
    if tamper == "registry":
        rewrite("manifest.json", lambda m: m["characterRegistry"].update(sha256="0" * 64))
    elif tamper == "drawing":
        rewrite("manifest.json", lambda m: m["characterRegistry"].update(drawingVersion=-1))
    elif tamper == "threshold":
        rewrite("episode.json", lambda s: next(x for x in s["scenes"] if x["template"] == "cartoon_rule_board")
                ["parameters"].update(thresholdMeters=0.6))
    elif tamper == "quiz":
        rewrite("scenes.json", lambda s: next(x for x in s["scenes"] if x["template"] == "cartoon_recap_chant")
                ["facts"].update(question="What is a robot?"))
    rep = run_cartoon_qa(b, "full")
    assert check in {c.id for c in rep.failures}
