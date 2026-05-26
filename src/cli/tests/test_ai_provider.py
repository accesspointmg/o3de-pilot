# O3DE Pilot - AI Provider Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for ai.provider — factory, NoAI, and provider construction."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


class TestNoAIProvider:
    def test_complete(self):
        from o3de_pilot.ai.provider import NoAIProvider
        p = NoAIProvider()
        result = p.complete("hello")
        assert "not configured" in result.lower()

    def test_complete_async_sync_wrapper(self):
        import asyncio
        from o3de_pilot.ai.provider import NoAIProvider
        p = NoAIProvider()
        result = asyncio.run(p.complete_async("hello"))
        assert "not configured" in result.lower()


class TestSystemPrompt:
    def test_system_prompt_content(self):
        from o3de_pilot.ai.provider import NoAIProvider
        p = NoAIProvider()
        sp = p.get_system_prompt()
        assert "O3DE" in sp
        assert "Gem" in sp


class TestGetAIProvider:
    def test_default_ollama(self):
        from o3de_pilot.ai.provider import get_ai_provider, OllamaProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "ollama",
                "ai.ollama_url": "http://localhost:11434",
                "ai.model": "llama3",
                "ai.api_keys": {},
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, OllamaProvider)

    def test_claude_no_key(self):
        from o3de_pilot.ai.provider import get_ai_provider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "claude",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "claude-sonnet-4-20250514",
            }.get(k, d)
            with pytest.raises(ValueError, match="API key"):
                get_ai_provider()

    def test_claude_with_key(self):
        from o3de_pilot.ai.provider import get_ai_provider, ClaudeProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "claude",
                "ai.api_keys": {"claude": "sk-test"},
                "ai.api_key": "",
                "ai.model": "claude-sonnet-4-20250514",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, ClaudeProvider)

    def test_gemini_no_key(self):
        from o3de_pilot.ai.provider import get_ai_provider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "gemini",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "gemini-2.5-flash",
            }.get(k, d)
            with pytest.raises(ValueError, match="Gemini"):
                get_ai_provider()

    def test_gemini_with_key(self):
        from o3de_pilot.ai.provider import get_ai_provider, GeminiProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "gemini",
                "ai.api_keys": {},
                "ai.api_key": "test-key",
                "ai.model": "gemini-2.5-flash",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, GeminiProvider)

    def test_openai_no_key(self):
        from o3de_pilot.ai.provider import get_ai_provider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "openai",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "gpt-4o",
            }.get(k, d)
            with pytest.raises(ValueError, match="OpenAI"):
                get_ai_provider()

    def test_openai_with_key(self):
        from o3de_pilot.ai.provider import get_ai_provider, OpenAIProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "openai",
                "ai.api_keys": {},
                "ai.api_key": "sk-test",
                "ai.model": "gpt-4o",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, OpenAIProvider)

    def test_groq_compat(self):
        from o3de_pilot.ai.provider import get_ai_provider, OpenAICompatibleProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "groq",
                "ai.api_keys": {},
                "ai.api_key": "gsk-test",
                "ai.model": "llama3",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, OpenAICompatibleProvider)
        assert "groq" in p.base_url

    def test_unknown_provider(self):
        from o3de_pilot.ai.provider import get_ai_provider, NoAIProvider
        with patch("o3de_pilot.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "unknown_provider",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, NoAIProvider)


class TestClaudeProvider:
    def test_no_anthropic_package(self):
        from o3de_pilot.ai.provider import ClaudeProvider
        p = ClaudeProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(RuntimeError, match="anthropic"):
                p._get_client()


class TestOpenAIProvider:
    def test_no_openai_package(self):
        from o3de_pilot.ai.provider import OpenAIProvider
        p = OpenAIProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(RuntimeError, match="openai"):
                p._get_client()


class TestOpenAICompatibleProvider:
    def test_headers(self):
        from o3de_pilot.ai.provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://api.test.com/v1", "key123", "model1")
        h = p._headers()
        assert "Bearer key123" in h["Authorization"]

    def test_body(self):
        from o3de_pilot.ai.provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://api.test.com/v1", "key", "m1")
        b = p._body("hello")
        assert b["model"] == "m1"
        assert len(b["messages"]) == 2
        assert b["messages"][1]["content"] == "hello"


class TestOllamaProvider:
    def test_init(self):
        from o3de_pilot.ai.provider import OllamaProvider
        p = OllamaProvider()
        assert p.url == "http://localhost:11434"
        assert p.model == "llama3"

    def test_complete_mocked(self):
        from o3de_pilot.ai.provider import OllamaProvider
        p = OllamaProvider()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "test answer"}
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.post", return_value=mock_resp):
            result = p.complete("hello")
        assert result == "test answer"


class TestGeminiProvider:
    def test_complete_mocked(self):
        from o3de_pilot.ai.provider import GeminiProvider
        p = GeminiProvider(api_key="test-key")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "gemini answer"}]}}]
        }
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.post", return_value=mock_resp):
            result = p.complete("hello")
        assert result == "gemini answer"


# ── Streaming tests ─────────────────────────────────────────────────


class TestOpenAIProviderStream:
    def test_stream_yields_chunks(self):
        import asyncio
        from o3de_pilot.ai.provider import OpenAIProvider

        p = OpenAIProvider(api_key="sk-test")

        # Build mock chunk objects
        def make_chunk(content):
            chunk = MagicMock()
            chunk.choices = [MagicMock()]
            chunk.choices[0].delta = MagicMock()
            chunk.choices[0].delta.content = content
            return chunk

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = [
            make_chunk("Hello"),
            make_chunk(" world"),
            make_chunk(None),  # final chunk has no content
        ]
        p._client = mock_client

        async def collect():
            return [token async for token in p.stream("test")]

        tokens = asyncio.run(collect())
        assert tokens == ["Hello", " world"]
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["stream"] is True


class TestClaudeProviderStream:
    def test_stream_yields_text(self):
        import asyncio
        from o3de_pilot.ai.provider import ClaudeProvider

        p = ClaudeProvider(api_key="sk-test")

        mock_client = MagicMock()
        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = ["Hello", " from", " Claude"]
        mock_client.messages.stream.return_value = mock_stream_ctx
        p._client = mock_client

        async def collect():
            return [token async for token in p.stream("test")]

        tokens = asyncio.run(collect())
        assert tokens == ["Hello", " from", " Claude"]


class TestGeminiProviderStream:
    def test_stream_yields_text(self):
        import asyncio
        from o3de_pilot.ai.provider import GeminiProvider

        p = GeminiProvider(api_key="test-key")

        # Build mock SSE lines
        sse_lines = [
            'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}]}',
            'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}]}',
            "",
        ]

        # httpx.AsyncClient().stream() returns an async context manager
        # whose response has aiter_lines()
        mock_response = MagicMock()
        mock_response.aiter_lines = MagicMock(return_value=_async_iter(sse_lines))
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        async def collect():
            with patch("httpx.AsyncClient", return_value=mock_client):
                return [token async for token in p.stream("test")]

        tokens = asyncio.run(collect())
        assert tokens == ["Hello", " world"]


class TestNoAIProviderStream:
    def test_stream_yields_fallback(self):
        import asyncio
        from o3de_pilot.ai.provider import NoAIProvider

        p = NoAIProvider()

        async def collect():
            return [token async for token in p.stream("test")]

        tokens = asyncio.run(collect())
        assert len(tokens) == 1
        assert "not configured" in tokens[0].lower()


async def _async_iter(items):
    """Helper to create an async iterator from a list."""
    for item in items:
        yield item
