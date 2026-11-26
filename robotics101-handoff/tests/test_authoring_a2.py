"""A2 (PLAN-authoring §8.4, §9): providers, fixtures, prompt registry, trace, budget guard, no network."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from robotics101.authoring import llm as L
from robotics101.authoring import prompts as PR
from robotics101.authoring.trace import Budget, BudgetExceeded, Trace, price_call

ROOT = Path(__file__).resolve().parents[1]
MSG = [{"role": "system", "content": "be kind"}, {"role": "user", "content": "plan  ep-002\n please"}]
SCHEMA = {"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}}


def test_fixture_key_is_stable_and_normalised():
    k1 = L.fixture_key("plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)
    k2 = L.fixture_key("plan", "1+abc", "claude-opus-5.5",
                       [{"role": "system", "content": "be  kind"}, {"role": "user", "content": "plan ep-002 please"}],
                       SCHEMA)
    assert k1 == k2 and len(k1) == 64
    assert k1 != L.fixture_key("plan", "2+abc", "claude-opus-5.5", MSG, SCHEMA)       # prompt version in key
    assert k1 != L.fixture_key("plan", "1+abc", "claude-sonnet-5.5", MSG, SCHEMA)     # model in key


def test_fixture_provider_replays_and_traces(tmp_path):
    L.write_fixture(tmp_path, "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA, {"ok": True},
                    {"inputTokens": 120, "outputTokens": 30})
    tr = Trace(tmp_path / "trace.jsonl")
    p = L.FixtureProvider(tmp_path, trace=tr, budget=Budget(run_usd=8.0))
    r = p.complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)
    assert r.output == {"ok": True} and r.usd == 0.0 and r.cache_hit
    rec = json.loads((tmp_path / "trace.jsonl").read_text().splitlines()[0])
    assert rec["provider"] == "fixture" and rec["fixtureKey"] == r.key and rec["usd"] == 0.0
    assert rec["inputTokens"] == 120 and rec["latencyMs"] == 0.0                        # deterministic, no clock


def test_missing_fixture_names_key(tmp_path):
    p = L.FixtureProvider(tmp_path)
    key = L.fixture_key("plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)
    with pytest.raises(L.MissingFixture, match=key):
        p.complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)


@pytest.mark.parametrize("bad,match", [("{\"ok\": tru", "not valid JSON"), ({"ok": "yes"}, "violates its schema"),
                                       ({}, "violates its schema")])
def test_malformed_output_is_rejected(tmp_path, bad, match):
    L.write_fixture(tmp_path, "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA, bad)
    with pytest.raises(L.ProviderOutputError, match=match):
        L.FixtureProvider(tmp_path).complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)


def test_budget_stops_before_the_call(tmp_path):
    L.write_fixture(tmp_path, "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA, {"ok": True})
    tr = Trace()
    p = L.FixtureProvider(tmp_path, trace=tr, budget=Budget(run_usd=0.01))
    with pytest.raises(BudgetExceeded, match="run budget"):
        p.complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA, max_output_tokens=8000)
    assert tr.records == []                                                     # nothing was "called"
    b = Budget(run_usd=8.0, stage_caps={"plan": 0.05})
    with pytest.raises(BudgetExceeded, match="stage cap"):
        b.check("plan", 0.06)
    b = Budget(run_usd=8.0, month_usd=10.0, month_spent=9.99)
    with pytest.raises(BudgetExceeded, match="monthly"):
        b.check("plan", 0.05)


def test_over_budget_trace_from_a_recorded_run(tmp_path):
    """A replayed trace whose real cost would exceed the cap stops the run (priced from prices.yaml)."""
    b = Budget(run_usd=1.0)
    b.charge("research", price_call("claude-sonnet-5.5", 150_000, 10_000, searches=25))
    b.charge("script", price_call("claude-opus-5.5", 45_000, 18_000))
    with pytest.raises(BudgetExceeded):
        b.check("revise", price_call("claude-opus-5.5", 55_000, 18_000))


def test_price_call_matches_plan_estimate():
    # §8.2: script stage 45k in / 18k out on Opus = $0.54
    assert price_call("claude-opus-5.5", 45_000, 18_000) == pytest.approx(0.54, abs=1e-6)
    with pytest.raises(KeyError):
        price_call("gpt-unknown", 1, 1)


def test_live_provider_refuses_without_flag(monkeypatch):
    with pytest.raises(L.LiveDisabled, match="ROBOTICS101_AUTHORING_LIVE"):
        L.AnthropicProvider()
    with pytest.raises(L.LiveDisabled):
        L.make_provider("record", Path("/tmp/none"))
    monkeypatch.setenv("ROBOTICS101_AUTHORING_LIVE", "1")
    with pytest.raises(L.LiveDisabled, match="ANTHROPIC_API_KEY"):          # dotenv points at a missing file
        L.AnthropicProvider()


def test_recording_provider_writes_fixture(tmp_path):
    class Fake(L.LLMProvider):
        name = "fake"

        def _raw(self, key, prompt_id, model, messages, schema, max_output_tokens):
            return {"output": {"ok": True}, "usage": {"inputTokens": 10, "outputTokens": 5}}
    rec = L.RecordingProvider(Fake(budget=Budget(run_usd=8.0)), tmp_path / "fx")
    r = rec.complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)
    assert r.usd > 0
    replay = L.FixtureProvider(tmp_path / "fx").complete("plan", "plan", "1+abc", "claude-opus-5.5", MSG, SCHEMA)
    assert replay.output == {"ok": True} and replay.key == r.key


def test_prompt_registry_versions_follow_registry():
    v = PR.version("script")
    assert v.startswith("1+") and len(v) == 2 + 12
    assert all(PR.version(p) for p in PR.PROMPT_IDS)
    assert PR.version("script", ["bolt", "maya"]) != v                       # registry excerpt is in the hash
    text = PR.render("plan", ageBand="6-9", topic="light", episodeNumber=2, objectives=[], canon={})
    assert "6-9" in text
    with pytest.raises(KeyError, match="unfilled"):
        PR.render("plan", ageBand="6-9")
    ex = PR.registry_excerpt()
    assert ex["nib"]["speaks"] is False and ex["maya"]["personality"]


def test_sockets_are_blocked():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    with pytest.raises(AssertionError, match="network"):
        s.connect(("93.184.216.34", 80))
    s.close()


NET_MODULES = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "anthropic", "openai", "elevenlabs",
               "urllib3", "ssl"}
ALLOWED = {"llm.py"}


def test_no_network_imports_outside_provider_module():
    roots = [ROOT / "src" / "robotics101" / "authoring", ROOT / "src" / "robotics101" / "cartoon" / "kit"]
    bad = []
    for root in roots:
        for p in sorted(root.rglob("*.py")) if root.is_dir() else []:
            tree = ast.parse(p.read_text())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for n in names:
                    if n.split(".")[0] in NET_MODULES and p.name not in ALLOWED:
                        bad.append(f"{p.relative_to(ROOT)} imports {n}")
    assert bad == []
