"""Source independence and citation checks (PLAN-authoring §3.2-3.4), deterministic.

Two supporting sources for a claim are independent only if (1) different publisher groups, (2) not near-duplicates
(word 5-gram shingle Jaccard < 0.5 and no shared run of >= 25 words between the two pages), (3) neither links to /
cites the other, (4) they do not cite the same upstream, (5) neither is Wikipedia / LLM output. Anything ambiguous
downgrades the claim to ``single_source``. Every excerpt must be present in its stored page text (no fabricated
citations). Fetched text is untrusted data and never executed.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from robotics101.authoring import DATA

SOURCES_ALLOWLIST = DATA / "sources.yaml"
SHINGLE_N = 5
JACCARD_MAX = 0.5
SHARED_RUN_MAX = 25


@lru_cache(maxsize=4)
def _allow(path: str) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def allowlist(path: Path | None = None) -> dict:
    return _allow(str(path or SOURCES_ALLOWLIST))


def domain_info(url: str, allow: dict | None = None) -> dict | None:
    """Allowlist entry for ``url`` (unknown subdomains inherit the parent's group); None if not allowlisted."""
    a = allow or allowlist()
    host = (urlsplit(url).hostname or "").lower()
    if any(host == b or host.endswith("." + b) for b in a.get("blocked", [])):
        return None
    parts = host.split(".")
    for i in range(len(parts) - 1):
        cand = ".".join(parts[i:])
        if cand in a["domains"]:
            return {"domain": cand, **a["domains"][cand]}
    return None


def _norm_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def shingles(text: str, n: int = SHINGLE_N) -> set[tuple[str, ...]]:
    w = _norm_words(text)
    return {tuple(w[i:i + n]) for i in range(max(0, len(w) - n + 1))}


def jaccard(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def longest_shared_run(a: str, b: str) -> int:
    """Longest run of identical consecutive words (dynamic programming over word lists)."""
    wa, wb = _norm_words(a), _norm_words(b)
    if not wa or not wb:
        return 0
    idx: dict[str, list[int]] = {}
    for j, w in enumerate(wb):
        idx.setdefault(w, []).append(j)
    best, prev = 0, {}
    for w in wa:
        cur = {}
        for j in idx.get(w, ()):
            cur[j] = prev.get(j - 1, 0) + 1
            if cur[j] > best:
                best = cur[j]
        prev = cur
    return best


def excerpt_present(excerpt: str, text: str) -> bool:
    return " ".join(_norm_words(excerpt)) in " ".join(_norm_words(text))


def _refs(src: dict) -> set[str]:
    return {r.lower().rstrip("/") for r in (src.get("outboundLinks") or []) + (src.get("references") or [])}


def pair_independence(a: dict, b: dict, text_a: str, text_b: str, allow: dict | None = None) -> dict:
    """Evidence dict + verdict for two supporting sources (a, b are sources.json entries)."""
    ia, ib = domain_info(a["url"], allow), domain_info(b["url"], allow)
    ev = {"publisherGroups": [a.get("publisherGroup"), b.get("publisherGroup")],
          "jaccard": round(jaccard(text_a, text_b), 3), "longestSharedRun": longest_shared_run(text_a, text_b)}
    reasons = []
    if not ia or not ib:
        reasons.append("not allowlisted")
    if (ia and ia.get("neverCounts")) or (ib and ib.get("neverCounts")):
        reasons.append("wikipedia/LLM never counts")
    if (ia or {}).get("group", a.get("publisherGroup")) == (ib or {}).get("group", b.get("publisherGroup")):
        reasons.append("same publisher group")
    if ev["jaccard"] >= JACCARD_MAX or ev["longestSharedRun"] >= SHARED_RUN_MAX:
        reasons.append("near-duplicate / syndicated")
    ra, rb = _refs(a), _refs(b)
    ua, ub = a["url"].lower().rstrip("/"), b["url"].lower().rstrip("/")
    if ub in ra or ua in rb or b.get("title", "").lower() in ra or a.get("title", "").lower() in rb:
        reasons.append("cite each other")
    if ra & rb:
        reasons.append("same upstream")
    ev["citeHits"] = sorted(ra & rb)
    ev["independent"] = not reasons
    ev["reasons"] = reasons
    return ev


def verify_claims(facts: dict, sources: dict, texts: dict[str, str], allow: dict | None = None) -> tuple[dict, list[str]]:
    """Recompute every claim's status from its support (§3.4) and attach independence evidence.

    verified: >= 2 independent sources, at least one tier A-C; single_source: otherwise when supported;
    unverified: an excerpt is missing from its page (fabricated citation) or no usable support. A claim the
    author marked ``contradicted`` stays contradicted. Returns (new facts, problems)."""
    by_id = {s["sourceId"]: s for s in sources["sources"]}
    out, probs = {"claims": [], **{k: v for k, v in facts.items() if k != "claims"}}, []
    for c in facts["claims"]:
        c = dict(c)
        good = []
        for sup in c["support"]:
            src = by_id.get(sup["sourceId"])
            if src is None:
                probs.append(f"{c['claimId']}: cites unknown source {sup['sourceId']}")
                continue
            if not excerpt_present(sup["excerpt"], texts.get(src["sourceId"], "")):
                probs.append(f"{c['claimId']}: excerpt not found in {src['sourceId']} (fabricated citation?)")
                continue
            good.append(src)
        pairs = []
        for i in range(len(good)):
            for j in range(i + 1, len(good)):
                pairs.append({"sources": [good[i]["sourceId"], good[j]["sourceId"]],
                              **pair_independence(good[i], good[j], texts[good[i]["sourceId"]],
                                                  texts[good[j]["sourceId"]], allow)})
        ok_pair = any(p["independent"] and any(by_id[s]["tier"] in "ABC" for s in p["sources"]) for p in pairs)
        if c.get("status") == "contradicted":
            pass
        elif ok_pair:
            c["status"] = "verified"
        elif good:
            c["status"] = "single_source"
        else:
            c["status"] = "unverified"
        c["independence"] = {"pairs": pairs}
        out["claims"].append(c)
    return out, probs


__all__ = ["JACCARD_MAX", "SHARED_RUN_MAX", "SHINGLE_N", "allowlist", "domain_info", "excerpt_present", "jaccard",
           "longest_shared_run", "pair_independence", "shingles", "verify_claims"]
