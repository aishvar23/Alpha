"""M01.5: `robotics101 render` / `qa` smoke tests (real Manim + ffmpeg; full episode behind a flag).

* ``test_render_cli_smoke_two_scenes`` — 2 short Manim scenes, fixture TTS, preview: the whole
  pipeline runs (~15 s); QA must FAIL only on the 270–330 s duration gate.
* ``test_render_sample_episode_e2e`` — the real examples/episode-001.json (Manim + Blender, ~100 s on
  8 CPUs). Opt-in: ``ROBOTICS101_E2E=1 make test``.
"""

import json
import os
import shutil

import pytest

from conftest import SAMPLE, scene_by_template
from robotics101.animation import blender_render as BR
from robotics101.animation.render import RenderSetupError, find_manim
from robotics101.cli import EXIT_OK, EXIT_QA_FAILED, main
from robotics101.manifest import verify_manifest


def _have(fn) -> bool:
    try:
        fn()
        return True
    except RenderSetupError:
        return False


HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
HAVE_MANIM = _have(find_manim)
HAVE_BLENDER = _have(BR.find_blender)


@pytest.mark.skipif(not (HAVE_MANIM and HAVE_FFMPEG), reason="manim and/or ffmpeg not installed")
def test_render_cli_smoke_two_scenes(tmp_path, spec, capsys):
    servo = scene_by_template(spec, "servo_rotation")
    recap = scene_by_template(spec, "recap_quiz")
    for seq, s in enumerate((servo, recap), 1):
        s["sequence"], s["durationTargetSeconds"] = seq, 3
        s["narration"] = "A short fixture line."
    spec["scenes"] = [servo, recap]
    ep = tmp_path / "ep.json"
    ep.write_text(json.dumps(spec))
    out = tmp_path / "out"

    assert main(["render", str(ep), "--out", str(out), "--profile", "preview", "--tts", "fixture"]) == EXIT_QA_FAILED
    for rel in ("final.mp4", "captions.srt", "qa_report.json", "qa_report.md", "manifest.json", "compose.json",
                "episode.json", "timing.json", "clips/scene-005.mp4", "clips/scene-007.mp4"):
        assert (out / rel).is_file(), rel
    qa = json.loads((out / "qa_report.json").read_text())
    assert qa["status"] == "FAIL" and {c["id"] for c in qa["failures"]} == {"final.duration_range"}
    warned = {c["id"] for c in qa["warnings"]}
    assert {"tts.production_voice", "profile.publishable"} <= warned
    v = qa["final"]["probe"]["video"]
    assert (v["width"], v["height"], v["fps"], v["frames"]) == (854, 480, 30, 180)
    m = json.loads((out / "manifest.json").read_text())
    assert m["profile"] == "preview" and m["qa"]["status"] == "FAIL"
    assert m["publish"]["status"] == "not_published" and m["publish"]["requiresApprovalOfSha256"] == m["finalVideoSha256"]
    assert m["specSha256"] == next(a["sha256"] for a in m["artifacts"] if a["role"] == "spec")
    assert verify_manifest(out, skip_roles=frozenset()) == []
    assert "finalVideoSha256" in capsys.readouterr().out

    # `qa` re-run on the bundle is stable; then tampering flips it to a manifest failure
    assert main(["qa", str(out)]) == EXIT_QA_FAILED
    (out / "captions.srt").write_text((out / "captions.srt").read_text() + "\n")
    assert main(["qa", str(out)]) == EXIT_QA_FAILED
    qa2 = json.loads((out / "qa_report.json").read_text())
    assert "manifest.hashes" in {c["id"] for c in qa2["failures"]}


@pytest.mark.skipif(os.environ.get("ROBOTICS101_E2E") != "1", reason="slow (~100 s): set ROBOTICS101_E2E=1")
@pytest.mark.skipif(not (HAVE_MANIM and HAVE_BLENDER and HAVE_FFMPEG), reason="manim/blender/ffmpeg missing")
def test_render_sample_episode_e2e(tmp_path):
    out = tmp_path / "episode-001"
    assert main(["render", str(SAMPLE), "--out", str(out), "--profile", "preview", "--tts", "fixture"]) == EXIT_OK
    qa = json.loads((out / "qa_report.json").read_text())
    assert qa["status"] == "PASS_WITH_WARNINGS" and not qa["failures"]
    assert 270 <= qa["final"]["probe"]["video"]["frames"] / 30 <= 330
