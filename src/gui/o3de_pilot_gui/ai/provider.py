# O3DE Pilot CLI - AI Provider
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""AI provider abstraction and factory."""

from abc import ABC, abstractmethod
from typing import AsyncIterator

# Normalized thinking effort levels
THINKING_LEVELS = ("off", "low", "medium", "high", "max")

# Maps normalized level → provider-native parameters
_CLAUDE_BUDGET = {"off": 0, "low": 1024, "medium": 4096, "high": 16384, "max": 128000}
_OPENAI_EFFORT = {"off": "low", "low": "low", "medium": "medium", "high": "high", "max": "high"}
_GEMINI_BUDGET = {"off": 0, "low": 1024, "medium": 4096, "high": 16384, "max": 24576}


class AIProvider(ABC):
    """Abstract base class for AI providers."""

    thinking_effort: str = "off"  # One of THINKING_LEVELS

    @abstractmethod
    def complete(self, prompt: str) -> str:
        """Generate a completion for the given prompt."""
        pass

    @abstractmethod
    async def complete_async(self, prompt: str) -> str:
        """Generate a completion asynchronously."""
        pass

    @abstractmethod
    async def stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream a completion for the given prompt."""
        pass

    def list_models(self) -> list[dict]:
        """Dynamically discover available models from the provider.

        Returns a list of dicts with at least ``id`` and optionally
        ``name``, ``created``, ``owned_by``, and ``context_window``.
        Returns an empty list if discovery is not supported or fails.
        """
        return []

    def get_system_prompt(self) -> str:
        """Get the O3DE-specific system prompt."""
        return """You are an expert assistant for the Open 3D Engine (O3DE), an open-source, 
real-time 3D development engine. You help developers with:

- Project setup and configuration
- Gem development and management
- Build system (CMake) issues
- Scripting (Lua, Python, Script Canvas)
- Editor usage and workflows
- Asset pipeline and processing
- Multiplayer and networking
- Physics and simulation
- Rendering and graphics

Provide clear, concise, and accurate answers. When suggesting code, use proper O3DE conventions.
If you're unsure about something, say so rather than guessing."""


class NoAIProvider(AIProvider):
    """Placeholder when no AI provider is configured."""

    def complete(self, prompt: str) -> str:
        return "AI is not configured. Use 'o3de-pilot config set ai.provider <name>' to configure."

    async def complete_async(self, prompt: str) -> str:
        return self.complete(prompt)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        yield self.complete(prompt)


