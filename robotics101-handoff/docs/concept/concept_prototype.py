"""Concept frames for the cartoon direction (THROWAWAY PROTOTYPE for docs/PLAN-cartoon.md, not pipeline code).

Render: manim -s --resolution 1920,1080 --disable_caching concept_prototype.py ConceptCast ConceptGag
"""
import math
import numpy as np
from manim import *

INK = "#2B2140"

def outline(m, w=6):
    return m.set_stroke(INK, w)

def bolt(expr="happy", squash=1.0, talk=0.0):
    """Bolt: round-ish teal robot hero with screen face, antenna bulb, tread base, noodle arms."""
    g = VGroup()
    tread = outline(RoundedRectangle(width=2.6, height=0.7, corner_radius=0.35, fill_color="#45505E", fill_opacity=1))
    tread.shift(DOWN * 1.65)
    wheels = VGroup(*[outline(Circle(0.22, fill_color="#FFC93C", fill_opacity=1), 4).move_to(tread.get_center() + RIGHT * x)
                      for x in (-0.85, 0, 0.85)])
    body = outline(RoundedRectangle(width=2.9, height=2.5, corner_radius=0.9, fill_color="#2EC4B6", fill_opacity=1))
    belly = outline(RoundedRectangle(width=1.3, height=0.55, corner_radius=0.2, fill_color="#FF9F1C", fill_opacity=1), 4)
    belly.move_to(body.get_center() + DOWN * 0.75)
    bolts = VGroup(*[Dot(belly.get_center() + RIGHT * x, 0.07, color=INK) for x in (-0.35, 0, 0.35)])
    screen = outline(RoundedRectangle(width=2.2, height=1.25, corner_radius=0.45, fill_color="#1B1B3A", fill_opacity=1), 5)
    screen.move_to(body.get_center() + UP * 0.35)
    eyes = VGroup()
    for sx in (-0.5, 0.5):
        if expr == "happy":
            e = Arc(radius=0.24, start_angle=0, angle=PI, color="#7CFFCB", stroke_width=14).move_to(screen.get_center() + RIGHT * sx + UP * 0.12)
        elif expr == "surprised":
            e = Circle(0.26, color="#7CFFCB", fill_opacity=1).move_to(screen.get_center() + RIGHT * sx + UP * 0.1)
            e.add(Dot(e.get_center() + UP * 0.05, 0.1, color="#1B1B3A"))
        else:  # dizzy
            e = VGroup(Line(LEFT * 0.2 + UP * 0.2, RIGHT * 0.2 + DOWN * 0.2), Line(LEFT * 0.2 + DOWN * 0.2, RIGHT * 0.2 + UP * 0.2))
            e.set_stroke("#7CFFCB", 12).move_to(screen.get_center() + RIGHT * sx + UP * 0.1)
        eyes.add(e)
    mouth_c = screen.get_center() + DOWN * 0.33
    if talk > 0:
        mouth = Ellipse(width=0.5, height=0.12 + 0.3 * talk, color="#7CFFCB", fill_opacity=1).move_to(mouth_c)
    elif expr == "dizzy":
        mouth = FunctionGraph(lambda x: 0.05 * math.sin(14 * x), x_range=[-0.3, 0.3], color="#7CFFCB", stroke_width=8).move_to(mouth_c)
    else:
        mouth = Arc(radius=0.3, start_angle=PI + 0.5, angle=PI - 1.0, color="#7CFFCB", stroke_width=10).move_to(mouth_c)
    cheeks = VGroup(*[Ellipse(width=0.3, height=0.16, color="#FF6B9A", fill_opacity=0.8, stroke_width=0)
                      .move_to(screen.get_center() + RIGHT * sx + DOWN * 0.25) for sx in (-0.85, 0.85)])
    stem = Line(body.get_top(), body.get_top() + UP * 0.6, stroke_width=8, color=INK)
    bulb = outline(Circle(0.2, fill_color="#FFE66D", fill_opacity=1), 5).move_to(stem.get_end() + UP * 0.12)
    glow = Circle(0.38, fill_color="#FFE66D", fill_opacity=0.35, stroke_width=0).move_to(bulb)
    arm_l = CubicBezier(body.get_left() + DOWN * 0.2, body.get_left() + LEFT * 0.8 + DOWN * 0.1,
                        body.get_left() + LEFT * 0.9 + UP * 0.6, body.get_left() + LEFT * 0.7 + UP * 1.0).set_stroke(INK, 14)
    arm_r = CubicBezier(body.get_right() + DOWN * 0.2, body.get_right() + RIGHT * 0.6 + DOWN * 0.5,
                        body.get_right() + RIGHT * 0.8 + DOWN * 0.6, body.get_right() + RIGHT * 0.95 + DOWN * 0.3).set_stroke(INK, 14)
    hands = VGroup(outline(Circle(0.2, fill_color="#FF9F1C", fill_opacity=1), 4).move_to(arm_l.get_end()),
                   outline(Circle(0.2, fill_color="#FF9F1C", fill_opacity=1), 4).move_to(arm_r.get_end()))
    g.add(glow, stem, bulb, arm_l, arm_r, hands, tread, wheels, body, belly, bolts, screen, cheeks, eyes, mouth)
    g.stretch(1 / squash, 0).stretch(squash, 1)
    return g

