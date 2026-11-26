"""Screenplay view of an EpisodeSpec for review R2 (PLAN-authoring §7): speaker, line, emotion, action, cards,
shots and kit visuals described in words, plus the visual-gap list. Plain Markdown, deterministic."""

from __future__ import annotations


def _kit_words(kit: dict) -> str:
    p = kit.get("params") or {}
    bits = ", ".join(f"{k}={v}" for k, v in sorted(p.items()) if not isinstance(v, (dict, list)))
    return f"kit {kit.get('primitive')}" + (f" “{kit['title']}”" if kit.get("title") else "") + (f" ({bits})" if bits else "")


def screenplay(spec: dict, gaps: dict | None = None, names: dict | None = None) -> str:
    names = names or {}
    out = [f"# {spec.get('title', spec.get('episodeId'))} ({spec.get('episodeId')})", ""]
    for o in spec.get("learningObjectives") or []:
        out.append(f"- objective: {o}")
    for s in spec["scenes"]:
        out += ["", f"## {s.get('sequence', '?')}. {s['sceneId']} — {s.get('title', '')} [{s['template']}]",
                f"_{s.get('educationalObjective', '')}_  target {s.get('durationTargetSeconds', '?')} s"]
        cards = {c.get("beforeBeat", 0): c for c in s.get("concepts") or []}
        shots = s.get("shots") or []
        for j, b in enumerate(s["beats"]):
            if j in cards:
                c = cards[j]
                out.append(f"> CONCEPT CARD: **{c['title']}** — {c.get('subtitle', '')} (icon {c.get('icon', '-')})")
            for sh in shots:
                if sh["fromBeat"] == j and sh["layout"] != "stage":
                    what = _kit_words(sh["kit"]) if sh.get("kit") else f"visual {sh.get('visual', 'concept')}"
                    out.append(f"> SHOT {sh['layout'].upper()} beats {sh['fromBeat']}–{sh['toBeat']}: {what}")
            t = b["type"]
            if t == "line":
                who = names.get(b["speaker"], b["speaker"].upper())
                cue = ", ".join(x for x in (b.get("emotion"), b.get("action") and f"does {b['action']}",
                                             b.get("pose") and f"pose {b['pose']}") if x)
                out.append(f"{j:>2}  **{who}**{f' ({cue})' if cue else ''}: {b['text']}"
                           + ("  ·teaching" if b.get("explain") else ""))
            elif t == "action":
                out.append(f"{j:>2}  [{b['who']} {b['do']}]")
            elif t == "sfx":
                out.append(f"{j:>2}  (sfx {b['id']})")
            elif t == "music":
                out.append(f"{j:>2}  (music {b['cue']})")
            elif t == "pause":
                out.append(f"{j:>2}  (pause {b['seconds']} s)")
    if gaps and gaps.get("gaps"):
        out += ["", "## Visual gaps"]
        for g in gaps["gaps"]:
            out.append(f"- {g['gapId']} [{g['severity']}] {g['sceneId']} beats {g['beats']}: {g['whatMustBeShown']} "
                       f"(suggest {g['suggestedKind']}; closest {g.get('closestExisting') or '-'})")
    return "\n".join(out) + "\n"


__all__ = ["screenplay"]
