"""sensor_range: robot + sensor beam of rangeMeters, obstacle drawn to scale, distance readout, detection."""

from __future__ import annotations

from manim import (
    DOWN, LEFT, RIGHT, UP, Create, DoubleArrow, FadeIn, GrowFromEdge, Line, MoveAlongPath,
    Polygon, Rectangle, Dot, SurroundingRectangle, VGroup, Write, DashedLine,
)

from robotics101.animation.manim_templates._base import (
    ACCENT, ALERT, BODY_SIZE, FG, LABEL_SIZE, MUTED, WARN, TemplateScene, content_box, text, wrapped_text,
)
from robotics101.animation.manim_templates._shapes import mobile_rover
from robotics101.animation.manim_templates._widgets import fmt_m, ruler
from robotics101.geometry import meters_to_scene_x, obstacle_detected, tick_step_meters

AXIS_Y = 0.75
BEAM_HALF_HEIGHT = 1.0
OBSTACLE_W, OBSTACLE_H = 0.55, 1.3


class SensorRangeScene(TemplateScene):
    TEMPLATE = "sensor_range"
    NOMINAL_SECONDS = 12.0

    def build(self) -> None:
        left, right, bottom, top = content_box()
        rng = float(self.params["rangeMeters"])
        dist = float(self.params["obstacleDistanceMeters"])

        robot = mobile_rover().scale_to_fit_height(1.3)
        robot.move_to([left + 0.2 + robot.width / 2, AXIS_Y, 0])
        sensor = Rectangle(width=0.16, height=0.36, color=ACCENT, fill_color=ACCENT, fill_opacity=1)
        sensor.next_to(robot, RIGHT, buff=0).set_y(AXIS_Y)
        origin_x = sensor.get_right()[0]
        available = (right - OBSTACLE_W - 0.25) - origin_x

        def sx(m: float) -> float:
            return meters_to_scene_x(m, rng, origin_x, available)

        end_x = sx(rng)
        step = tick_step_meters(rng, max_ticks=8)
        n_ticks = round(rng / step)
        axis = ruler(origin_x, end_x, AXIS_Y - 1.75, rng, step, label_every=1 if n_ticks <= 6 else 2)
        self.anim(FadeIn(robot), FadeIn(sensor), seconds=1.0)
        self.anim(Create(axis), seconds=1.0)

        beam = Polygon([origin_x, AXIS_Y, 0], [end_x, AXIS_Y + BEAM_HALF_HEIGHT, 0],
                       [end_x, AXIS_Y - BEAM_HALF_HEIGHT, 0], color=ACCENT, stroke_width=2,
                       fill_color=ACCENT, fill_opacity=0.18)
        range_mark = DashedLine([end_x, AXIS_Y + BEAM_HALF_HEIGHT, 0], [end_x, AXIS_Y - 1.75, 0],
                                color=ACCENT, stroke_width=2)
        range_lbl = text(f"range {fmt_m(rng)}", LABEL_SIZE, ACCENT).next_to(
            [end_x, AXIS_Y + BEAM_HALF_HEIGHT, 0], UP, buff=0.12)
        range_lbl.shift(LEFT * max(0.0, range_lbl.get_right()[0] - right))
        self.anim(GrowFromEdge(beam, LEFT), seconds=1.5)
        self.anim(Create(range_mark), FadeIn(range_lbl), seconds=0.8)

        obs_x = sx(dist)
        obstacle = Rectangle(width=OBSTACLE_W, height=OBSTACLE_H, color=FG, fill_color=MUTED, fill_opacity=0.9)
        obstacle.move_to([obs_x + OBSTACLE_W / 2, AXIS_Y, 0])
        self.anim(FadeIn(obstacle, shift=DOWN * 0.3), seconds=0.8)

        # ping travels to the obstacle face and back
        ping = Dot([origin_x, AXIS_Y, 0], radius=0.09, color=ACCENT)
        out_path = Line([origin_x, AXIS_Y, 0], [obs_x, AXIS_Y, 0])
        self.add(ping)
        self.anim(MoveAlongPath(ping, out_path), seconds=0.9)
        self.anim(MoveAlongPath(ping, out_path.copy().reverse_direction()), seconds=0.9)
        self.remove(ping)

        meas_y = AXIS_Y - 1.2
        meas = DoubleArrow([origin_x, meas_y, 0], [obs_x, meas_y, 0], buff=0, color=WARN,
                           stroke_width=4, tip_length=0.18)
        meas_lbl = text(fmt_m(dist), LABEL_SIZE, WARN).next_to(meas, UP, buff=0.08)
        self.anim(Create(meas), FadeIn(meas_lbl), seconds=1.0)

        detected = obstacle_detected(dist, rng)
        status = "OBSTACLE DETECTED" if detected else "nothing in range"
        readout = VGroup(
            text(f"Sensor range: {fmt_m(rng)}", BODY_SIZE, FG),
            text(f"Measured distance: {fmt_m(dist)}", BODY_SIZE, FG),
        ).arrange(RIGHT, buff=0.8)
        status_t = wrapped_text(status, right - left, size=BODY_SIZE + 4, color=ALERT if detected else MUTED,
                                max_lines=1, weight="BOLD")
        panel = VGroup(readout, status_t).arrange(DOWN, buff=0.25)
        if panel.width > right - left:
            panel.scale_to_fit_width(right - left)
        panel.move_to([0, bottom + panel.height / 2 + 0.05, 0])
        self.anim(Write(readout), seconds=1.2)
        anims = [FadeIn(status_t, scale=1.1)]
        if detected:
            anims += [obstacle.animate.set_fill(ALERT, opacity=0.9),
                      Create(SurroundingRectangle(obstacle, color=ALERT, buff=0.1, stroke_width=5))]
        self.anim(*anims, seconds=1.0)



