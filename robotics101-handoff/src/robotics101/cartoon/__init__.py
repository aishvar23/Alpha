"""Cartoon track (M02): catalogues shared by validation, audio and rendering."""

# Sound effects the mixer can produce (synthesised in code or from vendored CC0 files; M02.7).
SFX_IDS = frozenset({
    "zoom", "bonk", "boing", "pop", "ping", "echo", "charge", "skid", "whoosh", "clap", "motor",
    "nib_beep", "nib_whistle", "ding", "chalk", "sparkle", "page_flip", "stars", "toaster_pop", "swish",
})
# Music cues generated in code (M02.7).
MUSIC_CUES = frozenset({"theme_intro", "title_sting", "idea_sting", "chant_beat", "victory_sting", "outro",
                        "concept_sting"})
# Sets (backgrounds) the renderer can draw (M02.5).
SETS = frozenset({"garage"})

__all__ = ["MUSIC_CUES", "SETS", "SFX_IDS"]
