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

    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229") -> None:
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
        # TODO: Implement streaming
        yield self.complete(prompt)


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


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str, model: str = "gpt-4") -> None:
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
        yield self.complete(prompt)


def get_ai_provider() -> AIProvider:
    """Get the configured AI provider."""
    from o3de_pilot.core.config import get_config
    
    config = get_config()
    provider_name = config.get("ai.provider", "none")
    
    if provider_name == "claude" or provider_name == "anthropic":
        api_key = config.get("ai.api_key", "")
        model = config.get("ai.model", "claude-3-opus-20240229")
        if not api_key:
            raise ValueError("API key not configured for Claude. Use: o3de-pilot config set ai.api_key <key>")
        return ClaudeProvider(api_key, model)
    
    elif provider_name == "ollama":
        url = config.get("ai.ollama_url", "http://localhost:11434")
        model = config.get("ai.model", "llama3")
        return OllamaProvider(url, model)
    
    elif provider_name == "openai":
        api_key = config.get("ai.api_key", "")
        model = config.get("ai.model", "gpt-4")
        if not api_key:
            raise ValueError("API key not configured for OpenAI. Use: o3de-pilot config set ai.api_key <key>")
        return OpenAIProvider(api_key, model)
    
    else:
        return NoAIProvider()
