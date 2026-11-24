"""Burned-in kid subtitles (M03.5, re-laid out in M05.2): rounded Baloo 2 Bold in the speaker colour from the
character registry, on a compact, softly transparent dark caption box, always inside the reserved **caption band**
at the bottom of the frame (``layout.CAPTION_BAND``; the layout engine keeps characters, teaching visuals and
readouts out of it), inside the 5 % action-safe area.

Cues come from the dialogue lines in timing.json. One line per cue is preferred: a long line is split into
one-line chunks (sentence, clause, then word boundaries, timed by character share) as long as every chunk stays on
screen ≥ ``MIN_CUE_S``; otherwise chunks of ≤ 2 lines are used. Wrapping is measured with the bundled font (PIL).
Each text line is its own ASS event placed at an explicit position (tight line pitch), and the cue box recorded for
QA is the real ink box (cap top .. descender + outline), so the band holds two lines. The result is written as
``subtitles.ass`` (burned by ffmpeg/libass at compose) plus ``subtitles.json`` (cue boxes for QA). captions.srt is
still exported unchanged."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FONT_DIR = ROOT / "assets" / "fonts"
FONT_FILE = FONT_DIR / "Baloo2-VariableFont_wght.ttf"
FONT_NAME = "Baloo 2"
FONT_LICENSE = FONT_DIR / "Baloo2-OFL.txt"
W, H = 1920, 1080
SAFE = 0.05                                  # action-safe margin (fraction of each dimension)
DEFAULT_EM_PX = 52                           # em size at 1080p (≈ 36 px capital height; M03.5 used 58)
MIN_EM_PX = 48                               # legibility floor (QA)
MAX_LINES = 2
PREFERRED_LINES = 1
MIN_CUE_S = 1.2                              # a one-line chunk must stay on screen at least this long
MAX_TEXT_W = round(W * 0.78)                 # wrap width (inside title-safe)
OUTLINE_PX, SHADOW_PX = 3, 0                 # thin outline: the caption box carries the contrast
LINE_PITCH = 1.2                             # baseline-to-baseline distance in em
BOTTOM_MARGIN = 62                           # px from the bottom edge to the lowest ink (≥ 5 % = 54)
# M05.2: every cue sits on a compact rounded caption box, dark but see-through (≈ 58 % opaque) — lower contrast
# than the M03.6 panel (81 %) so it reads as part of the picture, yet the speaker colour stays legible on any art.
PANEL_COLOR, PANEL_ALPHA = "#1E1633", 0x6A   # ASS alpha: 0x00 opaque … 0xFF transparent
PANEL_PAD_X, PANEL_PAD_Y, PANEL_RADIUS = 22, 9, 18
PLACEMENT = "band"
DEFAULTS = {"burnIn": True, "fontSizePx": DEFAULT_EM_PX}


def settings(spec: dict) -> dict:
    return {**DEFAULTS, **(spec.get("subtitles") or {})}


@lru_cache(maxsize=8)
def _font(em: int):
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONT_FILE), em)
    try:
        f.set_variation_by_name("Bold")
    except (OSError, ValueError):
        pass
    return f


@lru_cache(maxsize=1)
def ass_per_em() -> float:
    """libass Fontsize per em (ascender + descender over units-per-em of the bundled font)."""
    a, d = _font(1000).getmetrics()
    return (a + d) / 1000.0


def text_width(text: str, em: int) -> float:
    return float(_font(em).getlength(text))


def wrap(text: str, em: int, max_w: int = MAX_TEXT_W) -> list[str]:
    """Greedy wrap to ``max_w``; a 2-line result is re-balanced (shortest longest line, punctuation preferred)."""
    lines = _greedy(text, em, max_w)
    if len(lines) == 2:
        words = text.split()
        best = None
        for i in range(1, len(words)):
            a, b = " ".join(words[:i]), " ".join(words[i:])
            wmax = max(text_width(a, em), text_width(b, em))
            if wmax > max_w:
                continue
            score = wmax - (0.08 * max_w if a[-1] in ",.!?;:" else 0)
            if best is None or score < best[0]:
                best = (score, [a, b])
        if best:
            return best[1]
    return lines


def _greedy(text: str, em: int, max_w: int) -> list[str]:
    lines, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if cur and text_width(cand, em) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def chunks(text: str, em: int, max_lines: int = MAX_LINES) -> list[str]:
    """Split a long line into pieces that each wrap to ≤ ``max_lines`` (sentence, then clause, then word
    boundaries)."""
    text = " ".join(text.split())
    if len(wrap(text, em)) <= max_lines:
        return [text]
    for pat in (r"(?<=[.!?])\s+", r"(?<=[,;:])\s+"):
        parts = [p for p in re.split(pat, text) if p]
        if len(parts) > 1:
            out, cur = [], ""
            for p in parts:
                cand = f"{cur} {p}".strip()
                if cur and len(wrap(cand, em)) > max_lines:
                    out.append(cur)
                    cur = p
                else:
                    cur = cand
            out.append(cur)
            if all(len(wrap(x, em)) <= max_lines for x in out):
                return out
            return [y for x in out for y in chunks(x, em, max_lines)] if len(out) > 1 else \
                _word_chunks(text, em, max_lines)
    return _word_chunks(text, em, max_lines)


def _word_chunks(text: str, em: int, max_lines: int = MAX_LINES) -> list[str]:
    out, cur = [], ""
    for w in text.split():
        cand = f"{cur} {w}".strip()
        if cur and len(wrap(cand, em)) > max_lines:
            out.append(cur)
            cur = w
        else:
            cur = cand
    return out + ([cur] if cur else [])


def cue_chunks(text: str, em: int, seconds: float) -> list[str]:
    """M05.2: prefer one-line cues; fall back to ≤ 2-line chunks when a one-line split would flash (any chunk
    shorter than ``MIN_CUE_S`` at the line's reading speed)."""
    text = " ".join(text.split())
    one = chunks(text, em, PREFERRED_LINES)
    total = sum(len(p) for p in one) or 1
    if all(len(wrap(p, em)) <= PREFERRED_LINES and seconds * len(p) / total >= MIN_CUE_S for p in one) \
            or len(one) == 1:
        return one
    return chunks(text, em, MAX_LINES)


@dataclass
class Cue:
    start: float
    end: float
    speaker: str
    color: str
    lines: list[str]
    box: list[int]           # px [x0, y0, x1, y1] of the text block incl. outline
    placement: str           # band (M05.2; M03.5 had bottom | raised | top)
    sceneId: str
    lineIndex: int

    @property
    def panel(self) -> list[int] | None:
        """px box of the compact caption box behind the text."""
        x0, y0, x1, y1 = self.box
        return [x0 - PANEL_PAD_X, y0 - PANEL_PAD_Y, x1 + PANEL_PAD_X, y1 + PANEL_PAD_Y]

    def to_dict(self) -> dict:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "speaker": self.speaker,
                "color": self.color, "lines": self.lines, "box": self.box, "placement": self.placement,
                "panel": self.panel, "sceneId": self.sceneId, "lineIndex": self.lineIndex}


