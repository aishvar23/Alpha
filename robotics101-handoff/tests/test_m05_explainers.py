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
            "areaShare": 0.80, "characters": [], "start": 0.9, "end": 3.2}

    def run(sh):
        rep = QaReport("ep", "full", "x")
        check_shots(rep, spec, timing, {"s1": {"facts": {"shots": [sh]}}})
        return {c.id: c for c in rep.checks}["layout.illustration_first"]

    assert run(good).ok
    assert not run({**good, "areaShare": 0.50}).ok
    assert not run({**good, "characters": [{"id": "maya", "area": 0.20}]}).ok
    # a tiny cameo is allowed
    assert run({**good, "characters": [{"id": "maya", "area": 0.05}]}).ok
    assert CORNER_MAX_AREA == 0.08 and ILLUSTRATION_MIN_AREA == 0.75


def test_qa_one_example_per_frame_and_clutter():
    from robotics101.cartoon.qa import check_clutter, check_one_example_per_frame
    spec = {"scenes": [{"sceneId": "s1", "beats": [
        {"type": "line", "speaker": "maya", "text": "A vacuum and an arm.",
         "examples": [{"id": "vacuum", "visual": "example_vacuum"},
                      {"id": "arm", "visual": "example_arm"}]}]}]}
    timing = {"scenes": [{"sceneId": "s1", "beats": [{"index": 0, "start_s": 1.0, "end_s": 5.0}]}]}
    split = [
        {"layout": "illustration", "visual": "example_vacuum", "example": "vacuum",
         "areaShare": 0.80, "characters": [], "start": 1.0, "end": 3.0},
        {"layout": "illustration", "visual": "example_arm", "example": "arm",
         "areaShare": 0.80, "characters": [], "start": 3.0, "end": 5.0},
    ]
    overlap = [{**split[1], "start": 2.5}]
    grid = [{"layout": "illustration", "visual": "robot_families", "areaShare": 0.80,
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



def test_illustration_box_fills_most_of_the_frame_and_clears_the_caption_band():
    from robotics101.cartoon.layout import band_overlap, box_area, norm_box
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX
    share = box_area(norm_box(*ILLUSTRATION_BOX))
    assert share >= ILLUSTRATION_MIN_AREA
    assert band_overlap(norm_box(*ILLUSTRATION_BOX)) == 0


def test_quiz_shows_picture_choices():
    pytest.importorskip("manim")
    from robotics101.cartoon.explainers import quiz_question
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX
    g = quiz_question(0.5, {"question": "Which part of a robot measures distance?"}, ILLUSTRATION_BOX)
    # three labelled choice cards are in the mobject tree
    blob = " ".join(getattr(m, "text", "") for m in g.family_members_with_points() if hasattr(m, "text"))
    # Text may store as manim Text; also search submobject texts via str
    texts = []
    def walk(m):
        if hasattr(m, "original_text"):
            texts.append(m.original_text)
        elif hasattr(m, "text"):
            texts.append(str(m.text))
        for c in getattr(m, "submobjects", []):
            walk(c)
    walk(g)
    joined = " ".join(texts).upper()
    assert "SENSOR" in joined and "WHEEL" in joined and "BATTERY" in joined


def test_servo_dial_fixed_labels_sit_outside_the_ring():
    pytest.importorskip("manim")
    import math
    from robotics101.cartoon.explainers import servo_dial
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX
    g = servo_dial(1.0, {"angle": 30, "spoken": 30}, ILLUSTRATION_BOX)
    texts = {}
    def walk(m):
        tx = getattr(m, "original_text", None) or (str(m.text) if hasattr(m, "text") else None)
        if tx and "°" in str(tx):
            texts[str(tx)] = m.get_center()
        for c in getattr(m, "submobjects", []):
            walk(c)
    walk(g)
    assert "0°" in texts and "90°" in texts and "180°" in texts
    # 90 at the top, 0 to the right, 180 to the left
    assert texts["90°"][1] > texts["0°"][1] and texts["90°"][1] > texts["180°"][1]
    assert texts["0°"][0] > texts["90°"][0] > texts["180°"][0]


def test_charge_cable_hugs_the_floor_and_misses_a_mid_stage_body():
    pytest.importorskip("manim")
    from robotics101.cartoon import props as PR
    from robotics101.cartoon.sets import FLOOR_Y, SOCKET_POS
    lead = PR.charge_lead(SOCKET_POS, PR.P(0.0, 0.8), 1.0)
    assert lead.seated and lead.plug.get_right()[0] >= lead.port.get_left()[0] + 0.02
    # A mid-stage torso (Maya's old stand, from shin up) must stay clear of the floor run.
    old_torso = [-3.9, FLOOR_Y + 0.55, -2.5, 1.8]
    assert not PR.cable_crosses_box(lead.cable_points, old_torso, pad=0.05)
    ys = [float(p[1]) for p in lead.cable_points]
    mid_ys = ys[6:18]
    assert max(mid_ys) <= FLOOR_Y + 0.20 + 1e-6


def test_battery_fill_goes_red_to_green():
    from robotics101.cartoon.props import ALERT, OK_GREEN, _lerp_hex
    assert _lerp_hex(ALERT, OK_GREEN, 0.0).lower() == ALERT.lower()
    assert _lerp_hex(ALERT, OK_GREEN, 1.0).lower() == OK_GREEN.lower()
    mid = _lerp_hex(ALERT, OK_GREEN, 0.5)
    assert mid.lower() not in {ALERT.lower(), OK_GREEN.lower()}


def test_qa_illustration_first_accepts_split_shots_and_a_short_held_prefix():
    """A line split across two example shots is covered, and a late start (charger hold) is allowed
    as long as the end of the line and most of its duration stay inside an illustration shot."""
    from robotics101.cartoon.qa import check_shots
    spec = {"scenes": [{"sceneId": "s1", "beats": [
        {"type": "line", "speaker": "maya", "text": "A robot vacuum. A factory arm.", "explain": True},
        {"type": "line", "speaker": "maya", "text": "And last, the controller.", "explain": True},
    ]}]}
    timing = {"scenes": [{"sceneId": "s1", "beats": [
        {"index": 0, "start_s": 1.0, "end_s": 5.0},
        {"index": 1, "start_s": 5.2, "end_s": 10.0},
    ]}]}

    def run(shots):
        rep = QaReport("ep", "full", "x")
        check_shots(rep, spec, timing, {"s1": {"facts": {"shots": shots}}})
        return {c.id: c for c in rep.checks}["layout.illustration_first"]

    split = [
        {"layout": "illustration", "visual": "example_vacuum", "example": "vacuum",
         "areaShare": 0.80, "characters": [], "start": 1.0, "end": 3.0},
        {"layout": "illustration", "visual": "example_arm", "example": "arm",
         "areaShare": 0.80, "characters": [], "start": 3.0, "end": 5.1},
        {"layout": "illustration", "visual": "part_controller", "example": "controller",
         "areaShare": 0.80, "characters": [], "start": 7.2, "end": 10.2},
    ]
    assert run(split).ok
    # line 0 spills out the end
    early = [split[0], {**split[1], "end": 4.0}, split[2]]
    assert not run(early).ok
    # controller starts so late that less than half the line is shown
    late = [split[0], split[1], {**split[2], "start": 9.5}]
    assert not run(late).ok


def test_teaching_shots_register_illustration_regions(tmp_path, monkeypatch):
    pytest.importorskip("manim")
    from robotics101.cartoon import lipsync
    from robotics101.cartoon import scenes as S
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    spec = expand_episode(_spec(), load_registry())
    timing = voice_episode(spec, load_registry(), tmp_path, B.FixtureBackend(), VoiceCache(tmp_path / "cache"),
                           log=lambda m: None)
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))
    sc3_t = next(x for x in timing["scenes"] if x["sceneId"] == "scene-003")
    sc = S.build_scene({s["sceneId"]: s for s in spec["scenes"]}["scene-003"], sc3_t, tmp_path)
    ids = [i["id"] for i in sc.illustrations]
    for name in ("structure", "sensors", "actuators", "power", "controller"):
        assert f"shot-{name}" in ids
    # sole-example shots (controller) start at the line, except a charger hold may push them later
    ctrl = next(s for s in sc.shots if s.get("example") == "controller")
    plug = next((b for b in sc.beats if b.get("type") == "action" and b.get("do") == "plug_in"), None)
    assert ctrl["end"] >= sc3_t["beats"][ctrl["fromBeat"]]["end_s"] - 0.05
    if plug:
        assert ctrl["start"] >= plug["end_s"] - 0.05


