"""Pure, deterministic geometry/kinematics helpers shared by validation and templates."""

from __future__ import annotations

SERVO_MIN_DEGREES = 0.0
SERVO_MAX_DEGREES = 180.0


def obstacle_detected(distance_m: float, range_m: float) -> bool:
    """Return True iff an obstacle at ``distance_m`` is within sensor ``range_m``.

    The boundary is inclusive: an obstacle exactly at max range is detected.
    """
    if range_m <= 0:
        raise ValueError(f"sensor range must be > 0, got {range_m}")
    if distance_m < 0:
        raise ValueError(f"distance must be >= 0, got {distance_m}")
    return distance_m <= range_m


def servo_angle_in_limits(angle_deg: float) -> bool:
    """Return True iff ``angle_deg`` is within the hobby-servo range [0, 180]."""
    return SERVO_MIN_DEGREES <= angle_deg <= SERVO_MAX_DEGREES
