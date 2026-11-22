"""Deterministic Manim scene templates (one module per template).

This package's ``__init__`` must not import manim: the host-side renderer uses
``SCENE_CLASSES`` to pick the class name, then runs manim in a subprocess on
``entry.py``. Scene parameters reach the template only as JSON data via the
``ROBOTICS101_SCENE_JOB`` environment variable — spec content is never executed.
"""

from __future__ import annotations

from pathlib import Path

JOB_ENV = "ROBOTICS101_SCENE_JOB"
ENTRY_FILE = Path(__file__).with_name("entry.py")

# template name -> Manim Scene class name defined in entry.py's imports
SCENE_CLASSES: dict[str, str] = {
    "robot_intro": "RobotIntroScene",
    "robot_anatomy": "RobotAnatomyScene",
    "sensor_range": "SensorRangeScene",
    "sense_think_act": "SenseThinkActScene",
    "servo_rotation": "ServoRotationScene",
    "recap_quiz": "RecapQuizScene",
}
