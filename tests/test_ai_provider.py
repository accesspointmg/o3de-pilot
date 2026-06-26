# O3DE Pilot - AI Provider Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for ai.provider — factory, NoAI, and provider construction."""

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


class TestNoAIProvider:
    def test_complete(self):
        from o3de_pilot_gui.ai.provider import NoAIProvider
        p = NoAIProvider()
        result = p.complete("hello")
        assert "not configured" in result.lower()

    def test_complete_async_sync_wrapper(self):
        import asyncio
        from o3de_pilot_gui.ai.provider import NoAIProvider
        p = NoAIProvider()
        result = asyncio.run(p.complete_async("hello"))
        assert "not configured" in result.lower()


class TestSystemPrompt:
    def test_system_prompt_content(self):
        from o3de_pilot_gui.ai.provider import NoAIProvider
        p = NoAIProvider()
        sp = p.get_system_prompt()
        assert "O3DE" in sp
        assert "Gem" in sp


class TestGetAIProvider:
    def test_default_ollama(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider, OllamaProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "ollama",
                "ai.ollama_url": "http://localhost:11434",
                "ai.model": "llama3",
                "ai.api_keys": {},
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, OllamaProvider)

    def test_claude_no_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "claude",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "claude-sonnet-4-20250514",
            }.get(k, d)
            with pytest.raises(ValueError, match="API key"):
                get_ai_provider()

    def test_claude_with_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider, ClaudeProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "claude",
                "ai.api_keys": {"claude": "sk-test"},
                "ai.api_key": "",
                "ai.model": "claude-sonnet-4-20250514",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, ClaudeProvider)

    def test_gemini_no_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "gemini",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "gemini-2.5-flash",
            }.get(k, d)
            with pytest.raises(ValueError, match="Gemini"):
                get_ai_provider()

    def test_gemini_with_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider, GeminiProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "gemini",
                "ai.api_keys": {},
                "ai.api_key": "test-key",
                "ai.model": "gemini-2.5-flash",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, GeminiProvider)

    def test_openai_no_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "openai",
                "ai.api_keys": {},
                "ai.api_key": "",
                "ai.model": "gpt-4o",
            }.get(k, d)
            with pytest.raises(ValueError, match="OpenAI"):
                get_ai_provider()

    def test_openai_with_key(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider, OpenAIProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
            mock_cfg.return_value.get.side_effect = lambda k, d=None: {
                "ai.provider": "openai",
                "ai.api_keys": {},
                "ai.api_key": "sk-test",
                "ai.model": "gpt-4o",
            }.get(k, d)
            p = get_ai_provider()
        assert isinstance(p, OpenAIProvider)

    def test_groq_compat(self):
        from o3de_pilot_gui.ai.provider import get_ai_provider, OpenAICompatibleProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
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
        from o3de_pilot_gui.ai.provider import get_ai_provider, NoAIProvider
        with patch("o3de_cli.core.config.get_config") as mock_cfg:
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
        from o3de_pilot_gui.ai.provider import ClaudeProvider
        p = ClaudeProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(RuntimeError, match="anthropic"):
                p._get_client()


class TestOpenAIProvider:
    def test_no_openai_package(self):
        from o3de_pilot_gui.ai.provider import OpenAIProvider
        p = OpenAIProvider(api_key="sk-test")
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(RuntimeError, match="openai"):
                p._get_client()


class TestOpenAICompatibleProvider:
    def test_headers(self):
        from o3de_pilot_gui.ai.provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://api.test.com/v1", "key123", "model1")
        h = p._headers()
        assert "Bearer key123" in h["Authorization"]

    def test_body(self):
        from o3de_pilot_gui.ai.provider import OpenAICompatibleProvider
        p = OpenAICompatibleProvider("https://api.test.com/v1", "key", "m1")
        b = p._body("hello")
        assert b["model"] == "m1"
        assert len(b["messages"]) == 2
        assert b["messages"][1]["content"] == "hello"


class TestOllamaProvider:
    def test_init(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        p = OllamaProvider()
        assert p.url == "http://localhost:11434"
        assert p.model == "llama3"

    def test_complete_mocked(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        p = OllamaProvider()
        p._model_checked = True  # skip ensure_model
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "test answer"}
        mock_resp.raise_for_status.return_value = None
        with patch("httpx.post", return_value=mock_resp):
            result = p.complete("hello")
        assert result == "test answer"


class TestGeminiProvider:
    def test_complete_mocked(self):
        from o3de_pilot_gui.ai.provider import GeminiProvider
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
        from o3de_pilot_gui.ai.provider import OpenAIProvider

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
        from o3de_pilot_gui.ai.provider import ClaudeProvider

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
        from o3de_pilot_gui.ai.provider import GeminiProvider

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
        from o3de_pilot_gui.ai.provider import NoAIProvider

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


class TestListModels:
    """Tests for dynamic model discovery via list_models()."""

    def test_noai_returns_empty(self):
        from o3de_pilot_gui.ai.provider import NoAIProvider
        assert NoAIProvider().list_models() == []

    @patch("httpx.get")
    def test_claude_list_models(self, mock_get):
        from o3de_pilot_gui.ai.provider import ClaudeProvider
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [
            {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4"},
            {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4"},
        ]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        p = ClaudeProvider(api_key="sk-test")
        models = p.list_models()
        assert len(models) == 2
        assert models[0]["id"] == "claude-sonnet-4-20250514"
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "api.anthropic.com" in call_args[0][0]

    @patch("httpx.get")
    def test_ollama_list_models(self, mock_get):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [
            {"name": "llama3:latest", "size": 4_000_000_000},
            {"name": "codellama:latest", "size": 7_000_000_000},
        ]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        p = OllamaProvider()
        models = p.list_models()
        assert len(models) == 2
        assert models[0]["id"] == "llama3:latest"
        assert models[1]["size"] == 7_000_000_000

    @patch("httpx.get")
    def test_gemini_list_models(self, mock_get):
        from o3de_pilot_gui.ai.provider import GeminiProvider
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [
            {"name": "models/gemini-2.5-flash", "displayName": "Gemini 2.5 Flash",
             "inputTokenLimit": 1048576,
             "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/embedding-001", "displayName": "Embedding",
             "supportedGenerationMethods": ["embedContent"]},
        ]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        p = GeminiProvider(api_key="test-key")
        models = p.list_models()
        # Should filter out embedding model (no generateContent)
        assert len(models) == 1
        assert models[0]["id"] == "gemini-2.5-flash"
        assert models[0]["context_window"] == 1048576

    @patch("httpx.get")
    def test_openai_list_models(self, mock_get):
        from o3de_pilot_gui.ai.provider import OpenAIProvider
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [
            {"id": "gpt-4o", "owned_by": "openai", "created": 1700000000},
            {"id": "gpt-4o-mini", "owned_by": "openai", "created": 1700000001},
            {"id": "dall-e-3", "owned_by": "openai", "created": 1700000002},
        ]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        p = OpenAIProvider(api_key="sk-test")
        models = p.list_models()
        # Should filter out dall-e (not gpt-/o1/o3/o4 prefix)
        assert len(models) == 2
        assert all(m["id"].startswith("gpt-") for m in models)

    @patch("httpx.get")
    def test_openai_compatible_list_models(self, mock_get):
        from o3de_pilot_gui.ai.provider import OpenAICompatibleProvider
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [
            {"id": "llama-3.3-70b-versatile", "owned_by": "meta"},
            {"id": "mixtral-8x7b-32768", "owned_by": "mistralai"},
        ]}
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        p = OpenAICompatibleProvider("https://api.groq.com/openai/v1", "key", "")
        models = p.list_models()
        assert len(models) == 2
        mock_get.assert_called_once()
        assert "/models" in mock_get.call_args[0][0]

    def test_list_models_handles_network_error(self):
        from o3de_pilot_gui.ai.provider import ClaudeProvider
        p = ClaudeProvider(api_key="invalid-key")
        # Real network call will fail — should return empty, not raise
        models = p.list_models()
        assert models == []


class TestDiscoverModels:
    """Tests for the discover_models convenience function."""

    @patch("o3de_cli.ai.provider.ClaudeProvider.list_models")
    def test_discover_anthropic(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "claude-sonnet-4-20250514"}]
        result = discover_models("anthropic", "sk-key")
        assert len(result) == 1
        mock_list.assert_called_once()

    @patch("o3de_cli.ai.provider.ClaudeProvider.list_models")
    def test_discover_claude_alias(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "test"}]
        result = discover_models("claude", "sk-key")
        assert len(result) == 1

    @patch("o3de_cli.ai.provider.OllamaProvider.list_models")
    def test_discover_ollama(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "llama3"}]
        result = discover_models("ollama", ollama_url="http://localhost:11434")
        assert len(result) == 1

    @patch("o3de_cli.ai.provider.GeminiProvider.list_models")
    def test_discover_gemini(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "gemini-2.5-flash"}]
        result = discover_models("gemini", "key")
        assert len(result) == 1

    @patch("o3de_cli.ai.provider.OpenAIProvider.list_models")
    def test_discover_openai(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "gpt-4o"}]
        result = discover_models("openai", "key")
        assert len(result) == 1

    @patch("o3de_cli.ai.provider.OpenAICompatibleProvider.list_models")
    def test_discover_groq(self, mock_list):
        from o3de_pilot_gui.ai.provider import discover_models
        mock_list.return_value = [{"id": "llama-3.3-70b-versatile"}]
        result = discover_models("groq", "key")
        assert len(result) == 1

    def test_discover_unknown_provider(self):
        from o3de_pilot_gui.ai.provider import discover_models
        result = discover_models("nonexistent", "key")
        assert result == []


