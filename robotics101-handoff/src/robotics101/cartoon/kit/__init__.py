"""Parametric visual kit (PLAN-authoring §5.2–5.4, A4–A6).

Each primitive is implemented **once** as deterministic, always-animated drawing code; an episode spec only supplies
*data* (a shot's ``kit = {primitive, params, cues, title}``), never drawing code. A primitive is
``fn(t, ctx, box) -> VGroup`` like every other wide visual (``cartoon.visuals``); ``ctx`` carries the shot's params
(``$param`` references already resolved to scene parameters) and cue times taken from the scene (``word:<w>`` = when
that word is spoken in the covered lines, ``sfx:<id>`` = when that sound plays in the covered beats).

``visual_gap`` (A4) is the explicit placeholder for a visual the catalogue cannot draw yet: unmistakably a
placeholder ("VISUAL COMING SOON"), listed in ``visual_gaps.json``, failed by QA ``authoring.visual_gaps`` and listed
as a publish blocker.
"""

from __future__ import annotations

from robotics101.cartoon.kit.common import PRIMITIVES, context, resolve_params, visual  # noqa: F401
from robotics101.cartoon.kit import placeholder  # noqa: F401  (registers visual_gap)

GAP_VISUAL = "visual_gap"
KIT_PREFIX = "kit_"


def _load_primitives() -> None:
    import importlib
    for mod in ("labeled_parts", "flow", "steps", "compare", "beam", "meter", "track_map"):
        try:
            importlib.import_module(f"robotics101.cartoon.kit.{mod}")
        except ModuleNotFoundError as e:                       # primitives land milestone by milestone (A5, A6)
            if e.name != f"robotics101.cartoon.kit.{mod}":
                raise


_load_primitives()

__all__ = ["GAP_VISUAL", "KIT_PREFIX", "PRIMITIVES", "context", "resolve_params", "visual"]