def _gray(mob, w=384, h=216):
    from robotics101.cartoon.render2d import frame_rgb
    import numpy as np
    return frame_rgb([mob], w, h, "#FFFFFF").mean(axis=2).astype(np.int16)


def _longest_hold_s(frames, dt, min_diff=1.0):
    """Longest run whose mean |grey| vs the run's first frame stays below ``min_diff`` (QA metric)."""
    import numpy as np
    best = start = 0
    anchor = frames[0]
    for i, f in enumerate(frames):
        if float(np.abs(f - anchor).mean()) >= min_diff:
            best = max(best, i - start)
            anchor, start = f, i
    return max(best, len(frames) - 1 - start) * dt


def test_structure_and_rule_boards_keep_moving():
    pytest.importorskip("manim")
    from robotics101.cartoon.explainers import checkup_part, the_rule
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX

    def centers(t):
        g = the_rule(t, {"threshold": 0.5}, ILLUSTRATION_BOX)
        out = []
        def walk(m):
            out.append(tuple(round(float(x), 3) for x in m.get_center()))
            for c in getattr(m, "submobjects", []):
                walk(c)
        walk(g)
        return out
    assert centers(0.0) != centers(0.8)
    # structure motion must survive fit-to-box (a uniform scale pulse does not)
    a = checkup_part(0.0, {"part": "structure"}, ILLUSTRATION_BOX)
    b = checkup_part(0.7, {"part": "structure"}, ILLUSTRATION_BOX)
    assert (_gray(a) != _gray(b)).mean() > 0  # smoke; the span test below is the real gate


