"""Deterministic authoring gates (PLAN-authoring §6.1) + the engagement gate (§6.2) → ``authoring_report.json``.

``run_gates(source_spec, facts=..., outline=..., gaps=..., ...)`` never renders or voices anything. Blocking gates
must all pass before R2; warnings are reported. Thresholds come from ``authoring/config.yaml`` (PROVISIONAL).
"""

from __future__ import annotations

import copy
import re
from functools import lru_cache
from pathlib import Path

import yaml

from robotics101.authoring import DATA
from robotics101.authoring.config import config
from robotics101.authoring.timeline import estimate_timing

RANGES = DATA / "ranges.yaml"
TOPIC_DENY = ("blood", "weapon", "gun", "bomb", "scary", "monster", "naked", "beer", "wine", "cigarette", "buy now",
              "subscribe", "brand", "kill", "fight", "lick the battery", "plug it in yourself", "stick your finger")
UNSAFE_WITHOUT_ADULT = ("battery", "mains", "socket", "outlet", "plug", "motor")
ADULT_NOTE = ("grown-up", "grownup", "adult", "ask a parent", "with help")


class Report:
    def __init__(self):
        self.gates: list[dict] = []

    def add(self, gid: str, ok: bool, message: str, blocking: bool = True, value=None) -> bool:
        g = {"id": gid, "blocking": blocking, "ok": bool(ok), "message": message}
        if value is not None:
            g["value"] = value
        self.gates.append(g)
        return bool(ok)

    @property
    def ok(self) -> bool:
        return all(g["ok"] for g in self.gates if g["blocking"])

    def doc(self, run_id: str | None = None, thresholds: dict | None = None) -> dict:
        d = {"status": "pass" if self.ok else "fail", "gates": self.gates}
        if run_id:
            d["runId"] = run_id
        if thresholds is not None:
            d["thresholds"] = thresholds
            d["provisional"] = list(config().get("provisional", []))
        return d


