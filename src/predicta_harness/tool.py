"""
tool.py — El decorador @tool y la clase Tool.

Defines una función Python normal con type hints + docstring, y `@tool` la
convierte en una herramienta que el modelo puede invocar: infiere el JSON Schema
de los parámetros (con pydantic) y usa el docstring como descripción.

    @tool
    def get_weather(city: str, units: str = "celsius") -> str:
        "Devuelve el tiempo de una ciudad."
        ...

El Agent ejecuta la tool automáticamente cuando el modelo la pide; tú no escribes
ningún `if name == "...":` (eso lo hacía a mano ai_service.py).
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from pydantic import create_model


class Tool:
    """Envuelve una función como herramienta invocable por el modelo."""

    def __init__(self, fn: Callable, name: str, description: str, input_schema: dict):
        self.fn = fn
        self.name = name
        self.description = description
        self.input_schema = input_schema

    @classmethod
    def from_function(
        cls, fn: Callable, *, name: str | None = None, description: str | None = None
    ) -> "Tool":
        tool_name = name or fn.__name__
        tool_desc = description or (inspect.getdoc(fn) or "").strip()

        # Construimos un modelo pydantic dinámico con los parámetros de la función
        # para derivar el JSON Schema. Cada parámetro aporta (tipo, default).
        sig = inspect.signature(fn)
        hints = get_type_hints(fn)
        fields: dict[str, Any] = {}
        for pname, param in sig.parameters.items():
            if pname in ("self", "cls"):
                continue
            annotation = hints.get(pname, str)
            default = param.default if param.default is not inspect.Parameter.empty else ...
            fields[pname] = (annotation, default)

        model = create_model(f"{tool_name}_Args", **fields)  # type: ignore[call-overload]
        schema = model.model_json_schema()
        # Anthropic/OpenAI quieren un object schema plano con properties/required.
        input_schema = {
            "type": "object",
            "properties": schema.get("properties", {}),
        }
        if schema.get("required"):
            input_schema["required"] = schema["required"]

        return cls(fn, tool_name, tool_desc, input_schema)

    def run(self, inputs: dict[str, Any]) -> str:
        """Ejecuta la función con los argumentos del modelo y devuelve un string."""
        result = self.fn(**inputs)
        return result if isinstance(result, str) else str(result)


def tool(
    fn: Callable | None = None, *, name: str | None = None, description: str | None = None
):
    """Decorador. Uso: `@tool` o `@tool(name=..., description=...)`."""
    def wrap(f: Callable) -> Tool:
        return Tool.from_function(f, name=name, description=description)

    return wrap(fn) if fn is not None else wrap
