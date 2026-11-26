"""A3 (PLAN-authoring §3.3-3.4, §4.4, §6.1-6.2): deterministic gates + engagement gate calibrated on episode 1."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from robotics101.authoring import engagement as E
from robotics101.authoring import gates as G
from robotics101.authoring import independence as I
from robotics101.authoring.config import config
from robotics101.authoring.curriculum import canon
from robotics101.authoring.readability import stats, syllables
from robotics101.authoring.screenplay import screenplay
from robotics101.authoring.timeline import estimate_timing

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / "tests" / "golden" / "authoring"
EP1_DIR = FX / "robots_sense_think_act"
V7 = ROOT / "out" / "m05.8-v7"


@pytest.fixture(scope="module")
def ep1():
    return json.loads((ROOT / "examples" / "episode-001-cartoon.json").read_text())


@pytest.fixture(scope="module")
def outline1():
    return json.loads((ROOT / "curriculum" / "outlines" / "ep-001.json").read_text())


@pytest.fixture(scope="module")
def fixture_allow():
    return yaml.safe_load((FX / "fixture_sources.yaml").read_text())


@pytest.fixture(scope="module")
def sources1():
    src = json.loads((EP1_DIR / "sources.json").read_text())
    return src, {s["sourceId"]: (EP1_DIR / s["textFile"]).read_text() for s in src["sources"]}


@pytest.fixture(scope="module")
def facts1(sources1, fixture_allow):
    src, texts = sources1
    facts, probs = I.verify_claims(json.loads((EP1_DIR / "facts.extracted.json").read_text()), src, texts, fixture_allow)
    assert probs == []
    return facts


def _gate(doc, gid):
    return next(g for g in doc["gates"] if g["id"] == gid)


# ---------------------------------------------------------------- baseline

def test_episode_1_passes_every_blocking_gate(ep1, outline1, facts1):
    doc = G.run_gates(ep1, facts=facts1, outline=outline1)
    failing = [g for g in doc["gates"] if g["blocking"] and not g["ok"]]
    assert failing == [] and doc["status"] == "pass"
    assert {g["id"] for g in doc["gates"]} >= {f"engagement.{c}" for c in (
        "visual_change", "gag_density", "reaction_density", "monologue", "hook", "hook_callback", "chant",
        "audience_questions", "first_concept")}
    assert "engagement" in doc["provisional"] and doc["thresholds"]["engagement"]["visualChangeMaxS"] == 9.0


@pytest.mark.skipif(not (V7 / "timing.json").is_file(), reason="needs the rendered ep-001 v7 bundle")
def test_episode_1_passes_engagement_on_real_timing(outline1, ep1):
    spec = json.loads((V7 / "episode.json").read_text())
    timing = json.loads((V7 / "timing.json").read_text())
    sj = json.loads((V7 / "scenes.json").read_text())
    ol = {**outline1, "gags": G.to_expanded(ep1, spec, outline1["gags"])}
    res = E.evaluate(spec, timing, shots_by_scene=E.shots_from_scenes_json(sj), outline=ol,
                     vocabulary=canon()["vocabulary"])
    assert res.ok, res.failures


# ---------------------------------------------------------------- independence §3.3

def test_independence_rules(sources1, fixture_allow):
    src, texts = sources1
    by = {s["sourceId"]: s for s in src["sources"]}
    ok = I.pair_independence(by["s-03"], by["s-04"], texts["s-03"], texts["s-04"], fixture_allow)
    assert ok["independent"], ok
    syn = I.pair_independence(by["s-04"], by["s-07"], texts["s-04"], texts["s-07"], fixture_allow)
    assert not syn["independent"] and "near-duplicate / syndicated" in syn["reasons"]
    assert syn["longestSharedRun"] >= I.SHARED_RUN_MAX and "cite each other" in syn["reasons"]
    same = dict(by["s-02"], url="https://sub.edu-a.fixture.test/x", publisherGroup="FixtureEduA")
    assert "same publisher group" in I.pair_independence(by["s-01"], same, texts["s-01"], texts["s-02"],
                                                         fixture_allow)["reasons"]
    up_a = dict(by["s-01"], references=["https://upstream.example/paper"])
    up_b = dict(by["s-02"], references=["https://upstream.example/paper"])
    assert "same upstream" in I.pair_independence(up_a, up_b, texts["s-01"], texts["s-02"], fixture_allow)["reasons"]
    wiki = dict(by["s-02"], url="https://wiki.fixture.test/Robot", publisherGroup="FixtureWiki")
    assert "wikipedia/LLM never counts" in I.pair_independence(by["s-01"], wiki, texts["s-01"], texts["s-02"],
                                                               fixture_allow)["reasons"]


def test_claim_status_downgrades(sources1, fixture_allow):
    src, texts = sources1
    claims = {"claims": [
        {"claimId": "c-01", "text": "t", "kidText": "k", "kind": "mechanism", "concept": "x", "status": "unverified",
         "support": [{"sourceId": "s-04", "excerpt": "Bats use echoes the same way"},
                     {"sourceId": "s-07", "excerpt": "Bats use echoes the same way"}]},          # syndicated
        {"claimId": "c-02", "text": "t", "kidText": "k", "kind": "number", "concept": "x", "status": "unverified",
         "support": [{"sourceId": "s-03", "excerpt": "Measuring range: about 9 cm to 40 m"}]},   # fabricated
        {"claimId": "c-03", "text": "t", "kidText": "k", "kind": "mechanism", "concept": "x", "status": "unverified",
         "support": [{"sourceId": "s-03", "excerpt": "the sooner the echo comes back, the closer the object is"},
                     {"sourceId": "s-04", "excerpt": "the faster the echo comes back, the closer the thing is"}]}]}
    facts, probs = I.verify_claims(claims, src, texts, fixture_allow)
    st = {c["claimId"]: c["status"] for c in facts["claims"]}
    assert st == {"c-01": "single_source", "c-02": "unverified", "c-03": "verified"}
    assert any("fabricated" in p for p in probs)


def test_real_allowlist_groups():
    assert I.domain_info("https://science.nasa.gov/x")["group"] == "NASA"
    assert I.domain_info("https://www.jpl.nasa.gov/edu")["group"] == "NASA"            # subdomain inherits
    assert I.domain_info("https://www.bbc.co.uk/bitesize")["group"] == "BBC"
    assert I.domain_info("https://medium.com/robots") is None                           # blocked
    assert I.domain_info("https://random-blog.example/robots") is None                  # not allowlisted


# ---------------------------------------------------------------- broken variants (one per gate)

def _line(spec, sid, idx):
    return next(s for s in spec["scenes"] if s["sceneId"] == sid)["beats"][idx]


def test_numbers_gate_variants(ep1, outline1, facts1):
    bad = copy.deepcopy(ep1)
    _line(bad, "scene-004", 13)["text"] = "Perfect! Your sensor can reach things up to 1.2 meters away."
    msg = _gate(G.run_gates(bad, facts=facts1, outline=outline1), "facts.numbers")
    assert not msg["ok"] and "canon" in msg["message"]                 # matches a parameter, contradicts canon 3 m
    bad = copy.deepcopy(ep1)
    _line(bad, "scene-004", 13)["text"] = "Perfect! Your sensor can measure things up to 5 meters away."
    assert _gate(G.run_gates(bad, facts=facts1, outline=outline1), "format.schema")["ok"] is False   # fact_problems
    bad = copy.deepcopy(ep1)
    next(s for s in bad["scenes"] if s["sceneId"] == "scene-004")["parameters"]["rangeMeters"] = 9.0
    assert G.run_gates(bad, facts=facts1, outline=outline1)["status"] == "fail"
    assert G.range_problems(bad) and G.cross_scene_problems(
        {"scenes": [{"parameters": {"thresholdMeters": 0.5}}, {"parameters": {"thresholdMeters": 0.4}}]})
    f2 = copy.deepcopy(facts1)
    for c in f2["claims"]:
        if c["claimId"] == "c-15":
            c["status"] = "single_source"                              # the 0.02-4 m range is no longer verified
    assert any("1.2 meters" in m for _, m in G.claim_number_problems(ep1, f2))


def test_fact_check_gate_variants(ep1, outline1, facts1):
    f2 = copy.deepcopy(facts1)
    f2["lineClaims"] = [x for x in f2["lineClaims"] if not (x["sceneId"] == "scene-004" and x["beat"] == 4)]
    g = _gate(G.run_gates(ep1, facts=f2, outline=outline1), "facts.claims")
    assert not g["ok"] and "no claim" in g["message"]
    f3 = copy.deepcopy(facts1)
    next(c for c in f3["claims"] if c["claimId"] == "c-12")["status"] = "unverified"
    assert "unverified" in _gate(G.run_gates(ep1, facts=f3, outline=outline1), "facts.claims")["message"]
    assert not _gate(G.run_gates(ep1, facts=None, outline=outline1), "facts.claims")["ok"]


def test_kidsafe_and_reading_level_variants(ep1, outline1, facts1):
    bad = copy.deepcopy(ep1)
    _line(bad, "scene-001", 6)["text"] = "Ow! That monster wall is scary!"
    g = _gate(G.run_gates(bad, facts=facts1, outline=outline1), "kidsafe")
    assert not g["ok"] and g["blocking"]                                 # made for kids -> hard
    assert syllables("robot") == 2 and syllables("sense") == 1 and syllables("actuator") >= 3
    hard = stats(["Electromechanical actuation necessitates sophisticated proportional-integral-derivative "
                  "controllers incorporating comprehensive feedback mechanisms."])
    assert hard["fkGrade"] > 10
    cfg = config()
    lvl = G.reading_level({"scenes": [{"sceneId": "s", "beats": [{"type": "line", "speaker": "maya", "text":
                          "Electromechanical actuation necessitates sophisticated proportional controllers."}]}]},
                          "6-9", cfg)
    assert not lvl["ok"]


def test_caption_and_layout_variants(ep1, outline1, facts1):
    words = " ".join(["robots"] * 30)
    est = {"scenes": [{"sceneId": "s", "beats": [{"type": "line", "index": i, "text": words, "start_s": 0.0,
                                                  "end_s": 2.0} for i in range(5)]}]}
    cap = G.caption_dry_run(est)
    assert not cap["ok"] and cap["oneLineShare"] < 0.8                  # rushed long lines -> 2-line cues
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    exp = expand_episode(ep1, load_registry())
    s1 = exp["scenes"][0]
    s1["beats"][7]["explain"] = True                                     # teaching line, but no shot covers it
    probs = G.layout_problems(exp, {"gaps": []}, None)
    assert any("outside an illustration/solo shot" in p for p in probs)
    s1.setdefault("shots", []).append({"layout": "illustration", "fromBeat": 7, "toBeat": 7, "visual": "visual_gap",
                                       "gap": {"gapId": "gap-01", "what": "something"}})
    assert any("not listed in visual_gaps.json" in p for p in G.layout_problems(exp, {"gaps": []}, None))


def test_timing_gate_is_a_warning(ep1, outline1, facts1):
    g = _gate(G.run_gates(ep1, facts=facts1, outline=outline1), "timing")
    assert g["blocking"] is False                                        # ep-001 runs long vs targets: warn only


@pytest.fixture(scope="module")
def ep1_expanded(ep1):
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    return expand_episode(ep1, load_registry())


def _eval(spec_src, outline, **kw):
    from robotics101.cartoon.episode import expand_episode
    from robotics101.characters import load_registry
    exp = expand_episode(spec_src, load_registry())
    ol = {**outline, "gags": G.to_expanded(spec_src, exp, outline.get("gags") or [])} if outline else None
    kw.setdefault("vocabulary", canon()["vocabulary"])
    return {c["id"][len("engagement."):]: c for c in E.evaluate(exp, estimate_timing(exp), outline=ol, **kw).checks}


def test_engagement_baseline(ep1, outline1):
    assert all(c["ok"] for c in _eval(ep1, outline1).values())


def test_engagement_visual_change_and_monologue_fail(ep1, outline1):
    bad = copy.deepcopy(ep1)
    s = next(s for s in bad["scenes"] if s["sceneId"] == "scene-007")
    long = "We keep talking and talking about the same thing so nothing new appears on the screen for a while"
    s["beats"][2:2] = [{"type": "line", "speaker": "maya", "text": long, "emotion": "happy"} for _ in range(3)]
    r = _eval(bad, outline1)
    assert not r["visual_change"]["ok"] and not r["monologue"]["ok"]


def test_engagement_gag_density_needs_tags(ep1, outline1):
    r = _eval(ep1, {**outline1, "gags": []})
    assert not r["gag_density"]["ok"] and "longest gap" in r["gag_density"]["message"]


def test_engagement_hook_and_callback_fail(ep1, outline1):
    bad = copy.deepcopy(ep1)
    s1 = bad["scenes"][0]
    s1["beats"] = [b for b in s1["beats"] if not (b["type"] == "sfx" and b["id"] in E.IMPACT_SFX)]
    for b in s1["beats"]:
        if b["type"] == "line":
            b["emotion"] = "happy"
            b.pop("pose", None)
            b["text"] = b["text"].replace("!", ".").replace("?", ".")
    r = _eval(bad, {**outline1, "gags": []})
    assert not r["hook"]["ok"]
    bad = copy.deepcopy(ep1)
    for s in bad["scenes"][-3:]:
        for b in s["beats"]:
            if b["type"] == "line":
                b["text"] = b["text"].replace("boxes", "obstacles")
    bad["scenes"][-2]["parameters"]["obstacle"] = "boxes"
    r = _eval(bad, {**outline1, "hook": {"id": "boxes", "problem": "x", "prop": "boxes"}})
    assert not r["hook_callback"]["ok"] and "does NOT mention" in r["hook_callback"]["message"]


def test_engagement_chant_questions_first_concept_reactions_fail(ep1, outline1):
    assert not _eval(ep1, outline1, vocabulary=[])["chant"]["ok"]
    bad = copy.deepcopy(ep1)
    _line(bad, "scene-005", 13)["text"] = "So 0.6 is still more than 0.5."
    assert not _eval(bad, outline1)["audience_questions"]["ok"]
    cfg = config()
    cfg["engagement"]["firstConceptMaxS"] = 30.0
    cfg["engagement"]["reactionPerMin"] = 40.0
    r = _eval(ep1, outline1, cfg=cfg)
    assert not r["first_concept"]["ok"] and not r["reaction_density"]["ok"]


def test_relaxed_thresholds_for_older_kids():
    a, b = E.engagement_thresholds("6-9"), E.engagement_thresholds("9-12")
    assert b["visualChangeMaxS"] > a["visualChangeMaxS"] and b["gagPerMin"] < a["gagPerMin"]


def test_screenplay_view(ep1):
    text = screenplay(ep1, {"gaps": [{"gapId": "gap-01", "sceneId": "scene-004", "beats": [4], "severity": "cosmetic",
                                      "whatMustBeShown": "bat", "suggestedKind": "icon"}]})
    assert "CONCEPT CARD: **Distance sensor**" in text or "CONCEPT CARD" in text
    assert "**MAYA**" in text and "(sfx bonk)" in text and "gap-01 [cosmetic]" in text


def test_cli_gate(tmp_path, capsys):
    from robotics101.cli import main
    rc = main(["authoring", "gate", str(ROOT / "examples" / "episode-001-cartoon.json"),
               "--outline", str(ROOT / "curriculum" / "outlines" / "ep-001.json"), "--out", str(tmp_path / "r.json")])
    doc = json.loads((tmp_path / "r.json").read_text())
    assert rc == 1 and doc["status"] == "fail"                           # no facts.json -> facts.claims blocks
    assert all(g["ok"] for g in doc["gates"] if g["id"].startswith("engagement."))
