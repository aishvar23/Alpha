"""M01.4: pure kinematics for mobile_robot_avoidance (path generation, sensing, collision check)."""

import ast
import math
from dataclasses import replace
from pathlib import Path

import pytest

from robotics101 import kinematics as K
from robotics101.animation.blender_templates import plan_mobile_robot_avoidance

CFG, GEOM = K.AvoidanceConfig(), K.RobotGeometry()
PARAMS = {"robotAsset": "simple_mobile_robot_v1", "obstacle": "cube", "collisionCheck": True}


@pytest.fixture(scope="module")
def path():
    return K.generate_avoidance_path(CFG, GEOM, fps=30)


def _phase(path, name):
    a, b = path.phase_frames[name]
    return path.poses[a:b + 1]


# ---------------------------------------------------------------- sensing

def test_ray_box_distance_hit_miss_range_inside():
    box = K.Box2D(4.0, 0.0, 0.3, 0.3)
    assert K.ray_box_distance(0.0, 0.0, 0.0, box, 10.0) == pytest.approx(3.7)
    assert K.ray_box_distance(0.0, 0.0, math.pi, box, 10.0) is None           # facing away
    assert K.ray_box_distance(0.0, 1.0, 0.0, box, 10.0) is None               # passes beside
    assert K.ray_box_distance(0.0, 0.0, 0.0, box, 1.5) is None                # beyond range
    assert K.ray_box_distance(4.0, 0.1, 1.0, box, 1.5) == 0.0                 # origin inside
    assert K.ray_box_distance(4.0, -2.0, math.pi / 2, box, 5.0) == pytest.approx(1.7)


# ---------------------------------------------------------------- path generation

def test_phases_in_order_and_contiguous(path):
    spans = [path.phase_frames[p] for p in K.PHASES]
    assert spans[0][0] == 0 and spans[-1][1] == path.motion_frames - 1
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert start == end + 1
    assert [p.frame for p in path.poses] == list(range(path.motion_frames))


def test_stop_distance_respects_threshold(path):
    step = CFG.drive_speed / 30
    assert path.poses[path.stop_frame].phase == K.PHASE_DETECTED
    # stops on the first reading below the threshold: within one drive step of it
    assert CFG.stop_threshold - step <= path.stop_reading < CFG.stop_threshold
    # while driving, the controller never saw a reading below the threshold
    for p in _phase(path, K.PHASE_DRIVE)[:-1]:
        assert not p.alert and (p.reading is None or p.reading >= CFG.stop_threshold)
    # the robot does not move while stopped; the beam is red the whole time
    detected = _phase(path, K.PHASE_DETECTED)
    assert len({(p.x, p.y, p.heading) for p in detected}) == 1
    assert all(p.alert for p in detected)


def test_heading_after_turn_and_clear_path(path):
    turn = _phase(path, K.PHASE_TURN)
    stop = path.poses[path.stop_frame]
    assert turn[-1].heading == pytest.approx(stop.heading + math.radians(CFG.turn_angle_deg))
    assert all((p.x, p.y) == (stop.x, stop.y) for p in turn)                   # turns in place
    assert not turn[-1].alert and turn[-1].reading is None                     # obstacle out of the beam
    resume = _phase(path, K.PHASE_RESUME)
    assert all(p.heading == pytest.approx(math.pi / 2) for p in resume)
    end = path.poses[-1]
    assert (end.x, end.y) == pytest.approx((stop.x, stop.y + CFG.resume_distance))
    assert all(p.reading is None for p in resume)


def test_wheel_rotation_equals_distance_over_radius(path):
    r = GEOM.wheel_radius
    start = path.poses[0]
    drive_end = path.poses[path.stop_frame]
    driven = math.hypot(drive_end.x - start.x, drive_end.y - start.y)
    assert drive_end.wheel_left == pytest.approx(driven / r)
    assert drive_end.wheel_right == pytest.approx(driven / r)
    # turn in place: wheels counter-rotate by angle * (track / 2) / r
    turn_end = _phase(path, K.PHASE_TURN)[-1]
    arc = math.radians(CFG.turn_angle_deg) * GEOM.track / 2
    assert turn_end.wheel_left - drive_end.wheel_left == pytest.approx(-arc / r)
    assert turn_end.wheel_right - drive_end.wheel_right == pytest.approx(arc / r)
    end = path.poses[-1]
    assert end.wheel_right - turn_end.wheel_right == pytest.approx(CFG.resume_distance / r)