class ClaudeProvider(AIProvider):
    """Anthropic Claude AI provider."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from anthropic import Anthropic
                self._client = Anthropic(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("anthropic package not installed. Run: pip install anthropic")
        return self._client

    def _thinking_kwargs(self) -> dict:
        budget = _CLAUDE_BUDGET.get(self.thinking_effort, 0)
        if budget > 0:
            return {
                "thinking": {"type": "adaptive", "budget_tokens": budget},
                "max_tokens": max(16384, budget + 4096),
            }
        return {"max_tokens": 4096}

    def complete(self, prompt: str) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            system=self.get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
            **self._thinking_kwargs(),
        )
        # When thinking is enabled, response has thinking + text blocks
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return response.content[0].text

    async def complete_async(self, prompt: str) -> str:
        return self.complete(prompt)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        client = self._get_client()
        with client.messages.stream(
            model=self.model,
            system=self.get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
            **self._thinking_kwargs(),
        ) as stream:
            for text in stream.text_stream:
                yield text

    def list_models(self) -> list[dict]:
        import httpx

        try:
            r = httpx.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10.0,
            )
            r.raise_for_status()
            return [
                {"id": m["id"], "name": m.get("display_name", m["id"]),
                 "created": m.get("created_at", "")}
                for m in r.json().get("data", [])
            ]
        except Exception:
            return []


# Default small model for local AI — fast enough for intent classification,
# basic explain/help, and error interpretation.  ~2 GB download.
DEFAULT_LOCAL_MODEL = "llama3.2:3b"


def _ollama_is_running(url: str = "http://localhost:11434") -> bool:
    """Return True if the Ollama daemon is reachable."""
    import httpx

    try:
        r = httpx.get(url, timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_has_model(url: str, model: str) -> bool:
    """Return True if *model* is already pulled locally."""
    import httpx

    try:
        r = httpx.get(f"{url}/api/tags", timeout=5.0)
        r.raise_for_status()
        names = {m["name"] for m in r.json().get("models", [])}
        # Match with and without tag — "llama3.2:3b" matches "llama3.2:3b",
        # and "llama3" matches "llama3:latest".
        if model in names:
            return True
        if ":" not in model and f"{model}:latest" in names:
            return True
        # Also try base name match (model may report "llama3.2:3b-instruct-…")
        base = model.split(":")[0]
        return any(n.split(":")[0] == base for n in names)
    except Exception:
        return False


def _ollama_pull(url: str, model: str, *, on_progress=None) -> bool:
    """Pull *model* from the Ollama library.

    *on_progress* is an optional callback ``(status: str, completed: int, total: int) -> None``
    called during download.  Returns ``True`` on success.
    """
    import httpx

    try:
        with httpx.stream(
            "POST",
            f"{url}/api/pull",
            json={"name": model, "stream": True},
            timeout=None,  # pulls can be large
        ) as response:
            response.raise_for_status()
            import json as _json

            for line in response.iter_lines():
                if not line:
                    continue
                data = _json.loads(line)
                if on_progress:
                    on_progress(
                        data.get("status", ""),
                        data.get("completed", 0),
                        data.get("total", 0),
                    )
                if data.get("status") == "success":
                    return True
            return True
    except Exception:
        return False


class OllamaProvider(AIProvider):
    """Ollama local AI provider."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self.url = url
        self.model = model
        self._model_checked = False

    def ensure_model(self, *, on_progress=None) -> None:
        """Ensure Ollama is running and the model is available.

        On first call, checks the daemon and auto-pulls the model if missing.
        Raises ``RuntimeError`` if Ollama is unreachable.
        """
        if self._model_checked:
            return
        if not _ollama_is_running(self.url):
            raise RuntimeError(
                "Ollama is not running. Start it with:\n"
                "  ollama serve\n"
                "Or download from https://ollama.com"
            )
        if not _ollama_has_model(self.url, self.model):
            if not _ollama_pull(self.url, self.model, on_progress=on_progress):
                raise RuntimeError(
                    f"Failed to pull model '{self.model}'. "
                    f"Try manually: ollama pull {self.model}"
                )
        self._model_checked = True

    def complete(self, prompt: str) -> str:
        self.ensure_model()
        import httpx
        
        response = httpx.post(
            f"{self.url}/api/generate",
            json={
                "model": self.model,
                "prompt": f"{self.get_system_prompt()}\n\nUser: {prompt}",
                "stream": False,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["response"]

    async def complete_async(self, prompt: str) -> str:
        self.ensure_model()
        import httpx
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{self.get_system_prompt()}\n\nUser: {prompt}",
                    "stream": False,
                },
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["response"]

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        self.ensure_model()
        import httpx
        
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": f"{self.get_system_prompt()}\n\nUser: {prompt}",
                    "stream": True,
                },
                timeout=60.0,
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]

    def list_models(self) -> list[dict]:
        import httpx

        try:
            r = httpx.get(f"{self.url}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [
                {"id": m["name"], "name": m["name"],
                 "size": m.get("size", 0)}
                for m in r.json().get("models", [])
            ]
        except Exception:
            return []


