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


def _reap_writers(root, timeout=10.0):
    """Kill and reap leftover processes still writing under ``root`` (the terminated worker's orphaned ffmpeg
    encoder can outlive pool.terminate() for a moment), so the temp dir can be removed."""
    import multiprocessing
    import os
    import signal
    for child in multiprocessing.active_children():   # reaps finished pool workers
        child.join(timeout=1.0)
    deadline = time.monotonic() + timeout
    root = str(root)
    while time.monotonic() < deadline:
        pids = []
        for pid in filter(str.isdigit, os.listdir("/proc")):
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    if root.encode() in fh.read():
                        pids.append(int(pid))
            except OSError:
                continue
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.2)


def _rmtree_retry(path, tries=20):
    import shutil
    for _ in range(tries):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:                                # "Directory not empty": a writer was still flushing
            time.sleep(0.25)
    shutil.rmtree(path, ignore_errors=True)


def test_wedged_worker_fails_loudly(tmp_path, monkeypatch):
    """Test-only hardening (CC-1): the killed worker may still be writing its chunk when render_clip leaves its
    TemporaryDirectory, which once failed the suite with 'OSError: Directory not empty'. The temp dir is put
    under tmp_path with ignore_cleanup_errors, leftover writers are reaped, then it is removed with retries."""
    import tempfile
    import types
    monkeypatch.setattr(render2d, "CHUNK_TIMEOUT_S", 3.0)
    work = tmp_path / "work"
    work.mkdir()
    real_td = tempfile.TemporaryDirectory
    monkeypatch.setattr(render2d, "tempfile", types.SimpleNamespace(
        TemporaryDirectory=lambda *a, **k: real_td(*a, dir=str(work), ignore_cleanup_errors=True, **k)))

    def stuck(t):
        time.sleep(60)
        return []

    t0 = time.monotonic()
    with pytest.raises(RuntimeError, match="no progress"):
        render2d.render_clip(stuck, 60, tmp_path / "c.mp4", width=160, height=90, workers=2)
    assert time.monotonic() - t0 < 30
    _reap_writers(work)
    _rmtree_retry(work)
    assert not work.exists()