def test_time_scale_compresses_script():
    full = K.generate_avoidance_path(CFG, GEOM, 30, 1.0)
    fast = K.generate_avoidance_path(CFG, GEOM, 30, 0.25)
    assert fast.motion_frames < full.motion_frames / 2
    assert fast.poses[-1].heading == pytest.approx(full.poses[-1].heading)
    assert fast.stop_reading < CFG.stop_threshold


def test_obstacle_never_detected_is_an_error():
    cfg = replace(CFG, obstacle=K.Box2D(4.0, 5.0, 0.3, 0.3), max_drive_distance=6.0)
    with pytest.raises(K.PathPlanningError, match="never detected"):
        K.generate_avoidance_path(cfg, GEOM, 30)


def test_invalid_config_rejected():
    with pytest.raises(K.PathPlanningError):
        K.generate_avoidance_path(replace(CFG, stop_threshold=2.0, sensor_range=1.5), GEOM, 30)
    with pytest.raises(K.PathPlanningError):
        K.generate_avoidance_path(CFG, GEOM, 30, time_scale=0.0)


# ---------------------------------------------------------------- collision check

def test_generated_path_is_collision_free(path):
    assert K.find_collision(path.poses, GEOM, CFG.obstacle, CFG.collision_margin) is None
    K.assert_collision_free(path, GEOM, CFG)


def test_straight_path_through_obstacle_collides():
    poses = [K.Pose(i, 0.1 * i, 0.0, 0.0, 0.0, 0.0, None, False, K.PHASE_DRIVE) for i in range(60)]
    hit = K.find_collision(poses, GEOM, CFG.obstacle)
    # front of the footprint (x + 0.3) reaches the obstacle face (3.7) at x = 3.4
    assert hit == 34
    assert K.find_collision(poses[:30], GEOM, CFG.obstacle) is None


def test_rotated_footprint_and_margin():
    box = K.Box2D(0.0, 0.0, 0.5, 0.5)
    # a 45-degree robot whose corner just misses the box, but not with a 0.1 m margin
    geom = K.RobotGeometry(chassis_length=0.4, chassis_width=0.4, track=0.3, wheel_width=0.0)
    d = 0.5 + 0.2 * math.sqrt(2) + 0.03
    corners = K.footprint_corners(d, 0.0, math.pi / 4, geom)
    assert not K.polygon_intersects_box(corners, box, margin=0.0)
    assert K.polygon_intersects_box(corners, box, margin=0.1)


def test_too_small_threshold_fails_collision_check():
    cfg = replace(CFG, stop_threshold=0.01)
    path = K.generate_avoidance_path(cfg, GEOM, 30)
    with pytest.raises(K.CollisionError, match="collisionCheck failed"):
        K.assert_collision_free(path, GEOM, cfg)


# ---------------------------------------------------------------- scene plan (host == Blender)

def test_plan_fills_scheduled_duration():
    plan = plan_mobile_robot_avoidance(PARAMS, 45.0, 30)
    assert plan.target_frames == 1350 and plan.path.time_scale == 1.0
    assert 0 < plan.path.motion_frames <= 1350 and plan.hold_frames == 1350 - plan.path.motion_frames
    assert plan.collision_checked


def test_plan_compresses_short_scene():
    plan = plan_mobile_robot_avoidance(PARAMS, 2.0, 30)
    assert plan.target_frames == 60 and plan.path.time_scale < 1.0
    assert plan.path.motion_frames <= 60 - 6  # at least 20% hold remains (animation_speed)


def test_plan_collision_check_can_be_disabled():
    assert not plan_mobile_robot_avoidance({**PARAMS, "collisionCheck": False}, 45.0, 30).collision_checked


def test_scene_bounds_cover_path_and_obstacle(path):
    xmin, xmax, ymin, ymax = K.scene_bounds(path, GEOM, CFG.obstacle)
    x0, x1, y0, y1 = CFG.obstacle.bounds
    assert xmin <= x0 and xmax >= x1 and ymin <= y0 and ymax >= y1
    assert ymax >= path.poses[-1].y


def test_kinematics_is_blender_python_compatible():
    """Blender 4.3 bundles Python 3.11: modules it imports must parse as 3.11 and avoid third-party deps."""
    src = Path(K.__file__).parent
    for rel in ("kinematics.py", "geometry.py", "animation/timing.py", "animation/blender_templates/__init__.py",
                "templates/registry.py"):
        tree = ast.parse((src / rel).read_text(encoding="utf-8"), feature_version=(3, 11))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
                for m in mods:
                    assert m.split(".")[0] in {"__future__", "math", "json", "dataclasses", "pathlib", "typing",
                                               "robotics101"}, (rel, m)
