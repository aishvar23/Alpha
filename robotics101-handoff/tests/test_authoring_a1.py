"""A1 (PLAN-authoring §1, §2, §5.1, §7): contracts, curriculum + canon, catalogue/cards, review packets."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from robotics101.authoring import catalog as C
from robotics101.authoring import curriculum as CU
from robotics101.authoring import review as R
from robotics101.authoring import schemas as S

ROOT = Path(__file__).resolve().parents[1]
EP1 = ROOT / "examples" / "episode-001-cartoon.json"


def test_all_contracts_are_valid_json_schema():
    from jsonschema import Draft202012Validator
    for n in S.NAMES:
        Draft202012Validator.check_schema(S.schema(n))


def test_request_defaults_and_rules():
    req = S.apply_defaults("request", {"topicId": "distance_with_light", "episodeNumber": 2})
    assert S.errors("request", req) == []
    assert req["mode"] == "fixture" and req["budgetUsd"] == 8.0 and req["ageBand"] == "6-9"
    assert S.errors("request", {"episodeNumber": 2})                       # needs topicId or topic
    assert S.errors("request", {"topic": "ab", "episodeNumber": 2})        # topic 3..120 chars
    assert S.errors("request", {"topicId": "x_y", "episodeNumber": 2, "mode": "yolo"})


def test_facts_and_gaps_contracts_reject_bad_shapes():
    good = {"claims": [{"claimId": "c-01", "text": "t", "kidText": "k", "kind": "number", "concept": "x",
                        "support": [{"sourceId": "s-01", "excerpt": "excerpt text"}], "status": "verified"}]}
    assert S.errors("facts", good) == []
    bad = copy.deepcopy(good)
    bad["claims"][0]["status"] = "probably"
    assert S.errors("facts", bad)
    gap = {"gaps": [{"gapId": "gap-01", "sceneId": "scene-003", "beats": [4], "whatMustBeShown": "arm",
                     "suggestedKind": "body", "severity": "cosmetic"}]}
    assert S.errors("visual_gaps", gap) == []
    gap["gaps"][0]["severity"] = "meh"
    assert S.errors("visual_gaps", gap)


def test_sequence_loads_and_is_ordered():
    seq = CU.sequence()
    assert CU.sequence_problems(seq) == []
    ids = [t["topicId"] for t in seq["topics"]]
    assert ids[1:4] == ["distance_with_light", "line_following", "arms_and_grippers"]
    assert len(ids) >= 4 + 8                                          # ep-001..004 + backlog of 8
    assert all(t["expectedVisuals"] for t in seq["topics"][1:])       # every planned topic lists its visuals
    assert "order" in seq["provisional"]


def test_sequence_problems_detects_bad_prereq():
    seq = copy.deepcopy(CU.sequence())
    seq["topics"][1]["prerequisites"] = ["line_following"]            # later topic
    assert any("not an earlier topic" in p for p in CU.sequence_problems(seq))


def test_canon_from_episode_1_matches_its_spec():
    canon = CU.canon()
    spec = json.loads(EP1.read_text())
    params = {k: v for s in spec["scenes"] for k, v in s["parameters"].items()}
    q = {x["id"]: x["value"] for x in canon["quantities"]}
    assert q["ultrasonic_range"] == params["rangeMeters"] == 3.0
    assert q["stop_threshold"] == params["thresholdMeters"] == 0.5
    assert q["servo_highfive"] == params["endAngleDegrees"] == 60
    assert CU.canon_problems(spec) == []                              # episode 1 agrees with its own canon


def test_canon_problem_on_contradicting_number():
    spec = {"scenes": [{"beats": [{"type": "line", "text": "My sensor can reach 5 meters!"},
                                  {"type": "line", "text": "The light sensor can reach 1 meter."},
                                  {"type": "line", "text": "Stop if it is closer than 2 meters."}]}]}
    probs = CU.canon_problems(spec)
    assert [p[0] for p in probs] == ["$.scenes[0].beats[0].text", "$.scenes[0].beats[2].text"]


def test_catalog_cards_match_code():
    assert C.card_problems() == []


def test_catalog_card_problem_detected():
    cards = copy.deepcopy(C.cards())
    cards["templates"].pop("cartoon_sensor_ping")
    cards["visuals"]["no_such_visual"] = {"shows": []}
    probs = C.card_problems(cards)
    assert any("cartoon_sensor_ping" in p and "no capability card" in p for p in probs)
    assert any("no_such_visual" in p and "no implementation" in p for p in probs)


def test_catalog_snapshot():
    snap = json.loads((ROOT / "tests" / "golden" / "authoring" / "catalog.json").read_text())
    assert C.build_catalog() == snap, "catalogue changed: regenerate with `robotics101 authoring catalog --out tests/golden/authoring/catalog.json`"


def _run(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    for n in ("outline.json", "facts.json", "sources.json", "episode.source.json", "visual_bindings.json",
              "visual_gaps.json", "authoring_report.json"):
        (run / n).write_text(json.dumps({"n": n}))
    return run


def _approve(run, point, sha, decision="approved"):
    R.approval_path(run, point).write_text(json.dumps(
        {"point": point, "approvedSha256": sha, "reviewer": "owner (test)", "decision": decision,
         "timestamp": "2026-11-26T16:00:00Z"}))


def test_review_statuses_and_chain(tmp_path):
    run = _run(tmp_path)
    assert R.check_review(run, "R1")["status"] == "missing"
    _, sha1 = R.write_packet(run, "R1")
    _approve(run, "R1", sha1, "changes_requested")
    assert R.check_review(run, "R1")["status"] == "not_approved"
    R.approval_path(run, "R1").write_text("{}")
    assert R.check_review(run, "R1")["status"] == "invalid"
    _approve(run, "R1", sha1)
    assert R.check_review(run, "R1")["status"] == "approved"
    _, sha2 = R.write_packet(run, "R2")
    _approve(run, "R2", sha2)
    assert R.check_review(run, "R2")["status"] == "approved"
    assert R.render_allowed(run) == (True, "approved")
    # editing an R2 artifact voids R2 only
    (run / "visual_gaps.json").write_text(json.dumps({"gaps": []}))
    assert R.check_review(run, "R2")["status"] == "sha_mismatch"
    assert R.check_review(run, "R1")["status"] == "approved"
    _, sha2 = R.write_packet(run, "R2")
    _approve(run, "R2", sha2)
    # editing an R1 artifact voids R1 and therefore R2 (its packet embeds the R1 packet hash)
    (run / "facts.json").write_text(json.dumps({"claims": []}))
    assert R.check_review(run, "R1")["status"] == "sha_mismatch"
    assert R.check_review(run, "R2")["status"] == "sha_mismatch"
    assert R.render_allowed(run)[0] is False
    assert R.render_allowed(run, allow_draft=True) == (True, "draft")


def test_cli_catalog(tmp_path, capsys):
    from robotics101.cli import main
    assert main(["authoring", "catalog", "--out", str(tmp_path / "c.json")]) == 0
    assert json.loads((tmp_path / "c.json").read_text())["templates"]["cartoon_sensor_ping"]["teaches"]
