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


# ---------------------------------------------------------------- registry

_TEMPLATES = [
    TemplateSpec("manim", "robot_intro", "Title card + everyday robot examples", _robot_intro),
    TemplateSpec("manim", "robot_anatomy", "Labelled robot body parts", _robot_anatomy),
    TemplateSpec("manim", "sensor_range", "Distance sensor cone and obstacle detection", _sensor_range),
    TemplateSpec("manim", "sense_think_act", "Sense -> think -> act loop with threshold rule", _sense_think_act),
    TemplateSpec("manim", "servo_rotation", "Servo joint rotating between two angles", _servo_rotation),
    TemplateSpec("manim", "recap_quiz", "Recap bullets and closing question", _recap_quiz),
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
