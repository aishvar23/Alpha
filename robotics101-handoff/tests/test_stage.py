"""M02.5: sets, props, 2D obstacle kinematics and the robot-cam (Blender) cutaway job."""

import ast
import math
import shutil
from pathlib import Path

import pytest

from robotics101.animation.blender_templates import JOB_STOP_THRESHOLD_KEY, plan_mobile_robot_avoidance
from robotics101.cartoon import obstacle as O
from robotics101.cartoon.robotcam import robotcam_job
from robotics101.templates.registry import get_template

TEMPLATE = Path(__file__).parents[1] / "src/robotics101/animation/blender_templates/mobile_robot_avoidance.py"


@pytest.mark.parametrize("t0,t_stop,d0", [(10, 18, 2.4), (0, 3, 1.5), (1, 6, 2.4), (2, 2.35, 0.9)])
def test_approach_stops_just_below_threshold_without_collision(t0, t_stop, d0):
    a = O.plan_approach(t0, t_stop, d0, 0.5)
    O.assert_no_collision(a)
    assert a.stop_t <= t_stop + 1e-9
    assert a.reading(a.stop_t) == pytest.approx(0.49)
    assert all(a.reading(t0 + k / 10) >= 0.5 for k in range(int((a.stop_t - t0) * 10)))   # never stops early
    ts = [t0 + k * 0.05 for k in range(int((a.stop_t - t0 + 2) / 0.05))]
    ds = [a.distance(t) for t in ts]
    assert all(x >= y for x, y in zip(ds, ds[1:])) and min(ds) == pytest.approx(a.stop_d)


def test_readings_are_truncated_not_rounded():
    assert O.trunc_cm(0.4999) == 0.49 and O.trunc_cm(1.209) == 1.2 and O.trunc_cm(0.5) == 0.5


def test_bad_plan_rejected():
    with pytest.raises(ValueError):
        O.plan_approach(0, 1, 0.4, 0.5)


def test_2d_staging_never_touches_the_box():
    from robotics101.cartoon import props as P
    from robotics101.cartoon.sets import METER
    a = O.plan_approach(1, 6, 2.4, 0.5)
    face, scale = 5.3 - P.BOX_W / 2, 0.78
    for k in range(200):
        t = k * 0.05
        front = O.bolt_center_x(a, t, face, scale, METER) + O.BOLT_FRONT * scale
        assert face - front >= 0.48 * METER


def test_robotcam_job_is_valid_cartoon_style_with_episode_threshold():
    job = robotcam_job(9.0, 0.5)
    assert job["style"] == "cartoon" and job[JOB_STOP_THRESHOLD_KEY] == 0.5 and job["title"] == "ROBOT-CAM"
    assert get_template("blender", "mobile_robot_avoidance").validate_params(job["params"]) == []
    plan = plan_mobile_robot_avoidance(job["params"], job["durationSeconds"], 30, job[JOB_STOP_THRESHOLD_KEY])
    assert plan.cfg.stop_threshold == 0.5 and plan.collision_checked
    assert plan.path.stop_reading < 0.5


def test_template_supports_cartoon_style():
    src = TEMPLATE.read_text()
    tree = ast.parse(src)
    names = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert "apply_cartoon_style" in names and 'job.get("style") == "cartoon"' in src


manim = pytest.importorskip("manim")


def test_garage_variants_and_props_build():
    from robotics101.cartoon import props as P, sets as S
    for v in ("default", "no_shelf", "no_pegboard"):
        assert len(S.garage(v).submobjects) > 5
    built = [P.box_pile(5), P.toaster(-4, 0.5), P.album(["vacuum", "arm", "rover"], [1, 0.5, 0]),
             P.checklist(["a", "b"], [1, 0]), P.battery(0.3, True), P.cable(P.P(0, 0), P.P(1, 1), 0.5),
             P.ruler(0, 3, danger=0.5), P.ruler_rev(4, 3), P.range_zone(0, 3), P.readout([("x", "#FFFFFF")], P.P(0, 0)),
             P.chalkboard(["IF", "distance", "<", "0.5 m"], 1), P.stc_chips("think"), P.protractor(P.P(0, 0), 60),
             P.card("Quiz", "What does Bolt do when something is closer than half a metre?", 1),
             P.top_down_inset((0.5, 0), 0, 0.5, 2.0, [(0, 0), (0.5, 0)], status="STOP"), P.icon("arm")]
    assert all(len(m.submobjects) for m in built)
    for fn in (P.title_card, ):
        assert len(fn(0).submobjects) == 0 and len(fn(1).submobjects) == 0 and len(fn(0.5).submobjects)


def test_card_and_chalkboard_fit_their_width():
    from robotics101.cartoon import props as P
    c = P.card("Quiz", "What does Bolt do when something gets closer than half a metre to him?", 1, width=9.5)
    assert c.width <= 9.5 + 0.2
    words = "IF distance < 0.5 m → STOP & TURN AND THEN SAY SORRY".split()
    assert P.chalkboard(words, 1, width=7.2).width <= 7.2 + 0.3


def test_props_render_frame():
    from robotics101.cartoon import props as P, sets as S
    from robotics101.cartoon.render2d import frame_rgb
    img = frame_rgb([S.garage(), P.box_pile(5.3)], 320, 180, "#FFF4E0")
    assert img.shape == (180, 320, 3) and img.std() > 10


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")
def test_demo_frames_render(tmp_path):
    from robotics101.cartoon.render2d import render_clip
    a = O.plan_approach(0.2, 1.0, 1.0, 0.5)
    out = render_clip(O.demo_frame_fn(a, 5.3, 1.2, 1.4), 45, tmp_path / "d.mp4", width=320, height=180, workers=2)
    assert out.stat().st_size > 1000
