"""Topic-to-script authoring (docs/PLAN-authoring.md, milestones A1-A7: offline / fixture mode only).

Every stage reads earlier JSON artifacts and writes its own (with a SHA-256) inside one run directory; nothing here
calls ``render``, ``voice``, ElevenLabs or ``publish``. Paid providers (A8) are opt-in and never used by tests.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts" / "authoring"
DATA = ROOT / "authoring"
CURRICULUM = ROOT / "curriculum"

__all__ = ["CONTRACTS", "CURRICULUM", "DATA", "ROOT"]