@lru_cache(maxsize=8)
def ink_extent(em: int) -> tuple[int, int]:
    """(top, bottom) of the ink relative to the top of a libass line box (ascender top): cap/ascender top to the
    descender bottom, measured on the bundled font."""
    b = _font(em).getbbox("ÅHdlgjpqy'!?")
    top = _font(em).getbbox("Hdl")[1]
    return int(top), int(b[3])


def pitch_px(em: int) -> int:
    return round(em * LINE_PITCH)


def block_size(lines: list[str], em: int) -> tuple[int, int]:
    """Ink box size (incl. outline) of a cue's lines."""
    top, bot = ink_extent(em)
    w = max(text_width(x, em) for x in lines) + 2 * OUTLINE_PX + SHADOW_PX
    h = (len(lines) - 1) * pitch_px(em) + (bot - top) + 2 * OUTLINE_PX + SHADOW_PX
    return round(w), round(h)


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def band_top_px() -> int:
    from robotics101.cartoon.layout import CAPTION_BAND
    return round(H * (1 - CAPTION_BAND))


def place(lines: list[str], em: int, keepouts: list[list[int]] | None = None) -> tuple[list[int], str]:
    """M05.2: always in the caption band, bottom-anchored (lowest ink ``BOTTOM_MARGIN`` above the frame edge), centred.
    Keep-outs no longer move captions: the layout engine keeps content out of the band and QA enforces it."""
    bw, bh = block_size(lines, em)
    x0 = (W - bw) // 2
    y1 = H - BOTTOM_MARGIN
    return [x0, y1 - bh, x0 + bw, y1], PLACEMENT


def line_tops(c: "Cue", em: int) -> list[int]:
    """libass ``\\an8`` y position (line-box top) of each text line of a placed cue."""
    top, _ = ink_extent(em)
    y = c.box[1] + OUTLINE_PX - top
    return [y + i * pitch_px(em) for i in range(len(c.lines))]


def _px_box(box: list[float]) -> list[int]:
    return [round(box[0] * W), round(box[1] * H), round(box[2] * W), round(box[3] * H)]


