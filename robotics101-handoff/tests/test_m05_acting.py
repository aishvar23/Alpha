"""M05.3: Cocomelon-style acting — emotion-pose library + script cues with auto defaults, squash/stretch hops, head
tilts, brows, secondary motion (antenna, hair), listener reactions, celebrations; motion-energy QA."""

import json
import math
from pathlib import Path

import numpy as np
import pytest

from robotics101.cartoon import acting as A
from robotics101.qa import QaReport

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", A.POSE_NAMES)
def test_every_pose_is_deterministic_and_eases_in_and_out(name):
    fn = A.pose_fn(name)
    assert fn(0.37) == fn(0.37)
    for u in (0.0, 1.0):                                # no pops at the ends of a pose
        o = fn(u)
        assert abs(o.get("lean", 0)) < 0.03 and abs(o.get("head_tilt", 0)) < 0.03 and abs(o.get("dy", 0)) < 0.03
        assert abs(o.get("arm_l", 20) - 20) < 8 and abs(o.get("arm_r", 20) - 20) < 8
    peak = max(abs(fn(k / 40).get("dy", 0)) + abs(fn(k / 40).get("lean", 0)) + abs(fn(k / 40).get("head_tilt", 0))
               + abs(fn(k / 40).get("squash", 1) - 1) for k in range(41))
    assert peak > 0.08                                  # visibly acts


def test_hops_squash_before_and_after_and_stretch_in_the_air():
    o = [A.pose_fn("excited")(k / 100) for k in range(50)]
    assert min(x["squash"] for x in o[:10]) < 0.9                  # anticipation squash
    air = max(o, key=lambda x: x["dy"])
    assert air["dy"] > 0.25 and air["squash"] > 1.05               # stretched at the top


def test_auto_pose_and_reaction_rules():
    assert A.auto_pose({"text": "Wow!", "emotion": "surprised"}) == "surprised"
    assert A.auto_pose({"text": "Ha!", "emotion": "laugh"}) == "giggle"
    assert A.auto_pose({"text": "Look at me", "emotion": "proud"}) == "proud"
    assert A.auto_pose({"text": "Is 0.6 less than 0.5?", "emotion": "happy"}) == "curious"
    assert A.auto_pose({"text": "Let's roll!", "emotion": "happy"}) == "excited"
    assert A.auto_pose({"text": "x", "pose": "celebrate"}) == "celebrate"
    assert A.auto_pose({"text": "A long calm explanation of how a sensor works."}) in ("talk_bounce", "nod")
    assert A.auto_react({"text": "x"}, "giggle") == ("giggle", 0.6)
    assert A.auto_react({"text": "x", "react": "nod"}, "giggle") == ("nod", 0.8)


pytest.importorskip("manim")

from robotics101.cartoon.motion import Performer  # noqa: E402
from robotics101.cartoon.rigs import Pose, build  # noqa: E402


def _part(g, name):
    return g.parts[name].get_center()


def test_rig_channels_move_the_right_parts_and_stay_on_the_ground():
    m0, m1 = build("maya", Pose()), build("maya", Pose(head_tilt=0.25))
    assert np.linalg.norm(_part(m0, "head") - _part(m1, "head")) > 0.1
    assert np.allclose(_part(m0, "torso"), _part(m1, "torso"))                 # the body stays, the head tilts
    assert _part(build("maya", Pose(brow=1.0)), "brows")[1] > _part(m0, "brows")[1] + 0.05
    assert _part(build("maya", Pose(hair=1.0)), "puffs")[1] > _part(m0, "puffs")[1] + 0.03
    legs = build("maya", Pose(stride=1.0)).parts["legs"]
    assert legs[0].get_center()[0] != pytest.approx(m0.parts["legs"][0].get_center()[0], abs=0.05)
    b0, b1 = build("bolt", Pose()), build("bolt", Pose(antenna=0.4))
    assert abs(_part(b0, "bulb")[0] - _part(b1, "bulb")[0]) > 0.15 and np.allclose(_part(b0, "body"), _part(b1, "body"))
    assert not np.allclose(_part(build("bolt", Pose(wheel=1.5)), "hubs"), _part(b0, "hubs"))
    assert len(build("bolt", Pose(expression="worried")).parts["brows"]) == 2       # LED brows for strong feelings
    for cid in ("bolt", "maya", "nib"):
        g = build(cid, Pose(expression="happy", head_tilt=0.3, brow=1, antenna=0.5, hair=1, stride=1, lean=0.2))
        assert g.get_bottom()[1] >= -1e-6


def test_emote_layers_on_actions_and_respects_rig_expressions():
    p = Performer("bolt", x=0.0)
    p.act(1.0, 2.0, "point")
    p.emote(1.0, "giggle")
    p.finalize(4.0)
    s = p.state(1.5)
    assert s.pose.expression == "laugh" and s.pose.arm_r > 80                   # pointing arm kept
    q = Performer("nib", x=0.0, scale=0.95)
    q.emote(0.0, "giggle")
    q.finalize(2.0)
    assert q.state(0.5).pose.expression == "happy"                              # Nib's rig has no laugh face
    with pytest.raises(ValueError):
        p.emote(0.0, "moonwalk")


