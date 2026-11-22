"""Pure, deterministic geometry/kinematics helpers shared by validation and templates."""

from __future__ import annotations

import math

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


# ---------------------------------------------------------------- template geometry (M01.3)
# Pure functions used by the Manim templates so the drawn geometry can be unit-tested
# without rendering. Angles follow the maths convention: 0 deg points along +x,
# angles increase counter-clockwise (90 deg = straight up, 180 deg = -x).

STOP_AND_TURN = "STOP_AND_TURN"
KEEP_GOING = "KEEP_GOING"


def servo_arm_endpoint(angle_deg: float, length: float,
                       pivot: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    """Return the (x, y) tip of a servo arm of ``length`` rotated to ``angle_deg`` about ``pivot``."""
    if length <= 0:
        raise ValueError(f"arm length must be > 0, got {length}")
    if not servo_angle_in_limits(angle_deg):
        raise ValueError(f"servo angle must be in [{SERVO_MIN_DEGREES:g}, {SERVO_MAX_DEGREES:g}], got {angle_deg}")
    a = math.radians(angle_deg)
    return (pivot[0] + length * math.cos(a), pivot[1] + length * math.sin(a))


def sensor_units_per_meter(range_m: float, available_units: float) -> float:
    """Scale factor so the full sensor range spans exactly ``available_units`` of scene space."""
    if range_m <= 0:
        raise ValueError(f"sensor range must be > 0, got {range_m}")
    if available_units <= 0:
        raise ValueError(f"available length must be > 0, got {available_units}")
    return available_units / range_m


def meters_to_scene_x(distance_m: float, range_m: float, origin_x: float, available_units: float) -> float:
    """Map a distance in metres along the sensor axis to a scene x coordinate (linear, to scale)."""
    if distance_m < 0:
        raise ValueError(f"distance must be >= 0, got {distance_m}")
    return origin_x + distance_m * sensor_units_per_meter(range_m, available_units)


def tick_step_meters(range_m: float, max_ticks: int = 8) -> float:
    """Smallest 'nice' tick spacing (0.1/0.2/0.25/0.5 x 10^k) giving at most ``max_ticks`` intervals."""
    if range_m <= 0:
        raise ValueError(f"sensor range must be > 0, got {range_m}")
    exp = math.floor(math.log10(range_m / max_ticks)) - 1
    while True:
        for m in (1.0, 2.0, 2.5, 5.0):
            step = m * 10.0 ** exp
            if range_m / step <= max_ticks + 1e-9:
                return step
        exp += 1


def threshold_decision(distance_m: float, threshold_m: float) -> str:
    """Controller rule shown in sense_think_act: ``if distance < threshold: stop & turn``.

    The comparison is strict, so a reading exactly at the threshold keeps going.
    """
    if threshold_m <= 0:
        raise ValueError(f"threshold must be > 0, got {threshold_m}")
    if distance_m < 0:
        raise ValueError(f"distance must be >= 0, got {distance_m}")
    return STOP_AND_TURN if distance_m < threshold_m else KEEP_GOING


def reading_sweep(threshold_m: float) -> tuple[float, float]:
    """Start/end distance readings for the sense_think_act demo: from 3x threshold down to 0.5x.

    Guarantees the start is a KEEP_GOING reading and the end is a STOP_AND_TURN reading.
    """
    if threshold_m <= 0:
        raise ValueError(f"threshold must be > 0, got {threshold_m}")
    return 3.0 * threshold_m, 0.5 * threshold_m
