"""
types.py — Tipos normalizados del harness, independientes del proveedor.

El "formato canónico" de mensajes es deliberadamente *Anthropic-like* (bloques
`text` / `tool_use` / `tool_result`), porque es el más limpio. Cada Provider
traduce de/a su propia API desde este formato. Así el Agent y el loop nunca
saben con qué proveedor hablan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# Un mensaje canónico: role + content. content puede ser un string simple
# (atajo para texto) o una lista de bloques (dicts) como los de Anthropic.
Role = Literal["user", "assistant"]
Message = dict[str, Any]  # {"role": Role, "content": str | list[Block]}
Block = dict[str, Any]    # {"type": "text"|"tool_use"|"tool_result", ...}


@dataclass
class ToolCall:
    """Una petición del modelo para ejecutar una tool (sigue siendo solo texto)."""
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Usage:
    """Contabilidad de tokens y coste de una ejecución (acumulable)."""
    model: str = ""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens
        self.cost_usd += other.cost_usd

    def __str__(self) -> str:
        tin = self.input_tokens + self.cache_read_tokens + self.cache_write_tokens
        return f"{tin}->{self.output_tokens} tok · ${self.cost_usd:.4f} · {self.calls} call(s)"


@dataclass
class AssistantTurn:
    """
    Resultado normalizado de UNA llamada al modelo (un turno del asistente).
    Lo devuelve cada Provider.complete(); el Agent no toca la API cruda.
    """
    text: str
    tool_calls: list[ToolCall]
    content_blocks: list[Block]   # contenido del assistant en formato canónico (para el historial)
    usage: Usage
    stop_reason: str              # "end_turn" | "tool_use" | otro


@dataclass
class RunResult:
    """Lo que devuelve Agent.run(): el texto final + telemetría + historial completo."""
    text: str
    usage: Usage
    messages: list[Message] = field(default_factory=list)
    steps: int = 0                # cuántas vueltas dio el loop (llamadas al modelo)
    data: Any = None              # objeto validado, si se pasó result_schema (structured output)
