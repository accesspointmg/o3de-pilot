# O3DE Pilot GUI - AI Provider Abstraction
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Minimal AI provider abstraction layer.

Provides a base class and a stub implementation so the voice pipeline
has a concrete endpoint.  Real providers (OpenAI, Anthropic, local LLM)
can be plugged in later by subclassing ``AiProvider``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class AiProvider(ABC):
    """Abstract base for AI completion providers."""

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Send *prompt* and return the model's response text."""
        ...


class StubAiProvider(AiProvider):
    """Echo provider used when no real backend is configured."""

    def complete(self, prompt: str) -> str:  # noqa: D401
        return f"AI assistance is not yet configured. Your input was: {prompt}"