@lru_cache(maxsize=2)
def _ranges(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _key(b: dict) -> tuple:
    return (b.get("type"), b.get("text"), b.get("do"), b.get("id"), b.get("cue"), b.get("seconds"))


def beat_map(src_scene: dict, exp_scene: dict) -> dict[int, int]:
    """Source beat index -> expanded beat index (expansion only inserts beats, e.g. concept stings)."""
    out, j = {}, 0
    eb = exp_scene.get("beats", [])
    for i, b in enumerate(src_scene.get("beats", [])):
        while j < len(eb) and _key(eb[j]) != _key(b):
            j += 1
        if j < len(eb):
            out[i] = j
            j += 1
    return out


def to_expanded(source: dict, expanded: dict, items: list[dict], beat_key: str = "beat") -> list[dict]:
    exp_by = {s["sceneId"]: s for s in expanded["scenes"]}
    maps = {s["sceneId"]: beat_map(s, exp_by[s["sceneId"]]) for s in source["scenes"] if s["sceneId"] in exp_by}
    out = []
    for it in items:
        m = maps.get(it["sceneId"])
        if m is not None and it[beat_key] in m:
            out.append({**it, beat_key: m[it[beat_key]]})
    return out


# ------------------------------------------------------------------ numbers

_UNIT_NORM = {"cm": ("m", 0.01), "mm": ("m", 0.001), "degrees": ("deg", 1.0), "°": ("deg", 1.0)}


def _si(value: float, unit: str) -> tuple[float, str]:
    u, k = _UNIT_NORM.get(unit, (unit, 1.0))
    return round(float(value) * k, 6), u


def claim_number_problems(spec: dict, facts: dict) -> list[tuple[str, str]]:
    """Every spoken quantity must be backed by a *verified* claim (§3.4): equal to an exact claim number, or an
    episode demo number (§3.5 rule 4) inside a verified claim's min..max range in the same unit."""
    from robotics101.cartoon.lint import spoken_quantities
    exact, lo, hi = set(), {}, {}
    for c in facts["claims"]:
        if c["status"] != "verified":
            continue
        for n in c.get("numbers") or []:
            v, u = _si(n["value"], n["unit"])
            role = n.get("role", "exact")
            if role == "exact":
                exact.add((v, u))
            else:
                (lo if role == "min" else hi).setdefault(c["claimId"], {})[u] = v
    ranges = [(lo[c][u], hi[c][u], u) for c in lo if c in hi for u in lo[c] if u in hi[c]]
    out = []
    for i, s in enumerate(spec["scenes"]):
        for j, b in enumerate(s["beats"]):
            if b["type"] != "line":
                continue
            for v, kind, txt in spoken_quantities(b["text"]):
                if (v, kind) in exact or any(a <= v <= z and u == kind for a, z, u in ranges):
                    continue
                out.append((f"$.scenes[{i}].beats[{j}].text",
                            f"number {txt!r} is not backed by a verified claim in facts.json"))
    return out


def range_problems(spec: dict, ranges: dict | None = None) -> list[tuple[str, str]]:
    r = ranges or _ranges(str(RANGES))
    out = []
    for i, s in enumerate(spec["scenes"]):
        for k, v in (s.get("parameters") or {}).items():
            lim = r["parameters"].get(k)
            if lim is None:
                continue
            vals = v if isinstance(v, list) else [v]
            for x in vals:
                if isinstance(x, (int, float)) and not (lim[0] <= x <= lim[1]):
                    out.append((f"$.scenes[{i}].parameters.{k}", f"{k} = {x} outside plausible range {lim}"))
    return out


def cross_scene_problems(spec: dict) -> list[tuple[str, str]]:
    """One value per named quantity per episode (scalar *Meters / *Degrees parameters)."""
    seen: dict[str, tuple[float, int]] = {}
    out = []
    for i, s in enumerate(spec["scenes"]):
        for k, v in (s.get("parameters") or {}).items():
            if not re.search(r"(Meters|Degrees)$", k) or not isinstance(v, (int, float)):
                continue
            if k in seen and seen[k][0] != v:
                out.append((f"$.scenes[{i}].parameters.{k}", f"{k} is {v} here but {seen[k][0]} in scene "
                                                            f"{seen[k][1] + 1}: one value per quantity per episode"))
            seen.setdefault(k, (v, i))
    return out


# ------------------------------------------------------------------ facts / kid-safe / reading / timing

def teaching_lines(expanded: dict) -> list[tuple[str, int, dict]]:
    return [(s["sceneId"], j, b) for s in expanded["scenes"] for j, b in enumerate(s["beats"])
            if b["type"] == "line" and b.get("explain")]


def fact_check_problems(source: dict, expanded: dict, facts: dict) -> list[str]:
    status = {c["claimId"]: c["status"] for c in facts["claims"]}
    lc = to_expanded(source, expanded, facts.get("lineClaims") or [])
    mapped = {(x["sceneId"], x["beat"]): x["claimIds"] for x in lc}
    out = []
    for sid, j, b in teaching_lines(expanded):
        ids = mapped.get((sid, j))
        if not ids:
            out.append(f"{sid} beat {j}: teaching line has no claim: {b['text'][:60]!r}")
            continue
        bad = [c for c in ids if status.get(c) in (None, "unverified")]
        if bad:
            out.append(f"{sid} beat {j}: uses unverified/unknown claim(s) {bad}")
        if all(status.get(c) == "contradicted" for c in ids):
            out.append(f"{sid} beat {j}: only contradicted claims")
    for c in facts["claims"]:
        if c["status"] == "verified" and not (c.get("independence") or {}).get("pairs"):
            out.append(f"{c['claimId']}: verified without independence evidence")
    return out


def kidsafe_topic_problems(spec: dict) -> list[tuple[str, str]]:
    out = []
    for i, s in enumerate(spec["scenes"]):
        for j, b in enumerate(s["beats"]):
            if b["type"] != "line":
                continue
            low = " " + b["text"].lower() + " "
            for w in TOPIC_DENY:
                if re.search(rf"\b{re.escape(w)}\b", low):
                    out.append((f"$.scenes[{i}].beats[{j}].text", f"topic deny list: {w!r}"))
            if any(re.search(rf"\b(you|your)\b.*\b{w}", low) for w in UNSAFE_WITHOUT_ADULT) and \
                    re.search(r"\b(try|touch|open|take apart|plug in)\b", low) and not any(a in low for a in ADULT_NOTE):
                out.append((f"$.scenes[{i}].beats[{j}].text", "unsafe imitation without an adult note"))
    return out


def reading_level(spec: dict, age_band: str, cfg: dict) -> dict:
    from robotics101.authoring.readability import stats
    lim = cfg["readingLevel"][age_band]
    rows, bad = {}, []
    for s in spec["scenes"]:
        for who in sorted({b["speaker"] for b in s["beats"] if b["type"] == "line"}):
            st = stats([b["text"] for b in s["beats"] if b["type"] == "line" and b["speaker"] == who])
            rows[f"{s['sceneId']}/{who}"] = st
            if st["fkGrade"] > lim["maxGrade"] + 1.5 or st["avgWords"] > lim["avgWords"] + 3 or st["maxWords"] > lim["maxWords"] + 8:
                bad.append(f"{s['sceneId']}/{who} grade {st['fkGrade']} avg {st['avgWords']} max {st['maxWords']}")
    allst = stats([b["text"] for s in spec["scenes"] for b in s["beats"] if b["type"] == "line"])
    ok = allst["fkGrade"] <= lim["maxGrade"] and allst["avgWords"] <= lim["avgWords"] and not bad
    return {"ok": ok, "episode": allst, "limits": lim, "outliers": bad, "rows": rows}


def timing_problems(spec: dict, est: dict) -> list[str]:
    out = []
    by = {s["sceneId"]: s for s in spec["scenes"]}
    for ts in est["scenes"]:
        tgt = by.get(ts["sceneId"], {}).get("durationTargetSeconds")
        if tgt and abs(ts["scene_duration_s"] - tgt) > 0.10 * tgt:
            out.append(f"{ts['sceneId']}: est {ts['scene_duration_s']:.0f}s vs target {tgt:g}s (±10 %)")
    for s in spec["scenes"]:
        for b in s["beats"]:
            if b["type"] == "pause" and float(b["seconds"]) > 1.5:
                out.append(f"{s['sceneId']}: pause {b['seconds']}s > 1.5s")
    tgt = spec.get("durationTargetSeconds")
    if tgt and abs(est["totalDurationSeconds"] - tgt) > 0.10 * tgt:
        out.append(f"episode: est {est['totalDurationSeconds']:.0f}s vs target {tgt:g}s (±10 %)")
    return out


def caption_dry_run(est: dict) -> dict:
    from robotics101.cartoon.subtitles import DEFAULT_EM_PX, MAX_LINES, MIN_CUE_S, cue_chunks, wrap
    n, one, bad, short = 0, 0, [], []
    for s in est["scenes"]:
        for b in s["beats"]:
            if b["type"] != "line":
                continue
            dur = b["end_s"] - b["start_s"]
            parts = cue_chunks(b["text"], DEFAULT_EM_PX, dur)
            total = sum(len(p) for p in parts) or 1
            for p in parts:
                n += 1
                k = len(wrap(p, DEFAULT_EM_PX))
                one += k == 1
                if k > MAX_LINES:
                    bad.append(f"{s['sceneId']}#{b['index']}: {k} lines")
                if len(parts) > 1 and dur * len(p) / total < MIN_CUE_S - 1e-6 and k == 1:
                    short.append(f"{s['sceneId']}#{b['index']}")
    share = one / max(1, n)
    return {"ok": not bad and share >= 0.80, "cues": n, "oneLineShare": round(share, 3), "overTwoLines": bad,
            "shortChunks": short}


def layout_problems(expanded: dict, gaps: dict | None, bindings: dict | None) -> list[str]:
    from robotics101.cartoon.episode import EXPLAIN_LAYOUTS
    out = []
    gap_beats = {(g["sceneId"], b) for g in (gaps or {}).get("gaps", []) for b in g["beats"]}
    for s in expanded["scenes"]:
        shots = s.get("shots") or []
        for j, b in enumerate(s["beats"]):
            if b["type"] == "line" and b.get("explain"):
                if not any(sh["layout"] in EXPLAIN_LAYOUTS and sh["fromBeat"] <= j <= sh["toBeat"] for sh in shots):
                    out.append(f"{s['sceneId']} beat {j}: explain line outside an illustration/solo shot")
        for sh in shots:
            if sh.get("visual") == "visual_gap" and (s["sceneId"], sh["fromBeat"]) not in gap_beats and gaps is not None:
                out.append(f"{s['sceneId']}: visual_gap placeholder at beat {sh['fromBeat']} not in visual_gaps.json")
    return out


# ------------------------------------------------------------------ all gates

def run_gates(source: dict, *, facts: dict | None = None, outline: dict | None = None, gaps: dict | None = None,
              bindings: dict | None = None, age_band: str = "6-9", vocabulary: list[str] | None = None,
              run_id: str | None = None, cfg: dict | None = None, registry=None) -> dict:
    from robotics101.authoring import engagement as E
    from robotics101.authoring.curriculum import canon, canon_problems
    from robotics101.cartoon.episode import expand_episode
    from robotics101.cartoon.lint import fact_problems, kidsafe_problems
    from robotics101.characters import load_registry
    from robotics101.validation import validate_episode
    cfg = cfg or config()
    reg = registry or load_registry()
    rep = Report()
    # 1 schema + _check_cartoon (+ kit schemas, A5)
    v = validate_episode(copy.deepcopy(source))
    rep.add("format.schema", v.ok, "schema + semantic checks: " + ("ok" if v.ok else
            "; ".join(f"{e.path}: {e.message}" for e in v.errors[:5])))
    if not v.ok:
        return rep.doc(run_id, {"engagement": cfg["engagement"], "rubric": cfg["rubric"]})
    # 2 expand dry run + re-validate
    expanded = expand_episode(source, reg)
    v2 = validate_episode(copy.deepcopy(expanded))
    rep.add("format.expand", v2.ok, f"expand_episode → {len(expanded['scenes'])} scenes; re-validate "
            + ("ok" if v2.ok else "; ".join(f"{e.path}: {e.message}" for e in v2.errors[:5])))
    # 3 numbers
    nums = [m for _, m in fact_problems(source)] + [m for _, m in range_problems(source)] + \
        [m for _, m in cross_scene_problems(source)] + [m for _, m in canon_problems(source, canon())]
    if facts is not None:
        nums += [m for _, m in claim_number_problems(source, facts)]
    rep.add("facts.numbers", not nums, "spoken numbers = parameters, verified claims, ranges, canon, one value per "
            "quantity: " + ("ok" if not nums else "; ".join(nums[:6])))
    # 4 fact-check
    if facts is None:
        rep.add("facts.claims", False, "no facts.json: every teaching line needs a verified claim")
    else:
        fp = fact_check_problems(source, expanded, facts)
        rep.add("facts.claims", not fp, f"{len(teaching_lines(expanded))} teaching lines mapped to claims: "
                + ("ok" if not fp else "; ".join(fp[:6])))
    # 5 kid-safe (hard when made for kids)
    ks = [m for _, m in kidsafe_problems(source)] + [m for _, m in kidsafe_topic_problems(source)]
    kids = (source.get("publishing") or {}).get("madeForKids", False)
    rep.add("kidsafe", not ks, "kid-safe wording + topic deny list: " + ("ok" if not ks else "; ".join(ks[:6])),
            blocking=kids)
    # 6 reading level (warn until A8 calibration)
    rl = reading_level(source, age_band, cfg)
    rep.add("reading_level", rl["ok"], f"episode FK grade {rl['episode']['fkGrade']} (≤ {rl['limits']['maxGrade']}), "
            f"avg {rl['episode']['avgWords']} words (≤ {rl['limits']['avgWords']}); outliers "
            f"{rl['outliers'][:3] or 'none'}", blocking=False, value=rl["episode"])
    # 7 timing (warn)
    est = estimate_timing(expanded, cfg["engagement"]["wps"])
    tp = timing_problems(source, est)
    rep.add("timing", not tp, f"estimate {est['totalDurationSeconds']:.0f}s: " + ("ok" if not tp else "; ".join(tp[:5])),
            blocking=False, value=est["totalDurationSeconds"])
    # 8 captions
    cap = caption_dry_run(est)
    rep.add("captions", cap["ok"], f"{cap['cues']} cues, one-line {cap['oneLineShare']:.0%} (≥ 80 %), > 2 lines: "
            f"{cap['overTwoLines'] or 'none'}")
    # 9 layout
    lp = layout_problems(expanded, gaps, bindings)
    rep.add("layout", not lp, "every explain line in an illustration/solo shot; visuals resolve; gaps consistent: "
            + ("ok" if not lp else "; ".join(lp[:5])))
    # engagement (§6.2) on the estimate
    ol = None
    if outline is not None:
        ol = {**outline, "gags": to_expanded(source, expanded, outline.get("gags") or [])}
    vocab = list(vocabulary if vocabulary is not None else canon()["vocabulary"])
    er = E.evaluate(expanded, est, age_band=age_band, outline=ol, vocabulary=vocab, cfg=cfg)
    rep.gates.extend(er.checks)
    return rep.doc(run_id, {"engagement": E.engagement_thresholds(age_band, cfg), "rubric": cfg["rubric"],
                            "readingLevel": cfg["readingLevel"][age_band]})


__all__ = ["Report", "beat_map", "caption_dry_run", "claim_number_problems", "cross_scene_problems",
           "fact_check_problems", "kidsafe_topic_problems", "layout_problems", "range_problems", "reading_level",
           "run_gates", "teaching_lines", "timing_problems", "to_expanded"]