class TestThinkingEffort:
    """Tests for thinking effort configuration across providers."""

    def test_thinking_levels_constant(self):
        from o3de_pilot_gui.ai.provider import THINKING_LEVELS
        assert THINKING_LEVELS == ("off", "low", "medium", "high", "max")

    def test_base_provider_default_off(self):
        from o3de_pilot_gui.ai.provider import AIProvider
        assert AIProvider.thinking_effort == "off"

    # ── Claude ──────────────────────────────────────────────────

    def test_claude_thinking_kwargs_off(self):
        from o3de_pilot_gui.ai.provider import ClaudeProvider
        p = ClaudeProvider.__new__(ClaudeProvider)
        p.thinking_effort = "off"
        kw = p._thinking_kwargs()
        assert "thinking" not in kw
        assert kw == {"max_tokens": 4096}

    def test_claude_thinking_kwargs_low(self):
        from o3de_pilot_gui.ai.provider import ClaudeProvider, _CLAUDE_BUDGET
        p = ClaudeProvider.__new__(ClaudeProvider)
        p.thinking_effort = "low"
        kw = p._thinking_kwargs()
        assert kw["thinking"]["type"] == "enabled"
        assert kw["thinking"]["budget_tokens"] == _CLAUDE_BUDGET["low"]
        assert "max_tokens" in kw

    def test_claude_thinking_kwargs_max(self):
        from o3de_pilot_gui.ai.provider import ClaudeProvider, _CLAUDE_BUDGET
        p = ClaudeProvider.__new__(ClaudeProvider)
        p.thinking_effort = "max"
        kw = p._thinking_kwargs()
        assert kw["thinking"]["budget_tokens"] == _CLAUDE_BUDGET["max"]

    # ── OpenAI ──────────────────────────────────────────────────

    def test_openai_reasoning_effort_o_series(self):
        """OpenAI o-series models should pass reasoning_effort."""
        from o3de_pilot_gui.ai.provider import OpenAIProvider, _OPENAI_EFFORT
        p = OpenAIProvider.__new__(OpenAIProvider)
        p.model = "o3-mini"
        p.api_key = "test"
        p.thinking_effort = "high"
        p._client = None

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="result"))]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai.OpenAI.return_value = mock_client

        import sys
        sys.modules["openai"] = mock_openai
        try:
            result = p.complete("test")
        finally:
            del sys.modules["openai"]

        call_kw = mock_client.chat.completions.create.call_args
        assert call_kw.kwargs.get("reasoning_effort") == _OPENAI_EFFORT["high"]

    def test_openai_no_reasoning_effort_non_o_series(self):
        """Non o-series models should NOT get reasoning_effort."""
        from o3de_pilot_gui.ai.provider import OpenAIProvider
        p = OpenAIProvider.__new__(OpenAIProvider)
        p.model = "gpt-4o"
        p.api_key = "test"
        p.thinking_effort = "high"
        p._client = None

        mock_openai = MagicMock()
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock(message=MagicMock(content="result"))]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_openai.OpenAI.return_value = mock_client

        import sys
        sys.modules["openai"] = mock_openai
        try:
            result = p.complete("test")
        finally:
            del sys.modules["openai"]

        call_kw = mock_client.chat.completions.create.call_args
        assert "reasoning_effort" not in call_kw.kwargs

    # ── Gemini ──────────────────────────────────────────────────

    def test_gemini_body_off(self):
        from o3de_pilot_gui.ai.provider import GeminiProvider
        p = GeminiProvider.__new__(GeminiProvider)
        p.thinking_effort = "off"
        body = p._gemini_body("hello")
        assert "generationConfig" not in body or "thinkingConfig" not in body.get("generationConfig", {})

    def test_gemini_body_high(self):
        from o3de_pilot_gui.ai.provider import GeminiProvider, _GEMINI_BUDGET
        p = GeminiProvider.__new__(GeminiProvider)
        p.thinking_effort = "high"
        body = p._gemini_body("hello")
        tc = body["generationConfig"]["thinkingConfig"]
        assert tc["thinkingBudget"] == _GEMINI_BUDGET["high"]

    # ── Factory ─────────────────────────────────────────────────

    @patch("o3de_cli.core.config.get_config")
    def test_factory_sets_thinking_effort(self, mock_gc):
        cfg = {
            "ai.enabled": "true",
            "ai.provider": "ollama",
            "ai.model": "llama3",
            "ai.thinking_effort": "medium",
        }
        mock_gc.return_value = MagicMock(get=lambda k, d=None: cfg.get(k, d))
        from o3de_pilot_gui.ai.provider import get_ai_provider
        p = get_ai_provider()
        assert p.thinking_effort == "medium"

    @patch("o3de_cli.core.config.get_config")
    def test_factory_defaults_to_off(self, mock_gc):
        cfg = {
            "ai.enabled": "true",
            "ai.provider": "ollama",
            "ai.model": "llama3",
        }
        mock_gc.return_value = MagicMock(get=lambda k, d=None: cfg.get(k, d))
        from o3de_pilot_gui.ai.provider import get_ai_provider
        p = get_ai_provider()
        assert p.thinking_effort == "off"


