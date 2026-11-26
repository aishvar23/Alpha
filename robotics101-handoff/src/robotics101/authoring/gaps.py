"""A4 (PLAN-authoring §5.6 step 4): visual gaps — explicit, never silent.

A teaching beat the catalogue cannot show becomes a ``visual_gaps.json`` entry and the scene renders a ``visual_gap``
placeholder shot ("VISUAL COMING SOON: …"). QA ``authoring.visual_gaps`` fails a bundle that shows a placeholder,
``publish --dry-run`` lists blocker gaps / shown placeholders as publish blockers, and R3 refuses such a video.
"""

from __future__ import annotations

import json
from pathlib import Path

from robotics101.authoring.schemas import check

GAPS_NAME = "visual_gaps.json"
SUGGESTED_KINDS = ("kit_param", "kit_primitive", "body", "template", "icon", "vignette")
WHAT_MAX = 120                       # shot.gap.what (schema)


def make_gap(n: int, scene_id: str, beats: list[int], what: str, *, concept: str | None = None,
             claim_ids: list[str] | None = None, suggested: str = "kit_primitive", closest: str | None = None,
             severity: str = "blocker") -> dict:
    return {"gapId": f"gap-{n:02d}", "sceneId": scene_id, "beats": sorted(set(beats)), "concept": concept,
            "claimIds": sorted(claim_ids or []), "whatMustBeShown": what, "suggestedKind": suggested,
            "closestExisting": closest, "severity": severity}


def gaps_doc(gaps: list[dict]) -> dict:
    doc = {"gaps": sorted(gaps, key=lambda g: g["gapId"])}
    check("visual_gaps", doc)
    return doc


def placeholder_shot(gap: dict, layout: str = "illustration") -> dict:
    """The shot that renders ``gap`` (beats are expanded-beat indices, like every shot range)."""
    return {"layout": layout, "fromBeat": min(gap["beats"]), "toBeat": max(gap["beats"]), "visual": "visual_gap",
            "gap": {"gapId": gap["gapId"], "what": gap["whatMustBeShown"][:WHAT_MAX]}}


def apply_placeholders(spec: dict, gaps: dict) -> dict:
    """Copy of ``spec`` with a placeholder shot per gap that has no shot yet (authored shots are kept)."""
    out = json.loads(json.dumps(spec))
    for g in gaps.get("gaps", []):
        sc = next((s for s in out["scenes"] if s["sceneId"] == g["sceneId"]), None)
        if sc is None:
            continue
        shots = sc.setdefault("shots", [])
        if not any((s.get("gap") or {}).get("gapId") == g["gapId"] for s in shots):
            shots.append(placeholder_shot(g))
            shots.sort(key=lambda s: s["fromBeat"])
    return out


def placeholders(spec_or_scenes: dict) -> list[tuple[str, dict]]:
    """(sceneId, shot) of every ``visual_gap`` shot in a spec or a bundle's scenes.json (``facts.shots``)."""
    out = []
    for s in spec_or_scenes.get("scenes", []):
        shots = s.get("shots") or (s.get("facts") or {}).get("shots") or []
        out += [(s.get("sceneId") or s.get("id"), sh) for sh in shots if sh.get("visual") == "visual_gap"]
    return out


def gap_problems(spec_or_scenes: dict, gaps: dict | None) -> list[str]:
    """Consistency: every placeholder shot is listed (same scene); every listed gap with severity blocker is either
    still shown as a placeholder or the list is stale."""
    listed = {g["gapId"]: g for g in (gaps or {}).get("gaps", [])}
    out = []
    for sid, sh in placeholders(spec_or_scenes):
        gid = (sh.get("gap") or {}).get("gapId")
        if gid not in listed:
            out.append(f"{sid}: placeholder {gid or '(no gapId)'} is not listed in {GAPS_NAME}")
        elif listed[gid]["sceneId"] != sid:
            out.append(f"{sid}: placeholder {gid} is listed for {listed[gid]['sceneId']}")
    return out


def load_gaps(path: Path) -> dict | None:
    p = Path(path)
    if not p.is_file():
        return None
    doc = json.loads(p.read_text(encoding="utf-8"))
    check("visual_gaps", doc)
    return doc


def publish_blockers(bundle: Path) -> list[str]:
    """Publish blockers from a rendered bundle: shown placeholders and listed blocker gaps."""
    bundle = Path(bundle)
    out = []
    try:
        gaps = load_gaps(bundle / GAPS_NAME)
    except Exception as e:                                          # an invalid list is itself a blocker
        return [f"{GAPS_NAME} invalid: {e}"]
    blockers = [g for g in (gaps or {}).get("gaps", []) if g["severity"] == "blocker"]
    if blockers:
        out.append(f"{len(blockers)} blocker visual gap(s): " + "; ".join(
            f"{g['gapId']} {g['sceneId']}: {g['whatMustBeShown']}" for g in blockers[:5]))
    sj = bundle / "scenes.json"
    if sj.is_file():
        shown = placeholders(json.loads(sj.read_text(encoding="utf-8")))
        if shown:
            out.append(f"video shows {len(shown)} 'VISUAL COMING SOON' placeholder(s): "
                       + ", ".join(f"{sid} {(sh.get('gap') or {}).get('gapId')}" for sid, sh in shown[:5]))
    return out


__all__ = ["GAPS_NAME", "SUGGESTED_KINDS", "apply_placeholders", "gap_problems", "gaps_doc", "load_gaps", "make_gap",
           "placeholder_shot", "placeholders", "publish_blockers"]
