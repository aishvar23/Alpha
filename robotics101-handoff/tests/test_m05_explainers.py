"""M05.6: one example per frame, illustration-only teaching shots, servo steps, seated charger, QA."""

import json
from pathlib import Path

import pytest

from robotics101.cartoon.episode import derive_examples, expand_episode
from robotics101.cartoon.layout import CORNER_MAX_AREA, ILLUSTRATION_MIN_AREA
from robotics101.characters import load_registry
from robotics101.qa import QaReport
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


def _spec():
    return json.loads(CARTOON.read_text(encoding="utf-8"))


def _by(e):
    return {s["sceneId"]: s for s in e["scenes"]}


def test_expand_is_schema_1_3_and_valid():
    e = expand_episode(_spec(), load_registry())
    assert e["schemaVersion"] == "1.3" and validate_episode(e).ok
    assert expand_episode(e, load_registry()) == e


def test_ep1_teaching_beats_are_illustration_only_one_example_each():
    e = expand_episode(_spec(), load_registry())
    by = _by(e)
    expected = {
        "scene-002": ["toaster", "vacuum", "arm", "rover"],
        "scene-003": ["structure", "sensors", "actuators", "power", "controller"],
        "scene-004": ["echo", "range"],
        "scene-005": ["the_rule", "sta"],
        "scene-006": ["servo_what", "servo_dial", "servo_head"],
        "scene-007": ["rule_test"],
        "scene-008": ["quiz"],
    }
    for sid, ids in expected.items():
        shots = by[sid]["shots"]
        assert [s.get("example") for s in shots] == ids
        assert all(s["layout"] == "illustration" and not s.get("character") for s in shots)
    # vacuum and factory arm share Maya's line but get sequential frames
    vac, arm = by["scene-002"]["shots"][1], by["scene-002"]["shots"][2]
    assert vac["fromBeat"] == arm["fromBeat"]
    assert "vacuum" in vac["atWord"].lower() and vac["untilWord"].lower().startswith("factory")
    assert arm["atWord"].lower().startswith("factory")
    # characters return between the toaster example and the family examples
    toaster, vacuum = by["scene-002"]["shots"][0], by["scene-002"]["shots"][1]
    assert toaster["toBeat"] < vacuum["fromBeat"]


def test_derive_examples_is_template_wide():
    sc = {"template": "cartoon_robot_checkup",
          "parameters": {"parts": ["structure", "power"]},
          "beats": [{"type": "line", "speaker": "maya", "text": "First, the structure."},
                    {"type": "line", "speaker": "maya", "text": "The power source is next."}]}
    rec = derive_examples(sc)
    assert [r["id"] for r in rec] == ["structure", "power"]
    assert rec[0]["visual"] == "part_structure"


def test_servo_steps_are_cutaway_then_dial_then_head():
    e = expand_episode(_spec(), load_registry())
    shots = _by(e)["scene-006"]["shots"]
    assert [s["visual"] for s in shots] == ["servo_cutaway", "servo_dial", "servo_head"]
    beats = _by(e)["scene-006"]["beats"]
    assert "exact angle" in beats[shots[0]["fromBeat"]]["text"].lower()
    assert "30" in beats[shots[1]["fromBeat"]]["text"]
    assert "high-five!" in beats[shots[1]["toBeat"]]["text"].lower()
    assert "servos turn arms" in beats[shots[2]["fromBeat"]]["text"].lower()
    # the "Easy peasy" challenge stays a character beat between cutaway and dial
    assert shots[0]["toBeat"] < shots[1]["fromBeat"]


def test_charger_plug_seats_fully_with_spark_and_battery_fill():
    pytest.importorskip("manim")
    from robotics101.cartoon import props as PR
    from robotics101.cartoon.sets import SOCKET_POS
    port = PR.P(0.0, 0.8)
    mid = PR.charge_lead(SOCKET_POS, port, 0.4)
    seated = PR.charge_lead(SOCKET_POS, port, 1.0)
    # mid-approach: the plug has not reached the jack
    assert mid.plug.get_right()[0] < seated.port.get_left()[0]
    # fully seated: no gap — the plug overlaps the port opening
    assert seated.seated
    assert seated.plug.get_right()[0] >= seated.port.get_left()[0] + 0.02
    assert seated.spark.width > 0 and seated.spark.height > 0
    batt = PR.battery(0.9, charging=True)
    assert batt.width > 0


def test_qa_illustration_first_rejects_small_teaching_visual_or_full_size_character():
    from robotics101.cartoon.qa import check_shots
    spec = {"scenes": [{"sceneId": "s1", "beats": [{"type": "line", "speaker": "maya",
                                                    "text": "A robot vacuum.", "explain": True}]}]}
    timing = {"scenes": [{"sceneId": "s1", "beats": [{"index": 0, "start_s": 1.0, "end_s": 3.0}]}]}
    good = {"layout": "illustration", "visual": "example_vacuum", "example": "vacuum",
            "areaShare": 0.70, "characters": [], "start": 0.9, "end": 3.2}

    def run(sh):
        rep = QaReport("ep", "full", "x")
        check_shots(rep, spec, timing, {"s1": {"facts": {"shots": [sh]}}})
        return {c.id: c for c in rep.checks}["layout.illustration_first"]

    assert run(good).ok
    assert not run({**good, "areaShare": 0.50}).ok
    assert not run({**good, "characters": [{"id": "maya", "area": 0.20}]}).ok
    # a tiny cameo is allowed
    assert run({**good, "characters": [{"id": "maya", "area": 0.05}]}).ok
    assert CORNER_MAX_AREA == 0.08 and ILLUSTRATION_MIN_AREA == 0.60


def test_qa_one_example_per_frame_and_clutter():
    from robotics101.cartoon.qa import check_clutter, check_one_example_per_frame
    spec = {"scenes": [{"sceneId": "s1", "beats": [
        {"type": "line", "speaker": "maya", "text": "A vacuum and an arm.",
         "examples": [{"id": "vacuum", "visual": "example_vacuum"},
                      {"id": "arm", "visual": "example_arm"}]}]}]}
    timing = {"scenes": [{"sceneId": "s1", "beats": [{"index": 0, "start_s": 1.0, "end_s": 5.0}]}]}
    split = [
        {"layout": "illustration", "visual": "example_vacuum", "example": "vacuum",
         "areaShare": 0.7, "characters": [], "start": 1.0, "end": 3.0},
        {"layout": "illustration", "visual": "example_arm", "example": "arm",
         "areaShare": 0.7, "characters": [], "start": 3.0, "end": 5.0},
    ]
    overlap = [{**split[1], "start": 2.5}]
    grid = [{"layout": "illustration", "visual": "robot_families", "areaShare": 0.7,
             "characters": [], "start": 1.0, "end": 5.0}]

    def ex(shots):
        rep = QaReport("ep", "full", "x")
        by = {"s1": {"facts": {"shots": shots}}}
        check_one_example_per_frame(rep, spec, timing, by)
        return {c.id: c for c in rep.checks}["layout.one_example_per_frame"]

    assert ex(split).ok
    assert not ex(overlap).ok
    assert not ex(grid).ok
    assert not ex([split[0]]).ok                          # arm has no frame of its own

    rep = QaReport("ep", "full", "x")
    check_clutter(rep, {"scenes": [{"sceneId": "s1", "beats": []}]},
                  {"s1": {"facts": {"shots": [split[0]]}}})
    assert {c.id: c for c in rep.checks}["layout.clutter"].ok
