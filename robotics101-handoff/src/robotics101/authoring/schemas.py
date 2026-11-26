"""Load and validate the authoring contracts (contracts/authoring/*.schema.json)."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from robotics101.authoring import CONTRACTS

NAMES = ("request", "curriculum", "sources", "facts", "outline", "visual_bindings", "visual_gaps", "trace",
         "critique", "authoring_report", "review_packet", "review_approval", "sequence", "canon")


class ContractError(ValueError):
    """An artifact does not match its contract."""


@lru_cache(maxsize=None)
def schema(name: str) -> dict:
    if name not in NAMES:
        raise KeyError(f"unknown authoring contract {name!r}; known: {NAMES}")
    return json.loads((CONTRACTS / f"{name}.schema.json").read_text(encoding="utf-8"))


def errors(name: str, doc: Any) -> list[str]:
    v = Draft202012Validator(schema(name))
    return [f"{'/'.join(map(str, e.absolute_path)) or '$'}: {e.message}"
            for e in sorted(v.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))]


def check(name: str, doc: Any) -> Any:
    errs = errors(name, doc)
    if errs:
        raise ContractError(f"{name}: " + "; ".join(errs[:8]))
    return doc


def canonical(doc: Any) -> bytes:
    """Deterministic bytes (sorted keys, no wall-clock) — the basis of every artifact hash."""
    return (json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def write_artifact(path: Path, doc: Any, contract: str | None = None) -> str:
    """Validate (when a contract is named), write canonical JSON, return its SHA-256."""
    if contract:
        check(contract, doc)
    data = canonical(doc)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def apply_defaults(name: str, doc: dict) -> dict:
    """Fill top-level ``default`` values of a contract (used for the normalised request)."""
    out = dict(doc)
    for k, p in schema(name).get("properties", {}).items():
        if k not in out and "default" in p:
            out[k] = json.loads(json.dumps(p["default"]))
    return out


__all__ = ["ContractError", "NAMES", "apply_defaults", "canonical", "check", "errors", "schema", "sha256_bytes",
           "sha256_file", "write_artifact"]