def test_teaching_shots_keep_moving_through_holds():
    """Pipeline default: every full-screen teaching shot stays in motion, including the cases
    that failed QA on the first M05.6 cut (pre-ping echo, in-range bar, STA, fit structure, held dial)."""
    pytest.importorskip("manim")
    from robotics101.cartoon.explainers import checkup_part, sensor_range, servo_dial
    from robotics101.cartoon.visuals import ILLUSTRATION_BOX, echo_diagram, sense_think_act

    dt = 0.25
    cases = {
        "structure": lambda t: checkup_part(t, {"part": "structure"}, ILLUSTRATION_BOX),
        "echo": lambda t: echo_diagram(t, {"ping": 5.0}, ILLUSTRATION_BOX),  # ping late in the shot
        "range": lambda t: sensor_range(t, {"oor": 8.0}, ILLUSTRATION_BOX),  # long in-range stretch
        "sta": lambda t: sense_think_act(t, {"sense": 3.0, "think": 6.0, "act": 9.0, "threshold": 0.5},
                                         ILLUSTRATION_BOX),
        "dial": lambda t: servo_dial(t, {"t0": 0.0, "t30": 2.0, "t60": 4.0}, ILLUSTRATION_BOX),
    }
    for name, fn in cases.items():
        frames = [_gray(fn(i * dt)) for i in range(int(8.0 / dt) + 1)]
        hold = _longest_hold_s(frames, dt)
        assert hold <= 1.75, f"{name} held still for {hold:.2f}s (limit 2.0s, sampled every {dt}s)"
