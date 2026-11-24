"""Frame layout rules shared by staging, shots, subtitles and QA (M05.1/M05.2).

* frame: 14.22 x 8 world units centred on 0 (1080p: 135 px per unit), normalised boxes are [x0, y0, x1, y1] with
  y measured DOWN from the top (0..1).
* **caption band** (M05.2): the bottom ``CAPTION_BAND`` of the frame belongs to the burned-in subtitles. Characters,
  teaching visuals and readouts stay above it (world y >= ``BAND_TOP_Y``); subtitles always sit inside it.
* **shots** (M05.1): ``stage`` (world staging), ``illustration`` (full-bleed teaching visual; no character or one
  small corner character) and ``solo`` (exactly one character + a wide visual).
"""

from __future__ import annotations

FRAME_X, FRAME_Y = 14.222222 / 2, 4.0
FRAME_W, FRAME_H = 2 * FRAME_X, 2 * FRAME_Y
CAPTION_BAND = 0.18                                   # bottom 18% of the frame (194 px at 1080p)
BAND_TOP_Y = FRAME_Y - (1 - CAPTION_BAND) * FRAME_H   # -2.56 world units
CONTENT_FLOOR_Y = BAND_TOP_Y + 0.12                   # feet / lowest content line for overlays (shots)
BAND_OVERLAP_TOL = 0.004                              # normalised slack (~4 px) for anti-aliased edges

# M05.1 shot rules (QA)
ILLUSTRATION_MIN_AREA = 0.55        # illustration visual covers >= 55% of the frame
SOLO_MIN_AREA = 0.35                # solo shot's wide visual >= 35% of the frame
MAX_CHARACTERS = {"illustration": 1, "solo": 1}
MIN_CHARACTERS = {"illustration": 0, "solo": 1}
CORNER_MAX_AREA = 0.10              # an illustration's corner character box <= 10% of the frame


def norm_box(x0: float, y0: float, x1: float, y1: float) -> list[float]:
    """World corners (any order) -> normalised frame box [x0, y0, x1, y1] (y down)."""
    xa, xb = sorted((float(x0), float(x1)))
    ya, yb = sorted((float(y0), float(y1)))
    return [round((xa + FRAME_X) / FRAME_W, 4), round((FRAME_Y - yb) / FRAME_H, 4),
            round((xb + FRAME_X) / FRAME_W, 4), round((FRAME_Y - ya) / FRAME_H, 4)]


def box_area(b: list[float]) -> float:
    return max(0.0, min(b[2], 1) - max(b[0], 0)) * max(0.0, min(b[3], 1) - max(b[1], 0))


def band_overlap(b: list[float], band: float = CAPTION_BAND) -> float:
    """How far (normalised height) a box reaches into the caption band (0 = clear)."""
    if b[2] <= 0 or b[0] >= 1:
        return 0.0
    return max(0.0, min(b[3], 1.0) - (1 - band))
