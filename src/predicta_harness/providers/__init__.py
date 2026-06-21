"""Harness providers. Built-in: anthropic, openai (and OpenAI-compatible)."""

from .base import Provider, register_provider, resolve

__all__ = ["Provider", "register_provider", "resolve"]