def maya(expr="grin"):
    """Maya: 9-year-old inventor; curly hair puffs, goggles on forehead, yellow overalls, toolbelt."""
    skin, hair = "#A8673F", "#2A1A12"
    g = VGroup()
    legs = VGroup(*[outline(RoundedRectangle(width=0.35, height=1.0, corner_radius=0.15, fill_color="#3D5A80", fill_opacity=1), 4)
                    .move_to(DOWN * 2.0 + RIGHT * x) for x in (-0.3, 0.3)])
    shoes = VGroup(*[outline(Ellipse(width=0.6, height=0.3, fill_color="#E63946", fill_opacity=1), 4)
                     .move_to(DOWN * 2.55 + RIGHT * x) for x in (-0.35, 0.35)])
    torso = outline(RoundedRectangle(width=1.5, height=1.5, corner_radius=0.5, fill_color="#FFD23F", fill_opacity=1))
    torso.move_to(DOWN * 0.95)
    belt = outline(Rectangle(width=1.5, height=0.22, fill_color="#8D5524", fill_opacity=1), 3).move_to(DOWN * 1.35)
    puffs = VGroup(*[outline(Circle(r, fill_color=hair, fill_opacity=1), 5).move_to(p) for r, p in
                     ((0.55, UP * 1.55 + LEFT * 0.95), (0.55, UP * 1.55 + RIGHT * 0.95), (0.75, UP * 1.6))])
    head = outline(Circle(0.95, fill_color=skin, fill_opacity=1)).move_to(UP * 0.85)
    goggle_band = Line(head.get_left() + UP * 0.75 + RIGHT * 0.15, head.get_right() + UP * 0.75 + LEFT * 0.15, stroke_width=12, color="#6C4AB6")
    goggles = VGroup(*[outline(Circle(0.27, fill_color="#9BF6FF", fill_opacity=1), 6).move_to(head.get_center() + UP * 0.92 + RIGHT * x)
                       for x in (-0.33, 0.33)])
    eyes = VGroup(*[VGroup(Ellipse(width=0.26, height=0.34, color=WHITE, fill_opacity=1, stroke_color=INK, stroke_width=3),
                           Dot(radius=0.08, color=INK).shift(RIGHT * 0.03)).move_to(head.get_center() + RIGHT * x + UP * 0.02)
                    for x in (-0.33, 0.33)])
    brows = VGroup(*[Line(LEFT * 0.12, RIGHT * 0.12, stroke_width=6, color=hair).rotate(r).move_to(head.get_center() + RIGHT * x + UP * 0.26)
                     for x, r in ((-0.33, 0.25), (0.33, -0.25))])
    if expr == "grin":
        mouth = outline(ArcBetweenPoints(LEFT * 0.3, RIGHT * 0.3, angle=PI * 0.9, fill_color="#7A1F3D", fill_opacity=1), 4)
        mouth.move_to(head.get_center() + DOWN * 0.4)
    else:
        mouth = Arc(radius=0.2, start_angle=PI + 0.6, angle=PI - 1.2, color=INK, stroke_width=6).move_to(head.get_center() + DOWN * 0.38)
    cheeks = VGroup(*[Ellipse(width=0.25, height=0.13, color="#FF6B9A", fill_opacity=0.7, stroke_width=0)
                      .move_to(head.get_center() + RIGHT * x + DOWN * 0.2) for x in (-0.55, 0.55)])
    arm_l = CubicBezier(torso.get_left() + UP * 0.4, LEFT * 1.4 + UP * 0.2, LEFT * 1.6 + UP * 0.9, LEFT * 1.5 + UP * 1.4).set_stroke(INK, 26)
    arm_l2 = arm_l.copy().set_stroke("#FFD23F", 18)
    hand_l = outline(Circle(0.18, fill_color=skin, fill_opacity=1), 4).move_to(arm_l.get_end())
    arm_r = CubicBezier(torso.get_right() + UP * 0.4, RIGHT * 1.3 + DOWN * 0.2, RIGHT * 1.2 + DOWN * 0.7, RIGHT * 1.0 + DOWN * 1.0).set_stroke(INK, 26)
    arm_r2 = arm_r.copy().set_stroke("#FFD23F", 18)
    hand_r = outline(Circle(0.18, fill_color=skin, fill_opacity=1), 4).move_to(arm_r.get_end())
    g.add(legs, shoes, arm_l, arm_l2, hand_l, arm_r, arm_r2, hand_r, torso, belt, puffs, head, cheeks, eyes, brows, mouth, goggle_band, goggles)
    return g

