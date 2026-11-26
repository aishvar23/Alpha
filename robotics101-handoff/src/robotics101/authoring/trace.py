"""Cost trace + budget guard (PLAN-authoring §8.4).

Every model/tool call appends one ``trace.jsonl`` record (validated against contracts/authoring/trace.schema.json).
Before each call the guard prices the worst case (prompt tokens + the stage's max output) and refuses when it would
exceed the run budget, the stage cap or the monthly cap — a hard stop with a report, never a partial overrun.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from robotics101.authoring.config import config, prices
from robotics101.authoring.schemas import check


class BudgetExceeded(RuntimeError):
    pass


def price_call(model: str, input_tokens: int, output_tokens: int, searches: int = 0, cache_hit_tokens: int = 0,
               price_doc: dict | None = None) -> float:
    pd = price_doc or prices()
    m = pd["models"].get(model)
    if m is None:
        raise KeyError(f"no price for model {model!r} in authoring/prices.yaml")
    usd = ((input_tokens - cache_hit_tokens) * m["input"] + cache_hit_tokens * m.get("cacheHit", m["input"])
           + output_tokens * m["output"]) / 1e6 + searches * pd.get("searchPer1000", 0.0) / 1000.0
    return round(usd, 6)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


@dataclass
class Budget:
    run_usd: float
    stage_caps: dict[str, float] = field(default_factory=dict)
    month_usd: float | None = None
    month_spent: float = 0.0
    spent: float = 0.0
    by_stage: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_config(cls, run_usd: float | None = None, month_spent: float = 0.0) -> "Budget":
        cfg = config()["budget"]
        env = os.environ.get("ROBOTICS101_AUTHORING_MAX_USD_MONTH")
        return cls(run_usd=cfg["perEpisodeUsd"] if run_usd is None else run_usd,
                   stage_caps=dict(cfg["stageCapsUsd"]), month_usd=float(env) if env else cfg["monthlyUsd"],
                   month_spent=month_spent)

    def check(self, stage: str, worst_usd: float) -> None:
        if self.spent + worst_usd > self.run_usd + 1e-9:
            raise BudgetExceeded(f"{stage}: worst case ${worst_usd:.4f} would exceed the run budget "
                                 f"(${self.spent:.4f} of ${self.run_usd:.2f} spent) — stopped before the call")
        cap = self.stage_caps.get(stage)
        if cap is not None and self.by_stage.get(stage, 0.0) + worst_usd > cap + 1e-9:
            raise BudgetExceeded(f"{stage}: worst case ${worst_usd:.4f} would exceed the stage cap ${cap:.2f}")
        if self.month_usd is not None and self.month_spent + self.spent + worst_usd > self.month_usd + 1e-9:
            raise BudgetExceeded(f"{stage}: would exceed the monthly authoring cap ${self.month_usd:.2f}")

    def charge(self, stage: str, usd: float) -> None:
        self.spent = round(self.spent + usd, 6)
        self.by_stage[stage] = round(self.by_stage.get(stage, 0.0) + usd, 6)


class Trace:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else None
        self.records: list[dict] = []
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("", encoding="utf-8")

    def add(self, **rec) -> dict:
        rec = {"seq": len(self.records), **rec}
        check("trace", rec)
        self.records.append(rec)
        if self.path:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
        return rec

    @property
    def usd(self) -> float:
        return round(sum(r["usd"] for r in self.records), 6)


__all__ = ["Budget", "BudgetExceeded", "Trace", "estimate_tokens", "price_call"]
