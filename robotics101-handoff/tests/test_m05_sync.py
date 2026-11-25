"""M05.8: every teaching visual is timed to its own narration (word timings) and matches what is said."""

import json
from pathlib import Path

from robotics101.cartoon.episode import expand_episode, trim_shots_at_gags
from robotics101.cartoon.sync import check_sync, first_keyword_time, keywords_for, row_problems, sync_rows
from robotics101.characters import load_registry
from robotics101.qa import QaReport

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"


def _words(d: Path, name: str, text: str, step: float = 0.4) -> str:
    ws = [{"text": w, "start_s": round(i * step, 3), "end_s": round(i * step + step * 0.8, 3)}
          for i, w in enumerate(text.split())]
    p = d / f"{name}.words.json"
    p.write_text(json.dumps({"source": "test", "words": ws}))
    return p.name


def _fixture(tmp_path, shot):
    l0 = "Sense, think, act. Got it! So my cousin the toaster is a robot!"
    l2 = "The toaster doesn't think. It just makes toast."
    beats = [{"index": 0, "type": "line", "text": l0, "start_s": 1.0, "end_s": 6.0, "words": _words(tmp_path, "a", l0)},
             {"index": 1, "type": "action", "who": "bolt", "do": "flinch", "start_s": 6.2, "end_s": 6.8},
             {"index": 2, "type": "line", "text": l2, "start_s": 7.0, "end_s": 10.0, "words": _words(tmp_path, "b", l2)}]
    timing = {"scenes": [{"sceneId": "s", "scene_start_s": 0.0, "scene_duration_s": 12.0, "beats": beats}]}
    by = {"s": {"facts": {"shots": [shot]}}}
    return {"scenes": [{"sceneId": "s"}]}, timing, by


def test_old_beat_range_toaster_is_flagged(tmp_path):
    # M05.6: the toaster frame ran from Bolt's joke through the flinch gag to the end of Maya's line
    spec, timing, by = _fixture(tmp_path, {"layout": "illustration", "visual": "example_toaster", "fromBeat": 0,
                                           "toBeat": 2, "start": 0.85, "end": 10.2})
    rows = sync_rows(spec, timing, by, tmp_path)
    probs = row_problems(rows[0])
    assert any("hides bolt flinch" in p for p in probs)
    assert rows[0]["keywordLead"] > 1.0 and not rows[0]["topic"]         # "toaster" said 3+ s after it appears
    rep = QaReport("e", "t", str(tmp_path))
    check_sync(rep, spec, timing, by, tmp_path)
    st = {c.id: c.status for c in rep.checks}
    assert st["sync.visual_narration"] == "fail" and st["sync.visual_topic"] == "fail"


def test_shot_on_its_own_line_passes(tmp_path):
    spec, timing, by = _fixture(tmp_path, {"layout": "illustration", "visual": "example_toaster", "fromBeat": 2,
                                           "toBeat": 2, "start": 6.85 + 0.4, "end": 10.0})
    rows = sync_rows(spec, timing, by, tmp_path)
    rep = QaReport("e", "t", str(tmp_path))
    check_sync(rep, spec, timing, by, tmp_path)
    assert {c.id: c.status for c in rep.checks}["sync.visual_narration"] == "pass", row_problems(rows[0])
    assert rows[0]["topic"]


def test_overhang_into_the_next_line_is_flagged(tmp_path):
    spec, timing, by = _fixture(tmp_path, {"layout": "illustration", "visual": "example_toaster", "fromBeat": 0,
                                           "toBeat": 0, "start": 3.9, "end": 9.0})
    probs = row_problems(sync_rows(spec, timing, by, tmp_path)[0])
    assert any("stays" in p for p in probs) and any("another line" in p for p in probs)


def test_first_keyword_time_uses_word_timings(tmp_path):
    l = "And last, the controller. It's your robot brain."
    b = {"type": "line", "text": l, "start_s": 2.0, "end_s": 5.0, "words": _words(tmp_path, "c", l, 0.5)}
    assert first_keyword_time(tmp_path, b, {"visual": "part_controller"}) == 2.0 + 3 * 0.5
    assert "controller" in keywords_for({"visual": "part_controller"})
    assert keywords_for({"visual": "example_drone", "example": "drone"}) == ("drone",)


