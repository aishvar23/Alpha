"""M03.4: animated robot families (vacuum / rover / factory arm vignettes in the album) + static-hold QA."""

import json
import shutil
import subprocess

import numpy as np
import pytest

pytest.importorskip("manim")

from robotics101.cartoon import props as PR  # noqa: E402
from robotics101.cartoon import vignettes as V  # noqa: E402
from robotics101.cartoon.qa import HOLD_MAX_S, check_static_holds, hold_runs  # noqa: E402
from robotics101.qa import QaReport  # noqa: E402

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def _px(mob, w=160, h=130):
    from robotics101.cartoon.render2d import frame_rgb
    return frame_rgb([mob.copy().scale(5.0)], w, h, "#FFFFFF").astype(np.int16)


@pytest.mark.parametrize("kind", ["vacuum", "rover", "arm"])
def test_every_family_vignette_is_animated_deterministic_and_fits_its_tile(kind):
    a, b = V.vignette(kind, 0.0), V.vignette(kind, 0.7)
    assert a.width <= V.TILE_W + 0.05 and a.height <= V.TILE_H + 0.05
    assert np.array_equal(_px(a), _px(V.vignette(kind, 0.0)))
    assert np.abs(_px(a) - _px(b)).mean() > 0.5                       # visibly different 0.7 s later
    # never still for long: sample every 0.25 s over two loops, consecutive samples always differ
    frames = [_px(V.vignette(kind, k * 0.25)) for k in range(32)]
    assert all(np.abs(f - g).mean() > 0.05 for f, g in zip(frames, frames[1:]))


def test_vacuum_cleans_and_bumps_the_walls():
    xs = [V.vacuum_x(k / 30) for k in range(int(V.VAC_PERIOD * 30))]
    assert min(x for x, _, _ in xs) < -0.4 and max(x for x, _, _ in xs) > 0.4
    assert {d for _, d, _ in xs} == {-1, 1}
    assert max(b for _, _, b in xs) > 0.9                               # wall bumps


def test_factory_arm_picks_and_places_with_elbow_up_ik():
    phases = {V.arm_target(k / 30)[1] for k in range(int(V.ARM_PERIOD * 30))}
    assert {"reach", "grip", "carry", "drop", "back"} <= phases
    for k in range(int(V.ARM_PERIOD * 30)):
        tgt, _ = V.arm_target(k / 30)
        elbow, tip = V._ik(tgt)
        assert elbow[1] >= V.BASE[1] - 1e-6                             # elbow never folds under the floor
        assert np.hypot(*(elbow - V.BASE)[:2]) == pytest.approx(V.L1, abs=1e-6)
        assert np.hypot(*(tip - elbow)[:2]) == pytest.approx(V.L2, abs=1e-3)


def test_album_uses_live_vignettes_when_given_time():
    still = PR.album(["vacuum", "arm", "rover"], [1, 1, 1])
    a, b = PR.album(["vacuum", "arm", "rover"], [1, 1, 1], t=0.0), PR.album(["vacuum", "arm", "rover"], [1, 1, 1], t=0.8)
    assert np.abs(_px(a, 320, 140) - _px(b, 320, 140)).mean() > 0.2
    assert len(still.family_members_with_points()) != len(a.family_members_with_points())


def _video(path, frames, fps=30):
    h, w = frames[0].shape
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-c:v", "libx264", "-qp", "0", "-pix_fmt", "yuv420p",
                          str(path)], stdin=subprocess.PIPE)
    p.stdin.write(b"".join(f.tobytes() for f in frames))
    p.stdin.close()
    assert p.wait() == 0


@needs_ffmpeg
def test_hold_detector_flags_frozen_picture_and_static_region(tmp_path):
    w, h = 384, 216
    frames = []
    for n in range(180):                     # 0-3 s: frozen picture; 3-6 s: a square moves in the left region only
        f = np.full((h, w), 200, np.uint8)
        if n >= 90:
            x = 10 + (n - 90) % 60
            f[40:80, x:x + 30] = 30
        frames.append(f)
    _video(tmp_path / "final.mp4", frames)
    timing = {"scenes": [{"sceneId": "scene-001", "scene_duration_s": 6.0}]}
    by = {"scene-001": {"illustrations": [
        {"id": "moving", "box": [0.0, 0.0, 0.3, 0.5], "start": 3.0, "end": 6.0},
        {"id": "still", "box": [0.6, 0.5, 1.0, 1.0], "start": 3.0, "end": 6.0}]}}
    res = hold_runs(tmp_path / "final.mp4", timing, by, half_s=0.0)
    assert res["frames"] == 180
    assert res["fullFrame"]["longestHoldS"] == pytest.approx(3.0, abs=0.05) and res["fullFrame"]["at"] == 0
    assert res["regions"]["scene-001/moving"]["longestHoldS"] < 0.2
    assert res["regions"]["scene-001/still"]["longestHoldS"] == pytest.approx(3.0, abs=0.05)
    rep = QaReport(None, "preview", str(tmp_path))
    check_static_holds(rep, tmp_path, {"scenes": [{"template": "cartoon_robot_family"}]}, timing, by, 0.0)
    st = {c.id: c.status for c in rep.checks}
    assert st == {"video.no_long_holds": "fail", "illustrations.animated": "fail"}
    assert json.loads((tmp_path / "qa" / "static_holds.json").read_text())["fullFrame"]["longestHoldS"] > HOLD_MAX_S


@needs_ffmpeg
def test_family_scene_does_not_register_a_stage_album_grid(tmp_path):
    """M05.6: family examples are full-screen one-example shots (see test_m05_layouts), not a stage album grid."""
    from robotics101.cartoon import scenes as S
    beats = [{"type": "sfx", "id": "toaster_pop", "start_s": 0.2, "end_s": 0.6},
             {"type": "sfx", "id": "page_flip", "start_s": 1.0, "end_s": 1.4},
             {"type": "line", "speaker": "maya", "index": 0, "start_s": 1.5, "end_s": 6.0, "wav": "x.wav",
              "text": "A robot vacuum, a factory arm and a rover!",
              "words": [{"w": "vacuum", "s": 2.0}, {"w": "arm", "s": 3.0}, {"w": "rover", "s": 4.0}]}]
    sc = S.Scene("scene-002", "cartoon_robot_family", {}, beats, 8.0, tmp_path)
    S.stage_robot_family(sc)
    assert sc.illustrations == []
    assert not any(i["id"].startswith("family-") for i in sc.illustrations)
