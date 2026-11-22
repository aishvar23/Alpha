"""Pure 2D kinematics for the ``mobile_robot_avoidance`` Blender template (no bpy, stdlib only).

The Blender script imports this module (Blender ships its own Python 3.11, so keep the syntax
3.11-compatible and the imports stdlib + ``robotics101.geometry`` only). Everything visible in the
3D scene — robot poses, wheel spin, sensor readings, beam colour, phase labels — is computed here
frame by frame, so it can be unit-tested without rendering.

Conventions: metres, radians, ground plane z = 0, heading 0 = +x, counter-clockwise positive.
The robot runs a sense -> think -> act loop once per frame using the same rule as the
``sense_think_act`` scene (``geometry.threshold_decision``: stop when reading < threshold).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from robotics101.geometry import STOP_AND_TURN, threshold_decision

# Phase names (also used as HUD label keys by the Blender template).
PHASE_START = "start"
PHASE_DRIVE = "drive"
PHASE_DETECTED = "detected"
PHASE_TURN = "turn"
PHASE_RESUME = "resume"
PHASES = (PHASE_START, PHASE_DRIVE, PHASE_DETECTED, PHASE_TURN, PHASE_RESUME)


class CollisionError(RuntimeError):
    """The planned robot path intersects (or comes within the margin of) the obstacle."""


class PathPlanningError(RuntimeError):
    """The avoidance script cannot be generated for this configuration."""


@dataclass(frozen=True)
class Box2D:
    """Axis-aligned rectangle on the ground plane (centre + half extents)."""

    cx: float
    cy: float
    half_x: float
    half_y: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return (self.cx - self.half_x, self.cx + self.half_x, self.cy - self.half_y, self.cy + self.half_y)

    def corners(self) -> list[tuple[float, float]]:
        x0, x1, y0, y1 = self.bounds
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


@dataclass(frozen=True)
class RobotGeometry:
    """Primitive ``simple_mobile_robot_v1``: box chassis, two drive wheels + front caster, sensor eye."""

    chassis_length: float = 0.60     # along heading
    chassis_width: float = 0.40
    chassis_height: float = 0.22
    ground_clearance: float = 0.06   # chassis underside above ground
    wheel_radius: float = 0.11
    wheel_width: float = 0.06
    track: float = 0.52              # distance between left/right wheel centres
    wheel_offset_x: float = -0.12    # drive axle position relative to chassis centre
    sensor_offset: float = 0.32      # sensor face, ahead of chassis centre

    @property
    def footprint_length(self) -> float:
        return self.chassis_length

    @property
    def footprint_width(self) -> float:
        """Overall width including the wheels (what must clear the obstacle)."""
        return max(self.chassis_width, self.track + self.wheel_width)


@dataclass(frozen=True)
class AvoidanceConfig:
    obstacle: Box2D = Box2D(4.0, 0.0, 0.30, 0.30)
    start: tuple[float, float, float] = (0.0, 0.0, 0.0)  # x, y, heading
    sensor_range: float = 1.5        # beam length (m)
    stop_threshold: float = 0.5      # stop & turn when reading < threshold (m); the render plan overrides it
                                     # with the episode's sense_think_act thresholdMeters (same rule as taught)
    drive_speed: float = 0.35        # m/s (slow enough for beginners to follow)
    turn_rate_deg: float = 45.0      # deg/s, in place
    turn_angle_deg: float = 90.0     # + = left (CCW)
    resume_distance: float = 2.4     # m along the clear path after the turn
    start_pause_s: float = 1.0
    detect_pause_s: float = 1.5      # robot stopped, beam red, "Obstacle detected"
    after_turn_pause_s: float = 0.5
    max_drive_distance: float = 20.0  # safety stop if the obstacle is never detected
    collision_margin: float = 0.05   # required clearance (m) between footprint and obstacle

    def validate(self) -> None:
        if not (0 < self.stop_threshold <= self.sensor_range):
            raise PathPlanningError("need 0 < stop_threshold <= sensor_range")
        for name in ("drive_speed", "turn_rate_deg", "resume_distance"):
            if getattr(self, name) <= 0:
                raise PathPlanningError(f"{name} must be > 0")
        for name in ("start_pause_s", "detect_pause_s", "after_turn_pause_s", "collision_margin"):
            if getattr(self, name) < 0:
                raise PathPlanningError(f"{name} must be >= 0")


@dataclass(frozen=True)
class Pose:
    frame: int                 # 0-based
    x: float
    y: float
    heading: float             # rad
    wheel_left: float          # cumulative wheel rotation (rad), + = rolling forward
    wheel_right: float
    reading: float | None      # sensor distance to obstacle along the beam, None = nothing in range
    alert: bool                # controller says STOP_AND_TURN for this reading (beam turns red)
    phase: str


@dataclass
class AvoidancePath:
    poses: list[Pose]
    fps: int
    time_scale: float
    stop_frame: int            # first frame of PHASE_DETECTED
    phase_frames: dict[str, tuple[int, int]] = field(default_factory=dict)  # phase -> [first, last]

    @property
    def motion_frames(self) -> int:
        return len(self.poses)

    @property
    def stop_reading(self) -> float:
        r = self.poses[self.stop_frame].reading
        assert r is not None
        return r


# ---------------------------------------------------------------- sensing

def sensor_origin(x: float, y: float, heading: float, geom: RobotGeometry) -> tuple[float, float]:
    return (x + geom.sensor_offset * math.cos(heading), y + geom.sensor_offset * math.sin(heading))


def ray_box_distance(ox: float, oy: float, heading: float, box: Box2D, max_range: float) -> float | None:
    """Distance from (ox, oy) along ``heading`` to ``box`` (slab method); None if no hit within range.

    An origin inside the box reads 0.0.
    """
    dx, dy = math.cos(heading), math.sin(heading)
    x0, x1, y0, y1 = box.bounds
    t_min, t_max = -math.inf, math.inf
    for o, d, lo, hi in ((ox, dx, x0, x1), (oy, dy, y0, y1)):
        if abs(d) < 1e-12:
            if not (lo <= o <= hi):
                return None
            continue
        t0, t1 = (lo - o) / d, (hi - o) / d
        if t0 > t1:
            t0, t1 = t1, t0
        t_min, t_max = max(t_min, t0), min(t_max, t1)
    if t_max < t_min or t_max < 0:
        return None
    dist = max(t_min, 0.0)
    return dist if dist <= max_range else None


def read_sensor(x: float, y: float, heading: float, geom: RobotGeometry, cfg: AvoidanceConfig) -> float | None:
    ox, oy = sensor_origin(x, y, heading, geom)
    return ray_box_distance(ox, oy, heading, cfg.obstacle, cfg.sensor_range)


def is_alert(reading: float | None, threshold: float) -> bool:
    return reading is not None and threshold_decision(reading, threshold) == STOP_AND_TURN


# ---------------------------------------------------------------- path generation

def _frames(seconds: float, fps: int) -> int:
    return max(0, round(seconds * fps))


def generate_avoidance_path(cfg: AvoidanceConfig = AvoidanceConfig(), geom: RobotGeometry = RobotGeometry(),
                            fps: int = 30, time_scale: float = 1.0) -> AvoidancePath:
    """Simulate drive -> detect -> stop -> turn -> resume, one pose per frame.

    ``time_scale`` (0 < s <= 1, from ``animation.timing.animation_speed``) compresses the whole
    script for short scenes: pauses are multiplied by it and speeds divided by it.
    """
    cfg.validate()
    if not (0 < time_scale <= 1.0):
        raise PathPlanningError(f"time_scale must be in (0, 1], got {time_scale}")
    if fps <= 0:
        raise PathPlanningError("fps must be > 0")
    r = geom.wheel_radius
    poses: list[Pose] = []
    phase_frames: dict[str, tuple[int, int]] = {}
    x, y, th = cfg.start
    wl = wr = 0.0

    def emit(phase: str) -> Pose:
        reading = read_sensor(x, y, th, geom, cfg)
        p = Pose(len(poses), x, y, th, wl, wr, reading, is_alert(reading, cfg.stop_threshold), phase)
        poses.append(p)
        first, _ = phase_frames.get(phase, (p.frame, p.frame))
        phase_frames[phase] = (first, p.frame)
        return p

    # 1. stand still
    for _ in range(max(1, _frames(cfg.start_pause_s * time_scale, fps))):
        emit(PHASE_START)

    # 2. drive forward; sense -> think -> act every frame
    step = cfg.drive_speed / time_scale / fps
    travelled = 0.0
    while True:
        reading = read_sensor(x, y, th, geom, cfg)
        if is_alert(reading, cfg.stop_threshold):
            break  # think: STOP_AND_TURN -> act: do not move this frame
        if travelled >= cfg.max_drive_distance:
            raise PathPlanningError(f"obstacle never detected within {cfg.max_drive_distance} m of driving")
        x += step * math.cos(th)
        y += step * math.sin(th)
        travelled += step
        wl += step / r
        wr += step / r
        emit(PHASE_DRIVE)

    # 3. stopped, obstacle detected
    stop_frame = len(poses)
    for _ in range(max(1, _frames(cfg.detect_pause_s * time_scale, fps))):
        emit(PHASE_DETECTED)

    # 4. turn in place (differential drive: wheels spin in opposite directions)
    turn = math.radians(cfg.turn_angle_deg)
    n_turn = max(1, _frames(abs(cfg.turn_angle_deg) / cfg.turn_rate_deg * time_scale, fps))
    dth = turn / n_turn
    th0 = th
    for i in range(1, n_turn + 1):
        th = th0 + dth * i
        arc = dth * geom.track / 2.0
        wl -= arc / r
        wr += arc / r
        emit(PHASE_TURN)
    for _ in range(_frames(cfg.after_turn_pause_s * time_scale, fps)):
        emit(PHASE_TURN)

    # 5. resume along the clear path (exact distance, whole frames)
    n_resume = max(1, round(cfg.resume_distance / cfg.drive_speed * time_scale * fps))
    step = cfg.resume_distance / n_resume
    for _ in range(n_resume):
        x += step * math.cos(th)
        y += step * math.sin(th)
        wl += step / r
        wr += step / r
        emit(PHASE_RESUME)

    return AvoidancePath(poses, fps, time_scale, stop_frame, phase_frames)


# ---------------------------------------------------------------- collision check

def footprint_corners(x: float, y: float, heading: float, geom: RobotGeometry) -> list[tuple[float, float]]:
    """Corners of the robot's oriented footprint rectangle (chassis length x overall width)."""
    hl, hw = geom.footprint_length / 2.0, geom.footprint_width / 2.0
    c, s = math.cos(heading), math.sin(heading)
    return [(x + c * px - s * py, y + s * px + c * py) for px, py in ((hl, hw), (-hl, hw), (-hl, -hw), (hl, -hw))]


