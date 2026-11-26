"""Prompt registry with versions (PLAN-authoring §4.2, §9).

Prompt templates live in ``src/robotics101/authoring/prompts/<id>.md`` with a ``version:`` header line. The
effective version is ``<declared>+<sha12>`` of the template text **and** the registry excerpt it embeds, so a
character-registry edit changes the prompt version (and therefore every fixture key) automatically.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from robotics101.authoring.schemas import sha256_bytes

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_IDS = ("plan", "research", "extract", "outline", "script", "bind", "critique", "revise")


def registry_excerpt(cast: list[str] | None = None) -> dict:
    """Cast voice for writer prompts, straight from characters/registry.json."""
    from robotics101.characters import load_registry
    reg = load_registry()
    out = {}
    for cid in cast or ["bolt", "maya", "nib"]:
        ch = reg.get(cid)
        out[cid] = {"name": ch.displayName, "speaks": ch.speaks, "personality": ch.raw.get("personality"), "role": ch.role,
                    "expressions": list(ch.expressions), "actions": list(ch.actions)}
    return out


@lru_cache(maxsize=None)
def _template(pid: str) -> tuple[str, str]:
    if pid not in PROMPT_IDS:
        raise KeyError(f"unknown prompt {pid!r}; known: {PROMPT_IDS}")
    text = (PROMPT_DIR / f"{pid}.md").read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    if not first.startswith("version:"):
        raise ValueError(f"prompts/{pid}.md must start with 'version: N'")
    return first.split(":", 1)[1].strip(), body


def version(pid: str, cast: list[str] | None = None) -> str:
    declared, body = _template(pid)
    blob = body.encode() + json.dumps(registry_excerpt(cast), sort_keys=True).encode()
    return f"{declared}+{sha256_bytes(blob)[:12]}"


def render(pid: str, **values) -> str:
    """Fill ``{{name}}`` placeholders (JSON-encoded values); unknown placeholders are an error."""
    _, body = _template(pid)
    out = body
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", v if isinstance(v, str) else json.dumps(v, sort_keys=True, ensure_ascii=False))
    if "{{" in out:
        missing = out[out.index("{{"):out.index("}}", out.index("{{")) + 2]
        raise KeyError(f"prompt {pid}: unfilled placeholder {missing}")
    return out


__all__ = ["PROMPT_DIR", "PROMPT_IDS", "registry_excerpt", "render", "version"]
