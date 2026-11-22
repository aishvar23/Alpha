"""FFmpeg composer (M01.5): scene clips + narration -> per-scene A/V clips -> final.mp4."""

from robotics101.compose.composer import (
    AUDIO_BITRATE,
    AUDIO_RATE,
    ComposeError,
    ComposeResult,
    SceneSegment,
    compose_episode,
    final_encode_command,
)

__all__ = ["AUDIO_BITRATE", "AUDIO_RATE", "ComposeError", "ComposeResult", "SceneSegment",
           "compose_episode", "final_encode_command"]
