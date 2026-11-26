"""The authoring catalogue (PLAN-authoring §5.1): built from code, joined with capability cards.

``build_catalog()`` lists what a script may use — cartoon templates, staging, default shots, library visuals,
concept icons, vignettes, SFX, music cues, sets, background themes and (A5/A6) the parametric kit primitives — each
with its capability card from ``authoring/capabilities.yaml``. ``card_problems()`` reports every disagreement
between code and cards (the consistency test fails on any).
"""

from __future__ import annotations

import inspect
import re
from functools import lru_cache
from pathlib import Path

import yaml

from robotics101.authoring import DATA

CARDS = DATA / "capabilities.yaml"


@lru_cache(maxsize=2)
def _cards(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def cards(path: Path | None = None) -> dict:
    return _cards(str(path or CARDS))


def code_icons() -> list[str]:
    """Concept-card icon kinds drawn by ``props.concept_icon`` (parsed from its ``if k == ...`` branches)."""
    from robotics101.cartoon import props
    return sorted(set(re.findall(r'if k == "([a-z_]+)"', inspect.getsource(props.concept_icon))))


def code_inventory() -> dict[str, list[str]]:
    from robotics101.cartoon import BACKGROUND_THEMES, MUSIC_CUES, SETS, SFX_IDS
    from robotics101.cartoon.vignettes import KINDS
    from robotics101.cartoon.visuals import all_visuals
    from robotics101.templates.registry import REGISTRY
    inv = {"templates": sorted(n for (e, n) in REGISTRY if e == "cartoon"),
           "visuals": sorted(all_visuals()),
           "icons": code_icons(),
           "vignettes": sorted(KINDS),
           "sfx": sorted(SFX_IDS), "music": sorted(MUSIC_CUES), "sets": sorted(SETS),
           "backgrounds": sorted(BACKGROUND_THEMES)}
    try:
        from robotics101.cartoon.kit import PRIMITIVES
        inv["kit"] = sorted(PRIMITIVES)
    except ImportError:                                 # before A5
        inv["kit"] = []
    return inv


def card_problems(card_doc: dict | None = None) -> list[str]:
    c = card_doc or cards()
    inv = code_inventory()
    out = []
    for key, names in inv.items():
        have = c.get(key) or ({} if key not in ("sfx", "music", "sets", "backgrounds") else [])
        have_names = set(have) if isinstance(have, (dict, list)) else set()
        for n in sorted(set(names) - have_names):
            out.append(f"{key}: {n!r} exists in code but has no capability card")
        for n in sorted(have_names - set(names)):
            out.append(f"{key}: card {n!r} has no implementation in code")
    from robotics101.cartoon.scenes import STAGING
    for n in (c.get("templates") or {}):
        if n not in STAGING:
            out.append(f"templates: {n!r} has a card but no staging function")
        card = c["templates"][n] or {}
        for f in ("teaches", "shows", "needs", "params", "cannotShow"):
            if f not in card:
                out.append(f"templates: {n!r} card misses {f!r}")
    for n, card in (c.get("kit") or {}).items():
        for f in ("teaches", "shows", "params", "cannotShow", "presets"):
            if f not in (card or {}):
                out.append(f"kit: {n!r} card misses {f!r}")
    return out


def build_catalog(card_doc: dict | None = None) -> dict:
    """Machine-readable catalogue for prompts / the binder (deterministic, sorted)."""
    from robotics101.cartoon.episode import DEFAULT_SHOTS
    c = card_doc or cards()
    inv = code_inventory()
    cat = {"version": c.get("version", 1)}
    for key in ("templates", "visuals", "icons", "vignettes", "kit"):
        cat[key] = {n: {**(c.get(key) or {}).get(n, {}), **({"defaultShots": n in DEFAULT_SHOTS}
                                                           if key == "templates" else {})}
                    for n in inv[key]}
    cat["visualPrefixes"] = c.get("visualPrefixes") or {}
    for key in ("sfx", "music", "sets", "backgrounds"):
        cat[key] = inv[key]
    return cat


def entries(cat: dict | None = None) -> list[dict]:
    """Flat list of bindable entries ``{kind, name, teaches, shows, cannotShow, presets}`` for the binder."""
    cat = cat or build_catalog()
    out = []
    for kind in ("templates", "visuals", "kit"):
        for name, card in cat[kind].items():
            out.append({"kind": {"templates": "template", "visuals": "visual", "kit": "kit"}[kind], "name": name,
                        "teaches": list(card.get("teaches") or []), "shows": list(card.get("shows") or []),
                        "cannotShow": list(card.get("cannotShow") or []), "presets": card.get("presets") or {}})
    return out


__all__ = ["CARDS", "build_catalog", "card_problems", "cards", "code_icons", "code_inventory", "entries"]
