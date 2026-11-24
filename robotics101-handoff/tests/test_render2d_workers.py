"""M05.4: forked render workers must never hang (fresh Pango font map per worker + watchdog)."""

from __future__ import annotations

import time

import pytest

from robotics101.cartoon import render2d


def _text_frames(t):
    from manim import Text
    return [Text(f"frame {int(t * 10) % 3}", font="Fredoka", font_size=40)]


def test_workers_render_text_after_parent_used_pango(tmp_path):
    """The parent lays out text first (as the pipeline does between scenes); forked workers then need new
    fontsets. Without the per-worker font-map reset this deadlocked in g_cond_wait."""
    from manim import Text, tempconfig
    with tempconfig({"media_dir": str(tmp_path / "parent-media"), "disable_caching": True}):
        Text("parent uses pango", font="Fredoka", font_size=30)
    out = render2d.render_clip(_text_frames, 60, tmp_path / "c.mp4", width=160, height=90, workers=2)
    assert out.stat().st_size > 0


def test_workers_install_pango_reset(monkeypatch):
    assert render2d._worker_init.__name__ == "_worker_init"
    called = []
    monkeypatch.setattr(render2d, "reset_pango_after_fork", lambda: called.append(1))
    render2d._worker_init()
    assert called == [1]
    monkeypatch.undo()
    render2d.reset_pango_after_fork()           # safe to call in-process


def test_wedged_worker_fails_loudly(tmp_path, monkeypatch):
    monkeypatch.setattr(render2d, "CHUNK_TIMEOUT_S", 3.0)

    def stuck(t):
        time.sleep(60)
        return []

    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="no progress"):
        render2d.render_clip(stuck, 60, tmp_path / "c.mp4", width=160, height=90, workers=2)
    assert time.monotonic() - t0 < 30