def test_ep1_derivation_toaster_and_range_frames_sit_on_their_own_lines():
    e = expand_episode(json.loads(CARTOON.read_text()), load_registry())
    by = {s["sceneId"]: s for s in e["scenes"]}
    fam = by["scene-002"]
    toaster = fam["shots"][0]
    assert toaster["fromBeat"] == toaster["toBeat"]
    assert "doesn't think" in fam["beats"][toaster["fromBeat"]]["text"]
    sens = by["scene-004"]
    rng = next(s for s in sens["shots"] if s["example"] == "range")
    oor = next(s for s in sens["shots"] if s["example"] == "out_of_range")
    assert rng["fromBeat"] == rng["toBeat"] and "3 meters" in sens["beats"][rng["fromBeat"]]["text"]
    assert "out of range" in sens["beats"][oor["fromBeat"]]["text"]
    # Nib's flight away (an action beat) is between the two frames, on stage
    fly = [i for i, b in enumerate(sens["beats"]) if b["type"] == "action" and b["do"] == "fly_to:3.6"]
    assert fly and rng["toBeat"] < fly[0] < oor["fromBeat"]


def test_trim_stops_a_derived_shot_at_a_character_gag():
    sc = {"beats": [{"type": "line", "text": "a"}, {"type": "line", "text": "b"},
                    {"type": "action", "who": "nib", "do": "fly_to:3.6"}, {"type": "line", "text": "c"}],
          "shots": [{"layout": "illustration", "visual": "sensor_range", "fromBeat": 0, "toBeat": 3},
                    {"layout": "illustration", "visual": "echo_diagram", "fromBeat": 0, "toBeat": 3}]}
    sc["beats"][2]["do"] = "ping"
    trim_shots_at_gags(sc)
    assert sc["shots"][0]["toBeat"] == 1                 # a ping is a gag for the range bar...
    assert sc["shots"][1]["toBeat"] == 3                 # ...but the echo diagram depicts it


def test_rover_moves_and_family_frames_use_the_middle_scale():
    from robotics101.cartoon.explainers import SUBJECT_SHARE, one_example, subject_share
    a = one_example(0.5, {"kind": "rover", "t0": 0.0, "t1": 4.0})
    b = one_example(3.5, {"kind": "rover", "t0": 0.0, "t1": 4.0})
    assert abs(a.get_center()[0] - b.get_center()[0]) < 1e-6   # same board...
    # ...but the rover itself drives: the wheel group is the right-most part of the scene panel and moves right
    sa = a.submobjects[2].submobjects[-1].get_center()[0]
    sb = b.submobjects[2].submobjects[-1].get_center()[0]
    assert sb - sa > 2.0
    sh = subject_share()
    lo, hi = SUBJECT_SHARE
    assert lo <= sh["width"] <= hi and lo <= sh["height"] <= hi and sh["marginX"] >= 0.1


def _charge_fixture(tmp_path, plug_before_controller: bool):
    low = "The power source gives you energy. Hmm... you look sleepy. Your battery is low!"
    yawn = "Yaaawn... I'm not sleepy... zzz..."
    ctl = "And last, the controller. It's your robot brain, and it decides what to do."
    L = lambda n, t, a, b: {"type": "line", "text": t, "start_s": a, "end_s": b, "words": _words(tmp_path, n, t, (b - a) / len(t.split()))}
    if plug_before_controller:     # M05.8 batch-1 cut: charging landed on the controller line
        beats = [L("low", low, 0.0, 6.4), L("yawn", yawn, 6.7, 10.7),
                 {"type": "action", "who": "maya", "do": "plug_in", "start_s": 11.0, "end_s": 11.9},
                 L("ctl", ctl, 11.9, 16.8)]
    else:                          # fixed: plugged in on the battery-low beat, Bolt yawns while it fills
        beats = [L("low", low, 0.0, 6.4),
                 {"type": "action", "who": "maya", "do": "plug_in", "start_s": 6.7, "end_s": 7.6},
                 L("yawn", yawn, 7.9, 11.9), L("ctl", ctl, 12.2, 17.1)]
    return {"scenes": [{"sceneId": "scene-003", "scene_start_s": 0.0, "scene_duration_s": 18.0, "beats": beats}]}