class TestLocalModel:
    """Tests for local model tier: Ollama detection, model check, auto-pull."""

    def test_default_local_model_constant(self):
        from o3de_pilot_gui.ai.provider import DEFAULT_LOCAL_MODEL
        assert ":" in DEFAULT_LOCAL_MODEL  # has explicit tag

    def test_ollama_is_running_true(self):
        from o3de_pilot_gui.ai.provider import _ollama_is_running
        mock_resp = MagicMock(status_code=200)
        with patch("httpx.get", return_value=mock_resp):
            assert _ollama_is_running("http://localhost:11434") is True

    def test_ollama_is_running_false(self):
        from o3de_pilot_gui.ai.provider import _ollama_is_running
        with patch("httpx.get", side_effect=Exception("connection refused")):
            assert _ollama_is_running("http://localhost:11434") is False

    def test_ollama_has_model_exact(self):
        from o3de_pilot_gui.ai.provider import _ollama_has_model
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
        with patch("httpx.get", return_value=mock_resp):
            assert _ollama_has_model("http://localhost:11434", "llama3.2:3b") is True

    def test_ollama_has_model_latest_shorthand(self):
        from o3de_pilot_gui.ai.provider import _ollama_has_model
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "llama3:latest"}]}
        with patch("httpx.get", return_value=mock_resp):
            assert _ollama_has_model("http://localhost:11434", "llama3") is True

    def test_ollama_has_model_missing(self):
        from o3de_pilot_gui.ai.provider import _ollama_has_model
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"models": [{"name": "mistral:latest"}]}
        with patch("httpx.get", return_value=mock_resp):
            assert _ollama_has_model("http://localhost:11434", "llama3") is False

    def test_ollama_pull_success(self):
        from o3de_pilot_gui.ai.provider import _ollama_pull

        lines = ['{"status":"downloading"}', '{"status":"success"}']
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_resp):
            assert _ollama_pull("http://localhost:11434", "llama3.2:3b") is True

    def test_ollama_pull_failure(self):
        from o3de_pilot_gui.ai.provider import _ollama_pull
        with patch("httpx.stream", side_effect=Exception("network error")):
            assert _ollama_pull("http://localhost:11434", "llama3.2:3b") is False

    def test_ollama_pull_progress_callback(self):
        from o3de_pilot_gui.ai.provider import _ollama_pull
        import json as _json

        lines = [
            _json.dumps({"status": "downloading", "completed": 500, "total": 1000}),
            _json.dumps({"status": "success", "completed": 0, "total": 0}),
        ]
        mock_resp = MagicMock()
        mock_resp.iter_lines.return_value = iter(lines)
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        progress_calls = []
        def on_progress(status, completed, total):
            progress_calls.append((status, completed, total))

        with patch("httpx.stream", return_value=mock_resp):
            _ollama_pull("http://localhost:11434", "test", on_progress=on_progress)

        assert len(progress_calls) == 2
        assert progress_calls[0] == ("downloading", 500, 1000)

    def test_ensure_model_not_running_raises(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        p = OllamaProvider("http://localhost:11434", "llama3")
        with patch("httpx.get", side_effect=Exception("refused")):
            with pytest.raises(RuntimeError, match="not running"):
                p.ensure_model()

    def test_ensure_model_auto_pulls(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider

        p = OllamaProvider("http://localhost:11434", "llama3.2:3b")

        # _ollama_is_running returns True
        running_resp = MagicMock(status_code=200)
        # _ollama_has_model returns False (empty models list)
        tags_resp = MagicMock()
        tags_resp.json.return_value = {"models": []}

        def mock_get(url, **kw):
            if "/api/tags" in url:
                return tags_resp
            return running_resp

        pull_lines = ['{"status":"success"}']
        mock_stream_resp = MagicMock()
        mock_stream_resp.iter_lines.return_value = iter(pull_lines)
        mock_stream_resp.__enter__ = MagicMock(return_value=mock_stream_resp)
        mock_stream_resp.__exit__ = MagicMock(return_value=False)

        with patch("httpx.get", side_effect=mock_get), \
             patch("httpx.stream", return_value=mock_stream_resp):
            p.ensure_model()  # should not raise

        assert p._model_checked is True

    def test_ensure_model_skips_on_second_call(self):
        from o3de_pilot_gui.ai.provider import OllamaProvider
        p = OllamaProvider("http://localhost:11434", "llama3")
        p._model_checked = True
        # Should return immediately — no httpx calls
        p.ensure_model()

    @patch("o3de_cli.core.config.get_config")
    def test_factory_uses_default_local_model(self, mock_gc):
        from o3de_pilot_gui.ai.provider import get_ai_provider, DEFAULT_LOCAL_MODEL
        cfg = {
            "ai.enabled": "true",
            "ai.provider": "ollama",
            # No ai.model set — should default to DEFAULT_LOCAL_MODEL
        }
        mock_gc.return_value = MagicMock(get=lambda k, d=None: cfg.get(k, d))
        p = get_ai_provider()
        assert p.model == DEFAULT_LOCAL_MODEL