def test_secondary_motion_follows_through_and_settles():
    p = Performer("bolt", x=-2.0)
    p.move(0.0, 0.6, x=2.0)
    p.finalize(4.0)
    during = [p.state(k / 30).pose.antenna for k in range(3, 18)]
    after = [p.state(0.6 + k / 30).pose.antenna for k in range(1, 15)]
    assert max(abs(a) for a in during) > 0.2 and max(abs(a) for a in after) > 0.05   # lags, then follows through
    assert abs(p.state(3.5).pose.antenna) < 0.08                                     # settles to the idle sway
    m = Performer("maya", x=0.0)
    m.emote(0.0, "excited")
    m.finalize(3.0)
    assert max(abs(m.state(k / 30).pose.hair) for k in range(36)) > 0.4             # hair bounces on the hops


def test_acting_metrics():
    from robotics101.cartoon.liveliness import acting_metrics
    still = [[(0.0, 0.0), (10.0, 10.0)]] * 60
    m = acting_metrics(still)
    assert m["energy"] == 0 and m["stillShare"] == 1.0
    moving = [[(5 * math.sin(i / 3) * 10, 0.0), (10.0, 10.0 + i)] for i in range(60)]
    m = acting_metrics(moving)
    assert m["energy"] > 20 and m["stillShare"] == 0.0


@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    d = tmp_path_factory.mktemp("voice")
    spec = expand_episode(json.loads((ROOT / "examples" / "episode-001-cartoon.json").read_text()), load_registry())
    timing = voice_episode(spec, load_registry(), d, B.FixtureBackend(), VoiceCache(d / "cache"), log=lambda m: None)
    return spec, timing, d


def _scene(voiced, sid, monkeypatch):
    from robotics101.cartoon import lipsync
    from robotics101.cartoon import scenes as S
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))
    spec, timing, d = voiced
    by = {s["sceneId"]: s for s in spec["scenes"]}
    t = next(x for x in timing["scenes"] if x["sceneId"] == sid)
    return S.build_scene(by[sid], t, d)


def test_scene_defaults_give_every_line_a_pose_listeners_react_and_victory_dances(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    from robotics101.cartoon.liveliness import ENERGY_MIN_PX_S, scene_acting
    sc = _scene(voiced, "scene-002", monkeypatch)
    for b in sc.lines():
        assert any(a.start == b["start_s"] and float(a.arg) == 1.0 for a in sc.perf[b["speaker"]].poses)
    assert sum(1 for a in sc.perf["nib"].poses if float(a.arg) < 1.0) >= 1                 # listener reactions
    act = scene_acting(sc, S.presence, S.HEIGHT, S.SCALES)
    assert act["maya"]["energy"] >= ENERGY_MIN_PX_S and act["bolt"]["energy"] >= ENERGY_MIN_PX_S
    assert {"giggle", "proud"} <= set(act["maya"]["poses"]) | set(act["bolt"]["poses"])
    rem = _scene(voiced, "scene-007", monkeypatch)
    vic = rem.beat("music", "cue", "victory_sting")
    assert all(any(a.name == "celebrate" and a.start == vic["start_s"] for a in p.poses) for p in rem.perf.values())


def test_authored_pose_and_react_cues_win_and_are_validated():
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    from robotics101.validation import validate_episode
    s = json.loads((ROOT / "examples" / "episode-001-cartoon.json").read_text())
    line = next(b for b in s["scenes"][1]["beats"] if b["type"] == "line")
    line.update(pose="celebrate", react="giggle")
    assert validate_episode(expand_episode(s, load_registry())).ok
    line["pose"] = "moonwalk"
    assert any("unknown pose 'moonwalk'" in str(e) for e in validate_episode(s).errors)


def _qa(spec, by):
    from robotics101.cartoon.qa import check_acting
    rep = QaReport("ep", "full", "x")
    check_acting(rep, spec, by)
    return {c.id: c for c in rep.checks}


def test_qa_acting():
    spec = {"scenes": [{"sceneId": "s1", "beats": [{"type": "line", "speaker": "maya", "text": "x"}]}]}
    good = {"maya": {"energy": 150.0, "stillShare": 0.02, "frames": 300, "poses": ["giggle", "proud", "surprised",
                                                                                   "celebrate"], "poseCount": 5},
            "nib": {"energy": 50.0, "stillShare": 0.1, "frames": 300, "poses": [], "poseCount": 0}}
    c = _qa(spec, {"s1": {"acting": good}})
    assert c["characters.acting"].status == "pass" and c["characters.celebrate"].status == "pass"
    for cid, patch, needle in (("maya", {"energy": 60.0}, "energy"), ("nib", {"energy": 30.0}, "energy"),
                               ("maya", {"stillShare": 0.5}, "still"), ("maya", {"poseCount": 0}, "without an emotion pose"),
                               ("maya", {"poses": ["nod", "giggle"]}, "distinct emotion poses")):
        bad = json.loads(json.dumps(good))
        bad[cid].update(patch)
        r = _qa(spec, {"s1": {"acting": bad}})["characters.acting"]
        assert r.status == "fail" and needle in r.message
    assert _qa(spec, {"s1": {}})["characters.acting"].status == "warn"
