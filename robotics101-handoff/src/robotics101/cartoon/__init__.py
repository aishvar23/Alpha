"""Cartoon track (M02): catalogues shared by validation, audio and rendering."""

# Sound effects the mixer can produce (synthesised in code or from vendored CC0 files; M02.7).
SFX_IDS = frozenset({
    "zoom", "bonk", "boing", "pop", "ping", "echo", "charge", "skid", "whoosh", "clap", "motor",
    "nib_beep", "nib_whistle", "ding", "chalk", "sparkle", "page_flip", "stars", "toaster_pop", "swish",
})
# Music cues generated in code (M02.7).
MUSIC_CUES = frozenset({"theme_intro", "title_sting", "idea_sting", "chant_beat", "victory_sting", "outro",
                        "concept_sting"})
# Sets (backgrounds) the renderer can draw (M02.5); per-section themes live in ``cartoon.backgrounds`` (M05.5).
SETS = frozenset({"garage"})
# Cartoon (dialogue) spec versions: 1.1 (M02) and 1.2 (M05.5 section backgrounds; 1.1 specs get the defaults).
CARTOON_SCHEMA_VERSIONS = ("1.1", "1.2")
LATEST_CARTOON_SCHEMA = "1.2"

# M05.5 section background themes -> palettes (drawn by ``cartoon.backgrounds``; this manim-free catalogue is what
# validation and expansion use). Order matters: the first palette is the default.
BACKGROUND_THEMES = {
    "workshop": ("sunny", "evening"),
    "studio": ("violet", "teal"),
    "museum": ("mint", "rose"),
    "lab_bench": ("clinic", "lilac"),
    "sound_lab": ("ocean", "sunset"),
    "control_room": ("night", "steel"),
    "blueprint": ("classic", "teal"),
    "test_track": ("day", "dusk"),
    "quiz_stage": ("gold", "aqua"),
}

__all__ = ["BACKGROUND_THEMES", "CARTOON_SCHEMA_VERSIONS", "LATEST_CARTOON_SCHEMA", "MUSIC_CUES", "SETS", "SFX_IDS"]