def nib():
    """Nib: tiny bird-drone sidekick, one big eye, propeller hat; speaks in beeps (SFX only)."""
    body = outline(Ellipse(width=0.9, height=0.75, fill_color="#FF6B9A", fill_opacity=1), 5)
    eye = VGroup(Circle(0.2, color=WHITE, fill_opacity=1, stroke_color=INK, stroke_width=3), Dot(radius=0.09, color=INK).shift(RIGHT * 0.05))
    beak = outline(Triangle(fill_color="#FFC93C", fill_opacity=1).scale(0.12).rotate(-PI / 2), 3).next_to(body, RIGHT, buff=-0.08)
    mast = Line(body.get_top(), body.get_top() + UP * 0.2, color=INK, stroke_width=5)
    prop = outline(Ellipse(width=0.9, height=0.12, fill_color="#9BF6FF", fill_opacity=1), 3).move_to(mast.get_end())
    wing = outline(Ellipse(width=0.45, height=0.25, fill_color="#FF9FC0", fill_opacity=1), 3).move_to(body.get_center() + LEFT * 0.25 + DOWN * 0.05).rotate(0.4)
    feet = VGroup(*[Line(UP * 0.0, DOWN * 0.15, color=INK, stroke_width=4).move_to(body.get_bottom() + RIGHT * x + DOWN * 0.05) for x in (-0.12, 0.12)])
    return VGroup(feet, body, wing, eye.move_to(body.get_center() + RIGHT * 0.12 + UP * 0.08), beak, mast, prop)

def garage():
    wall = Rectangle(width=16, height=9, fill_color="#FFE8C2", fill_opacity=1, stroke_width=0)
    stripes = VGroup(*[Rectangle(width=0.6, height=9, fill_color="#FFDDA8", fill_opacity=1, stroke_width=0).shift(RIGHT * x) for x in np.arange(-7.5, 8, 1.2)])
    floor = Rectangle(width=16, height=2.6, fill_color="#B5838D", fill_opacity=1, stroke_width=0).to_edge(DOWN, buff=0)
    floor_line = Line(LEFT * 8, RIGHT * 8, stroke_width=8, color=INK).move_to(floor.get_top())
    window = outline(RoundedRectangle(width=2.8, height=2.0, corner_radius=0.2, fill_color="#9BF6FF", fill_opacity=1)).move_to(UP * 2.2 + LEFT * 4.6)
    sun = Circle(0.4, fill_color="#FFE66D", fill_opacity=1, stroke_width=0).move_to(window.get_center() + UP * 0.35 + RIGHT * 0.6)
    cross = VGroup(Line(window.get_top(), window.get_bottom()), Line(window.get_left(), window.get_right())).set_stroke(INK, 6)
    shelf = outline(Rectangle(width=3.2, height=0.18, fill_color="#8D5524", fill_opacity=1), 4).move_to(UP * 1.4 + RIGHT * 4.6)
    jars = VGroup(*[outline(RoundedRectangle(width=0.5, height=h, corner_radius=0.1, fill_color=c, fill_opacity=1), 4)
                    .next_to(shelf, UP, buff=0).shift(RIGHT * x) for x, h, c in ((-1.1, 0.7, "#06D6A0"), (-0.4, 0.5, "#EF476F"), (0.4, 0.9, "#118AB2"), (1.1, 0.6, "#FFD166"))])
    box = outline(RoundedRectangle(width=1.8, height=1.2, corner_radius=0.1, fill_color="#E76F51", fill_opacity=1)).move_to(DOWN * 2.2 + RIGHT * 5.6)
    lbl = Text("BOXES", font="Luckiest Guy", font_size=24, color=INK).move_to(box)
    return VGroup(wall, stripes, floor, floor_line, window, sun, cross, shelf, jars, box, lbl)

