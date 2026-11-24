"""M05.5: section backgrounds (schema 1.2), per-section card kickers, and the cosmetic fixes."""

import itertools
import json
from pathlib import Path

import numpy as np
import pytest

from robotics101.cartoon import BACKGROUND_THEMES
from robotics101.cartoon.episode import TEMPLATE_KICKERS, expand_episode, resolve_backgrounds, resolve_kickers
from robotics101.characters import load_registry
from robotics101.qa import QaReport
from robotics101.validation import validate_episode

ROOT = Path(__file__).resolve().parents[1]
EP1 = ROOT / "examples" / "episode-001-cartoon.json"


def _ep1():
    return json.loads(EP1.read_text())


def _expanded():
    return expand_episode(_ep1(), load_registry())


# ------------------------------------------------------------------ backgrounds: model + auto-assign

def test_ep1_every_section_gets_its_own_background():
    s = _expanded()
    assert s["schemaVersion"] == "1.3" and validate_episode(s).ok
    bg = {x["background"]["section"]: x["background"]["theme"] for x in s["scenes"]}
    assert bg == {"cold_open": "workshop", "intro": "studio", "robot_family": "museum", "checkup": "lab_bench",
                  "sensors": "sound_lab", "the_rule": "control_room", "servo": "blueprint", "rule_test": "test_track",
                  "quiz": "quiz_stage"}
    themes = [x["background"]["theme"] for x in s["scenes"]]
    assert all(a != b for a, b in zip(themes, themes[1:])) and len(set(themes)) == len(themes)
    assert expand_episode(s, load_registry()) == s                       # idempotent


def _scenes(templates, sections=None):
    return [{"sceneId": f"scene-{i:03d}", "template": t, **({"section": sections[i]} if sections else {})}
            for i, t in enumerate(templates)]


def test_auto_never_repeats_adjacent_and_rotates_palettes():
    sc = _scenes(["cartoon_rule_board"] * 12)
    resolve_backgrounds(sc)
    th = [(x["background"]["theme"], x["background"]["palette"]) for x in sc]
    assert all(a[0] != b[0] for a, b in zip(th, th[1:]))
    assert len({t for t, _ in th[:9]}) == 9                           # every theme used before any repeats
    reused = [p for t, p in th if t == th[0][0]]
    assert len(reused) >= 2 and reused[0] != reused[1]                 # a re-used theme takes its next palette


def test_section_groups_share_one_background_and_authored_wins():
    sc = _scenes(["cartoon_cold_open", "cartoon_robot_family", "cartoon_robot_checkup", "cartoon_sensor_ping"],
                 ["a", "b", "b", "c"])
    sc[3]["background"] = {"theme": "test_track", "palette": "dusk"}
    resolve_backgrounds(sc)
    assert sc[1]["background"] == sc[2]["background"] and sc[1]["background"]["section"] == "b"
    assert sc[3]["background"] == {"theme": "test_track", "palette": "dusk", "section": "c", "auto": False}
    assert sc[0]["background"]["theme"] != sc[1]["background"]["theme"]


def test_v11_specs_still_valid_and_get_the_defaults():
    s = _ep1()
    s["schemaVersion"] = "1.1"
    for x in s["scenes"]:
        x.pop("section", None)
        x.pop("background", None)
    assert validate_episode(s).ok
    e = expand_episode(s, load_registry())
    assert e["schemaVersion"] == "1.3" and validate_episode(e).ok
    assert all(x["background"]["theme"] for x in e["scenes"])


@pytest.mark.parametrize("mutate,needle", [
    (lambda s: [s["scenes"][2].update(background={"theme": "lab_bench"}),
                s["scenes"][3].update(background={"theme": "lab_bench"})], "same background theme"),
    (lambda s: s["scenes"][2].update(background={"theme": "lab_bench", "palette": "plaid"}), "unknown palette"),
    (lambda s: s["scenes"][4].update(section="checkup"), "split by another section"),
    (lambda s: s["scenes"][2].update(background={"theme": "moon_base"}), "schema"),
])
def test_validation_rejects_bad_sections(mutate, needle):
    s = _ep1()
    mutate(s)
    rep = validate_episode(s)
    msgs = [i.message for i in rep.issues if i.severity == "error"] if hasattr(rep, "issues") else [str(rep)]
    assert not rep.ok and any(needle in m for m in msgs), msgs


# ------------------------------------------------------------------ backgrounds: drawing

def test_themes_catalogue_matches_and_look_different():
    from robotics101.cartoon import backgrounds as B
    from robotics101.cartoon.qa import SECTION_SWATCH_MIN
    assert {t: B.palettes(t) for t in B.THEME_NAMES} == BACKGROUND_THEMES
    sw = {(t, p): B.swatch(t, p) for t, ps in BACKGROUND_THEMES.items() for p in ps}
    for a, b in itertools.combinations(sw, 2):
        if a[0] != b[0]:
            assert B.swatch_distance(sw[a], sw[b]) >= SECTION_SWATCH_MIN, (a, b)
    with pytest.raises(ValueError):
        B.backdrop("moon_base")


