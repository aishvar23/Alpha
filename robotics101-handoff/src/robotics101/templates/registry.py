"""Template registry: the allowlist of (engine, template) pairs and their parameter validators.

Scene parameters come from an untrusted EpisodeSpec, so every template declares
exactly which keys it accepts; unknown keys are rejected. Validators return a
list of human-readable error strings (empty list == valid).

Rendering implementations are attached in later milestones (Manim: M01.3,
Blender: M01.4); this module only defines the stable selection contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from robotics101.geometry import SERVO_MAX_DEGREES, SERVO_MIN_DEGREES, servo_angle_in_limits

ParamValidator = Callable[[dict[str, Any]], list[str]]

# Primitive-geometry assets the Blender worker is allowed to build (no downloads).
SAFE_BLENDER_ROBOT_ASSETS = frozenset({"simple_mobile_robot_v1"})
SAFE_BLENDER_OBSTACLES = frozenset({"cube", "cylinder"})
CARTOON_OBSTACLES = frozenset({"boxes"})


@dataclass(frozen=True)
class TemplateSpec:
    engine: str
    name: str
    description: str
    validate_params: ParamValidator


# ---------------------------------------------------------------- helpers

def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _check_keys(params: dict[str, Any], required: set[str], optional: set[str] = frozenset()) -> list[str]:
    errors = [f"missing required parameter '{k}'" for k in sorted(required - params.keys())]
    unknown = params.keys() - required - optional
    errors += [f"unknown parameter '{k}'" for k in sorted(unknown)]
    return errors


def _string_list(params: dict[str, Any], key: str, min_items: int, max_items: int) -> list[str]:
    value = params.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
        return [f"'{key}' must be a list of non-empty strings"]
    errors = []
    if not (min_items <= len(value) <= max_items):
        errors.append(f"'{key}' must have {min_items}..{max_items} items, got {len(value)}")
    if len(set(value)) != len(value):
        errors.append(f"'{key}' contains duplicate entries")
    return errors


def _non_empty_string(params: dict[str, Any], key: str) -> list[str]:
    value = params.get(key)
    if value is not None and not (isinstance(value, str) and value.strip()):
        return [f"'{key}' must be a non-empty string"]
    return []


# ---------------------------------------------------------------- validators

def _robot_intro(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, set(), {"examples"}) + _string_list(p, "examples", 1, 6)


def _robot_anatomy(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, {"parts"}) + _string_list(p, "parts", 1, 8)


def _sensor_range(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"rangeMeters", "obstacleDistanceMeters"})
    rng, dist = p.get("rangeMeters"), p.get("obstacleDistanceMeters")
    if "rangeMeters" in p and not (_is_number(rng) and rng > 0):
        errors.append(f"'rangeMeters' must be a number > 0, got {rng!r}")
    if "obstacleDistanceMeters" in p and not (_is_number(dist) and dist > 0):
        errors.append(f"'obstacleDistanceMeters' must be a number > 0, got {dist!r}")
    if not errors and dist > rng:
        errors.append(
            f"sensor geometry: obstacleDistanceMeters ({dist}) must be <= rangeMeters ({rng}) "
            "so the scene can show a detection"
        )
    return errors


def _sense_think_act(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"thresholdMeters"})
    t = p.get("thresholdMeters")
    if "thresholdMeters" in p and not (_is_number(t) and t > 0):
        errors.append(f"'thresholdMeters' must be a number > 0, got {t!r}")
    return errors


def _servo_rotation(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"startAngleDegrees", "endAngleDegrees"})
    for key in ("startAngleDegrees", "endAngleDegrees"):
        if key in p:
            v = p[key]
            if not _is_number(v) or not servo_angle_in_limits(v):
                errors.append(
                    f"joint constraint: '{key}' must be a number in "
                    f"{SERVO_MIN_DEGREES:g}..{SERVO_MAX_DEGREES:g}, got {v!r}"
                )
    return errors


def _mobile_robot_avoidance(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"robotAsset", "obstacle"}, {"collisionCheck"})
    if "robotAsset" in p and p["robotAsset"] not in SAFE_BLENDER_ROBOT_ASSETS:
        errors.append(
            f"safe asset: 'robotAsset' {p['robotAsset']!r} not in allowlist {sorted(SAFE_BLENDER_ROBOT_ASSETS)}"
        )
    if "obstacle" in p and p["obstacle"] not in SAFE_BLENDER_OBSTACLES:
        errors.append(f"safe asset: 'obstacle' {p['obstacle']!r} not in allowlist {sorted(SAFE_BLENDER_OBSTACLES)}")
    if "collisionCheck" in p and not isinstance(p["collisionCheck"], bool):
        errors.append("'collisionCheck' must be a boolean")
    return errors


def _recap_quiz(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, {"question"}) + _non_empty_string(p, "question")


# ---------------------------------------------------------------- cartoon (M02) validators

def _positive(p: dict[str, Any], key: str) -> list[str]:
    v = p.get(key)
    if key in p and not (_is_number(v) and v > 0):
        return [f"'{key}' must be a number > 0, got {v!r}"]
    return []


def _cartoon_cold_open(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, set(), {"obstacle"})
    if "obstacle" in p and p["obstacle"] not in CARTOON_OBSTACLES:
        errors.append(f"'obstacle' must be one of {sorted(CARTOON_OBSTACLES)}")
    return errors


def _cartoon_robot_family(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, {"examples"}) + _string_list(p, "examples", 1, 4)


def _cartoon_robot_checkup(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, {"parts"}) + _string_list(p, "parts", 1, 6)


def _cartoon_sensor_ping(p: dict[str, Any]) -> list[str]:
    return _sensor_range(p)


def _cartoon_rule_board(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"thresholdMeters", "readings"}) + _positive(p, "thresholdMeters")
    r = p.get("readings")
    if "readings" in p:
        if not isinstance(r, list) or not (2 <= len(r) <= 6) or not all(_is_number(x) and x > 0 for x in r):
            errors.append("'readings' must be a list of 2..6 numbers > 0")
        elif any(b >= a for a, b in zip(r, r[1:])):
            errors.append("'readings' must be strictly decreasing (the robot drives closer)")
        elif not errors and not (r[-1] < p["thresholdMeters"] <= r[0]):
            errors.append("'readings' must start at/above the threshold and end below it (so the robot stops)")
    return errors


def _cartoon_servo_highfive(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"startAngleDegrees", "endAngleDegrees"}, {"missAngleDegrees"})
    for key in ("startAngleDegrees", "endAngleDegrees", "missAngleDegrees"):
        if key in p and (not _is_number(p[key]) or not servo_angle_in_limits(p[key])):
            errors.append(f"joint constraint: '{key}' must be a number in {SERVO_MIN_DEGREES:g}..{SERVO_MAX_DEGREES:g}")
    return errors


def _cartoon_obstacle_rematch(p: dict[str, Any]) -> list[str]:
    errors = _check_keys(p, {"thresholdMeters", "obstacle"}) + _positive(p, "thresholdMeters")
    if "obstacle" in p and p["obstacle"] not in CARTOON_OBSTACLES:
        errors.append(f"'obstacle' must be one of {sorted(CARTOON_OBSTACLES)}")
    return errors


def _cartoon_recap_chant(p: dict[str, Any]) -> list[str]:
    return _check_keys(p, {"question"}) + _non_empty_string(p, "question")


# ---------------------------------------------------------------- registry

_TEMPLATES = [
    TemplateSpec("manim", "robot_intro", "Title card + everyday robot examples", _robot_intro),
    TemplateSpec("manim", "robot_anatomy", "Labelled robot body parts", _robot_anatomy),
    TemplateSpec("manim", "sensor_range", "Distance sensor cone and obstacle detection", _sensor_range),
    TemplateSpec("manim", "sense_think_act", "Sense -> think -> act loop with threshold rule", _sense_think_act),
    TemplateSpec("manim", "servo_rotation", "Servo joint rotating between two angles", _servo_rotation),
    TemplateSpec("manim", "recap_quiz", "Recap bullets and closing question", _recap_quiz),
    TemplateSpec("cartoon", "cartoon_cold_open", "Cold open gag in the garage set", _cartoon_cold_open),
    TemplateSpec("cartoon", "cartoon_robot_family", "What is a robot + family-album examples", _cartoon_robot_family),
    TemplateSpec("cartoon", "cartoon_robot_checkup", "Robot check-up: the main parts glow in turn", _cartoon_robot_checkup),
    TemplateSpec("cartoon", "cartoon_sensor_ping", "Ultrasonic ping, echo distance and sensor range", _cartoon_sensor_ping),
    TemplateSpec("cartoon", "cartoon_rule_board", "Chalkboard rule + readings crossing the threshold", _cartoon_rule_board),
    TemplateSpec("cartoon", "cartoon_servo_highfive", "Servo arm rotates to an angle for a high-five", _cartoon_servo_highfive),
    TemplateSpec("cartoon", "cartoon_obstacle_rematch", "Drive, sense, stop, turn, resume (2D)", _cartoon_obstacle_rematch),
    TemplateSpec("cartoon", "cartoon_recap_chant", "Sense-think-act chant + closing question", _cartoon_recap_chant),
    TemplateSpec(
        "blender",
        "mobile_robot_avoidance",
        "Primitive mobile robot: drive, detect obstacle, stop, turn, resume",
        _mobile_robot_avoidance,
    ),
]

REGISTRY: dict[tuple[str, str], TemplateSpec] = {(t.engine, t.name): t for t in _TEMPLATES}


def get_template(engine: str, name: str) -> TemplateSpec | None:
    return REGISTRY.get((engine, name))
