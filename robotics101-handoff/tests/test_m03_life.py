"""M03.3: character life — idle breathing/sway/glances, listener reactions, anticipation/follow-through, and the
pose-track "nobody is ever static" check (unit level + QA wiring)."""

import pytest

from robotics101.cartoon.liveliness import MAX_STATIC_S, key_points, static_runs
from robotics101.cartoon.motion import Performer, glance_schedule
from robotics101.cartoon.qa import check_liveliness
from robotics101.qa import QaReport


def _track(p: Performer, seconds: float, height: float = 1.12):
    return [key_points(p.state(n / 30), height) for n in range(int(seconds * 30))]


def test_static_runs_detects_a_frozen_character_and_resets_on_excluded_frames():
    frozen = [[(0.0, 0.0), (10.0, 10.0)]] * 60
    assert static_runs(frozen)[0] == pytest.approx(2.0)
    split = frozen[:20] + [None] + frozen[:20]
    assert static_runs(split)[0] == pytest.approx(20 / 30)
    moving = [[(float(i * 7), 0.0)] for i in range(60)]
    assert static_runs(moving)[0] <= 1 / 30


def test_idle_landed_nib_is_alive_with_life_and_frozen_without():
    alive = Performer("nib", x=0.0, scale=0.95).finalize(6.0)
    frozen = Performer("nib", x=0.0, scale=0.95).finalize(6.0)
    frozen.life = False
    assert static_runs(_track(alive, 6.0))[0] <= MAX_STATIC_S
    assert static_runs(_track(frozen, 6.0))[0] > MAX_STATIC_S


@pytest.mark.parametrize("cid,h", [("bolt", 3.3), ("maya", 3.96), ("nib", 1.12)])
def test_idle_characters_never_hold_still_for_a_second(cid, h):
    p = Performer(cid, x=0.0, scale=0.8).finalize(12.0)
    assert static_runs(_track(p, 12.0, h))[0] <= MAX_STATIC_S


def test_glances_are_seeded_bounded_and_spread_out():
    g = glance_schedule("maya", 30.0)
    assert g == glance_schedule("maya", 30.0) and g != glance_schedule("bolt", 30.0)
    assert len(g) >= 8
    for (a, b, dx, dy), nxt in zip(g, g[1:] + [None]):
        assert 0.4 <= b - a <= 0.95 and abs(dx) <= 0.5 and abs(dy) <= 0.2
        if nxt:
            assert nxt[0] - b >= 1.0
    p = Performer("maya", x=0.0).finalize(30.0)
    a, b, dx, _ = g[0]
    assert p.state((a + b) / 2).pose.gaze[0] == pytest.approx(dx, abs=1e-6)


def test_listener_leans_toward_the_speaker_and_reacts_when_the_line_ends():
    quiet = Performer("bolt", x=0.0, facing=1).finalize(5.0)
    lis = Performer("bolt", x=0.0, facing=1).listen(1.0, 3.0, speaker_x=3.0).finalize(5.0)
    assert lis.state(2.0).pose.lean > quiet.state(2.0).pose.lean + 0.03            # leans toward the speaker
    left = Performer("bolt", x=0.0, facing=1).listen(1.0, 3.0, speaker_x=-3.0).finalize(5.0)
    assert left.state(2.0).pose.lean < quiet.state(2.0).pose.lean - 0.03
    assert lis.state(3.3).pose.squash < quiet.state(3.3).pose.squash - 0.03         # reaction bounce


def test_moves_get_anticipation_and_follow_through():
    still = Performer("maya", x=0.0, facing=1).finalize(6.0)
    p = Performer("maya", x=0.0, facing=1)
    p.move(2.0, 3.0, x=3.0)
    p.finalize(6.0)
    assert p.state(1.9).pose.lean < still.state(1.9).pose.lean - 0.03              # wind-up backwards
    over = [p.state(3.0 + k / 30).pose.lean - still.state(3.0 + k / 30).pose.lean for k in range(1, 36)]
    assert max(over) > 0.05 and abs(over[-1]) < max(over) / 2                       # overshoot, then settles


def test_qa_flags_a_static_character_and_passes_lively_ones():
    rep = QaReport(None, "full", "x")
    check_liveliness(rep, {"scene-001": {"liveliness": {"bolt": {"longestStaticS": 0.4, "at": 1.0}}},
                           "scene-002": {"liveliness": {"nib": {"longestStaticS": 1.6, "at": 7.2}}}})
    c = rep.checks[-1]
    assert c.id == "characters.alive" and c.status == "fail" and "nib 1.60s in scene-002" in c.message
    rep = QaReport(None, "full", "x")
    check_liveliness(rep, {"scene-001": {"liveliness": {"bolt": {"longestStaticS": 0.4, "at": 1.0}}}})
    assert rep.checks[-1].status == "pass"
    rep = QaReport(None, "full", "x")
    check_liveliness(rep, {"scene-001": {}})
    assert rep.checks[-1].status == "warn"