def _project(points: list[tuple[float, float]], ax: tuple[float, float]) -> tuple[float, float]:
    vals = [p[0] * ax[0] + p[1] * ax[1] for p in points]
    return min(vals), max(vals)


def polygon_intersects_box(corners: list[tuple[float, float]], box: Box2D, margin: float = 0.0) -> bool:
    """Separating-axis test: convex rectangle ``corners`` vs ``box`` grown by ``margin`` on every side."""
    grown = Box2D(box.cx, box.cy, box.half_x + margin, box.half_y + margin)
    box_pts = grown.corners()
    axes = [(1.0, 0.0), (0.0, 1.0)]
    for i in range(2):  # the rectangle's two edge normals
        ex, ey = corners[i + 1][0] - corners[i][0], corners[i + 1][1] - corners[i][1]
        n = math.hypot(ex, ey)
        if n > 0:
            axes.append((-ey / n, ex / n))
    for ax in axes:
        a0, a1 = _project(corners, ax)
        b0, b1 = _project(box_pts, ax)
        if a1 < b0 or b1 < a0:
            return False  # found a separating axis
    return True


def find_collision(poses: list[Pose], geom: RobotGeometry, box: Box2D, margin: float = 0.0) -> int | None:
    """Frame index of the first pose whose footprint touches the (margin-grown) obstacle, else None."""
    for p in poses:
        if polygon_intersects_box(footprint_corners(p.x, p.y, p.heading, geom), box, margin):
            return p.frame
    return None


def assert_collision_free(path: AvoidancePath, geom: RobotGeometry, cfg: AvoidanceConfig) -> None:
    hit = find_collision(path.poses, geom, cfg.obstacle, cfg.collision_margin)
    if hit is not None:
        p = path.poses[hit]
        raise CollisionError(
            f"collisionCheck failed: robot footprint at frame {hit} (x={p.x:.3f}, y={p.y:.3f}, "
            f"heading={math.degrees(p.heading):.1f} deg, phase {p.phase}) is within {cfg.collision_margin} m "
            f"of the obstacle box {cfg.obstacle.bounds}")


# ---------------------------------------------------------------- scene helpers

def scene_bounds(path: AvoidancePath, geom: RobotGeometry, box: Box2D) -> tuple[float, float, float, float]:
    """(xmin, xmax, ymin, ymax) covering every footprint along the path and the obstacle."""
    pts = list(box.corners())
    for p in path.poses:
        pts.extend(footprint_corners(p.x, p.y, p.heading, geom))
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), max(xs), min(ys), max(ys)