def test_charging_over_the_controller_line_is_flagged(tmp_path):
    from robotics101.cartoon.sync import action_rows, check_action_overlap
    timing = _charge_fixture(tmp_path, plug_before_controller=True)
    rows = action_rows(timing, tmp_path)
    assert rows and rows[0]["unrelatedLines"] and "controller" in rows[0]["unrelatedLines"][0]["text"]
    rep = QaReport("e", "t", str(tmp_path))
    check_action_overlap(rep, timing, tmp_path)
    assert {c.id: c.status for c in rep.checks}["sync.action_narration"] == "fail"


def test_charging_on_the_battery_low_beat_passes(tmp_path):
    from robotics101.cartoon.sync import check_action_overlap
    timing = _charge_fixture(tmp_path, plug_before_controller=False)
    rep = QaReport("e", "t", str(tmp_path))
    rows = check_action_overlap(rep, timing, tmp_path)
    assert {c.id: c.status for c in rep.checks}["sync.action_narration"] == "pass", rows


def test_ep1_spec_plugs_in_on_the_battery_low_beat():
    spec = json.loads(CARTOON.read_text())
    beats = next(s for s in spec["scenes"] if s["sceneId"] == "scene-003")["beats"]
    i = next(k for k, b in enumerate(beats) if b.get("do") == "plug_in")
    assert "battery" in beats[i - 1]["text"].lower()
    nxt = next(b for b in beats[i + 1:] if b["type"] == "line")
    assert nxt["speaker"] == "bolt" and "sleepy" in nxt["text"].lower()


def test_safe_area_excess():
    from robotics101.cartoon.scenes import safe_area_excess
    assert safe_area_excess([0.1, 0.1, 0.9, 0.9]) == 0.0
    assert safe_area_excess([0.7, -0.02, 0.98, 0.3]) > 0.03          # M05.7 card poked above the top edge


def test_servo_track_drives_arm_and_dial_together():
    """M05.8: the split screen's dial and Bolt's stage arm read one servo track: 0 -> 30, hold, 30 -> 60, hold."""
    from robotics101.cartoon.motion import ACTIONS as MOTIONS
    from robotics101.cartoon.scenes import servo_angle
    track = [(1.0, 2.0, 5.0, 0.0, 30.0), (5.0, 6.0, 9.0, 30.0, 60.0)]
    assert servo_angle(track, 0.5) == 0.0 and servo_angle(track, 2.0) == 30.0 and servo_angle(track, 4.9) == 30.0
    assert 30.0 < servo_angle(track, 5.5) < 60.0 and servo_angle(track, 8.0) == 60.0
    # the stage verb ends exactly where the dial ends (arm_r = 90 + servo angle)
    assert MOTIONS["servo_arm"](1.0, "30:60")["arm_r"] == 150.0
    assert MOTIONS["servo_arm"](0.0, "30:60")["arm_r"] == 120.0


def test_servo_split_and_cause_visuals_draw():
    import pytest
    pytest.importorskip("manim")
    from robotics101.cartoon.explainers import ILLUSTRATION_BOX, servo_cause, servo_split
    track = [(1.0, 2.0, 5.0, 0.0, 30.0), (5.0, 6.0, 9.0, 30.0, 60.0)]
    for t in (0.5, 1.5, 3.0, 6.2, 8.0):
        g = servo_split(t, {"track": track, "clap": 6.0}, ILLUSTRATION_BOX)
        assert g.width > 10
    for t in (0.2, 1.2, 2.2, 3.5):
        assert servo_cause(t, {"goal": 60, "t0": 0.0, "send": 0.5, "end": 4.0}, ILLUSTRATION_BOX).width > 10
