"""15-second motion test (M02.4): the cold-open gag performed by the rigs with real voiced lines + lip sync.

Bolt zooms in and bonks the boxes, gets dizzy, says "Ow!"; Maya laughs and points; Bolt turns and answers;
Nib flies over, lands on the boxes and topples off. Uses scene-001 lines from a `robotics101 voice` output
dir (any backend). The backdrop is a placeholder (sets arrive in M02.5).
"""

from __future__ import annotations

import array
import json
import wave
from pathlib import Path

import numpy as np
from manim import DOWN, LEFT, RIGHT, UP, Line, Rectangle, RoundedRectangle, Text, VGroup

from robotics101.cartoon.lipsync import line_cues
from robotics101.cartoon.motion import Performer, bump, clamp01
from robotics101.cartoon.rigs import build, style

GROUND = -2.55
BOX_X, BOX_W, BOX_H = 5.3, 1.9, 1.25
DURATION = 15.0
SCALES = {"bolt": 0.78, "maya": 0.8, "nib": 0.95}


def backdrop() -> VGroup:
    ink = style("bolt").ink
    wall = Rectangle(width=16, height=9, fill_color="#FFE8C2", fill_opacity=1, stroke_width=0)
    stripes = VGroup(*[Rectangle(width=0.6, height=9, fill_color="#FFDDA8", fill_opacity=1, stroke_width=0)
                       .shift(RIGHT * x) for x in np.arange(-7.5, 8, 1.2)])
    floor = Rectangle(width=16, height=4.0 + GROUND + 0.5, fill_color="#B5838D", fill_opacity=1, stroke_width=0)
    floor.move_to(np.array([0, (-4 + GROUND + 0.5) / 2, 0]))
    floor_line = Line(LEFT * 8, RIGHT * 8, stroke_width=8, color=ink).shift(UP * (GROUND + 0.5))
    box = RoundedRectangle(width=BOX_W, height=BOX_H, corner_radius=0.08, fill_color="#E76F51", fill_opacity=1) \
        .set_stroke(ink, 6).move_to(np.array([BOX_X, GROUND + BOX_H / 2, 0]))
    tape = Rectangle(width=0.3, height=BOX_H, fill_color="#F4A261", fill_opacity=1, stroke_width=0).move_to(box)
    lbl = Text("BOXES", font="Luckiest Guy", font_size=26, color=ink).move_to(box.get_center() + DOWN * 0.15)
    return VGroup(wall, stripes, floor, floor_line, box, tape, lbl)


def _lines(voice_dir: Path) -> list[dict]:
    doc = json.loads((Path(voice_dir) / "timing.json").read_text(encoding="utf-8"))
    beats = [b for b in doc["scenes"][0]["beats"] if b["type"] == "line"]
    return beats[:3]                                     # "Ow!...", Maya "Bolt, that's not a wall...", "Tuesday?..."


