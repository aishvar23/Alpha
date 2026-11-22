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
    validator = Draft202012Validator(schema or load_schema(), format_checker=Draft202012Validator.FORMAT_CHECKER)
    for err in sorted(validator.iter_errors(spec), key=lambda e: list(e.absolute_path)):
        report.error(_json_path(err.absolute_path), f"schema: {err.message}")
    if not report.ok:
        return report

    scenes = spec["scenes"]
    _check_scene_ids(scenes, report)
    _check_sequences(scenes, report)
    _check_durations(spec, report)
    _check_templates(scenes, report)
    return report


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
