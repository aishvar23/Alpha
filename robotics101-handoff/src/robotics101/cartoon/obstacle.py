"""2D obstacle-avoidance demo kinematics (M02.5) — the main (cartoon) view of the rematch scene.

The sensing/stop moment also cuts to the M01 Blender scene as a cartoon-styled "robot-cam" insert (see
``robotcam.py``); both use the same episode threshold.

The robot drives straight at an obstacle at constant speed, its distance sensor samples at ``SAMPLE_HZ`` and the
controller applies the episode rule *if distance < threshold: stop and turn*. Readings are truncated to whole
centimetres for display (so a stop never reads "0.50 m" next to "< 0.5 m"). ``plan_approach`` picks the speed so
the stop lands on the scripted beat time; ``assert_no_collision`` is the safety check used by tests and QA.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

SAMPLE_HZ = 10.0


@dataclass(frozen=True)
class Approach:
    t0: float                 # drive starts
    d0: float                 # true distance at t0 (m)
    speed: float              # m/s
    threshold: float
    stop_t: float             # first sample with reading < threshold (robot stops here)
    stop_d: float             # true distance at the stop

    def distance(self, t: float) -> float:
        if t <= self.t0:
            return self.d0
        return max(self.stop_d, self.d0 - self.speed * (min(t, self.stop_t) - self.t0))

    def reading(self, t: float) -> float:
        """Last sensor sample at or before ``t`` (truncated to cm)."""
        if t < self.t0:
            return trunc_cm(self.d0)
        k = math.floor((min(t, self.stop_t) - self.t0) * SAMPLE_HZ + 1e-9)
        return trunc_cm(self.distance(self.t0 + k / SAMPLE_HZ))

    def stopped(self, t: float) -> bool:
        return t >= self.stop_t


def trunc_cm(d: float) -> float:
    return math.floor(d * 100 + 1e-9) / 100


def plan_approach(t0: float, t_stop: float, d0: float, threshold: float, stop_at: float | None = None) -> Approach:
    """Constant speed so the first sample below ``threshold`` happens at (or just before) ``t_stop``.

    ``stop_at`` (m, < threshold) picks the stop distance — e.g. the robot-cam clip's stop reading, so the 2D view
    and the cutaway show the same number; default: 1 cm under the threshold (0.49 m for 0.5 m)."""
    if not (d0 > threshold > 0 and t_stop > t0):
        raise ValueError("need d0 > threshold > 0 and t_stop > t0")
    if stop_at is not None and not (0 < stop_at < threshold):
        raise ValueError("stop_at must be in (0, threshold)")
    n = max(1, math.floor((t_stop - t0) * SAMPLE_HZ))           # samples available
    target = (stop_at if stop_at is not None else threshold - 0.01) + 1e-6
    # the sample before the stop must still read >= threshold, else the rule would fire one sample early:
    # need speed/HZ > threshold - target; if the window is too long for that, start driving later.
    min_step = (threshold - target) * 1.0001
    n = min(n, max(1, math.floor((d0 - target) / min_step))) if min_step > 0 else n
    speed = (d0 - target) / (n / SAMPLE_HZ)
    start = t_stop - n / SAMPLE_HZ                               # waits (if needed) so the stop lands on t_stop
    stop_t = None
    for k in range(1, n + 1):
        if d0 - speed * k / SAMPLE_HZ < threshold:
            stop_t = start + k / SAMPLE_HZ
            break
    assert stop_t is not None
    return Approach(round(start, 6), d0, speed, threshold, round(stop_t, 6), d0 - speed * (stop_t - start))


def assert_no_collision(a: Approach) -> None:
    if not (0 < a.stop_d < a.threshold):
        raise AssertionError(f"stop distance {a.stop_d:.3f} m not inside (0, {a.threshold}) m")
    if a.reading(a.stop_t) >= a.threshold:
        raise AssertionError("robot stopped although the reading was not below the threshold")


# ------------------------------------------------------------------------------------------ 2D staging

BOLT_FRONT = 2.03        # rig units from Bolt's centre to his frontmost point (hands); distance is measured from here


CLEAR_READING = "distance: > 3 m (clear)"


def hud_lines(reading: float, threshold: float, turned: bool) -> list[tuple[str, str]]:
    """Distance-HUD rows. Once the robot has turned away the sensor no longer sees the obstacle, so the HUD shows a
    clear reading with 'path clear → GO' (M05.5: never the old 0.47 m next to GO, which contradicted itself)."""
    rule = (f"rule: stop if < {threshold:g} m", "#FFFFFF")
    if turned:
        return [(CLEAR_READING, "#7CFFCB"), rule, ("path clear → GO", "#FFD166")]
    alert = reading < threshold
    rows = [(f"distance: {reading:.2f} m", "#EF476F" if alert else "#7CFFCB"), rule]
    if alert:
        rows.append(("STOP & TURN!", "#FFD166"))
    return rows


def bolt_center_x(a: Approach, t: float, box_face_x: float, scale: float, meter: float) -> float:
    """Bolt's centre x while approaching an obstacle face on his right (facing +1)."""
    return box_face_x - a.distance(t) * meter - BOLT_FRONT * scale


def demo_frame_fn(a: Approach, box_x: float, turn_t: float, resume_t: float, scale: float = 0.78):
    """Stand-alone 2D obstacle demo (props gallery / M02.5 sample): drive, stop below threshold, turn, resume."""
    import numpy as np

    from . import props as p
    from .rigs import Pose, build
    from .sets import GROUND, METER, garage

    face = box_x - p.BOX_W / 2
    bg = garage("no_shelf")
    pile = p.box_pile(box_x)
    tape = p.ruler_rev(face, 3.0, danger=a.threshold)

    def frame(t: float):
        x = bolt_center_x(a, t, face, scale, METER)
        facing = 1
        if t >= turn_t:
            facing = -1
            x -= max(0.0, t - resume_t) * 1.6
        stopped = a.stopped(t)
        expr = "surprised" if stopped and t < turn_t else "happy"
        pose = Pose(expression=expr, facing=facing, mouth="X", arm_l=20, arm_r=20, lean=0.05 if not stopped else -0.05)
        bolt = build("bolt", pose).scale(scale, about_point=np.zeros(3)).shift(np.array([x, GROUND, 0]))
        lines = hud_lines(a.reading(t), a.threshold, t >= turn_t)
        mobs = [bg, tape, pile, bolt, p.readout(lines, p.P(3.9, 2.6))]
        if not stopped:
            sensor = np.array([x + BOLT_FRONT * scale * 0.7, GROUND + 1.6 * scale, 0])
            u = ((t - a.t0 + 0.25) / 0.6) % 1.0 if t >= a.t0 else 0.0   # visual ping cycle (sensor samples faster)
            mobs.append(p.ping_waves(sensor, u, max(0.2, face - sensor[0])))
        if stopped and t < a.stop_t + 0.9:
            mobs.append(p.sfx_text("SKREEECH!", "#EF476F", (t - a.stop_t) / 0.9, p.P(face - 1.6, 1.0)))
        return mobs
    return frame
