"""Authoring configuration (authoring/config.yaml). PROVISIONAL values are owner-tunable plan defaults (§12)."""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path

import yaml

from robotics101.authoring import DATA

CONFIG = DATA / "config.yaml"
PRICES = DATA / "prices.yaml"


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def config(path: Path | None = None) -> dict:
    return copy.deepcopy(_load(str(path or CONFIG)))


def prices(path: Path | None = None) -> dict:
    return copy.deepcopy(_load(str(path or PRICES)))


def engagement_thresholds(age_band: str = "6-9", cfg: dict | None = None) -> dict:
    e = dict((cfg or config())["engagement"])
    if age_band == "9-12":                      # slightly relaxed for older kids (§6.2)
        k = e["relax9to12"]
        for key in ("visualChangeMaxS", "visualChangeWarnS", "monologueMaxS", "gagWindowS", "hookFirstGagS"):
            e[key] = round(e[key] * k, 3)
        for key in ("gagPerMin", "reactionPerMin"):
            e[key] = round(e[key] / k, 3)
    return e


__all__ = ["CONFIG", "PRICES", "config", "engagement_thresholds", "prices"]
