"""M03.1: registry-driven character intro — registry rules, episode expansion defaults, staging, QA."""

import copy
import json
from pathlib import Path

import pytest

from robotics101.cartoon.episode import INTRO_SCENE_ID, INTRO_TEMPLATE, expand_episode, main_characters
from robotics101.characters import load_registry, registry_problems
from robotics101.qa import QaReport
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "examples" / "episode-001-cartoon.json"
REG = ROOT / "characters" / "registry.json"


def _spec():
    return json.loads(CARTOON.read_text(encoding="utf-8"))


def test_every_main_character_has_a_valid_intro():
    reg = load_registry()
    assert main_characters(reg) == ["bolt", "maya", "nib"]
    for cid in main_characters(reg):
        it = reg.get(cid).raw["intro"]
        assert reg.get(cid).displayName in it["line"]["text"] and it["tagline"]


@pytest.mark.parametrize("mutate,needle", [
    (lambda c: c["bolt"].pop("intro"), "bolt.intro: required"),
    (lambda c: c["maya"]["intro"]["line"].update(text="Hello there!"), "must say the name"),
    (lambda c: c["nib"]["intro"]["line"].update(speaker="nib"), "speaking character"),
    (lambda c: c["bolt"]["intro"].update(entrance="teleport"), "not one of the character's actions"),
])
def test_registry_rejects_bad_intro(mutate, needle):
    doc = json.loads(REG.read_text())
    mutate(doc["characters"])
    assert any(needle in p for p in registry_problems(doc))


def test_expansion_adds_intro_after_cold_open_and_is_idempotent():
    reg = load_registry()
    src = _spec()
    e = expand_episode(src, reg)
    assert [s["template"] for s in e["scenes"]][:2] == ["cartoon_cold_open", INTRO_TEMPLATE]
    assert [s["sequence"] for s in e["scenes"]] == list(range(1, len(src["scenes"]) + 2))
    assert src == _spec(), "input spec must not be modified"
    assert expand_episode(e, reg) == e
    assert validate_episode(e).ok
    intro = e["scenes"][1]
    lines = [b for b in intro["beats"] if b["type"] == "line"]
    assert {b["target"] for b in lines} == {"bolt", "maya", "nib"}
    assert all(reg.get(b["target"]).displayName in b["text"] for b in lines)
    assert [c["name"] for c in intro["parameters"]["characters"]] == ["Bolt", "Maya", "Nib"]


def test_intro_defaults_apply_to_any_episode_and_can_be_turned_off_or_moved():
    reg = load_registry()
    s = _spec()
    s["scenes"] = s["scenes"][1:]                                  # no cold open -> intro goes first
    assert expand_episode(s, reg)["scenes"][0]["sceneId"] == INTRO_SCENE_ID
    s2 = _spec()
    s2["intro"] = {"enabled": False}
    assert all(x["template"] != INTRO_TEMPLATE for x in expand_episode(s2, reg)["scenes"])
    s3 = _spec()
    s3["intro"] = {"position": "start"}
    assert expand_episode(s3, reg)["scenes"][0]["template"] == INTRO_TEMPLATE
    assert validate_episode(s3).ok


def _intro_by(names=("bolt", "maya", "nib"), presence=1.0, line_ok=True):
    reg = load_registry()
    facts = [{"id": c, "name": reg.get(c).displayName, "tagline": "x", "plate": [1.0, 5.0],
              "line": (f"I'm {reg.get(c).displayName}!" if line_ok else "Hello!"), "lineStart": 1.2} for c in names]
    return {INTRO_SCENE_ID: {"facts": {"introduced": facts}, "minPresence": {c: presence for c in names}}}


@pytest.mark.parametrize("kw,ok", [({}, True), ({"names": ("bolt", "maya")}, False), ({"presence": 0.5}, False),
                                   ({"line_ok": False}, False)])
def test_qa_intro_cast(kw, ok):
    from robotics101.cartoon.qa import check_intro
    rep = QaReport("ep-001", "full", ".")
    check_intro(rep, expand_episode(_spec(), load_registry()), _intro_by(**kw))
    assert ("intro.cast" not in {c.id for c in rep.failures}) is ok
    assert "intro.present" not in {c.id for c in rep.failures}


def test_qa_intro_missing_is_a_hard_failure():
    from robotics101.cartoon.qa import check_intro
    rep = QaReport("ep-001", "full", ".")
    check_intro(rep, _spec(), {})                                   # un-expanded spec: no intro scene
    assert "intro.present" in {c.id for c in rep.failures}
    rep2 = QaReport("ep-001", "full", ".")
    s = copy.deepcopy(_spec())
    s["intro"] = {"enabled": False}
    check_intro(rep2, s, {})
    assert not rep2.failures
