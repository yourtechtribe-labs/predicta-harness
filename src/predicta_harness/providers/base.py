"""
base.py — La abstracción Provider.

Un Provider sabe hablar con UN backend (Anthropic, OpenAI, OpenAI-compatible...).
Recibe el historial en formato canónico + las tools + el system prompt, y devuelve
un AssistantTurn normalizado. El Agent (y el loop) son agnósticos del proveedor:
ESTE es el punto del framework.

Registro de modelos: un model-spec es "provider/model-id" (ej. "anthropic/claude-sonnet-4-6").
`resolve_provider()` mapea el prefijo a una instancia de Provider.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..tool import Tool
from ..types import AssistantTurn, Message


class Provider(ABC):
    """Interfaz que todo backend de modelo debe implementar."""

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
        """Una llamada al modelo. Devuelve el turno normalizado."""
        raise NotImplementedError


# --- Registro provider-id -> instancia ------------------------------------

_REGISTRY: dict[str, Provider] = {}


def register_provider(provider_id: str, provider: Provider) -> None:
    """Registra (o reemplaza) un provider bajo un id usado en el model-spec."""
    _REGISTRY[provider_id] = provider


def resolve(model_spec: str) -> tuple[Provider, str]:
    """
    "anthropic/claude-sonnet-4-6" -> (AnthropicProvider, "claude-sonnet-4-6").
    Registra los providers built-in de forma perezosa la primera vez.
    """
    if "/" not in model_spec:
        raise ValueError(
            f'model debe ser "provider/model-id", recibido: {model_spec!r}. '
            f'Ej: "anthropic/claude-sonnet-4-6" o "local/llama3.1:8b".'
        )
    provider_id, model_id = model_spec.split("/", 1)

    if provider_id not in _REGISTRY:
        _autoregister(provider_id)

    if provider_id not in _REGISTRY:
        raise ValueError(
            f'Provider "{provider_id}" no registrado. Regístralo con '
            f"register_provider('{provider_id}', ...) antes de usarlo."
        )
    return _REGISTRY[provider_id], model_id


def _autoregister(provider_id: str) -> None:
    """Built-ins: 'anthropic' y 'openai' se registran solos al primer uso."""
    if provider_id == "anthropic":
        from .anthropic import AnthropicProvider
        register_provider("anthropic", AnthropicProvider())
    elif provider_id == "openai":
        from .openai import OpenAIProvider
        register_provider("openai", OpenAIProvider())
    # Cualquier otro id (ej. "local", "ollama", "deepseek") debe registrarlo el usuario
    # con un OpenAIProvider apuntando a su baseURL. Ver README.
