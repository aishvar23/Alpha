"""M01.3: scene timing, render job contract, probe checks, render-scenes CLI and a Manim smoke render."""

import ast
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from robotics101.animation.manim_templates import ENTRY_FILE, SCENE_CLASSES
from robotics101.animation.probe import check_clip
from robotics101.animation.render import PROFILES, RenderSetupError, build_job, find_manim, render_scenes
from robotics101.animation.timing import animation_speed, frames_for, resolve_scene_durations, target_frames
from robotics101.cli import main
from robotics101.templates.registry import REGISTRY

from conftest import SAMPLE

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _have_manim() -> bool:
    try:
        find_manim()
        return True
    except RenderSetupError:
        return False


# ---------------------------------------------------------------- timing

@pytest.mark.parametrize("dur, fps, frames", [(30.0, 30, 900), (49.999, 30, 1500), (2.0, 30, 60), (0.01, 30, 1)])
def test_target_frames(dur, fps, frames):
    assert target_frames(dur, fps) == frames


def test_target_frames_within_half_frame():
    for dur in (10.313, 25.0, 47.77, 55.555):
        assert abs(target_frames(dur, 30) / 30 - dur) <= 0.5 / 30 + 1e-9


def test_frames_for_minimum_one():
    assert frames_for(0.0, 30) == 1 and frames_for(1.0, 30) == 30


def test_animation_speed_full_and_compressed():
    assert animation_speed(50.0, 12.0) == 1.0
    s = animation_speed(2.0, 12.0)                # 2 s smoke render: 1.6 s budget
    assert s == pytest.approx(1.6 / 12.0)
    assert animation_speed(12.5, 12.0) == pytest.approx(11.5 / 12.0)


def test_resolve_durations_from_timing_json(spec, tmp_path):
    doc = {"episodeId": spec["episodeId"],
           "scenes": [{"sceneId": s["sceneId"], "scene_duration_s": s["durationTargetSeconds"] + 1.5}
                      for s in spec["scenes"]]}
    (tmp_path / "timing.json").write_text(json.dumps(doc))
    durations, source = resolve_scene_durations(spec, tmp_path / "timing.json")
    assert source.endswith("timing.json")
    assert durations["scene-001"] == 31.5


def test_resolve_durations_fallback_to_targets(spec, tmp_path):
    durations, source = resolve_scene_durations(spec, tmp_path / "timing.json")
    assert "durationTargetSeconds" in source
    assert durations == {s["sceneId"]: float(s["durationTargetSeconds"]) for s in spec["scenes"]}


@pytest.mark.parametrize("doc", [
    {"episodeId": "ep-999", "scenes": []},
    {"episodeId": "ep-001", "scenes": [{"sceneId": "scene-001", "scene_duration_s": 30}]},
])
def test_resolve_durations_rejects_stale_timing(spec, tmp_path, doc):
    (tmp_path / "timing.json").write_text(json.dumps(doc))
    with pytest.raises(ValueError, match="re-run narrate"):
        resolve_scene_durations(spec, tmp_path / "timing.json")


# ---------------------------------------------------------------- template wiring / job contract

def test_every_manim_template_has_a_scene_class():
    manim_templates = {name for (engine, name) in REGISTRY if engine == "manim"}
    assert manim_templates == set(SCENE_CLASSES)


def test_entry_defines_all_scene_classes():
    tree = ast.parse(ENTRY_FILE.read_text())
    defined = {n.name for n in tree.body if isinstance(n, ast.ClassDef)}
    assert set(SCENE_CLASSES.values()) <= defined


def test_template_modules_never_use_latex():
    banned = {"Tex", "MathTex", "SingleStringMathTex", "DecimalNumber", "Integer", "NumberLine", "Axes",
              "NumberPlane", "Variable", "BulletedList", "Title"}
    for f in ENTRY_FILE.parent.glob("*.py"):
        tree = ast.parse(f.read_text())
        used = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "manim"
                for a in n.names}
        used |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                 and isinstance(n.value, ast.Name) and n.value.id == "manim"}
        assert "*" not in used, f"{f.name} star-imports manim"
        assert not used & banned, f"{f.name} uses LaTeX-backed {used & banned}"


def test_build_job_carries_only_data(spec):
    scene = spec["scenes"][2]
    job = build_job(spec, scene, 50.0)
    assert job["params"] == {"rangeMeters": 3.0, "obstacleDistanceMeters": 1.2}
    assert job["durationSeconds"] == 50.0 and job["template"] == "sensor_range"
    assert "narration" not in job
    json.dumps(job)  # JSON-serialisable


# ---------------------------------------------------------------- probe

@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe not installed")
def test_check_clip_detects_wrong_duration_and_size(tmp_path):
    clip = tmp_path / "t.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=30:duration=1",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    assert check_clip(clip, 320, 240, 30, 1.0).ok
    bad = check_clip(clip, 854, 480, 30, 2.0)
    assert not bad.ok
    assert any("resolution" in p for p in bad.problems)
    assert any("duration" in p for p in bad.problems)
    assert not check_clip(tmp_path / "missing.mp4", 320, 240, 30, 1.0).ok


# ---------------------------------------------------------------- prerequisites / CLI

def test_find_manim_reports_prerequisites(monkeypatch, tmp_path):
    monkeypatch.setenv("MANIM_BIN", str(tmp_path / "nope"))
    monkeypatch.setattr("robotics101.animation.render.sys.executable", str(tmp_path / "python"))
    monkeypatch.setattr("robotics101.animation.render.shutil.which", lambda _: None)
    with pytest.raises(RenderSetupError, match="uv pip install"):
        find_manim()


def test_cli_render_scenes_unknown_only_is_input_error(tmp_path):
    assert main(["render-scenes", str(SAMPLE), "--out", str(tmp_path), "--only", "scene-999"]) == 2


def test_cli_render_scenes_invalid_spec(tmp_path, spec):
    spec["scenes"][2]["parameters"]["obstacleDistanceMeters"] = 9.0
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(spec))
    assert main(["render-scenes", str(bad), "--out", str(tmp_path / "o")]) == 1


@pytest.mark.skipif(not (_have_manim() and HAVE_FFMPEG), reason="manim and/or ffmpeg not installed")
def test_blender_scene_is_skipped_not_rendered(spec, tmp_path):
    results = render_scenes(spec, {"scene-006": 45.0}, tmp_path, PROFILES["preview"], only={"scene-006"})
    assert [(r.sceneId, r.status) for r in results] == [("scene-006", "skipped")]
    assert "M01.4" in results[0].message
    assert not list((tmp_path / "scenes").glob("*.mp4"))


# ---------------------------------------------------------------- Manim smoke render

@pytest.mark.skipif(not (_have_manim() and HAVE_FFMPEG), reason="manim and/or ffmpeg not installed")
def test_smoke_render_servo_scene_preview(spec, tmp_path):
    """Render the servo template for ~2 s at preview profile and verify the probed clip."""
    results = render_scenes(spec, {"scene-005": 2.0}, tmp_path, PROFILES["preview"], only={"scene-005"},
                            timeout_s=300)
    (r,) = results
    assert r.status == "rendered", (r.message, r.problems, Path(r.log).read_text()[-2000:] if r.log else "")
    out = tmp_path / "scenes" / "scene-005.mp4"
    assert out.is_file()
    assert r.probe["width"] == 854 and r.probe["height"] == 480
    assert r.probe["frames"] == 60
    assert abs(r.probe["duration_s"] - 2.0) <= 1 / 30
    assert (tmp_path / "logs" / "scene-005.log").is_file()
    assert not (tmp_path / ".manim").exists()
