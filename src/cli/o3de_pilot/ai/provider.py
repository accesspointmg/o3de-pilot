# O3DE Pilot CLI - AI Provider
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""AI provider abstraction and factory."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class AIProvider(ABC):
    """Abstract base class for AI providers."""

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

    def complete(self, prompt: str) -> str:
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=self.get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    async def complete_async(self, prompt: str) -> str:
        # For now, just wrap sync version
        return self.complete(prompt)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        client = self._get_client()
        with client.messages.stream(
            model=self.model,
            max_tokens=4096,
            system=self.get_system_prompt(),
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                yield text


class OllamaProvider(AIProvider):
    """Ollama local AI provider."""

    def __init__(self, url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self.url = url
        self.model = model

    def complete(self, prompt: str) -> str:
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


class GeminiProvider(AIProvider):
    """Google Gemini AI provider (free tier available)."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": self.get_system_prompt()}]},
            "contents": [{"parts": [{"text": prompt}]}],
        }
        response = httpx.post(url, json=body, timeout=60.0)
        response.raise_for_status()
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]

    async def complete_async(self, prompt: str) -> str:
        import httpx

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        body = {
            "system_instruction": {"parts": [{"text": self.get_system_prompt()}]},
            "contents": [{"parts": [{"text": prompt}]}],
        }
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=body, timeout=60.0)
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
        body = {
            "system_instruction": {"parts": [{"text": self.get_system_prompt()}]},
            "contents": [{"parts": [{"text": prompt}]}],
        }
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "POST", url, json=body, timeout=60.0,
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
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content or ""

    async def complete_async(self, prompt: str) -> str:
        return self.complete(prompt)

    async def stream(self, prompt: str) -> AsyncIterator[str]:
        client = self._get_client()
        stream = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.get_system_prompt()},
                {"role": "user", "content": prompt},
            ],
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content


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
    from o3de_pilot.core.config import get_config
    
    config = get_config()
    provider_name = config.get("ai.provider", "ollama")

    # Per-provider keys (preferred) with legacy fallback
    _per_keys = config.get("ai.api_keys", {})
    def _get_key() -> str:
        if isinstance(_per_keys, dict) and provider_name in _per_keys:
            return _per_keys[provider_name]
        return config.get("ai.api_key", "")
    
    if provider_name == "claude" or provider_name == "anthropic":
        api_key = _get_key()
        model = config.get("ai.model", "claude-sonnet-4-20250514")
        if not api_key:
            raise ValueError("API key not configured for Claude. Use: o3de-pilot config set ai.api_key <key>")
        return ClaudeProvider(api_key, model)
    
    elif provider_name == "ollama":
        url = config.get("ai.ollama_url", "http://localhost:11434")
        model = config.get("ai.model", "llama3")
        return OllamaProvider(url, model)
    
    elif provider_name == "gemini":
        api_key = _get_key()
        model = config.get("ai.model", "gemini-2.5-flash")
        if not api_key:
            raise ValueError(
                "API key not configured for Gemini.\n"
                "Get a free key at https://aistudio.google.com/apikey\n"
                "Then: o3de-pilot config set ai.api_key <key>"
            )
        return GeminiProvider(api_key, model)
    
    elif provider_name == "openai":
        api_key = _get_key()
        model = config.get("ai.model", "gpt-4o")
        if not api_key:
            raise ValueError("API key not configured for OpenAI. Use: o3de-pilot config set ai.api_key <key>")
        return OpenAIProvider(api_key, model)
    
    elif provider_name in OPENAI_COMPATIBLE_URLS:
        api_key = _get_key()
        model = config.get("ai.model", "")
        if not api_key:
            raise ValueError(
                f"API key not configured for {provider_name}. "
                "Use: o3de-pilot config set ai.api_key <key>"
            )
        return OpenAICompatibleProvider(
            OPENAI_COMPATIBLE_URLS[provider_name], api_key, model
        )
    
    else:
        return NoAIProvider()
