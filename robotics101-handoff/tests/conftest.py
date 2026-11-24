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
