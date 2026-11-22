from conftest import scene_by_template

from robotics101.templates.registry import REGISTRY
from robotics101.validation import validate_episode


def _messages(report):
    return " | ".join(str(i) for i in report.issues)


def test_sample_spec_is_valid_without_warnings(spec):
    report = validate_episode(spec)
    assert report.ok, _messages(report)
    assert report.warnings == []


def test_registry_covers_sample_templates(spec):
    used = {(s["engine"], s["template"]) for s in spec["scenes"]}
    assert used <= set(REGISTRY)
    assert len(REGISTRY) == 7


def test_schema_violation_rejected(spec):
    spec["episodeId"] = "episode-one"  # pattern ^ep-[0-9]{3,}$
    del spec["scenes"][0]["narration"]
    report = validate_episode(spec)
    assert not report.ok
    paths = {i.path for i in report.errors}
    assert "$.episodeId" in paths
    assert "$.scenes[0]" in paths


def test_duplicate_sequence_rejected(spec):
    spec["scenes"][1]["sequence"] = 1
    report = validate_episode(spec)
    assert not report.ok
    assert "duplicate scene sequence" in _messages(report)


def test_sequence_gap_rejected(spec):
    spec["scenes"][-1]["sequence"] = 9
    report = validate_episode(spec)
    assert not report.ok
    assert "contiguous" in _messages(report)


def test_duplicate_scene_id_rejected(spec):
    spec["scenes"][2]["sceneId"] = spec["scenes"][0]["sceneId"]
    report = validate_episode(spec)
    assert not report.ok
    assert "duplicate sceneId" in _messages(report)


def test_unknown_template_rejected(spec):
    spec["scenes"][0]["template"] = "robot_dance_party"
    report = validate_episode(spec)
    assert not report.ok
    assert "unknown template 'robot_dance_party'" in _messages(report)


def test_template_engine_mismatch_rejected(spec):
    scene_by_template(spec, "mobile_robot_avoidance")["engine"] = "manim"
    report = validate_episode(spec)
    assert not report.ok
    assert "unknown template 'mobile_robot_avoidance' for engine 'manim'" in _messages(report)


def test_invalid_sensor_geometry_rejected(spec):
    scene = scene_by_template(spec, "sensor_range")
    scene["parameters"]["obstacleDistanceMeters"] = 4.5  # beyond 3.0 m range
    report = validate_episode(spec)
    assert not report.ok
    assert "sensor geometry" in _messages(report)


def test_servo_angle_out_of_limits_rejected(spec):
    scene_by_template(spec, "servo_rotation")["parameters"]["endAngleDegrees"] = 270
    report = validate_episode(spec)
    assert not report.ok
    assert "joint constraint" in _messages(report)


def test_unsafe_blender_asset_rejected(spec):
    scene_by_template(spec, "mobile_robot_avoidance")["parameters"]["robotAsset"] = "https://example.com/x.blend"
    report = validate_episode(spec)
    assert not report.ok
    assert "safe asset" in _messages(report)


def test_unknown_parameter_rejected(spec):
    scene_by_template(spec, "recap_quiz")["parameters"]["exec"] = "import os"
    report = validate_episode(spec)
    assert not report.ok
    assert "unknown parameter 'exec'" in _messages(report)


def test_duration_mismatch_is_warning_not_error(spec):
    spec["scenes"][0]["durationTargetSeconds"] = 120  # sum 390 s vs 300 s target
    report = validate_episode(spec)
    assert report.ok
    assert any("sum of scene targets" in w.message for w in report.warnings)


def test_episode_target_outside_window_is_warning(spec):
    spec["durationTargetSeconds"] = 600
    report = validate_episode(spec)
    assert report.ok
    assert any(w.path == "$.durationTargetSeconds" for w in report.warnings)
