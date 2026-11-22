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