def build_performance(voice_dir: Path) -> tuple[dict[str, Performer], list[tuple[float, Path]], dict]:
    lines = _lines(voice_dir)
    starts = [3.3, 4.8, 9.6]
    bolt = Performer("bolt", x=-9.5, facing=1, scale=SCALES["bolt"], expression="happy")
    maya = Performer("maya", x=-4.6, facing=1, scale=SCALES["maya"], expression="happy")
    nib = Performer("nib", x=-1.2, y=4.6, facing=1, scale=SCALES["nib"], airborne=True)
    audio, methods = [], {}
    for (b, t0) in zip(lines, starts):
        wav = Path(voice_dir) / b["wav"]
        cues, method = line_cues(wav, b["text"])
        methods[b["speaker"]] = method
        {"bolt": bolt, "maya": maya}[b["speaker"]].mouth.add_line(t0, cues)
        audio.append((t0, wav))
    # Bolt: zoom in, bonk, dizzy, "Ow!", turn to Maya, answer, hop
    bolt.move(0.0, 1.2, x=BOX_X - BOX_W / 2 - 1.55 * SCALES["bolt"], ease="out").act(0.0, 1.2, "zoom")
    bolt.feel(0.0, "happy").act(1.2, 1.9, "bonk").feel(1.2, "dizzy")
    bolt.move(1.2, 1.9, x=BOX_X - BOX_W / 2 - 1.55 * SCALES["bolt"] - 0.35, ease="out")
    bolt.act(1.9, 3.3, "dizzy").act(3.3, 4.45, "dizzy")
    bolt.feel(4.5, "worried").act(4.6, 5.2, "turn").look(5.2, (0.6, 0.2))
    bolt.feel(9.5, "surprised").act(9.6, 10.1, "flinch").feel(10.6, "worried").feel(12.0, "thinking")
    bolt.feel(13.4, "laugh").act(13.6, 14.4, "hop")
    # Maya: watch, laugh, point at the boxes, wave
    maya.look(0.6, (1.0, 0.0)).feel(1.3, "surprised").feel(2.2, "laugh").feel(4.8, "grin")
    maya.act(6.4, 8.8, "point").feel(9.4, "happy").feel(13.4, "laugh").act(13.4, 14.8, "cheer")
    # Nib: hover, fly to the box top, land, topple off
    nib.move(0.0, 3.0, x=-0.4, y=2.2, ease="in_out").act(0.0, 3.0, "hover")
    nib.move(10.6, 12.0, x=BOX_X + 0.1, y=BOX_H - 0.01, arc=2.6).act(10.6, 12.0, "fly_to")
    nib.act(12.0, 12.6, "land").fly(12.6, False).feel(12.6, "proud")
    nib.feel(13.2, "surprised").act(13.2, 14.2, "fall").move(13.3, 14.0, x=BOX_X + 0.55, y=0.0, arc=0.3)
    nib.feel(14.2, "dizzy")
    for p in (bolt, maya, nib):
        p.finalize(DURATION)
    return {"bolt": bolt, "maya": maya, "nib": nib}, audio, methods


def frame_fn_for(perf: dict[str, Performer]):
    bg = backdrop()
    ink = style("bolt").ink

    def frame(t: float):
        mobs = [bg]
        for cid in ("maya", "bolt", "nib"):
            st = perf[cid].state(t)
            g = build(cid, st.pose).scale(st.scale, about_point=np.zeros(3))
            g.shift(np.array([st.x, GROUND + st.y, 0]))
            mobs.append(g)
        if 1.2 <= t < 2.0:                                   # comic "BONK!" pop
            u = (t - 1.2) / 0.8
            k = 0.6 + 0.5 * bump(clamp01(u / 0.35)) + 0.4 * clamp01(u / 0.35)
            bonk = Text("BONK!", font="Bangers", font_size=96, color="#EF476F").set_stroke(ink, 5, background=True)
            mobs.append(bonk.scale(k).rotate(0.18).move_to(np.array([BOX_X - 0.4, 1.4, 0])))
        return mobs
    return frame


def mix_audio(audio: list[tuple[float, Path]], out_wav: Path, duration: float = DURATION) -> Path:
    n = round(duration * 48000)
    mix = array.array("h", bytes(2 * n))
    for t0, wav in audio:
        with wave.open(str(wav), "rb") as w:
            a = array.array("h", w.readframes(w.getnframes()))
        s0 = round(t0 * 48000)
        for k in range(min(len(a), n - s0)):
            mix[s0 + k] = a[k]
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)
        w.writeframes(mix.tobytes())
    return out_wav


def render_motion_test(voice_dir: Path, out_mp4: Path, width: int = 1920, height: int = 1080,
                       workers: int | None = None) -> dict:
    from robotics101.cartoon.render2d import render_clip

    perf, audio, methods = build_performance(voice_dir)
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    wav = mix_audio(audio, out_mp4.with_suffix(".wav"))
    render_clip(frame_fn_for(perf), int(DURATION * 30), out_mp4, width=width, height=height, workers=workers,
                audio_wav=wav)
    from robotics101.cartoon.lipsync import lipsync_agreement

    speakers = {Path(w).name.split("-")[-1][:-4]: (t0, w) for t0, w in audio}
    agreement = {f"{Path(w).name}": round(lipsync_agreement(perf[Path(w).name.split("-")[-1][:-4]].mouth, w, t0), 3)
                 for t0, w in audio}
    return {"video": str(out_mp4), "lipsync": methods, "lipsyncAgreement": agreement,
            "speakers": sorted(speakers), "mouthCues": {c: len(p.mouth.cues) for c, p in perf.items()}}
