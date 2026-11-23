"""EpisodeSpec validation: JSON Schema contract + semantic checks.

Severity policy
---------------
ERROR   -> spec cannot be rendered safely/deterministically; `validate` exits 1.
           Schema violations, duplicate sceneIds, non-contiguous sequences,
           unknown (engine, template), invalid template parameters.
WARNING -> editorial/pacing concern; spec is still renderable, exit 0
           (unless --strict). Applies to durations:
           * episode durationTargetSeconds outside the product window
             270..330 s (300 s +/- 10%). The schema itself allows 120..900.
           * sum of scene durationTargetSeconds deviates > 10% from the
             episode target. Real timing is derived from narration audio
             later (M01.2), so scene targets are planning hints only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from robotics101.templates.registry import get_template

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCHEMA_PATH = PROJECT_ROOT / "contracts" / "episode.schema.json"
SCHEMA_PATHS = {"1.0": DEFAULT_SCHEMA_PATH, "1.1": PROJECT_ROOT / "contracts" / "episode.v1.1.schema.json"}
DIALOGUE_WPS = 2.6            # planning estimate: words per second of cartoon dialogue
MIN_DIALOGUE_COVERAGE = 0.6   # warn when estimated dialogue covers less of a scene's target

EPISODE_DURATION_WINDOW_S = (270, 330)
SCENE_SUM_TOLERANCE = 0.10


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7} {self.path}: {self.message}"


@dataclass
class ValidationReport:
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, path: str, message: str) -> None:
        self.issues.append(Issue("error", path, message))

    def warn(self, path: str, message: str) -> None:
        self.issues.append(Issue("warning", path, message))


def schema_path() -> Path:
    return Path(os.environ.get("ROBOTICS101_SCHEMA", DEFAULT_SCHEMA_PATH))


def load_schema(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or schema_path()).read_text(encoding="utf-8"))


def _json_path(parts) -> str:
    out = "$"
    for p in parts:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def validate_episode(spec: Any, schema: dict[str, Any] | None = None) -> ValidationReport:
    """Validate a parsed EpisodeSpec. Semantic checks run only if the schema passes."""
    report = ValidationReport()
    if schema is None:
        version = spec.get("schemaVersion") if isinstance(spec, dict) else None
        schema = load_schema(SCHEMA_PATHS.get(version, DEFAULT_SCHEMA_PATH))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    for err in sorted(validator.iter_errors(spec), key=lambda e: list(e.absolute_path)):
        report.error(_json_path(err.absolute_path), f"schema: {err.message}")
    if not report.ok:
        return report

    scenes = spec["scenes"]
    _check_scene_ids(scenes, report)
    _check_sequences(scenes, report)
    _check_durations(spec, report)
    _check_templates(scenes, report)
    if spec.get("schemaVersion") == "1.1":
        _check_cartoon(spec, report)
    return report


def _check_cartoon(spec: dict, report: ValidationReport) -> None:
    """v1.1: cast/registry, beats (speakers, emotions, actions, sfx, music), teaching facts, kid-safe wording."""
    from robotics101.cartoon import MUSIC_CUES, SETS, SFX_IDS
    from robotics101.cartoon.lint import fact_problems, kidsafe_problems
    from robotics101.characters import RegistryError, load_registry

    try:
        reg = load_registry()
    except (OSError, ValueError, RegistryError) as e:
        report.error("$.characters", f"character registry unavailable: {e}")
        return
    cast = spec["characters"]
    for i, cid in enumerate(cast):
        if reg.get(cid) is None:
            report.error(f"$.characters[{i}]", f"unknown character '{cid}' (not in characters/registry.json)")
    if spec["set"] not in SETS:
        report.error("$.set", f"unknown set '{spec['set']}' (known: {sorted(SETS)})")
    theme = (spec.get("music") or {}).get("theme")
    if theme and theme not in MUSIC_CUES:
        report.error("$.music.theme", f"unknown music cue '{theme}'")
    in_cast = {c for c in cast if reg.get(c)}

    concept_ids: set[str] = set()
    for i, scene in enumerate(spec["scenes"]):
        words = 0
        lines = 0
        for j, b in enumerate(scene["beats"]):
            path = f"$.scenes[{i}].beats[{j}]"
            t = b["type"]
            if t == "line":
                lines += 1
                words += len(b["text"].split())
                ch = reg.get(b["speaker"])
                if b["speaker"] not in in_cast:
                    report.error(path + ".speaker", f"speaker '{b['speaker']}' is not in the episode cast {cast}")
                    continue
                if not ch.speaks:
                    report.error(path + ".speaker", f"'{b['speaker']}' does not speak (use sfx beats, e.g. nib_beep)")
                if b.get("emotion") and b["emotion"] not in ch.expressions:
                    report.error(path + ".emotion", f"'{b['emotion']}' is not an expression of {b['speaker']} {list(ch.expressions)}")
                if b.get("action") and not ch.allows_action(b["action"]):
                    report.error(path + ".action", f"'{b['action']}' is not an action of {b['speaker']}")
                if b.get("target") and b["target"] not in in_cast:
                    report.error(path + ".target", f"target '{b['target']}' is not in the cast")
            elif t == "action":
                ch = reg.get(b["who"])
                if b["who"] not in in_cast:
                    report.error(path + ".who", f"'{b['who']}' is not in the episode cast {cast}")
                    continue
                if not ch.allows_action(b["do"]):
                    report.error(path + ".do", f"'{b['do']}' is not an action of {b['who']} {list(ch.actions)}")
                if b.get("emotion") and b["emotion"] not in ch.expressions:
                    report.error(path + ".emotion", f"'{b['emotion']}' is not an expression of {b['who']}")
            elif t == "sfx":
                if b["id"] not in SFX_IDS:
                    report.error(path + ".id", f"unknown sfx '{b['id']}'")
                if b.get("who") and b["who"] not in in_cast:
                    report.error(path + ".who", f"'{b['who']}' is not in the cast")
            elif t == "music" and b["cue"] not in MUSIC_CUES:
                report.error(path + ".cue", f"unknown music cue '{b['cue']}'")
        if lines == 0:
            report.error(f"$.scenes[{i}].beats", "a cartoon scene needs at least one dialogue line")
        for k, c in enumerate(scene.get("concepts") or []):              # M03.2 concept markers
            if c.get("beforeBeat", 0) > len(scene["beats"]):
                report.error(f"$.scenes[{i}].concepts[{k}].beforeBeat", f"beyond the scene's {len(scene['beats'])} beats")
            if c["id"] in concept_ids:
                report.error(f"$.scenes[{i}].concepts[{k}].id", f"concept '{c['id']}' is introduced twice")
            concept_ids.add(c["id"])
        est = words / DIALOGUE_WPS
        if est < MIN_DIALOGUE_COVERAGE * scene["durationTargetSeconds"]:
            report.warn(f"$.scenes[{i}].beats",
                        f"~{est:.0f}s of dialogue for a {scene['durationTargetSeconds']:g}s scene "
                        f"(< {MIN_DIALOGUE_COVERAGE:.0%}): add lines/gags or shorten the scene")

    thresholds = {s["parameters"]["thresholdMeters"] for s in spec["scenes"] if "thresholdMeters" in s["parameters"]}
    if len(thresholds) > 1:
        report.error("$.scenes", f"stop threshold must be the same in every scene, got {sorted(thresholds)}")
    for path, msg in fact_problems(spec):
        report.error(path, msg)
    kids = (spec.get("publishing") or {}).get("madeForKids", False)
    for path, msg in kidsafe_problems(spec):
        (report.error if kids else report.warn)(path, msg)


def _check_scene_ids(scenes: list[dict], report: ValidationReport) -> None:
    seen: dict[str, int] = {}
    for i, scene in enumerate(scenes):
        sid = scene["sceneId"]
        if sid in seen:
            report.error(f"$.scenes[{i}].sceneId", f"duplicate sceneId '{sid}' (first at scenes[{seen[sid]}])")
        else:
            seen[sid] = i


def _check_sequences(scenes: list[dict], report: ValidationReport) -> None:
    seqs = [s["sequence"] for s in scenes]
    dupes = sorted({q for q in seqs if seqs.count(q) > 1})
    if dupes:
        report.error("$.scenes", f"duplicate scene sequence numbers: {dupes}")
    expected = list(range(1, len(scenes) + 1))
    if sorted(seqs) != expected and not dupes:
        report.error("$.scenes", f"scene sequences must be contiguous 1..{len(scenes)}, got {sorted(seqs)}")


def _check_durations(spec: dict, report: ValidationReport) -> None:
    target = spec["durationTargetSeconds"]
    lo, hi = EPISODE_DURATION_WINDOW_S
    if not lo <= target <= hi:
        report.warn(
            "$.durationTargetSeconds",
            f"episode target {target}s outside product window {lo}..{hi}s (5-minute lesson)",
        )
    total = sum(s["durationTargetSeconds"] for s in spec["scenes"])
    if abs(total - target) > SCENE_SUM_TOLERANCE * target:
        report.warn(
            "$.scenes",
            f"sum of scene targets {total:g}s differs from episode target {target}s "
            f"by more than {SCENE_SUM_TOLERANCE:.0%}",
        )


def _check_templates(scenes: list[dict], report: ValidationReport) -> None:
    for i, scene in enumerate(scenes):
        engine, name = scene["engine"], scene["template"]
        tmpl = get_template(engine, name)
        if tmpl is None:
            report.error(f"$.scenes[{i}].template", f"unknown template '{name}' for engine '{engine}'")
            continue
        for msg in tmpl.validate_params(scene["parameters"]):
            report.error(f"$.scenes[{i}].parameters", f"{name}: {msg}")


def validate_file(path: Path) -> ValidationReport:
    """Load and validate an EpisodeSpec file. Raises OSError / json.JSONDecodeError on bad input."""
    spec = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_episode(spec)
