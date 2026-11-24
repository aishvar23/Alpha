"""M03.5 / M05.2: burned-in kid subtitles — bundled OFL font, compact caption box in the reserved bottom caption band,
1 line preferred (≤ 2), safe area, speaker colours, coverage of every dialogue line, the ffmpeg/libass burn and the
QA checks."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from robotics101.cartoon import subtitles as S
from robotics101.characters import load_registry

ROOT = Path(__file__).resolve().parents[1]
needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg required")


def _timing(lines, start=10.0):
    beats = [{"type": "line", "index": i, "speaker": sp, "text": tx, "start_s": a, "end_s": b, "wav": "x.wav"}
             for i, (sp, tx, a, b) in enumerate(lines)]
    return {"scenes": [{"sceneId": "scene-001", "scene_start_s": start, "scene_duration_s": 30.0, "beats": beats}]}


LONG = ("Boxes don't beep, silly. Robots have to notice things by themselves. Today, you're going to learn how "
        "robots measure distance with a sensor, decide with a rule, and then act with their motors, step by step!")


def test_font_is_bundled_with_its_ofl_licence_and_listed():
    assert S.FONT_FILE.is_file() and S.FONT_LICENSE.is_file()
    lic = S.FONT_LICENSE.read_text(encoding="utf-8")
    assert "SIL Open Font License, Version 1.1" in lic and "Baloo 2 Project Authors" in lic
    fonts = json.loads((ROOT / "assets" / "LICENSES.json").read_text())["fonts"]
    entry = next(f for f in fonts if f["family"] == "Baloo 2")
    assert entry["license"] == "OFL-1.1" and "Baloo2-OFL.txt" in entry["licenseFile"]


def test_defaults_are_on_and_large():
    st = S.settings({})
    assert st["burnIn"] is True and st["fontSizePx"] >= S.MIN_EM_PX
    assert S.settings({"subtitles": {"burnIn": False}})["burnIn"] is False


def test_long_lines_become_several_cues_of_at_most_two_lines_covering_the_line():
    cues = S.build_cues(_timing([("maya", LONG, 1.0, 13.0)]), load_registry())
    assert len(cues) >= 2 and all(1 <= len(c.lines) <= S.MAX_LINES for c in cues)
    assert cues[0].start == pytest.approx(11.0) and cues[-1].end == pytest.approx(23.0)
    assert all(a.end == pytest.approx(b.start) for a, b in zip(cues, cues[1:]))
    assert " ".join(" ".join(c.lines) for c in cues).split() == LONG.split()
    for c in cues:
        for ln in c.lines:
            assert S.text_width(ln, S.DEFAULT_EM_PX) <= S.MAX_TEXT_W


def test_speaker_colours_come_from_the_registry_and_boxes_sit_in_the_safe_area():
    reg = load_registry()
    cues = S.build_cues(_timing([("bolt", "Hi, I'm Bolt!", 0.5, 1.5), ("maya", "And I'm Maya!", 2.0, 3.0)]), reg)
    assert [c.color for c in cues] == [reg.get("bolt").captionColor, reg.get("maya").captionColor]
    for c in cues:
        x0, y0, x1, y1 = c.box
        assert x0 >= S.W * S.SAFE and x1 <= S.W * (1 - S.SAFE) and y0 >= S.H * S.SAFE and y1 <= S.H * (1 - S.SAFE)
        assert c.placement == "band" and abs((x0 + x1) / 2 - S.W / 2) <= 1
        assert c.panel[1] >= S.band_top_px() and c.box[3] <= S.H * (1 - S.SAFE)          # inside the caption band


def test_cues_stay_in_the_band_even_with_keepouts():
    """M05.2: captions no longer jump above teaching visuals (the old raised/top placement); the layout engine keeps
    content out of the band instead and QA flags anything that intrudes."""
    ruler = {"box": [0.1, 0.82, 0.9, 0.92], "start": 0.0, "end": 30.0}
    cues = S.build_cues(_timing([("maya", "Look at the ruler, Bolt!", 1.0, 3.0)]), load_registry(),
                        {"scene-001": [ruler]})
    assert cues[0].placement == "band" and cues[0].panel[1] >= S.band_top_px()


def test_one_line_cues_are_preferred_two_lines_only_when_one_line_would_flash():
    two_sent = "The sound bounces off things and comes back. The faster the echo, the closer it is."
    slow = S.build_cues(_timing([("maya", two_sent, 1.0, 7.0)]), load_registry())
    assert len(slow) == 2 and all(len(c.lines) == 1 for c in slow)
    assert all(c.end - c.start >= S.MIN_CUE_S for c in slow)
    fast = S.build_cues(_timing([("maya", LONG, 1.0, 4.0)]), load_registry())        # one-line chunks would flash
    assert any(len(c.lines) == 2 for c in fast) and all(len(c.lines) <= S.MAX_LINES for c in fast)
    two = S.place(["a line", "another line"], S.DEFAULT_EM_PX)[0]
    assert two[1] - S.PANEL_PAD_Y >= S.band_top_px()                                   # two lines fit the band


def test_ass_document_uses_the_font_colours_and_positions(tmp_path):
    reg = load_registry()
    doc = S.write_subtitles(tmp_path, _timing([("bolt", "Hi, I'm Bolt!", 0.5, 1.5)]), reg, {})
    ass = (tmp_path / "subtitles.ass").read_text()
    assert "Style: Kid,Baloo 2," in ass and "PlayResX: 1920" in ass
    col = reg.get("bolt").captionColor.lstrip("#").upper()
    assert f"\\c&H{col[4:6]}{col[2:4]}{col[0:2]}&" in ass and "0:00:10.50" in ass
    assert doc["burnIn"] is True and doc["cues"][0]["speaker"] == "bolt"


@needs_ffmpeg
def test_libass_burns_the_text_inside_the_predicted_box(tmp_path):
    doc = S.write_subtitles(tmp_path, _timing([("maya", "Robots sense, think and act!", 0.0, 2.0)], start=0.0),
                            load_registry(), {})
    out = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x223344:s=1920x1080:d=1",
                    "-vf", S.burn_filter(tmp_path), "-ss", "0.5", "-frames:v", "1", "-update", "1", str(out)],
                   check=True)
    from PIL import Image
    img = np.asarray(Image.open(out).convert("RGB")).astype(int)
    ink = np.abs(img - [0x22, 0x33, 0x44]).sum(axis=2) > 60
    ys, xs = np.nonzero(ink)
    x0, y0, x1, y1 = doc["cues"][0]["box"]
    assert xs.min() >= x0 - 4 and xs.max() <= x1 + 4 and ys.min() >= y0 - 4 and ys.max() <= y1 + 4
    assert (xs.max() - xs.min()) > 0.6 * (x1 - x0)                    # the box is tight, not a loose guess
    assert (ys.max() - ys.min()) > 0.6 * (y1 - y0)
    maya = np.array([0xFF, 0xD2, 0x3F])
    assert (np.abs(img - maya).sum(axis=2) < 90).sum() > 2000          # speaker-coloured text pixels


def test_qa_flags_uncovered_lines_and_unsafe_boxes(tmp_path):
    from robotics101.cartoon.qa import check_subtitles
    from robotics101.qa import QaReport
    timing = _timing([("bolt", "Hi, I'm Bolt!", 0.5, 1.5), ("maya", "And I'm Maya!", 2.0, 3.0)])
    S.write_subtitles(tmp_path, timing, load_registry(), {})
    (tmp_path / "compose.json").write_text(json.dumps({"subtitles": {"burnedIn": True, "cues": 2}}))
    rep = QaReport(None, "preview", str(tmp_path))
    check_subtitles(rep, tmp_path, {}, timing, None)
    assert {c.id: c.status for c in rep.checks} == {"subtitles.burned": "pass", "subtitles.coverage": "pass",
                                                    "subtitles.layout": "pass", "subtitles.compact": "pass"}
    doc = json.loads((tmp_path / "subtitles.json").read_text())
    doc["cues"] = doc["cues"][:1]
    doc["cues"][0]["box"][3] = 1075
    (tmp_path / "subtitles.json").write_text(json.dumps(doc))
    rep = QaReport(None, "preview", str(tmp_path))
    check_subtitles(rep, tmp_path, {}, timing, None)
    st = {c.id: c for c in rep.checks}
    assert st["subtitles.coverage"].status == "fail" and "scene-001#1" in st["subtitles.coverage"].message
    assert st["subtitles.layout"].status == "fail"
    rep = QaReport(None, "preview", str(tmp_path))
    check_subtitles(rep, tmp_path, {"subtitles": {"burnIn": False}}, timing, None)
    assert [c.status for c in rep.checks] == ["warn"]


@needs_ffmpeg
def test_every_cue_has_a_compact_see_through_caption_box(tmp_path):
    """M05.2: a compact rounded caption box (dark, ≈ 58 % opaque: lower contrast than the M03.6 81 % panel) behind
    every cue, hugging the text, two-line cues drawn one event per line at a tight pitch."""
    timing = _timing([("maya", "Robots sense, think and act!", 0.0, 2.0)], start=0.0)
    doc = S.write_subtitles(tmp_path, timing, load_registry(), {})
    c = doc["cues"][0]
    assert c["placement"] == "band" and c["panel"] and doc["captionBand"][1] == S.band_top_px()
    px0, py0, px1, py1 = c["panel"]
    assert px0 < c["box"][0] and px1 > c["box"][2] and py0 < c["box"][1] and py1 > c["box"][3]
    assert py1 - py0 <= 90                                       # compact: one line ≈ 70 px tall at 1080p
    ass = (tmp_path / "subtitles.ass").read_text()
    assert ass.count("\\p1") == 1 and "Dialogue: 1," in ass
    yellow = "0xFFD23F"                                          # Maya's caption colour as the background
    out = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c={yellow}:s=1920x1080:d=1",
                    "-vf", S.burn_filter(tmp_path), "-ss", "0.5", "-frames:v", "1", "-update", "1", str(out)],
                   check=True)
    from PIL import Image
    img = np.asarray(Image.open(out).convert("RGB")).astype(int)
    inner = img[py0 + 3:py1 - 3, px0 + 8:px0 + 18]               # caption box margin, left of the text
    lum = inner.sum(axis=2).mean()                               # yellow background sums to 528
    assert 180 < lum < 400                                       # darker than the art, but see-through
    maya = np.array([0xFF, 0xD2, 0x3F])
    box = img[py0:py1, px0:px1]
    assert (np.abs(box - maya).sum(axis=2) < 90).sum() > 1500    # the yellow text is still there, on the box
    assert (np.abs(img[: py0 - 10] - maya).sum(axis=2) < 30).mean() > 0.99   # above the band: untouched
    two = S.write_subtitles(tmp_path, _timing([("maya", LONG, 0.0, 3.0)], start=0.0), load_registry(), {})
    c2 = next(c for c in two["cues"] if len(c["lines"]) == 2)
    ass = (tmp_path / "subtitles.ass").read_text()
    assert sum(1 for ln in ass.splitlines() if ln.startswith("Dialogue: 1,")) == sum(len(c["lines"]) for c in two["cues"])
    assert c2["panel"][1] >= S.band_top_px()


def test_qa_requires_caption_box_inside_the_band(tmp_path):
    from robotics101.cartoon.qa import check_subtitles
    from robotics101.qa import QaReport
    timing = _timing([("maya", "Look at the ruler, Bolt!", 1.0, 3.0)])
    S.write_subtitles(tmp_path, timing, load_registry(), {})
    (tmp_path / "compose.json").write_text(json.dumps({"subtitles": {"burnedIn": True, "cues": 1}}))
    rep = QaReport(None, "preview", str(tmp_path))
    check_subtitles(rep, tmp_path, {}, timing, None)
    st = {c.id: c for c in rep.checks}
    assert st["subtitles.layout"].status == "pass" and st["subtitles.compact"].status == "pass"
    good = json.loads((tmp_path / "subtitles.json").read_text())
    for patch, needle in (({"panel": None}, "without caption box: ['scene-001#0']"),
                          ({"placement": "raised"}, "outside the caption band"),
                          ({"box": [700, 600, 1200, 660], "panel": [680, 590, 1220, 670]}, "outside the caption band")):
        doc = json.loads(json.dumps(good))
        doc["cues"][0].update(patch)
        (tmp_path / "subtitles.json").write_text(json.dumps(doc))
        rep = QaReport(None, "preview", str(tmp_path))
        check_subtitles(rep, tmp_path, {}, timing, None)
        lay = {c.id: c for c in rep.checks}["subtitles.layout"]
        assert lay.status == "fail" and needle in lay.message