class ConceptCast(Scene):
    def construct(self):
        self.camera.background_color = "#FFE8C2"
        bg = garage()
        b = bolt("happy").scale(0.95).move_to(LEFT * 0.4 + DOWN * 0.55)
        m = maya("grin").scale(0.95).move_to(LEFT * 4.3 + DOWN * 0.6)
        n = nib().scale(1.2).move_to(RIGHT * 2.4 + UP * 1.6)
        title = Text("ROBOTICS 101", font="Luckiest Guy", font_size=84, color="#FF6B9A").set_stroke(INK, 3, background=True).to_edge(UP, buff=0.3)
        sub = Text("with Bolt, Maya & Nib", font="Fredoka", weight=BOLD, font_size=36, color=INK).next_to(title, DOWN, buff=0.1)
        names = VGroup(*[Text(t, font="Fredoka", weight=BOLD, font_size=30, color=INK).next_to(o, DOWN, buff=0.12)
                         for t, o in (("Maya", m), ("Bolt", b))])
        names.add(Text("Nib", font="Fredoka", weight=BOLD, font_size=30, color=INK).next_to(n, DOWN, buff=0.15))
        self.add(bg, m, b, n, title, sub, names)

class ConceptGag(Scene):
    """Story beat: Bolt bonks the garage box (dizzy), Maya laughs, Nib beeps; speech bubble + 'BONK!' SFX text."""
    def construct(self):
        self.camera.background_color = "#FFE8C2"
        bg = garage()
        b = bolt("dizzy", squash=0.85).scale(0.95).move_to(RIGHT * 3.2 + DOWN * 0.8).rotate(0.12)
        stars = VGroup(*[Star(5, outer_radius=0.22, fill_color="#FFE66D", fill_opacity=1, stroke_color=INK, stroke_width=3)
                         .move_to(b.get_top() + UP * 0.2 + RIGHT * x) for x in (-0.7, 0, 0.7)])
        bonk = Text("BONK!", font="Bangers", font_size=110, color="#EF476F").set_stroke(INK, 6, background=True).rotate(0.2).move_to(RIGHT * 5.4 + UP * 1.2)
        m = maya("grin").scale(0.95).move_to(LEFT * 3.6 + DOWN * 0.6)
        bubble = outline(RoundedRectangle(width=5.4, height=1.5, corner_radius=0.6, fill_color=WHITE, fill_opacity=1))
        bubble.move_to(LEFT * 3.2 + UP * 2.6)
        tail = outline(Polygon(bubble.get_bottom() + LEFT * 0.4, bubble.get_bottom() + RIGHT * 0.1, bubble.get_bottom() + DOWN * 0.6 + LEFT * 0.4,
                               fill_color=WHITE, fill_opacity=1))
        txt = Text("Bolt... that box has been\nthere since Tuesday!", font="Fredoka", weight=BOLD, font_size=34, color=INK, line_spacing=0.8).move_to(bubble)
        n = nib().scale(1.1).move_to(LEFT * 0.3 + UP * 0.8).rotate(-0.3)
        beep = Text("beep?", font="Fredoka", weight=BOLD, font_size=30, color="#6C4AB6").next_to(n, UP, buff=0.05)
        cap = Rectangle(width=16, height=0.9, fill_color=BLACK, fill_opacity=0.55, stroke_width=0).to_edge(DOWN, buff=0)
        sub = Text("MAYA: Bolt... that box has been there since Tuesday!", font="Nunito", font_size=30, color=WHITE).move_to(cap)
        self.add(bg, b, stars, bonk, m, tail, bubble, txt, n, beep, cap, sub)


class ConceptMotion(Scene):
    """Perf probe: 6 s of bounce (squash/stretch), blink and amplitude-driven lip flap at 1080p30."""
    def construct(self):
        self.camera.background_color = "#FFE8C2"
        self.add(garage())
        t = ValueTracker(0)
        rng = np.random.default_rng(1)
        amp = np.clip(np.abs(np.sin(np.linspace(0, 40, 181))) * rng.uniform(0.4, 1, 181), 0, 1)
        def rig():
            k = t.get_value()
            ph = (k % 1.0)
            sq = 1 + 0.12 * math.sin(2 * math.pi * ph)
            i = min(int(k * 30), 180)
            b = bolt("surprised" if int(k) % 3 == 2 else "happy", squash=sq, talk=float(amp[i]) if k < 4 else 0)
            return b.scale(0.95).move_to(LEFT * 0.4 + DOWN * 0.55 + UP * 0.25 * abs(math.sin(math.pi * ph)))
        b = always_redraw(rig)
        m = maya("grin").scale(0.95).move_to(LEFT * 4.3 + DOWN * 0.6)
        self.add(m, b)
        self.play(t.animate.set_value(6), run_time=6, rate_func=linear)
