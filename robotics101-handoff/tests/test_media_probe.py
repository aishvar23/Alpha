"""M05.4: decode probes (-count_frames) get a longer budget and one retry on timeout; real errors are not retried."""

import json
from types import SimpleNamespace

import pytest

from robotics101 import media


def _fake_run(outcomes, calls):
    def run(cmd, timeout=0, what=""):
        calls.append((cmd, timeout))
        o = outcomes.pop(0)
        if isinstance(o, Exception):
            raise o
        return SimpleNamespace(stdout=json.dumps(o))
    return run


def test_decode_probe_retries_once_on_timeout(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "run", _fake_run([media.MediaError("ffprobe timed out after 900s: x"),
                                                 {"streams": []}], calls))
    assert media.ffprobe_json("x.mp4", "ffprobe", count_frames=True) == {"streams": []}
    assert len(calls) == 2 and all("-count_frames" in c for c, _ in calls)
    assert all(t == media.DECODE_PROBE_TIMEOUT_S for _, t in calls)


def test_decode_probe_second_timeout_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "run", _fake_run([media.MediaError("ffprobe timed out after 900s: x")] * 2, calls))
    with pytest.raises(media.MediaError, match="timed out"):
        media.ffprobe_json("x.mp4", "ffprobe", count_frames=True)
    assert len(calls) == 2


def test_probe_errors_and_header_probes_not_retried(monkeypatch):
    calls = []
    monkeypatch.setattr(media, "run", _fake_run([media.MediaError("ffprobe failed (exit 1): x")], calls))
    with pytest.raises(media.MediaError, match="exit 1"):
        media.ffprobe_json("x.mp4", "ffprobe", count_frames=True)
    assert len(calls) == 1
    calls.clear()
    monkeypatch.setattr(media, "run", _fake_run([media.MediaError("ffprobe timed out after 300s: x")], calls))
    with pytest.raises(media.MediaError):
        media.ffprobe_json("x.mp4", "ffprobe")
    assert len(calls) == 1 and calls[0][1] == media.PROBE_TIMEOUT_S
