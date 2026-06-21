"""Providers del harness. Built-in: anthropic, openai (y OpenAI-compatible)."""

from .base import Provider, register_provider, resolve

__all__ = ["Provider", "register_provider", "resolve"]
