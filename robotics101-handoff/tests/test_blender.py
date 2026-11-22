"""M01.4: headless Blender scene wiring (prerequisites, job contract, encode) + a tiny real render."""

import ast
import shutil
from pathlib import Path

import pytest

from robotics101.animation import blender_render as BR
from robotics101.animation.blender_templates import TEMPLATE_SCRIPTS
from robotics101.animation.render import PROFILES, Profile, RenderSetupError, build_job, render_scenes
from robotics101.kinematics import CollisionError
from robotics101.templates.registry import REGISTRY

from conftest import scene_by_template

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _have_blender() -> bool:
    try:
        BR.find_blender()
        return True
    except RenderSetupError:
        return False


def test_every_blender_template_has_a_script():
    blender = {name for (engine, name) in REGISTRY if engine == "blender"}
    assert blender == set(TEMPLATE_SCRIPTS)
    assert all(p.is_file() for p in TEMPLATE_SCRIPTS.values())


def test_template_script_imports_only_allowlisted_modules():
    """The Blender script loads no assets/add-ons and no network modules: bpy + stdlib + robotics101 only."""
    allowed = {"__future__", "argparse", "json", "math", "sys", "time", "pathlib", "traceback",
               "bpy", "bpy_extras", "mathutils", "robotics101"}
    for path in TEMPLATE_SCRIPTS.values():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, feature_version=(3, 11))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                assert all(m.split(".")[0] in allowed for m in mods), mods
        for forbidden in ("bpy.ops.wm.open_mainfile", "bpy.ops.import_", "bpy.data.libraries", "urllib", "addon"):
            assert forbidden not in src


def test_find_blender_reports_prerequisites(monkeypatch, tmp_path):
    monkeypatch.setenv("BLENDER_BIN", str(tmp_path / "nope"))
    monkeypatch.setattr(BR.shutil, "which", lambda _: None)
    with pytest.raises(RenderSetupError) as e:
        BR.find_blender()
    msg = str(e.value)
    assert "blender executable not found" in msg and "Blender >= 4.2" in msg and "BLENDER_BIN" in msg


def test_find_blender_rejects_old_version(monkeypatch, tmp_path):
    fake = tmp_path / "blender"
    fake.write_text("#!/bin/sh\necho 'Blender 3.6.0'\n")
    fake.chmod(0o755)
    monkeypatch.setenv("BLENDER_BIN", str(fake))
    with pytest.raises(RenderSetupError, match="too old"):
        BR.find_blender()


def test_missing_blender_fails_setup_without_needing_manim(spec, tmp_path, monkeypatch):
    def no_manim():
        raise AssertionError("manim must not be required for a blender-only render")
    monkeypatch.setattr("robotics101.animation.render.find_manim", no_manim)
    monkeypatch.setattr(BR, "find_blender", lambda: (_ for _ in ()).throw(RenderSetupError(BR.BLENDER_PREREQS)))
    if not HAVE_FFMPEG:
        pytest.skip("ffmpeg not installed")
    with pytest.raises(RenderSetupError, match="Blender"):
        render_scenes(spec, {"scene-006": 45.0}, tmp_path, PROFILES["preview"], only={"scene-006"})


def test_default_procs_respects_env_and_memory(monkeypatch):
    monkeypatch.setenv(BR.BLENDER_PROCS_ENV, "3")
    assert BR.default_procs("full") == 3
    monkeypatch.delenv(BR.BLENDER_PROCS_ENV)
    monkeypatch.setattr(BR.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(BR, "available_memory_mb", lambda: 100_000)
    assert BR.default_procs("full") == 4
    monkeypatch.setattr(BR, "available_memory_mb", lambda: 2200)   # 0.75 * 2200 // 800 = 2
    assert BR.default_procs("full") == 2
    monkeypatch.setattr(BR, "available_memory_mb", lambda: 300)
    assert BR.default_procs("full") == 1


@pytest.mark.parametrize("n, parts", [(595, 4), (10, 3), (3, 8), (1, 1)])
def test_chunk_ranges_cover_all_frames(n, parts):
    ranges = BR.chunk_ranges(n, parts)
    assert ranges[0][0] == 0 and ranges[-1][1] == n
    assert all(a < b for a, b in ranges) and len(ranges) == min(n, parts)
    assert all(r1[1] == r2[0] for r1, r2 in zip(ranges, ranges[1:]))


def test_encode_command_pads_hold_to_exact_frames(tmp_path):
    cmd = BR.encode_command("ffmpeg", tmp_path, 30, 755, 1350, tmp_path / "o.mp4")
    assert cmd[cmd.index("-vf") + 1] == "tpad=stop_mode=clone:stop=755"
    assert cmd[cmd.index("-frames:v") + 1] == "1350"
    assert "-an" in cmd and "yuv420p" in cmd
    no_hold = BR.encode_command("ffmpeg", tmp_path, 30, 0, 10, tmp_path / "o.mp4")
    assert no_hold[no_hold.index("-vf") + 1] == "null"


def test_collision_fails_scene_before_launching_blender(spec, tmp_path, monkeypatch):
    def collide(*_a, **_k):
        raise CollisionError("collisionCheck failed: robot footprint at frame 7")
    monkeypatch.setattr(BR, "plan_mobile_robot_avoidance", collide)
    monkeypatch.setattr(BR.subprocess, "Popen", lambda *a, **k: pytest.fail("blender must not be launched"))
    (tmp_path / "logs").mkdir()
    job = build_job(spec, scene_by_template(spec, "mobile_robot_avoidance"), 45.0)
    r = BR.render_blender_scene("/nonexistent/blender", "ffmpeg", "ffprobe", job, tmp_path, PROFILES["preview"], 60)
    assert r.status == "failed" and "collisionCheck failed" in r.message
    assert "collisionCheck failed" in (tmp_path / "logs" / "scene-006.log").read_text()


# ---------------------------------------------------------------- real Blender smoke render

@pytest.mark.skipif(not (_have_blender() and HAVE_FFMPEG), reason="blender and/or ffmpeg not installed")
def test_smoke_render_blender_scene_tiny(spec, tmp_path):
    """1 s at 160x90: compressed motion script + hold, encoded and probed like a real scene."""
    tiny = Profile("smoke", 160, 90, 30)
    results = render_scenes(spec, {"scene-006": 1.0}, tmp_path, tiny, only={"scene-006"},
                            timeout_s=300, blender_procs=2)
    (r,) = results
    assert r.status == "rendered", (r.message, r.problems, Path(r.log).read_text()[-3000:] if r.log else "")
    assert (tmp_path / "scenes" / "scene-006.mp4").is_file()
    assert (r.probe["width"], r.probe["height"], r.probe["frames"]) == (160, 90, 30)
    assert abs(r.probe["duration_s"] - 1.0) <= 1 / 30
    log = (tmp_path / "logs" / "scene-006.log").read_text()
    assert "collisionCheck passed" in log and "RENDERED" in log
    assert not (tmp_path / ".blender").exists()
