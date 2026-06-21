"""
tool.py — The @tool decorator and the Tool class.

Define a plain Python function with type hints + docstring, and @tool turns it into
a tool the model can call: it infers the JSON Schema of the parameters (with pydantic)
and uses the docstring as the description.

    @tool
    def get_weather(city: str, units: str = "celsius") -> str:
        "Return the weather for a city."
        ...

The Agent runs the tool automatically when the model asks for it; you never write
any `if name == "...":` dispatch by hand.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_type_hints

from pydantic import create_model


def object_input_schema(json_schema: dict) -> dict:
    """
    Turn a pydantic ``model_json_schema()`` into a tool input_schema.

    Keeps ``properties``, ``required`` and — critically — ``$defs``. Fields typed
    as an Enum or a nested model produce a ``$ref`` into ``$defs``; dropping
    ``$defs`` would leave a dangling reference that providers reject.
    """
    schema: dict = {"type": "object", "properties": json_schema.get("properties", {})}
    if json_schema.get("required"):
        schema["required"] = json_schema["required"]
    if json_schema.get("$defs"):  # nested models / Enum fields live here
        schema["$defs"] = json_schema["$defs"]
    return schema


class Tool:
    """Wraps a function as a tool the model can invoke."""

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

        # Build a dynamic pydantic model from the function parameters to derive the
        # JSON Schema. Each parameter contributes (type, default).
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
        input_schema = object_input_schema(model.model_json_schema())
        return cls(fn, tool_name, tool_desc, input_schema)

    def run(self, inputs: dict[str, Any]) -> str:
        """Run the function with the model's arguments and return a string."""
        result = self.fn(**inputs)
        return result if isinstance(result, str) else str(result)


def tool(
    fn: Callable | None = None, *, name: str | None = None, description: str | None = None
):
    """Decorator. Usage: `@tool` or `@tool(name=..., description=...)`."""
    def wrap(f: Callable) -> Tool:
        return Tool.from_function(f, name=name, description=description)

    return wrap(fn) if fn is not None else wrap
