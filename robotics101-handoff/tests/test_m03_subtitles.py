"""M03.5: burned-in kid subtitles — bundled OFL font, ≤ 2 lines, safe area, speaker colours, keep-out aware placement,
coverage of every dialogue line, the ffmpeg/libass burn and the QA checks."""

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
        assert c.placement == "bottom" and abs((x0 + x1) / 2 - S.W / 2) <= 1


def test_cues_move_off_registered_teaching_visuals():
    ruler = {"box": [0.1, 0.82, 0.9, 0.92], "start": 0.0, "end": 30.0}
    cues = S.build_cues(_timing([("maya", "Look at the ruler, Bolt!", 1.0, 3.0)]), load_registry(),
                        {"scene-001": [ruler]})
    c = cues[0]
    assert c.placement in ("raised", "top") and c.box[3] <= 0.82 * S.H
    later = S.build_cues(_timing([("maya", "Look at the ruler, Bolt!", 1.0, 3.0)]), load_registry(),
                         {"scene-001": [{**ruler, "start": 5.0}]})
    assert later[0].placement == "bottom"                  # keep-out not on screen during the cue


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
                                                    "subtitles.layout": "pass"}
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
