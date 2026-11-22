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