def test_every_theme_keeps_the_stage_geometry():
    """The ink floor line at FLOOR_Y in every theme, so staging and the caption band don't depend on the set."""
    from robotics101.cartoon import backgrounds as B
    from robotics101.cartoon.render2d import frame_rgb
    from robotics101.cartoon.sets import FLOOR_Y, ink
    w, h = 320, 180
    row = int(round((4.0 - FLOOR_Y) / 8.0 * h))
    c = np.array([int(ink()[i:i + 2], 16) for i in (1, 3, 5)])
    for t, ps in BACKGROUND_THEMES.items():
        img = frame_rgb([B.backdrop(t, ps[0])], w, h, "#000000")[..., :3].astype(int)
        d = np.abs(img[row - 2:row + 3, 20:300] - c).sum(-1).min(0)
        assert (d < 90).mean() > 0.8, t


# ------------------------------------------------------------------ QA scenes.section_backgrounds

def _by(themes, sections=None):
    from robotics101.cartoon import backgrounds as B
    by, spec = {}, {"scenes": []}
    for i, th in enumerate(themes):
        sid = f"scene-{i}"
        pal = BACKGROUND_THEMES[th][0]
        spec["scenes"].append({"sceneId": sid})
        by[sid] = {"background": {"theme": th, "palette": pal, "section": (sections or {}).get(i, sid),
                                  "swatch": B.swatch(th, pal)}}
    return spec, by


def _status(fn, *a):
    rep = QaReport("ep", "full", "x")
    fn(rep, *a)
    return {c.id: c.status for c in rep.checks}


def test_qa_section_backgrounds():
    from robotics101.cartoon.qa import check_section_backgrounds as chk
    k = "scenes.section_backgrounds"
    assert _status(chk, *_by(["workshop", "studio", "museum"]))[k] == "pass"
    assert _status(chk, *_by(["workshop", "workshop"]))[k] == "fail"
    assert _status(chk, *_by(["workshop", "workshop"], {0: "a", 1: "a"}))[k] == "pass"
    spec, by = _by(["workshop", "studio"])
    by["scene-1"]["background"]["swatch"] = by["scene-0"]["background"]["swatch"]          # look-alike sets
    assert _status(chk, spec, by)[k] == "fail"
    spec, by = _by(["workshop", "studio"])
    del by["scene-1"]["background"]
    assert _status(chk, spec, by)[k] == "fail"


# ------------------------------------------------------------------ kickers

def test_ep1_kickers_are_per_section_and_never_new_idea():
    s = _expanded()
    got = {x["background"]["section"]: x.get("kicker") for x in s["scenes"] if "kicker" in x}
    assert got == {"cold_open": None, "intro": None, "robot_family": "Meet the robots!", "checkup": "Checkup time!",
                   "sensors": "Sensor science!", "the_rule": "The Rule", "servo": "Servo time!",
                   "rule_test": "Let's test it!", "quiz": "Recap & quiz!"}
    cards = [c["kicker"] for x in s["scenes"] for c in x.get("concepts") or [] if c["kicker"]]
    assert len({c.casefold() for c in cards}) == len(cards) == 5
    assert "new idea!" not in {(k or "").casefold() for k in TEMPLATE_KICKERS.values()}
    assert "NEW IDEA" not in (ROOT / "src" / "robotics101" / "cartoon" / "props.py").read_text()


def test_kicker_authoring_hiding_and_dedupe():
    sc = _scenes(["cartoon_robot_checkup", "cartoon_sensor_ping", "cartoon_rule_board", "cartoon_robot_checkup"])
    sc[0]["concepts"] = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]
    sc[1]["kicker"] = None                                            # section kicker hidden
    sc[1]["concepts"] = [{"id": "c", "title": "C"}]
    sc[2]["kicker"] = "Big idea"
    sc[2]["concepts"] = [{"id": "d", "title": "D", "kicker": ""}]      # card kicker hidden
    resolve_kickers(sc)                                               # scene 3 repeats scene 0's type
    assert [c["kicker"] for c in sc[0]["concepts"]] == ["Checkup time!", None]
    assert sc[1]["kicker"] is None and sc[1]["concepts"][0]["kicker"] is None
    assert sc[2]["kicker"] == "Big idea" and sc[2]["concepts"][0]["kicker"] is None
    assert sc[3]["kicker"] is None                                    # a default never repeats: hidden
    unknown = [{"sceneId": "s", "template": "cartoon_mystery"}]
    resolve_kickers(unknown)
    assert unknown[0]["kicker"] is None                               # no good default -> hidden, no global fallback


def _kby(kickers_per_scene):
    spec, by = {"scenes": []}, {}
    for i, ks in enumerate(kickers_per_scene):
        sid = f"s{i}"
        spec["scenes"].append({"sceneId": sid})
        f = {"conceptCards": [{"id": f"c{i}{j}", "start": float(j), "kicker": k}
                              for j, k in enumerate(ks.get("cards", []))]}
        if ks.get("banner"):
            f["sectionBanner"] = {"kicker": ks["banner"], "start": 0.5}
        by[sid] = {"facts": f}
    return spec, by


