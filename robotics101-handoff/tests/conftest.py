import copy
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "episode-001.json"


@pytest.fixture(scope="session")
def _sample_spec() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.fixture
def spec(_sample_spec) -> dict:
    """A fresh, mutable deep copy of examples/episode-001.json."""
    return copy.deepcopy(_sample_spec)


def scene_by_template(spec: dict, template: str) -> dict:
    return next(s for s in spec["scenes"] if s["template"] == template)


@pytest.fixture(autouse=True)
def _no_elevenlabs_network(monkeypatch, tmp_path):
    """M04.1: tests never see the real key (project .env) and never build a real SDK client."""
    monkeypatch.setenv("ROBOTICS101_DOTENV", str(tmp_path / "no-such.env"))
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    from robotics101.voice import backends

    def _blocked():
        raise AssertionError("tests must not create a real ElevenLabs client (inject client_factory)")
    monkeypatch.setattr(backends, "_sdk_client", _blocked)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """A2 (PLAN-authoring §9): tests never open an internet socket (AF_INET/AF_INET6). Unix sockets (used by
    multiprocessing / asyncio internals) stay allowed. Paid authoring providers are also disabled."""
    import socket

    real_connect, real_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def _guard(self, *a, **k):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"tests must not use the network (tried to connect to {a[0] if a else '?'})")
        return real_connect(self, *a, **k)

    def _guard_ex(self, *a, **k):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError("tests must not use the network")
        return real_connect_ex(self, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", _guard)
    monkeypatch.setattr(socket.socket, "connect_ex", _guard_ex)
    monkeypatch.delenv("ROBOTICS101_AUTHORING_LIVE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
