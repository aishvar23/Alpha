"""M02.3: character rigs + model sheets (pose contract, registry consistency, golden images)."""

import os
from pathlib import Path

import numpy as np
import pytest

manim = pytest.importorskip("manim")

from robotics101.cartoon import rigs  # noqa: E402
from robotics101.cartoon.model_sheet import SHEETS, render_png, sheet  # noqa: E402
from robotics101.cartoon.rigs import MOUTH_SHAPES, RIG_VERSION, Pose, build  # noqa: E402
from robotics101.characters import load_registry  # noqa: E402

GOLDEN = Path(__file__).parent / "golden"
GOLDEN_SIZE = (960, 540)
MAX_CHANGED_PX = 60          # renders are bit-identical run to run; allow a little cairo/AA drift only
UPDATE = os.environ.get("ROBOTICS101_UPDATE_GOLDEN") == "1"
TABLES = {"bolt": rigs.BOLT_EXPR, "maya": rigs.MAYA_EXPR, "nib": rigs.NIB_EYES}


def test_rig_version_and_expression_tables_match_registry():
    reg = load_registry()
    assert reg.rig_version == RIG_VERSION
    for cid, table in TABLES.items():
        assert set(table) == set(reg.get(cid).expressions), cid


@pytest.mark.parametrize("cid", ["bolt", "maya", "nib"])
def test_every_expression_and_mouth_builds(cid):
    for e in load_registry().get(cid).expressions:
        for m in MOUTH_SHAPES:
            g = build(cid, Pose(expression=e, mouth=m))
            assert len(g.family_members_with_points()) > 10
    with pytest.raises(ValueError):
        build(cid, Pose(expression="furious"))


@pytest.mark.parametrize("cid", ["bolt", "maya", "nib"])
@pytest.mark.parametrize("pose", [Pose(), Pose(squash=0.8), Pose(squash=1.2), Pose(facing=-1), Pose(arm_l=170, arm_r=0)])
def test_feet_on_ground_and_centred(cid, pose):
    pose = pose.with_(expression=load_registry().get(cid).expressions[0])
    g = build(cid, pose)
    body = g.parts["body" if cid != "maya" else "torso"]
    assert abs(body.get_bottom()[1] - (0.65 if cid == "bolt" else 1.1 if cid == "maya" else 0.175) * pose.squash) < 0.06
    feet = g.parts["tread" if cid == "bolt" else "shoes" if cid == "maya" else "feet"]
    assert abs(feet.get_bottom()[1]) < 0.02                      # ground contact stays at y=0
    assert abs(feet.get_center()[0]) < 0.08                      # and does not slide sideways


def test_squash_is_area_preserving_and_facing_mirrors():
    a, b = build("bolt", Pose()).parts["body"], build("bolt", Pose(squash=0.8)).parts["body"]
    assert a.width * a.height == pytest.approx(b.width * b.height, rel=1e-3)
    assert b.height < a.height and b.width > a.width
    r, l = build("bolt", Pose(arm_r=160)), build("bolt", Pose(arm_r=160, facing=-1))
    assert r.parts["hands"][1].get_center()[0] == pytest.approx(-l.parts["hands"][1].get_center()[0], abs=1e-6)


def test_blink_gaze_and_mouth_change_geometry():
    open_, shut = build("maya", Pose(expression="happy")), build("maya", Pose(expression="happy", blink=1.0))
    assert shut.parts["eyes"].height < open_.parts["eyes"].height * 0.6
    l, r = build("maya", Pose(gaze=(-1, 0))), build("maya", Pose(gaze=(1, 0)))
    assert r.parts["eyes"][0][1].get_center()[0] > l.parts["eyes"][0][1].get_center()[0]
    heights = {m: build("bolt", Pose(mouth=m)).parts["mouth"].height for m in "ABCD"}
    assert heights["A"] < heights["B"] < heights["C"] < heights["D"]
    beak = {m: build("nib", Pose(mouth=m)).parts["beak"].height for m in "XD"}
    assert beak["D"] > beak["X"]


def test_deterministic_geometry():
    a, b = build("bolt", Pose(expression="dizzy", squash=0.9, lean=0.1)), build("bolt", Pose(expression="dizzy",
                                                                                            squash=0.9, lean=0.1))
    pa = np.concatenate([m.points for m in a.family_members_with_points()])
    pb = np.concatenate([m.points for m in b.family_members_with_points()])
    assert np.array_equal(pa, pb)


def _load(p: Path) -> np.ndarray:
    from PIL import Image
    return np.asarray(Image.open(p).convert("RGB"), dtype=np.int16)


@pytest.mark.parametrize("name", SHEETS)
def test_model_sheet_matches_golden(name, tmp_path):
    out = render_png(sheet(name), tmp_path / f"{name}.png", *GOLDEN_SIZE)
    golden = GOLDEN / f"model-sheet-{name}-{GOLDEN_SIZE[0]}.png"
    if UPDATE or not golden.exists():
        if not UPDATE:
            pytest.fail(f"missing golden {golden}; run with ROBOTICS101_UPDATE_GOLDEN=1 and review the PNGs")
        golden.write_bytes(out.read_bytes())
    a, b = _load(out), _load(golden)
    assert a.shape == b.shape
    diff = np.abs(a - b)
    changed = int((diff.max(axis=2) > 48).sum())
    assert changed <= MAX_CHANGED_PX and diff.mean() < 0.05, \
        f"{name}: {changed} px changed (mean {diff.mean():.3f}) — rig changed? review the sheet, then re-bless"
