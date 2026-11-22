"""Manim entry file: ``manim render entry.py <SceneClass>``.

Manim only discovers Scene classes *defined* in the rendered module, so each template class is
re-declared here as a trivial subclass with the same name.
"""

from robotics101.animation.manim_templates import recap_quiz, robot_anatomy, robot_intro, sense_think_act, \
    sensor_range, servo_rotation


class RobotIntroScene(robot_intro.RobotIntroScene):
    pass


class RobotAnatomyScene(robot_anatomy.RobotAnatomyScene):
    pass


class SensorRangeScene(sensor_range.SensorRangeScene):
    pass


class SenseThinkActScene(sense_think_act.SenseThinkActScene):
    pass


class ServoRotationScene(servo_rotation.ServoRotationScene):
    pass


class RecapQuizScene(recap_quiz.RecapQuizScene):
    pass