def test_qa_kicker_variety():
    from robotics101.cartoon.qa import check_kicker_variety as chk
    ok = _status(chk, *_kby([{"cards": ["Checkup time!"]}, {"cards": [None]}, {"banner": "Let's test it!"}]))
    assert ok == {"cards.kicker_variety": "pass", "cards.kicker_adjacent": "pass"}
    adj = _status(chk, *_kby([{"cards": ["NEW IDEA!"]}, {"cards": ["new idea!"]}]))
    assert adj == {"cards.kicker_variety": "fail", "cards.kicker_adjacent": "warn"}
    far = _status(chk, *_kby([{"cards": ["The Rule"]}, {"banner": "Quiz!"}, {"cards": ["the  rule"]}]))
    assert far == {"cards.kicker_variety": "fail", "cards.kicker_adjacent": "pass"}


# ------------------------------------------------------------------ engine + cosmetic fixes

@pytest.fixture(scope="module")
def voiced(tmp_path_factory):
    pytest.importorskip("manim")
    from robotics101.voice import VoiceCache, voice_episode
    from robotics101.voice import backends as B
    d = tmp_path_factory.mktemp("voice")
    spec = _expanded()
    timing = voice_episode(spec, load_registry(), d, B.FixtureBackend(), VoiceCache(d / "cache"), log=lambda m: None)
    return spec, timing, d


def _scene(voiced, sid, monkeypatch):
    from robotics101.cartoon import lipsync
    from robotics101.cartoon import scenes as S
    monkeypatch.setattr(S, "line_cues", lambda wav, text: lipsync.line_cues(wav, text, prefer_rhubarb=False))
    spec, timing, d = voiced
    ss = next(s for s in spec["scenes"] if s["sceneId"] == sid)
    t = next(x for x in timing["scenes"] if x["sceneId"] == sid)
    return S.build_scene(ss, t, d)


def test_engine_draws_the_section_background_and_records_it(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    from robotics101.cartoon.render2d import frame_rgb
    sc = _scene(voiced, "scene-003", monkeypatch)
    assert sc.background["theme"] == "lab_bench"
    rec = S.background_record(sc)
    assert rec["theme"] == "lab_bench" and rec["section"] == "checkup" and len(rec["swatch"]) == 12
    img = frame_rgb(S.frame_fn(sc)(sc.duration / 2), 320, 180, "#000000")[..., :3].astype(int)
    assert np.abs(img[4, 160] - np.array([0xE0, 0xFB, 0xFC])).sum() < 60          # clinic wall, not the garage


def test_engine_card_kicker_and_section_banner(voiced, monkeypatch):
    sc4 = _scene(voiced, "scene-004", monkeypatch)
    assert [c["kicker"] for c in sc4.concepts] == ["Sensor science!"] and "sectionBanner" not in sc4.facts
    sc7 = _scene(voiced, "scene-007", monkeypatch)
    b = sc7.facts["sectionBanner"]
    assert b["kicker"] == "Let's test it!" and b["end"] - b["start"] >= 1.0
    sc8 = _scene(voiced, "scene-008", monkeypatch)        # recap chants own the top band: the banner waits
    b8 = sc8.facts["sectionBanner"]
    assert b8["kicker"] == "Recap & quiz!" and b8["end"] - b8["start"] >= 1.0 and sc8.top_busy
    assert not any(a < b8["end"] and b > b8["start"] for a, b in sc8.top_busy)


def test_rematch_hud_never_shows_the_old_reading_next_to_go():
    from robotics101.cartoon.obstacle import CLEAR_READING, hud_lines
    before = [t for t, _ in hud_lines(0.47, 0.5, turned=False)]
    after = [t for t, _ in hud_lines(0.47, 0.5, turned=True)]
    assert before[0] == "distance: 0.47 m" and "STOP & TURN!" in before and "path clear → GO" not in before
    assert after[0] == CLEAR_READING and "path clear → GO" in after and not any("0.47" in t for t in after)


def test_rematch_ruler_labels_are_drawn_in_front(voiced, monkeypatch):
    from manim import Text
    sc = _scene(voiced, "scene-007", monkeypatch)
    t = sc.duration - 2.0
    texts = lambda ms: [x.text.replace(" ", "") for m in ms for x in m.get_family() if isinstance(x, Text)]
    back = texts([m for f in sc.back for m in f(t, {})])
    front = texts([m for f in sc.front for m in f(t, {})])
    assert not any(x in ("3m", "0m", "1.5m") for x in back)
    assert {"3m", "0m"} <= set(front)


def test_intro_lineup_stays_inside_the_frame(voiced, monkeypatch):
    from robotics101.cartoon import scenes as S
    sc = _scene(voiced, "scene-intro", monkeypatch)
    worst = -9.0
    for t in np.arange(0, sc.duration, 0.1):
        mobs, _, _ = S.frame_layers(sc, t)
        for cid, m in mobs.items():
            if t >= sc.enter_at.get(cid, 0) + 0.2:
                worst = max(worst, -m.get_left()[0] - 7.11, m.get_right()[0] - 7.11)
    assert worst <= -0.15, worst