def build_cues(timing: dict, registry, keepouts: dict[str, list[dict]] | None = None,
               em: int = DEFAULT_EM_PX) -> list[Cue]:
    """``keepouts``: sceneId -> [{box: [x0,y0,x1,y1] normalised, start, end}] (scene-relative seconds)."""
    colors = {cid: (c.captionColor or "#FFFFFF") for cid, c in registry.characters.items()}
    cues = []
    for s in timing["scenes"]:
        t0 = float(s.get("scene_start_s", 0.0))
        kos = (keepouts or {}).get(s["sceneId"], [])
        for b in s["beats"]:
            if b["type"] != "line":
                continue
            parts = cue_chunks(b["text"], em, float(b["end_s"]) - float(b["start_s"]))
            total = sum(len(p) for p in parts)
            a, z, acc, prev = t0 + b["start_s"], t0 + b["end_s"], 0, t0 + b["start_s"]
            for p in parts:
                acc += len(p)
                edge = a + (z - a) * acc / total
                ko = [_px_box(k["box"]) for k in kos
                      if k["start"] < edge - t0 and prev - t0 < k["end"]]
                lines = wrap(p, em)
                box, where = place(lines, em, ko)
                cues.append(Cue(round(prev, 3), round(edge, 3), b["speaker"], colors.get(b["speaker"], "#FFFFFF"),
                                lines, box, where, s["sceneId"], int(b.get("index", 0))))
                prev = edge
    return cues


def _ass_color(hex_: str, alpha: int = 0) -> str:
    h = hex_.lstrip("#")
    return f"&H{alpha:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _ass_c(hex_: str) -> str:
    h = hex_.lstrip("#").upper()
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&"


def _ts(t: float) -> str:
    cs = max(0, round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def rounded_rect_path(w: int, h: int, r: int) -> str:
    """ASS vector drawing (\\p1) of a w×h rounded rectangle with corner radius r, origin top-left."""
    r = max(0, min(r, w // 2, h // 2))
    k = round(r * 0.448)                     # cubic control offset for a quarter circle (1 - 0.552)
    return (f"m {r} 0 l {w - r} 0 b {w - k} 0 {w} {k} {w} {r} l {w} {h - r} b {w} {h - k} {w - k} {h} {w - r} {h} "
            f"l {r} {h} b {k} {h} 0 {h - k} 0 {h - r} l 0 {r} b 0 {k} {k} 0 {r} 0")


def _esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def to_ass(cues: list[Cue], em: int = DEFAULT_EM_PX) -> str:
    size = round(em * ass_per_em())
    head = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2",
            "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV, Encoding",
            f"Style: Kid,{FONT_NAME},{size},&H00FFFFFF,&H00FFFFFF,&H00301A1A,&H64000000,-1,0,0,0,100,100,0,0,1,"
            f"{OUTLINE_PX},{SHADOW_PX},8,0,0,0,1", "",
            "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    ev = []
    for c in cues:
        x = (c.box[0] + c.box[2]) // 2
        if c.panel:
            px0, py0, px1, py1 = c.panel
            ev.append(f"Dialogue: 0,{_ts(c.start)},{_ts(c.end)},Kid,{c.speaker},0,0,0,,"
                      f"{{\\an7\\pos({px0},{py0})\\bord0\\shad0\\1c{_ass_c(PANEL_COLOR)}"
                      f"\\1a&H{PANEL_ALPHA:02X}&\\p1}}{rounded_rect_path(px1 - px0, py1 - py0, PANEL_RADIUS)}{{\\p0}}")
        for line, y in zip(c.lines, line_tops(c, em)):          # one event per line: tight, exact line pitch
            ev.append(f"Dialogue: 1,{_ts(c.start)},{_ts(c.end)},Kid,{c.speaker},0,0,0,,"
                      f"{{\\an8\\pos({x},{y})\\c{_ass_c(c.color)}}}{_esc(line)}")
    return "\n".join(head + ev) + "\n"


def write_subtitles(out_dir: Path, timing: dict, registry, spec: dict, scenes_report: dict | None = None) -> dict:
    """Write ``subtitles.ass`` + ``subtitles.json``; returns the json document."""
    st = settings(spec)
    em = int(st["fontSizePx"])
    kos = {}
    for r in (scenes_report or {}).get("scenes", []):
        kos[r["sceneId"]] = r.get("keepouts", [])
    cues = build_cues(timing, registry, kos, em)
    out_dir = Path(out_dir)
    (out_dir / "subtitles.ass").write_text(to_ass(cues, em), encoding="utf-8")
    doc = {"schemaVersion": "robotics101.subtitles/1", "burnIn": bool(st["burnIn"]), "font": FONT_NAME,
           "fontFile": str(FONT_FILE.relative_to(ROOT)), "emPx": em, "assFontSize": round(em * ass_per_em()),
           "outlinePx": OUTLINE_PX, "frame": [W, H], "safeMargin": SAFE, "maxLines": MAX_LINES,
           "preferredLines": PREFERRED_LINES, "captionBand": [0, band_top_px(), W, H],
           "cues": [c.to_dict() for c in cues]}
    (out_dir / "subtitles.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def burn_filter(out_dir: Path) -> str:
    """ffmpeg filter that burns ``<out>/subtitles.ass`` with the bundled font (scales to the output size)."""
    p = str((Path(out_dir) / "subtitles.ass").resolve()).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    f = str(FONT_DIR.resolve()).replace(":", "\\:").replace("'", "\\'")
    return f"subtitles=filename='{p}':fontsdir='{f}'"
