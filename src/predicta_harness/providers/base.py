"""
base.py — The Provider abstraction.

A Provider knows how to talk to ONE backend (Anthropic, OpenAI, OpenAI-compatible...).
It receives the history in canonical format + the tools + the system prompt, and
returns a normalized AssistantTurn. The Agent (and the loop) are provider-agnostic:
THIS is the point of the framework.

Model registry: a model-spec is "provider/model-id" (e.g. "anthropic/claude-sonnet-4-6").
`resolve()` maps the prefix to a Provider instance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..tool import Tool
from ..types import AssistantTurn, Message


class Provider(ABC):
    """Interface that every model backend must implement."""

    @abstractmethod
    def complete(
        self,
        *,
        model_id: str,
        system: str,
        messages: list[Message],
        tools: list[Tool],
        max_tokens: int = 2048,
        **kwargs: Any,
    ) -> AssistantTurn:
        """One model call. Returns the normalized turn."""
        raise NotImplementedError


# --- provider-id -> instance registry -------------------------------------

_REGISTRY: dict[str, Provider] = {}


def register_provider(provider_id: str, provider: Provider) -> None:
    """Register (or replace) a provider under an id used in the model-spec."""
    _REGISTRY[provider_id] = provider


def resolve(model_spec: str) -> tuple[Provider, str]:
    """
    "anthropic/claude-sonnet-4-6" -> (AnthropicProvider, "claude-sonnet-4-6").
    Lazily registers the built-in providers the first time.
    """
    if "/" not in model_spec:
        raise ValueError(
            f'model must be "provider/model-id", got: {model_spec!r}. '
            f'e.g. "anthropic/claude-sonnet-4-6" or "local/llama3.1:8b".'
        )
    provider_id, model_id = model_spec.split("/", 1)

    if provider_id not in _REGISTRY:
        _autoregister(provider_id)

    if provider_id not in _REGISTRY:
        raise ValueError(
            f'Provider "{provider_id}" not registered. Register it with '
            f"register_provider('{provider_id}', ...) before use."
        )
    return _REGISTRY[provider_id], model_id


def _autoregister(provider_id: str) -> None:
    """Built-ins: 'anthropic' and 'openai' register themselves on first use."""
    if provider_id == "anthropic":
        from .anthropic import AnthropicProvider
        register_provider("anthropic", AnthropicProvider())
    elif provider_id == "openai":
        from .openai import OpenAIProvider
        register_provider("openai", OpenAIProvider())
    # Any other id (e.g. "local", "ollama", "deepseek") must be registered by the
    # user with an OpenAIProvider pointing at its base_url. See README.
