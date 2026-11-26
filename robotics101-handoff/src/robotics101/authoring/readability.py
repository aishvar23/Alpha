"""Reading level (PLAN-authoring §4.4): pure-Python syllable counter + Flesch-Kincaid grade."""

from __future__ import annotations

import re

_VOWELS = "aeiouy"
_WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")


def syllables(word: str) -> int:
    w = word.lower().strip("'")
    w = re.sub(r"'[a-z]+$", "", w)
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    groups = re.findall(r"[aeiouy]{1,2}", w)
    return max(1, len(groups))


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+|\.\.\.", text) if p.strip()]
    return [p for p in parts if _WORD.search(p)]


def stats(texts: list[str]) -> dict:
    sents = [s for t in texts for s in sentences(t)]
    words = [w for s in sents for w in _WORD.findall(s)]
    n_s, n_w = max(1, len(sents)), max(1, len(words))
    syl = sum(syllables(w) for w in words)
    grade = 0.39 * (n_w / n_s) + 11.8 * (syl / n_w) - 15.59
    longest = max((len(_WORD.findall(s)) for s in sents), default=0)
    return {"sentences": len(sents), "words": len(words), "avgWords": round(n_w / n_s, 2), "maxWords": longest,
            "fkGrade": round(grade, 2)}


__all__ = ["sentences", "stats", "syllables"]
