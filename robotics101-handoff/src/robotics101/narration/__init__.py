"""Narration: TTS providers, audio-driven scene timing, SRT captions (M01.2)."""

from robotics101.narration.providers import (
    ESPEAK_LABEL,
    FIXTURE_LABEL,
    EspeakProvider,
    ExternalProvider,
    FixtureProvider,
    NarrationResult,
    TtsError,
    TtsProvider,
    get_provider,
    probe_duration,
)
from robotics101.narration.timing import narrate_episode

__all__ = [
    "ESPEAK_LABEL", "FIXTURE_LABEL", "EspeakProvider", "ExternalProvider", "FixtureProvider",
    "NarrationResult", "TtsError", "TtsProvider", "get_provider", "probe_duration", "narrate_episode",
]
