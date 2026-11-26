"""Provider interface (PLAN-authoring §9): fixture (default) / recording / Anthropic (opt-in, A8).

``LLMProvider.complete(stage, prompt_id, prompt_version, model, messages, schema, max_output_tokens) -> Result``.
Fixtures are keyed by SHA-256 of (prompt id, prompt version, model, normalised messages, schema) and stored as
``<fixture_dir>/<key>.json``; in fixture mode a missing fixture is an error naming the key. Every call goes through
the budget guard and the trace. This is the ONLY authoring module allowed to touch the network (AST-checked), and
only ``AnthropicProvider`` does, behind ``ROBOTICS101_AUTHORING_LIVE=1`` + a key + an owner-approved budget.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from robotics101.authoring.schemas import canonical, errors as _schema_errors, sha256_bytes
from robotics101.authoring.trace import Budget, Trace, estimate_tokens, price_call

LIVE_ENV = "ROBOTICS101_AUTHORING_LIVE"


class MissingFixture(LookupError):
    pass


class ProviderOutputError(ValueError):
    """Malformed / schema-violating model output."""


class LiveDisabled(RuntimeError):
    pass


def _norm_messages(messages: list[dict]) -> list[dict]:
    return [{"role": m["role"], "content": " ".join(str(m["content"]).split())} for m in messages]


def fixture_key(prompt_id: str, prompt_version: str, model: str, messages: list[dict], schema: dict | None) -> str:
    return sha256_bytes(canonical({"promptId": prompt_id, "promptVersion": prompt_version, "model": model,
                                   "messages": _norm_messages(messages), "schema": schema}))


@dataclass
class Result:
    output: Any
    key: str
    input_tokens: int
    output_tokens: int
    searches: int
    usd: float
    cache_hit: bool


class LLMProvider:
    name = "base"

    def __init__(self, trace: Trace | None = None, budget: Budget | None = None):
        self.trace = trace or Trace()
        self.budget = budget or Budget.from_config()

    def _raw(self, key: str, prompt_id: str, model: str, messages: list[dict], schema: dict | None,
             max_output_tokens: int) -> dict:
        raise NotImplementedError

    def complete(self, stage: str, prompt_id: str, prompt_version: str, model: str, messages: list[dict],
                 schema: dict | None = None, max_output_tokens: int = 8000) -> Result:
        key = fixture_key(prompt_id, prompt_version, model, messages, schema)
        in_tok = sum(estimate_tokens(m["content"]) for m in messages)
        self.budget.check(stage, price_call(model, in_tok, max_output_tokens))      # worst case, before the call
        t0 = time.monotonic()
        raw = self._raw(key, prompt_id, model, messages, schema, max_output_tokens)
        out = raw.get("output")
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except json.JSONDecodeError as e:
                raise ProviderOutputError(f"{stage}/{prompt_id}: output is not valid JSON ({e.msg} at {e.pos})") from e
        if schema is not None:
            errs = _schema_errors_for(schema, out)
            if errs:
                raise ProviderOutputError(f"{stage}/{prompt_id}: output violates its schema: {'; '.join(errs[:5])}")
        u = raw.get("usage") or {}
        res = Result(out, key, int(u.get("inputTokens", in_tok)), int(u.get("outputTokens", 0)),
                     int(u.get("searches", 0)), 0.0, bool(u.get("cacheHit", self.name == "fixture")))
        res.usd = 0.0 if self.name == "fixture" else price_call(model, res.input_tokens, res.output_tokens,
                                                                 res.searches)
        self.budget.charge(stage, res.usd)
        self.trace.add(stage=stage, provider=self.name, model=model, promptId=prompt_id, promptVersion=prompt_version,
                       fixtureKey=key, inputTokens=res.input_tokens, outputTokens=res.output_tokens,
                       searches=res.searches, usd=res.usd,
                       latencyMs=0.0 if self.name == "fixture" else round((time.monotonic() - t0) * 1000, 1),
                       cacheHit=res.cache_hit)
        return res


def _schema_errors_for(schema: dict, doc: Any) -> list[str]:
    if isinstance(schema, dict) and set(schema) == {"contract"}:
        return _schema_errors(schema["contract"], doc)
    from jsonschema import Draft202012Validator
    return [e.message for e in Draft202012Validator(schema).iter_errors(doc)]


class FixtureProvider(LLMProvider):
    """Replays ``<dir>/<key>.json`` = ``{key, promptId, model, output, usage}``. No network, $0."""
    name = "fixture"

    def __init__(self, fixture_dir: Path, **kw):
        super().__init__(**kw)
        self.dir = Path(fixture_dir)

    def _raw(self, key, prompt_id, model, messages, schema, max_output_tokens):
        p = self.dir / f"{key}.json"
        if not p.is_file():
            raise MissingFixture(f"fixture mode: no fixture for {prompt_id} ({model}) — key {key} "
                                 f"(expected {p}); record it in A8 or hand-write it")
        return json.loads(p.read_text(encoding="utf-8"))


class RecordingProvider(LLMProvider):
    """Wraps a real provider and writes every response as a fixture (A8 `record` mode)."""
    name = "recording"

    def __init__(self, inner: LLMProvider, fixture_dir: Path, **kw):
        super().__init__(trace=inner.trace, budget=inner.budget)
        self.inner, self.dir = inner, Path(fixture_dir)
        self.name = f"recording:{inner.name}"

    def _raw(self, key, prompt_id, model, messages, schema, max_output_tokens):
        raw = self.inner._raw(key, prompt_id, model, messages, schema, max_output_tokens)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{key}.json").write_bytes(canonical({"key": key, "promptId": prompt_id, "model": model,
                                                          "output": raw.get("output"), "usage": raw.get("usage")}))
        return raw


class AnthropicProvider(LLMProvider):
    """Opt-in paid provider (A8). Refuses unless ROBOTICS101_AUTHORING_LIVE=1 and a key is configured; the key is
    read from the environment or the gitignored .env via python-dotenv and never logged or stored."""
    name = "anthropic"

    def __init__(self, **kw):
        if os.environ.get(LIVE_ENV) != "1":
            raise LiveDisabled(f"paid authoring calls are disabled (set {LIVE_ENV}=1 only after the owner's S1 yes)")
        super().__init__(**kw)
        from dotenv import load_dotenv
        load_dotenv(os.environ.get("ROBOTICS101_DOTENV", ".env"))
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise LiveDisabled("ANTHROPIC_API_KEY is not configured")
        self._client = None

    def _raw(self, key, prompt_id, model, messages, schema, max_output_tokens):   # pragma: no cover - A8 only
        if self._client is None:
            import anthropic                    # lazy: not a dependency until A8
            self._client = anthropic.Anthropic()
        system = "\n".join(m["content"] for m in messages if m["role"] == "system")
        msgs = [m for m in messages if m["role"] != "system"]
        r = self._client.messages.create(model=model, max_tokens=max_output_tokens, temperature=0,
                                         system=system or None, messages=msgs)
        text = "".join(getattr(b, "text", "") for b in r.content)
        return {"output": text, "usage": {"inputTokens": r.usage.input_tokens, "outputTokens": r.usage.output_tokens}}


def make_provider(mode: str, fixture_dir: Path, trace: Trace | None = None, budget: Budget | None = None) -> LLMProvider:
    if mode == "fixture":
        return FixtureProvider(fixture_dir, trace=trace, budget=budget)
    live = AnthropicProvider(trace=trace, budget=budget)
    return RecordingProvider(live, fixture_dir) if mode == "record" else live


def write_fixture(fixture_dir: Path, prompt_id: str, prompt_version: str, model: str, messages: list[dict],
                  schema: dict | None, output: Any, usage: dict | None = None) -> Path:
    """Hand-written fixture helper (A7)."""
    key = fixture_key(prompt_id, prompt_version, model, messages, schema)
    p = Path(fixture_dir) / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(canonical({"key": key, "promptId": prompt_id, "model": model, "output": output,
                             "usage": usage or {"inputTokens": 0, "outputTokens": 0}}))
    return p


__all__ = ["AnthropicProvider", "FixtureProvider", "LIVE_ENV", "LLMProvider", "LiveDisabled", "MissingFixture",
           "ProviderOutputError", "RecordingProvider", "Result", "fixture_key", "make_provider", "write_fixture"]
