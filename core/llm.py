"""Unified LLM client — drop-in replacement for anthropic.Anthropic.

Supports both Anthropic API and OpenAI-compatible APIs (DeepSeek etc.).
All existing code using anthropic.Anthropic().messages.create() works unchanged.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass
class LLMConfig:
    provider: LLMProvider = LLMProvider.ANTHROPIC
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    base_url: str = ""  # e.g. https://api.deepseek.com
    temperature: float = 0.7
    max_tokens: int = 4096


# ── Fake response objects matching anthropic SDK shape ──────

class _FakeTextBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeResponse:
    def __init__(self, content: list[_FakeTextBlock], model: str, usage: _FakeUsage):
        self.content = content
        self.model = model
        self.usage = usage


class _MessagesProxy:
    """Proxy that exposes .create() matching anthropic.Anthropic.messages.create() signature."""

    def __init__(self, config: LLMConfig, api_key: str):
        self._config = config
        self._api_key = api_key
        self._anthropic_client = None
        self._openai_client = None

    def create(
        self,
        *,
        model: str,
        max_tokens: int,
        messages: list[dict],
        system: str = "",
        temperature: float = 0.7,
        **kwargs,
    ) -> _FakeResponse:
        if self._config.provider == LLMProvider.ANTHROPIC:
            return self._create_anthropic(model, max_tokens, messages, system, temperature)
        else:
            return self._create_openai(model, max_tokens, messages, system, temperature)

    def _create_anthropic(self, model, max_tokens, messages, system, temperature):
        import anthropic
        if self._anthropic_client is None:
            self._anthropic_client = anthropic.Anthropic(api_key=self._api_key)

        kwargs = dict(model=model, max_tokens=max_tokens, messages=messages, temperature=temperature)
        if system:
            kwargs["system"] = system

        resp = self._anthropic_client.messages.create(**kwargs)
        texts = [b for b in resp.content if hasattr(b, "text")]
        usage = resp.usage if hasattr(resp, "usage") else _FakeUsage(0, 0)
        return _FakeResponse(
            content=texts if texts else [_FakeTextBlock(str(resp.content))],
            model=resp.model,
            usage=usage,
        )

    def _create_openai(self, model, max_tokens, messages, system, temperature):
        import openai
        if self._openai_client is None:
            self._openai_client = openai.OpenAI(
                api_key=self._api_key,
                base_url=self._config.base_url,
            )

        openai_messages = []
        if system:
            openai_messages.append({"role": "system", "content": system})
        for m in messages:
            openai_messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        resp = self._openai_client.chat.completions.create(
            model=model,
            messages=openai_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = resp.choices[0]
        content_text = choice.message.content or ""
        # DeepSeek reasoning models may return empty content and put answer in reasoning_content
        if not content_text and hasattr(choice.message, "reasoning_content"):
            content_text = choice.message.reasoning_content or ""
            logger.debug("Falling back to reasoning_content: %s...", content_text[:100])
        inp = resp.usage.prompt_tokens if resp.usage else 0
        out = resp.usage.completion_tokens if resp.usage else 0

        return _FakeResponse(
            content=[_FakeTextBlock(content_text)],
            model=resp.model,
            usage=_FakeUsage(inp, out),
        )


def get_llm_client_from_settings() -> "LLMClient":
    """Factory: build LLMClient from application settings."""
    from core.config import settings
    config = LLMConfig(
        provider=LLMProvider(settings.llm_provider),
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return LLMClient(api_key=settings.llm_api_key, config=config)


class LLMClient:
    """Drop-in replacement for anthropic.Anthropic.

    Usage (same as Anthropic SDK):
        client = LLMClient(api_key="...", config=LLMConfig(...))
        resp = client.messages.create(model="...", messages=[...], max_tokens=4096)
        text = resp.content[0].text
    """

    def __init__(self, api_key: str = "", config: LLMConfig | None = None):
        self._config = config or LLMConfig(api_key=api_key)
        self.api_key = api_key
        self.messages = _MessagesProxy(self._config, api_key)
