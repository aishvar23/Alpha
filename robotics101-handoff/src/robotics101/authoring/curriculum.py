"""Curriculum sequence (curriculum/sequence.yaml) and canon (curriculum/canon.json), PLAN-authoring §2."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import yaml

from robotics101.authoring import CURRICULUM
from robotics101.authoring.schemas import check

SEQUENCE = CURRICULUM / "sequence.yaml"
CANON = CURRICULUM / "canon.json"
# a line that names a different robot / sensor may use a different value for a canon quantity (§2)
DIFFERENT_MARKERS = ("light", "infrared", " ir ", "new sensor", "different", "another", "other robot", "this robot",
                     "laser", "camera")


@lru_cache(maxsize=4)
def _load_sequence(path: str) -> dict:
    return check("sequence", yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def sequence(path: Path | None = None) -> dict:
    return _load_sequence(str(path or SEQUENCE))


def topic(topic_id: str, path: Path | None = None) -> dict:
    for t in sequence(path)["topics"]:
        if t["topicId"] == topic_id:
            return t
    raise KeyError(f"topic {topic_id!r} is not in {path or SEQUENCE}")


def sequence_problems(seq: dict) -> list[str]:
    """Prerequisites must exist and come earlier in the sequence; ids unique."""
    out, seen = [], set()
    for t in seq["topics"]:
        if t["topicId"] in seen:
            out.append(f"{t['topicId']}: duplicate topicId")
        for p in t["prerequisites"]:
            if p not in seen:
                out.append(f"{t['topicId']}: prerequisite {p!r} is not an earlier topic")
        seen.add(t["topicId"])
    return out


def canon(path: Path | None = None) -> dict:
    return check("canon", json.loads(Path(path or CANON).read_text(encoding="utf-8")))


_UNIT_OF = {"m": "m", "deg": "deg"}


def canon_problems(spec: dict, canon_doc: dict | None = None) -> list[tuple[str, str]]:
    """A spoken number about a canon quantity that differs from canon (§2), unless the line marks a different
    robot/sensor. A line is "about" a quantity when it contains one of its keywords and a number in its unit; it is a
    problem only when none of its numbers in that unit equals the canon value (readings near a threshold are fine
    as long as the threshold itself is stated correctly)."""
    from robotics101.cartoon.lint import spoken_quantities
    cdoc = canon_doc or canon()
    out = []
    for i, s in enumerate(spec.get("scenes", [])):
        for j, b in enumerate(s.get("beats", [])):
            if b.get("type") != "line":
                continue
            text = b.get("text", "")
            low = f" {text.lower()} "
            if any(m in low for m in DIFFERENT_MARKERS):
                continue
            qs = spoken_quantities(text)
            for q in cdoc["quantities"]:
                if not any(re.search(rf"\b{re.escape(k)}", low) for k in q["keywords"]):
                    continue
                vals = [v for v, kind, _ in qs if _kind_unit(kind) == q["unit"]]
                if vals and all(abs(v - q["value"]) > 1e-6 for v in vals):
                    out.append((f"$.scenes[{i}].beats[{j}].text",
                                f"canon: {q['subject']} is {q['value']:g} {q['unit']} ({q['episode']}); line says "
                                f"{', '.join(f'{v:g}' for v in vals)} {q['unit']} — mark a different robot/sensor or "
                                f"use the canon value"))
    return out


def _kind_unit(kind: str) -> str:
    return {"length": "m", "angle": "deg", "m": "m", "deg": "deg", "meters": "m", "degrees": "deg"}.get(kind, kind)


__all__ = ["CANON", "DIFFERENT_MARKERS", "SEQUENCE", "canon", "canon_problems", "sequence", "sequence_problems",
           "topic"]
