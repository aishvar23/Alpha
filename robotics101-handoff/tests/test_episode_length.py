"""ADR-034: the episode length window is a configurable pipeline default (270..420 s)."""

import json

import pytest

from robotics101.qa import QaReport
from robotics101.validation import (DEFAULT_EPISODE_DURATION_RANGE_S, episode_duration_range,
                                    episode_duration_range_for, validate_episode)


def test_default_allows_the_6m38s_episode():
    lo, hi = episode_duration_range()
    assert (lo, hi) == DEFAULT_EPISODE_DURATION_RANGE_S == (270.0, 420.0)
    assert lo <= 398.267 <= hi
    assert not lo <= 269.0 and not 421.0 <= hi


def test_spec_field_overrides_and_env_overrides(monkeypatch):
    assert episode_duration_range({"final": {"durationRangeSeconds": [240, 360]}}) == (240.0, 360.0)
    monkeypatch.setenv("ROBOTICS101_DURATION_RANGE", "250, 500")
    assert episode_duration_range() == (250.0, 500.0)
    assert episode_duration_range({"final": {"durationRangeSeconds": [240, 360]}}) == (240.0, 360.0)   # spec wins
    with pytest.raises(ValueError):
        episode_duration_range({"final": {"durationRangeSeconds": [400, 300]}})


def test_bundle_reads_its_episode_json(tmp_path):
    assert episode_duration_range_for(tmp_path) == (270.0, 420.0)
    (tmp_path / "episode.json").write_text(json.dumps({"final": {"durationRangeSeconds": [100, 200]}}))
    assert episode_duration_range_for(tmp_path) == (100.0, 200.0)


def test_schema_accepts_final_duration_range():
    from pathlib import Path
    spec = json.loads((Path(__file__).resolve().parents[1] / "examples" / "episode-001-cartoon.json").read_text())
    spec["final"] = {"durationRangeSeconds": [270, 420]}
    assert validate_episode(spec).ok
    spec["final"] = {"durationRangeSeconds": [270]}
    assert not validate_episode(spec).ok


def test_dialogue_total_duration_uses_the_window(tmp_path):
    from robotics101.voice import qa as VQ
    lo, hi = episode_duration_range_for(tmp_path)
    assert (lo, hi) == (270.0, 420.0) and VQ.TOTAL_RANGE_S == (270.0, 420.0)
    rep = QaReport("e", "t", str(tmp_path))
    rep.soft("dialogue.total_duration", lo <= 398.3 <= hi, "x", 398.3)
    assert rep.checks[0].status == "pass"
