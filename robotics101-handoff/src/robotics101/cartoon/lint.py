"""Script lints for cartoon episodes (M02.1): teaching facts and kid-appropriate language.

* Teaching facts: every distance/angle spoken in dialogue ("1.2 meters", "half a meter", "60 degrees",
  "three meters") must equal a numeric parameter somewhere in the episode, so the dialogue can never
  contradict what the animation shows (e.g. the 0.5 m stop rule).
* Kid-safe wording: a small deny-list for an under-13 audience (made-for-kids). Deliberately simple.
"""

from __future__ import annotations

import re

_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
          "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90}
_UNIT = r"(meters?|metres?|m\b|centimeters?|centimetres?|cm\b|degrees?|°)"
_NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*" + _UNIT, re.I)
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")\s+" + _UNIT, re.I)
_HALF_RE = re.compile(r"\bhalf\s+(?:a\s+)?(meter|metre)s?\b", re.I)
_POINT_RE = re.compile(r"\b(zero|one|two|three)\s+point\s+(" + "|".join(k for k in _WORDS if _WORDS[k] < 10) + r")\s+" + _UNIT, re.I)

DENY_WORDS = ("stupid", "dumb", "idiot", "shut up", "kill", "hate", "die", "dead", "gun", "loser", "ugly", "fat")


def _to_si(value: float, unit: str) -> tuple[float, str]:
    u = unit.lower()
    if u.startswith(("cent", "cm")):
        return value / 100.0, "m"
    if u.startswith(("deg", "°")):
        return value, "deg"
    return value, "m"


def spoken_quantities(text: str) -> list[tuple[float, str, str]]:
    """(value, 'm'|'deg', matched text) for every quantity spoken in a line."""
    out: list[tuple[float, str, str]] = []
    taken: list[tuple[int, int]] = []

    def add(m, v, unit):
        if any(a <= m.start() < b for a, b in taken):
            return
        taken.append((m.start(), m.end()))
        val, kind = _to_si(v, unit)
        out.append((round(val, 6), kind, m.group(0)))

    for m in _POINT_RE.finditer(text):
        add(m, _WORDS[m.group(1).lower()] + _WORDS[m.group(2).lower()] / 10, m.group(3))
    for m in _HALF_RE.finditer(text):
        add(m, 0.5, m.group(1))
    for m in _NUM_RE.finditer(text):
        add(m, float(m.group(1)), m.group(2))
    for m in _WORD_RE.finditer(text):
        add(m, float(_WORDS[m.group(1).lower()]), m.group(2))
    return out


def _numbers(obj) -> set[float]:
    found: set[float] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, (int, float)):
        found.add(round(float(obj), 6))
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _numbers(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _numbers(v)
    return found


def fact_problems(spec: dict) -> list[tuple[str, str]]:
    """(json path, message) for spoken quantities that match no episode parameter."""
    allowed = set()
    for s in spec.get("scenes", []):
        allowed |= _numbers(s.get("parameters", {}))
    probs = []
    for i, s in enumerate(spec.get("scenes", [])):
        for j, b in enumerate(s.get("beats", [])):
            if b.get("type") != "line":
                continue
            for val, kind, txt in spoken_quantities(b.get("text", "")):
                if val not in allowed:
                    probs.append((f"$.scenes[{i}].beats[{j}].text",
                                  f"teaching fact: dialogue says {txt!r} ({val:g} {kind}) but no scene parameter has "
                                  f"that value — dialogue must match what the animation shows"))
    return probs


def kidsafe_problems(spec: dict) -> list[tuple[str, str]]:
    probs = []
    for i, s in enumerate(spec.get("scenes", [])):
        for j, b in enumerate(s.get("beats", [])):
            if b.get("type") != "line":
                continue
            low = " " + re.sub(r"[^a-z' ]", " ", b.get("text", "").lower()) + " "
            for w in DENY_WORDS:
                if f" {w} " in low:
                    probs.append((f"$.scenes[{i}].beats[{j}].text", f"kid-safe wording: avoid {w!r} for a made-for-kids audience"))
    return probs


__all__ = ["DENY_WORDS", "fact_problems", "kidsafe_problems", "spoken_quantities"]
