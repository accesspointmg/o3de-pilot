# O3DE Pilot GUI - Speech Utilities
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Check availability of speech recognition dependencies."""

try:
    import speech_recognition as _sr  # noqa: F401
    SPEECH_AVAILABLE = True
except ImportError:
    SPEECH_AVAILABLE = False
