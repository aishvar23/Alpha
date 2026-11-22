import pytest

from robotics101.geometry import obstacle_detected, servo_angle_in_limits


@pytest.mark.parametrize(
    "distance, rng, expected",
    [(1.2, 3.0, True), (3.0, 3.0, True), (3.01, 3.0, False), (0.0, 3.0, True), (10.0, 3.0, False)],
)
def test_obstacle_detected_iff_within_range(distance, rng, expected):
    assert obstacle_detected(distance, rng) is expected


@pytest.mark.parametrize("distance, rng", [(1.0, 0.0), (1.0, -1.0), (-0.5, 3.0)])
def test_obstacle_detected_rejects_invalid_inputs(distance, rng):
    with pytest.raises(ValueError):
        obstacle_detected(distance, rng)


@pytest.mark.parametrize("angle, ok", [(0, True), (60, True), (180, True), (-1, False), (180.5, False)])
def test_servo_angle_limits(angle, ok):
    assert servo_angle_in_limits(angle) is ok


# ---------------------------------------------------------------- template geometry (M01.3)
import math  # noqa: E402

from robotics101.geometry import (  # noqa: E402
    KEEP_GOING, STOP_AND_TURN, meters_to_scene_x, reading_sweep, sensor_units_per_meter, servo_arm_endpoint,
    threshold_decision, tick_step_meters,
)


@pytest.mark.parametrize("angle, expected", [
    (0, (2.0, 0.0)), (90, (0.0, 2.0)), (180, (-2.0, 0.0)),
    (60, (1.0, math.sqrt(3))), (45, (math.sqrt(2), math.sqrt(2))),
])
def test_servo_arm_endpoint_matches_angle(angle, expected):
    x, y = servo_arm_endpoint(angle, 2.0)
    assert x == pytest.approx(expected[0], abs=1e-9) and y == pytest.approx(expected[1], abs=1e-9)


def test_servo_arm_endpoint_offset_pivot_and_length_preserved():
    x, y = servo_arm_endpoint(60, 2.5, pivot=(-1.6, -2.0))
    assert math.hypot(x + 1.6, y + 2.0) == pytest.approx(2.5)
    assert math.degrees(math.atan2(y + 2.0, x + 1.6)) == pytest.approx(60)


@pytest.mark.parametrize("angle, length", [(-1, 1.0), (181, 1.0), (90, 0.0)])
def test_servo_arm_endpoint_rejects_out_of_limits(angle, length):
    with pytest.raises(ValueError):
        servo_arm_endpoint(angle, length)


def test_sensor_scale_is_linear_and_to_scale():
    # episode-001: 3 m range over 9 scene units -> 3 units/m; obstacle at 1.2 m
    assert sensor_units_per_meter(3.0, 9.0) == pytest.approx(3.0)
    assert meters_to_scene_x(0.0, 3.0, -5.0, 9.0) == pytest.approx(-5.0)
    assert meters_to_scene_x(1.2, 3.0, -5.0, 9.0) == pytest.approx(-1.4)
    assert meters_to_scene_x(3.0, 3.0, -5.0, 9.0) == pytest.approx(4.0)  # range end == available span
    # ratio of obstacle to range distance is preserved on screen
    x_obs, x_end = meters_to_scene_x(1.2, 3.0, 0, 7.3), meters_to_scene_x(3.0, 3.0, 0, 7.3)
    assert x_obs / x_end == pytest.approx(1.2 / 3.0)


@pytest.mark.parametrize("bad", [dict(range_m=0, available_units=1), dict(range_m=3, available_units=0)])
def test_sensor_scale_rejects_degenerate(bad):
    with pytest.raises(ValueError):
        sensor_units_per_meter(**bad)


@pytest.mark.parametrize("rng, step", [(3.0, 0.5), (1.0, 0.2), (10.0, 2.0), (0.5, 0.1), (25, 5.0)])
def test_tick_step_is_nice_and_bounded(rng, step):
    s = tick_step_meters(rng, max_ticks=8)
    assert s == pytest.approx(step)
    assert rng / s <= 8 + 1e-9


@pytest.mark.parametrize("distance, threshold, expected", [
    (0.2, 0.5, STOP_AND_TURN), (0.49, 0.5, STOP_AND_TURN), (0.5, 0.5, KEEP_GOING), (1.5, 0.5, KEEP_GOING),
])
def test_threshold_decision_is_strict_less_than(distance, threshold, expected):
    assert threshold_decision(distance, threshold) == expected


def test_reading_sweep_crosses_threshold():
    start, end = reading_sweep(0.5)
    assert threshold_decision(start, 0.5) == KEEP_GOING
    assert threshold_decision(end, 0.5) == STOP_AND_TURN
    with pytest.raises(ValueError):
        reading_sweep(0)