class GeminiProvider(AIProvider):
    """Google Gemini AI provider (free tier available)."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model

    def _gemini_body(self, prompt: str) -> dict:
        body: dict = {
            "system_instruction": {"parts": [{"text": self.get_system_prompt()}]},
            "contents": [{"parts": [{"text": prompt}]}],
        }
        budget = _GEMINI_BUDGET.get(self.thinking_effort, 0)
        if budget > 0:
            body["generationConfig"] = {
                "thinkingConfig": {"thinkingBudget": budget}
            }
        return body

    def complete(self, prompt: str) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        response = httpx.post(url, json=self._gemini_body(prompt), timeout=60.0)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def complete_async(self, prompt: str) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=self._gemini_body(prompt), timeout=60.0)
            response.raise_for_status()
            data = response.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        import httpx
        import json

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:streamGenerateContent?alt=sse&key={self.api_key}"
        )
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=self._gemini_body(prompt), timeout=60.0,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = json.loads(line[6:])
                        parts = (
                            data.get("candidates", [{}])[0]
                            .get("content", {})
                            .get("parts", [])
                        )
                        for part in parts:
                            text = part.get("text")
                            if text:
                                yield text

    def list_models(self) -> list[dict]:
        import httpx

        try:
            r = httpx.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}",
                timeout=10.0,
            )
            r.raise_for_status()
            return [
                {"id": m["name"].removeprefix("models/"),
                 "name": m.get("displayName", m["name"]),
                 "context_window": m.get("inputTokenLimit", 0)}
                for m in r.json().get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
            ]
        except Exception:
            return []


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key)
            except ImportError:
                raise RuntimeError("openai package not installed. Run: pip install openai")
        return self._client

    def complete(self, prompt: str) -> str:
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
        }
        if self.thinking_effort != "off" and self.model.startswith(("o1", "o3", "o4")):
            kwargs["reasoning_effort"] = _OPENAI_EFFORT.get(self.thinking_effort, "medium")
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def complete_async(self, prompt: str) -> str:
        return self.complete(prompt)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        client = self._get_client()
        kwargs: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        }
        if self.thinking_effort != "off" and self.model.startswith(("o1", "o3", "o4")):
            kwargs["reasoning_effort"] = _OPENAI_EFFORT.get(self.thinking_effort, "medium")
        stream = client.chat.completions.create(**kwargs)
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    def list_models(self) -> list[dict]:
        import httpx

        try:
            r = httpx.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10.0,
            )
            r.raise_for_status()
            return [
                {"id": m["id"], "name": m["id"],
                 "owned_by": m.get("owned_by", ""),
                 "created": m.get("created", 0)}
                for m in r.json().get("data", [])
                if m["id"].startswith(("gpt-", "o1", "o3", "o4"))
            ]
        except Exception:
            return []


class OpenAICompatibleProvider(AIProvider):
    """Generic provider for any OpenAI-compatible API.

    Works with Groq, Mistral, DeepSeek, xAI, OpenRouter, Together AI,
    Perplexity, and any other service that implements the OpenAI chat
    completions endpoint.  Uses ``httpx`` directly — no SDK needed.
    """

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _body(self, prompt: str, *, stream: bool = False) -> dict:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            "stream": stream,
        }

    def complete(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=self._body(prompt),
            timeout=60.0,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    async def complete_async(self, prompt: str) -> str:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._body(prompt),
                timeout=60.0,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        import httpx
        import json as _json

        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=self._body(prompt, stream=True),
                timeout=60.0,
            ) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        data = _json.loads(line[6:])
                        delta = data.get("choices", [{}])[0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content

    def list_models(self) -> list[dict]:
        import httpx

        try:
            r = httpx.get(
                f"{self.base_url}/models",
                headers=self._headers(),
                timeout=10.0,
            )
            r.raise_for_status()
            return [
                {"id": m["id"], "name": m.get("id", ""),
                 "owned_by": m.get("owned_by", "")}
                for m in r.json().get("data", [])
            ]
        except Exception:
            return []


# ── Base URLs for OpenAI-compatible providers ───────────────────────

OPENAI_COMPATIBLE_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "deepseek": "https://api.deepseek.com",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "perplexity": "https://api.perplexity.ai",
}


def get_ai_provider() -> AIProvider:
    """Get the configured AI provider.

    Default is Ollama (local, free).  If no provider is explicitly set
    the factory tries Ollama first, then falls back to ``NoAIProvider``.
    """
    from o3de_cli.core.config import get_config
    
    config = get_config()
    provider_name = config.get("ai.provider", "ollama")
    thinking = config.get("ai.thinking_effort", "off")
    if thinking not in THINKING_LEVELS:
        thinking = "off"

    # Per-provider keys (preferred) with legacy fallback
    _per_keys = config.get("ai.api_keys", {})
    def _get_key() -> str:
        if isinstance(_per_keys, dict) and provider_name in _per_keys:
            return _per_keys[provider_name]
        return config.get("ai.api_key", "")

    def _apply(p: AIProvider) -> AIProvider:
        p.thinking_effort = thinking
        return p
    
    if provider_name == "claude" or provider_name == "anthropic":
        api_key = _get_key()
        model = config.get("ai.model", "claude-sonnet-4-20250514")
        if not api_key:
            raise ValueError("API key not configured for Claude. Use: o3de-pilot config set ai.api_key <key>")
        return _apply(ClaudeProvider(api_key, model))
    
    elif provider_name == "ollama":
        url = config.get("ai.ollama_url", "http://localhost:11434")
        model = config.get("ai.model", DEFAULT_LOCAL_MODEL)
        return _apply(OllamaProvider(url, model))
    
    elif provider_name == "gemini":
        api_key = _get_key()
        model = config.get("ai.model", "gemini-2.5-flash")
        if not api_key:
            raise ValueError(
                "API key not configured for Gemini.\n"
                "Get a free key at https://aistudio.google.com/apikey\n"
                "Then: o3de-pilot config set ai.api_key <key>"
            )
        return _apply(GeminiProvider(api_key, model))
    
    elif provider_name == "openai":
        api_key = _get_key()
        model = config.get("ai.model", "gpt-4o")
        if not api_key:
            raise ValueError("API key not configured for OpenAI. Use: o3de-pilot config set ai.api_key <key>")
        return _apply(OpenAIProvider(api_key, model))
    
    elif provider_name in OPENAI_COMPATIBLE_URLS:
        api_key = _get_key()
        model = config.get("ai.model", "")
        if not api_key:
            raise ValueError(
                f"API key not configured for {provider_name}. "
                "Use: o3de-pilot config set ai.api_key <key>"
            )
        return _apply(OpenAICompatibleProvider(
            OPENAI_COMPATIBLE_URLS[provider_name], api_key, model
        ))
    
    else:
        return NoAIProvider()


def discover_models(provider_name: str, api_key: str = "", ollama_url: str = "") -> list[dict]:
    """Discover available models for a provider without full provider setup.

    Args:
        provider_name: Provider identifier (e.g. "anthropic", "openai", "ollama").
        api_key: API key for cloud providers.
        ollama_url: Ollama server URL (only for "ollama" provider).

    Returns:
        List of model dicts with at least ``id`` key, or empty list on failure.
    """
    if provider_name in ("claude", "anthropic"):
        return ClaudeProvider(api_key or "").list_models()
    elif provider_name == "ollama":
        return OllamaProvider(ollama_url or "http://localhost:11434").list_models()
    elif provider_name == "gemini":
        return GeminiProvider(api_key or "").list_models()
    elif provider_name == "openai":
        return OpenAIProvider(api_key or "").list_models()
    elif provider_name in OPENAI_COMPATIBLE_URLS:
        return OpenAICompatibleProvider(
            OPENAI_COMPATIBLE_URLS[provider_name], api_key or "", ""
        ).list_models()
    return []
