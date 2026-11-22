"""Blender template: primitive mobile robot drives, detects an obstacle, stops, turns, resumes.

Run headless (the host renderer does this; see ``animation/blender_render.py``)::

    blender --background --factory-startup --python-exit-code 1 \\
        --python mobile_robot_avoidance.py -- --params job.json --out FRAMES_DIR \\
        --width 854 --height 480 --fps 30 [--engine workbench|eevee] [--frames A:B]

Only primitive geometry is created (no assets are loaded). All motion comes from the pure
``robotics101.kinematics`` plan (the same one the host checks before launching Blender);
``collisionCheck`` is re-asserted here and any failure exits non-zero. Each motion frame is set
explicitly and rendered to ``FRAMES_DIR/NNNNN.png`` (0-based frame index); the static hold after
the motion is appended by the host when encoding, so it is not re-rendered.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Euler, Vector

SRC = Path(__file__).resolve().parents[3]  # .../src
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from robotics101 import kinematics as K  # noqa: E402
from robotics101.animation.blender_templates import (  # noqa: E402
    JOB_STOP_THRESHOLD_KEY,
    format_reading_m,
    format_threshold_m,
    plan_mobile_robot_avoidance,
)
from robotics101.templates.registry import get_template  # noqa: E402

# ---------------------------------------------------------------- style
BG = (0.80, 0.85, 0.90)                 # light blue-grey "studio" background
GROUND = (0.62, 0.66, 0.62, 1.0)
GRID = (0.52, 0.56, 0.53, 1.0)
CHASSIS = (0.10, 0.36, 0.78, 1.0)
LID = (0.86, 0.89, 0.93, 1.0)
WHEEL = (0.10, 0.10, 0.11, 1.0)
HUB = (0.95, 0.75, 0.15, 1.0)
SENSOR = (0.15, 0.17, 0.20, 1.0)
EYE = (0.75, 0.78, 0.82, 1.0)
OBSTACLE = (0.85, 0.35, 0.12, 1.0)
BEAM_CLEAR = (0.15, 0.80, 0.30, 0.45)   # nothing in range
BEAM_SEEN = (0.98, 0.72, 0.10, 0.50)    # obstacle in range, still >= threshold
BEAM_ALERT = (0.92, 0.12, 0.10, 0.60)   # reading < threshold -> STOP_AND_TURN
TEXT_DARK = (0.06, 0.08, 0.12, 1.0)
TEXT_DIM = (0.45, 0.50, 0.56, 1.0)
TEXT_MID = (0.22, 0.25, 0.30, 1.0)
TEXT_ACTIVE = (0.92, 0.12, 0.10, 1.0)
TEXT_GO = (0.02, 0.45, 0.16, 1.0)
PANEL = (0.97, 0.97, 0.98, 1.0)

OUTLINE = None                          # (r, g, b) Workbench object outline colour, or None (M01 look)


def _lin(hexstr: str, a: float = 1.0) -> tuple:
    """sRGB hex -> linear RGBA (Blender material colours are linear)."""
    c = [int(hexstr[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*lin, a)


def apply_cartoon_style() -> None:
    """'robot-cam' cutaway for the cartoon episode (M02.5): the cartoon palette + ink outlines.
    Same geometry, motion plan, threshold and HUD logic as M01 — only colours/outlines change."""
    g = globals()
    g.update(
        BG=_lin("#FFE8C2")[:3], GROUND=_lin("#F2D3B3"), GRID=_lin("#E0B894"), CHASSIS=_lin("#2EC4B6"),
        LID=_lin("#1B1B3A"), WHEEL=_lin("#45505E"), HUB=_lin("#FFC93C"), SENSOR=_lin("#2B2140"), EYE=_lin("#7CFFCB"),
        OBSTACLE=_lin("#E76F51"), BEAM_CLEAR=_lin("#06D6A0", 0.45), BEAM_SEEN=_lin("#FFD166", 0.5),
        BEAM_ALERT=_lin("#EF476F", 0.6), TEXT_DARK=_lin("#2B2140"), TEXT_DIM=_lin("#9A8C98"),
        TEXT_MID=_lin("#6C4AB6"), TEXT_ACTIVE=_lin("#EF476F"), TEXT_GO=_lin("#06A77D"), PANEL=_lin("#FFF4E0"),
        OUTLINE=_lin("#2B2140")[:3])


STEPS = [  # HUD step chips: (label, phases that highlight it)
    ("Drive", {K.PHASE_START, K.PHASE_DRIVE}),
    ("Obstacle detected", {K.PHASE_DETECTED}),
    ("Stop", {K.PHASE_DETECTED}),
    ("Turn", {K.PHASE_TURN}),
    ("Resume", {K.PHASE_RESUME}),
]
# chip colour: green while the robot drives (Drive / Resume), red for the stop-and-turn response
GO_PHASES = {K.PHASE_START, K.PHASE_DRIVE, K.PHASE_RESUME}
BEAM_HALF_ANGLE = math.radians(7.0)
HUD_DIST = 1.0                          # HUD plane distance in front of the camera (m)
# Allowed region (normalised camera coords) for the 3D action, leaving room for the HUD bands.
SAFE_X = (0.04, 0.96)
SAFE_Y = (0.17, 0.84)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="mobile_robot_avoidance")
    ap.add_argument("--params", type=Path, required=True, help="job JSON written by the host renderer")
    ap.add_argument("--out", type=Path, required=True, help="directory for NNNNN.png frames")
    ap.add_argument("--width", type=int, required=True)
    ap.add_argument("--height", type=int, required=True)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--engine", choices=["workbench", "eevee"], default="workbench")
    ap.add_argument("--aa", default="8", help="workbench anti-aliasing samples (OFF/FXAA/5/8/11/16/32)")
    ap.add_argument("--frames", default=None, help="render only motion frames A:B (0-based, B exclusive)")
    ap.add_argument("--summary", type=Path, default=None, help="write a JSON summary of the plan here")
    return ap.parse_args(argv)


# ---------------------------------------------------------------- materials / primitives

def material(name: str, rgba: tuple) -> bpy.types.Material:
    """Workbench uses ``diffuse_color``; EEVEE/Cycles use the node tree. ``hud_*`` materials are
    emissive (unlit) in EEVEE so overlay text keeps its exact colour."""
    m = bpy.data.materials.new(name)
    m.diffuse_color = rgba                         # Workbench (color_type=MATERIAL)
    m.use_nodes = True                             # EEVEE / Cycles
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.55
    if name.startswith("hud_"):
        bsdf.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        bsdf.inputs["Specular IOR Level"].default_value = 0.0
        bsdf.inputs["Emission Color"].default_value = rgba
        bsdf.inputs["Emission Strength"].default_value = 1.0
    else:
        bsdf.inputs["Base Color"].default_value = rgba
    if rgba[3] < 1.0:
        bsdf.inputs["Alpha"].default_value = rgba[3]
        m.blend_method = "BLEND"
        m.surface_render_method = "BLENDED"
    return m


def set_rgba(m: bpy.types.Material, rgba: tuple) -> None:
    m.diffuse_color = rgba
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Alpha"].default_value = rgba[3]
    bsdf.inputs["Emission Color"].default_value = rgba     # beam glows slightly in EEVEE
    bsdf.inputs["Emission Strength"].default_value = 0.3


def finish(obj, name: str, mat, parent=None):
    obj.name = name
    if mat is not None:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    if parent is not None:
        obj.parent = parent
    return obj


def box(name, size, loc, mat, parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.scale = size
    return finish(o, name, mat, parent)


def cylinder(name, radius, depth, loc, rot, mat, parent=None, verts=32):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc, rotation=rot)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    return finish(o, name, mat, parent)


def empty(name, loc=(0, 0, 0), parent=None):
    o = bpy.data.objects.new(name, None)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.parent = parent
    return o


def text(name, body, size, mat, parent, loc, align="LEFT"):
    curve = bpy.data.curves.new(name, "FONT")
    curve.body = body
    curve.size = size
    curve.align_x = align
    curve.align_y = "CENTER"
    o = bpy.data.objects.new(name, curve)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    o.location = loc
    o.visible_shadow = False
    return o


# ---------------------------------------------------------------- scene construction

def build_world(engine: str, args) -> None:
    scene = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    scene.render.resolution_x, scene.render.resolution_y = args.width, args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = args.fps
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"   # keep palette colours exact
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.color = BG                                  # Workbench background
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (*BG, 1.0)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    if engine == "workbench":
        scene.render.engine = "BLENDER_WORKBENCH"
        sh = scene.display.shading
        sh.light = "STUDIO"
        sh.studio_light = "paint.sl"   # bright, even studio light (the default one looks hazy/dim)
        sh.color_type = "MATERIAL"
        sh.show_shadows = True
        sh.shadow_intensity = 0.35
        sh.show_specular_highlight = True
        sh.show_object_outline = OUTLINE is not None
        if OUTLINE is not None:
            sh.object_outline_color = OUTLINE
        scene.display.light_direction = (-0.35, -0.45, 0.82)
        scene.display.render_aa = args.aa
    else:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
        scene.eevee.taa_render_samples = 16
    # 3-point lighting (used by EEVEE/Cycles; Workbench uses its studio light + shadow direction).
    for name, kind, energy, loc in (("Key", "AREA", 250, (-2.0, -4.0, 5.0)),
                                    ("Fill", "AREA", 80, (6.0, -3.0, 3.0)),
                                    ("Rim", "AREA", 150, (4.0, 6.0, 4.0))):
        ld = bpy.data.lights.new(name, kind)
        ld.energy, ld.size = energy, 3.0
        lo = bpy.data.objects.new(name, ld)
        scene.collection.objects.link(lo)
        lo.location = loc
        lo.rotation_euler = (Vector((2.0, 1.0, 0.0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def build_ground(center: tuple[float, float], half: float) -> None:
    cx, cy = center
    bpy.ops.mesh.primitive_plane_add(size=2 * half, location=(cx, cy, 0.0))
    finish(bpy.context.active_object, "Ground", material("ground", GROUND))
    # 1 m grid lines so the motion reads clearly (thin quads just above the ground).
    verts, faces, w, z = [], [], 0.012, 0.001
    lo_x, hi_x, lo_y, hi_y = cx - half, cx + half, cy - half, cy + half
    for k in range(math.ceil(lo_x), math.floor(hi_x) + 1):
        i = len(verts)
        verts += [(k - w, lo_y, z), (k + w, lo_y, z), (k + w, hi_y, z), (k - w, hi_y, z)]
        faces.append((i, i + 1, i + 2, i + 3))
    for k in range(math.ceil(lo_y), math.floor(hi_y) + 1):
        i = len(verts)
        verts += [(lo_x, k - w, z), (hi_x, k - w, z), (hi_x, k + w, z), (lo_x, k + w, z)]
        faces.append((i, i + 1, i + 2, i + 3))
    mesh = bpy.data.meshes.new("Grid")
    mesh.from_pydata(verts, [], faces)
    o = bpy.data.objects.new("Grid", mesh)
    bpy.context.scene.collection.objects.link(o)
    mesh.materials.append(material("grid", GRID))


def build_robot(geom: K.RobotGeometry):
    root = empty("Robot")
    body_z = geom.ground_clearance + geom.chassis_height / 2
    box("Chassis", (geom.chassis_length, geom.chassis_width, geom.chassis_height), (0, 0, body_z),
        material("chassis", CHASSIS), root)
    top = geom.ground_clearance + geom.chassis_height
    box("Lid", (geom.chassis_length * 0.7, geom.chassis_width * 0.8, 0.03),
        (-0.04, 0, top + 0.015), material("lid", LID), root)
    # sensor housing + two ultrasonic "eyes" on the front face
    sx = geom.chassis_length / 2
    box("SensorHousing", (0.04, 0.22, 0.09), (sx + 0.0, 0, body_z + 0.03), material("sensor", SENSOR), root)
    eye = material("eye", EYE)
    for side, dy in (("L", 0.055), ("R", -0.055)):
        cylinder(f"Eye{side}", 0.035, 0.04, (geom.sensor_offset - 0.005, dy, body_z + 0.03),
                 (0, math.pi / 2, 0), eye, root, verts=24)
    # drive wheels: hub empties with the spin applied to a child cylinder
    wheels = {}
    wheel_mat, hub_mat = material("wheel", WHEEL), material("hub", HUB)
    for side, sgn in (("left", 1), ("right", -1)):
        hub = empty(f"Axle_{side}", (geom.wheel_offset_x, sgn * geom.track / 2, geom.wheel_radius), root)
        w = cylinder(f"Wheel_{side}", geom.wheel_radius, geom.wheel_width, (0, 0, 0), (0, 0, 0), wheel_mat, hub)
        w.rotation_mode = "ZXY"           # local spin (Z) first, then tilt the axle to lateral (X)
        w.rotation_euler = (math.pi / 2, 0, 0)
        # contrasting spoke so the spin is visible, on the outer face (local +Z maps to world -y)
        box(f"Spoke_{side}", (geom.wheel_radius * 1.7, 0.035, 0.008),
            (0, 0, -sgn * (geom.wheel_width / 2 + 0.004)), hub_mat, w)
        wheels[side] = w
    # front caster
    bpy.ops.mesh.primitive_uv_sphere_add(radius=geom.ground_clearance / 2, location=(0.2, 0, geom.ground_clearance / 2),
                                         segments=16, ring_count=8)
    finish(bpy.context.active_object, "Caster", wheel_mat, root)
    # sensor beam: cone with its tip at the sensor, pointing +x, unit length (scaled to the reading)
    beam_mat = material("beam", BEAM_CLEAR)
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=math.tan(BEAM_HALF_ANGLE), radius2=0.0, depth=1.0,
                                    location=(0, 0, 0), rotation=(0, -math.pi / 2, 0))
    cone = bpy.context.active_object
    # move the origin to the tip so scaling x stretches the beam away from the sensor
    cone.location = (0.5, 0, 0)
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=False)
    beam_pivot = empty("BeamPivot", (geom.sensor_offset + 0.02, 0, body_z + 0.03), root)
    finish(cone, "Beam", beam_mat, beam_pivot)
    cone.visible_shadow = False
    return root, wheels, beam_pivot, beam_mat


def build_obstacle(kind: str, box2d: K.Box2D):
    mat = material("obstacle", OBSTACLE)
    h = 2 * box2d.half_x
    if kind == "cylinder":   # inscribed in the bounding box used by sensing/collision (conservative)
        return cylinder("Obstacle", min(box2d.half_x, box2d.half_y), h, (box2d.cx, box2d.cy, h / 2), (0, 0, 0), mat)
    return box("Obstacle", (2 * box2d.half_x, 2 * box2d.half_y, h), (box2d.cx, box2d.cy, h / 2), mat)


def place_camera(plan, scene) -> bpy.types.Object:
    """3/4 view from the front-left, pulled back until robot path + obstacle fit the safe region."""
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 32.0
    cam_data.sensor_fit = "HORIZONTAL"
    cam_data.clip_start = 0.05
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    xmin, xmax, ymin, ymax = K.scene_bounds(plan.path, plan.geom, plan.cfg.obstacle)
    target = Vector(((xmin + xmax) / 2, (ymin + ymax) / 2, 0.15))
    direction = Vector((-0.30, -1.0, 0.78)).normalized()
    top = plan.geom.ground_clearance + plan.geom.chassis_height + 0.05
    key_pts = [Vector((x, y, z)) for x, y in K.Box2D((xmin + xmax) / 2, (ymin + ymax) / 2,
                                                       (xmax - xmin) / 2, (ymax - ymin) / 2).corners()
               for z in (0.0, max(top, 2 * plan.cfg.obstacle.half_x))]
    beam_z = plan.geom.ground_clearance + plan.geom.chassis_height / 2 + 0.03
    for p in plan.path.poses[::5] + [plan.path.poses[-1]]:
        key_pts += [Vector((x, y, z)) for x, y in K.footprint_corners(p.x, p.y, p.heading, plan.geom)
                    for z in (0.0, top)]
        # the beam's far end (its visible length is the reading, or the full range when clear)
        reach = p.reading if p.reading is not None else plan.cfg.sensor_range
        ox, oy = K.sensor_origin(p.x, p.y, p.heading, plan.geom)
        tx, ty, rad = ox + reach * math.cos(p.heading), oy + reach * math.sin(p.heading), reach * math.tan(BEAM_HALF_ANGLE)
        key_pts += [Vector((tx - rad * math.sin(p.heading) * k, ty + rad * math.cos(p.heading) * k, beam_z + rad * j))
                    for k in (-1, 1) for j in (-1, 1)]

    def project(dist: float) -> list:
        cam.location = target + direction * dist
        cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
        bpy.context.view_layer.update()
        return [world_to_camera_view(scene, cam, v) for v in key_pts]

    def fits(cs) -> bool:
        return all(SAFE_X[0] <= c.x <= SAFE_X[1] and SAFE_Y[0] <= c.y <= SAFE_Y[1] and c.z > 0 for c in cs)

    # pull back until everything fits; at each distance centre the content vertically in the
    # safe band with a lens shift (keeps the 3/4 angle, frees room for the HUD bands)
    aspect = scene.render.resolution_y / scene.render.resolution_x
    for step in range(300):
        dist = 2.0 + 0.05 * step
        cam_data.shift_y = 0.0
        for _ in range(3):
            cs = project(dist)
            mid = (min(c.y for c in cs) + max(c.y for c in cs)) / 2
            cam_data.shift_y += (mid - sum(SAFE_Y) / 2) * aspect
        if fits(project(dist)):
            return cam
    raise RuntimeError("camera framing failed: robot path and obstacle do not fit the safe frame region")


def build_hud(cam, title: str, scene) -> dict:
    """Camera-parented overlay: title (top-left), sensor readout (top-right), step chips (bottom)."""
    aspect = scene.render.resolution_y / scene.render.resolution_x
    half_w = HUD_DIST * (cam.data.sensor_width / 2) / cam.data.lens
    half_h = half_w * aspect
    sy = cam.data.shift_y * 2 * half_w           # lens shift moves the frame centre (in HUD units)
    px = 2 * half_w / 1920.0                      # one 1080p pixel in HUD units (layout is resolution-independent)
    hud = empty("HUD", (0, 0, 0), cam)
    z = -HUD_DIST
    m_dark, m_dim, m_act, m_go = (material("hud_dark", TEXT_DARK), material("hud_dim", TEXT_DIM),
                                  material("hud_active", TEXT_ACTIVE), material("hud_go", TEXT_GO))
    margin = 56 * px
    text("Title", title, 64 * px, m_dark, hud, (-half_w + margin, sy + half_h - margin - 22 * px, z))
    readout = text("Readout", "", 44 * px, m_dark, hud, (half_w - margin, sy + half_h - margin - 18 * px, z), "RIGHT")
    rule = text("Rule", "", 34 * px, material("hud_mid", TEXT_MID), hud,
                (half_w - margin, sy + half_h - margin - 74 * px, z), "RIGHT")
    # bottom panel with the step chips "Drive → Obstacle detected → Stop → Turn → Resume"
    bar_h = 120 * px
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    panel = finish(bpy.context.active_object, "HudPanel", material("hud_panel", PANEL), hud)
    panel.scale = (2 * half_w, bar_h, 1)
    panel.location = (0, sy - half_h + bar_h / 2, z - 0.001)
    panel.visible_shadow = False
    chip_size = 46 * px
    labels = []
    for i, (label, _) in enumerate(STEPS):
        labels.append(label)
        if i < len(STEPS) - 1:
            labels.append("→")
    y = sy - half_h + bar_h / 2
    objs = [text(f"Chip_{i}", s, chip_size, m_dim, hud, (0, y, z), "LEFT") for i, s in enumerate(labels)]
    bpy.context.view_layer.update()
    gap = 22 * px
    widths = [o.dimensions.x for o in objs]
    x = -(sum(widths) + gap * (len(objs) - 1)) / 2
    if x < -half_w + margin / 2:
        raise RuntimeError("HUD step chips do not fit the frame width")
    for o, w in zip(objs, widths):
        o.location.x = x
        x += w + gap
    chips = [o for o, s in zip(objs, labels) if s != "→"]
    return {"readout": readout, "rule": rule, "chips": chips, "mats": (m_dark, m_dim, m_act, m_go)}


# ---------------------------------------------------------------- per-frame state

def apply_pose(p: K.Pose, plan, robot, wheels, beam_pivot, beam_mat, hud) -> None:
    robot.location = (p.x, p.y, 0.0)
    robot.rotation_euler = (0.0, 0.0, p.heading)
    # Rolling forward (+x) is a positive rotation about +y. The wheel cylinder is tilted by
    # Rx(90 deg), so its local Z (the axle) points along -y: forward spin is negative about local Z.
    wheels["left"].rotation_euler = Euler((math.pi / 2, 0.0, -p.wheel_left), "ZXY")
    wheels["right"].rotation_euler = Euler((math.pi / 2, 0.0, -p.wheel_right), "ZXY")
    reach = p.reading if p.reading is not None else plan.cfg.sensor_range
    beam_pivot.scale = (max(reach, 0.02), max(reach, 0.02), max(reach, 0.02))
    colour = BEAM_ALERT if p.alert else (BEAM_SEEN if p.reading is not None else BEAM_CLEAR)
    set_rgba(beam_mat, colour)
    m_dark, m_dim, m_act, m_go = hud["mats"]
    if p.reading is None:
        hud["readout"].data.body = "Sensor: path clear"
        hud["readout"].data.materials[0] = m_go
    else:
        hud["readout"].data.body = f"Sensor: {format_reading_m(p.reading)}"
        hud["readout"].data.materials[0] = m_act if p.alert else m_dark
    hud["rule"].data.body = f"rule: stop & turn if distance < {format_threshold_m(plan.cfg.stop_threshold)}"
    for chip, (_, phases) in zip(hud["chips"], STEPS):
        active = p.phase in phases
        chip.data.materials[0] = (m_go if p.phase in GO_PHASES else m_act) if active else m_dim


# ---------------------------------------------------------------- main

def main() -> int:
    args = parse_args()
    job = json.loads(args.params.read_text(encoding="utf-8"))
    if job.get("template") != "mobile_robot_avoidance":
        raise SystemExit(f"wrong template for this script: {job.get('template')!r}")
    if job.get("style") == "cartoon":
        apply_cartoon_style()
    params = job.get("params", {})
    errors = get_template("blender", "mobile_robot_avoidance").validate_params(params)
    if errors:
        raise SystemExit("invalid parameters: " + "; ".join(errors))

    plan = plan_mobile_robot_avoidance(params, float(job["durationSeconds"]), args.fps,
                                       job.get(JOB_STOP_THRESHOLD_KEY))  # raises on collision
    n = plan.path.motion_frames
    first, last = 0, n
    if args.frames:
        a, b = args.frames.split(":")
        last = min(n, int(b))
        first = min(max(0, int(a)), last)

    scene = bpy.context.scene
    build_world(args.engine, args)
    xmin, xmax, ymin, ymax = K.scene_bounds(plan.path, plan.geom, plan.cfg.obstacle)
    build_ground(((xmin + xmax) / 2, (ymin + ymax) / 2), 16.0)
    robot, wheels, beam_pivot, beam_mat = build_robot(plan.geom)
    build_obstacle(params["obstacle"], plan.cfg.obstacle)
    cam = place_camera(plan, scene)
    hud = build_hud(cam, job.get("title") or "Obstacle avoidance", scene)

    summary = {
        "template": "mobile_robot_avoidance", "engine": scene.render.engine, "fps": args.fps,
        "resolution": [args.width, args.height], "motion_frames": n, "target_frames": plan.target_frames,
        "hold_frames": plan.hold_frames, "time_scale": plan.path.time_scale, "stop_frame": plan.path.stop_frame,
        "stop_reading_m": round(plan.path.stop_reading, 4), "stop_threshold_m": plan.cfg.stop_threshold,
        "phase_frames": plan.path.phase_frames, "collision_checked": plan.collision_checked,
        "camera": {"location": list(cam.location), "shift_y": cam.data.shift_y},
        "rendered_frames": [first, last],
    }
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PLAN", json.dumps(summary), flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    for i in range(first, last):
        apply_pose(plan.path.poses[i], plan, robot, wheels, beam_pivot, beam_mat, hud)
        scene.frame_set(i + 1)
        scene.render.filepath = str(args.out / f"{i:05d}.png")
        bpy.ops.render.render(write_still=True)
        if (i - first) % 60 == 0:
            print(f"frame {i}/{n} ({time.monotonic() - t0:.1f}s)", flush=True)
    print(f"RENDERED {last - first} frames in {time.monotonic() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit:
        raise
    except Exception as e:  # make failures (incl. CollisionError) visible and non-zero
        import traceback
        traceback.print_exc()
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        sys.exit(1)
    sys.exit(rc)
