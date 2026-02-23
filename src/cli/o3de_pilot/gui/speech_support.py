# O3DE Pilot GUI - Speech Support Detection
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Probe for optional speech recognition dependencies."""


def check_speech_available() -> bool:
    """Return True if both SpeechRecognition and pyaudio are importable."""
    try:
        import speech_recognition as _sr  # noqa: F401
        import pyaudio as _pa  # noqa: F401
        return True
    except ImportError:
        return False


SPEECH_AVAILABLE: bool = check_speech_available()

SPEECH_MISSING_TOOLTIP = (
    "Speech recognition unavailable.\n"
    'Install with: pip install "o3de-pilot[speech]"'
)
