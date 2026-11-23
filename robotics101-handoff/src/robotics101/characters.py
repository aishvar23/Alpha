"""Character registry (M02.1): the recurring cast, loaded from ``characters/registry.json``.

One registry is reused by every episode so designs, palettes, voices and allowed expressions/actions stay
consistent. The registry's SHA-256 is recorded in bundle manifests; episodes may only reference characters,
expressions and actions declared here. No secrets live in the registry (voice IDs are public identifiers;
API keys come only from the environment at synthesis time).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "characters" / "registry.json"
REGISTRY_SCHEMA = "robotics101.characters/1"
_ID = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
VOICE_PROVIDERS = ("elevenlabs", "kokoro", "espeak")


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Character:
    id: str
    displayName: str
    role: str
    rig: str
    expressions: tuple[str, ...]
    actions: tuple[str, ...]
    speaks: bool
    voice: dict | None
    palette: dict
    captionColor: str
    raw: dict

    def allows_action(self, action: str) -> bool:
        return action.split(":", 1)[0] in self.actions


@dataclass(frozen=True)
class Registry:
    path: Path
    sha256: str
    rig_version: int
    characters: dict[str, Character]

    def get(self, cid: str) -> Character | None:
        return self.characters.get(cid)


def registry_problems(doc: dict) -> list[str]:
    """Structural problems in a registry document (empty == valid)."""
    p: list[str] = []
    if not isinstance(doc, dict) or doc.get("schemaVersion") != REGISTRY_SCHEMA:
        return [f"schemaVersion must be {REGISTRY_SCHEMA!r}"]
    if not isinstance(doc.get("rigVersion"), int):
        p.append("rigVersion must be an integer")
    chars = doc.get("characters")
    if not isinstance(chars, dict) or not chars:
        return p + ["characters must be a non-empty object"]
    for cid, c in chars.items():
        where = f"characters.{cid}"
        if not _ID.match(cid):
            p.append(f"{where}: invalid id")
        if not isinstance(c, dict):
            p.append(f"{where}: must be an object")
            continue
        for k in ("displayName", "role", "description", "personality", "rig", "captionColor"):
            if not isinstance(c.get(k), str) or not c.get(k):
                p.append(f"{where}.{k}: required non-empty string")
        for k in ("expressions", "actions"):
            v = c.get(k)
            if not isinstance(v, list) or not v or not all(isinstance(x, str) and _ID.match(x) for x in v):
                p.append(f"{where}.{k}: required list of ids")
        pal = c.get("palette")
        if not isinstance(pal, dict) or not pal or not all(isinstance(x, str) and _HEX.match(x) for x in pal.values()):
            p.append(f"{where}.palette: required object of #RRGGBB colours")
        if isinstance(c.get("captionColor"), str) and not _HEX.match(c["captionColor"]):
            p.append(f"{where}.captionColor: must be #RRGGBB")
        speaks = c.get("speaks")
        if not isinstance(speaks, bool):
            p.append(f"{where}.speaks: must be boolean")
        voice = c.get("voice")
        if speaks:
            if not isinstance(voice, dict):
                p.append(f"{where}.voice: required for a speaking character")
            else:
                if not any(isinstance(voice.get(pv), dict) for pv in VOICE_PROVIDERS):
                    p.append(f"{where}.voice: needs at least one of {VOICE_PROVIDERS}")
                if not isinstance(voice.get("espeak"), dict):
                    p.append(f"{where}.voice.espeak: required (offline fallback)")
                el = voice.get("elevenlabs")
                if el is not None and (not isinstance(el, dict) or not isinstance(el.get("modelId"), str)):
                    p.append(f"{where}.voice.elevenlabs: needs modelId (voiceId may be null until auditioned)")
                fx = voice.get("fx", [])
                if not isinstance(fx, list) or not all(isinstance(x, str) for x in fx):
                    p.append(f"{where}.voice.fx: must be a list of sox effect tokens")
                blob = json.dumps(voice).lower()
                if any(w in blob for w in ("api_key", "apikey", "xi-api-key", "secret", "token")):
                    p.append(f"{where}.voice: must not contain credentials")
        elif voice is not None:
            p.append(f"{where}.voice: must be null for a non-speaking character")
        if "main" in c and not isinstance(c["main"], bool):
            p.append(f"{where}.main: must be boolean")
        if c.get("main"):
            p += _intro_problems(where, c, chars)
    return p


def _intro_problems(where: str, c: dict, chars: dict) -> list[str]:
    """M03.1: a main character needs an ``intro`` block (tagline, entrance + action from its own action list, and a
    line spoken by a speaking character that says the character's display name)."""
    it = c.get("intro")
    if not isinstance(it, dict):
        return [f"{where}.intro: required for a main character (tagline, entrance, line)"]
    p = []
    if not isinstance(it.get("tagline"), str) or not 3 <= len(it.get("tagline", "")) <= 48:
        p.append(f"{where}.intro.tagline: required string of 3..48 characters")
    acts = c.get("actions") or []
    for k in ("entrance", "action"):
        if k in it and it[k] not in acts:
            p.append(f"{where}.intro.{k}: '{it[k]}' is not one of the character's actions")
    if "emotion" in it and it["emotion"] not in (c.get("expressions") or []):
        p.append(f"{where}.intro.emotion: not one of the character's expressions")
    line = it.get("line")
    if not isinstance(line, dict) or not isinstance(line.get("text"), str) or not line.get("text"):
        p.append(f"{where}.intro.line: required {{speaker, text}}")
    else:
        spk = chars.get(line.get("speaker"))
        if not isinstance(spk, dict) or not spk.get("speaks"):
            p.append(f"{where}.intro.line.speaker: must be a speaking character")
        if str(c.get("displayName", "")).lower() not in line["text"].lower():
            p.append(f"{where}.intro.line.text: must say the name '{c.get('displayName')}'")
    return p


def load_registry(path: Path | None = None) -> Registry:
    path = Path(path or DEFAULT_REGISTRY_PATH)
    data = path.read_bytes()
    doc = json.loads(data)
    problems = registry_problems(doc)
    if problems:
        raise RegistryError(f"{path}: " + "; ".join(problems))
    chars = {}
    for cid, c in doc["characters"].items():
        chars[cid] = Character(cid, c["displayName"], c["role"], c["rig"], tuple(c["expressions"]), tuple(c["actions"]),
                               c["speaks"], c.get("voice"), dict(c["palette"]), c["captionColor"], c)
    return Registry(path, hashlib.sha256(data).hexdigest(), doc["rigVersion"], chars)


__all__ = ["Character", "DEFAULT_REGISTRY_PATH", "Registry", "RegistryError", "load_registry", "registry_problems"]
