"""
agent.py — El Agent y el run-loop. El corazón del harness.

Esto es lo que en `ai_service.py` era el `while True` con `messages.create` +
`stop_reason` + `_execute_tool` hecho a mano: ahora vive aquí, una sola vez,
provider-agnostic. El usuario solo define tools y un system prompt.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .providers.base import Provider, resolve
from .tool import Tool
from .types import RunResult, Usage

_SUBMIT_NAME = "submit_result"


def _noop(**_kwargs: Any) -> str:  # la submit tool nunca se ejecuta; se intercepta
    return ""


class Agent:
    """
    Un agente = modelo + system prompt + tools. Su método `run()` ejecuta el
    bucle de tool-use automáticamente hasta que el modelo da una respuesta final.

        agent = Agent(model="anthropic/claude-sonnet-4-6", system="...", tools=[...])
        result = agent.run("haz X")
        print(result.text, result.usage)
    """

    def __init__(
        self,
        model: str,
        system: str = "",
        tools: list[Tool] | None = None,
        *,
        max_tokens: int = 2048,
        max_steps: int = 12,
        on_tool: Callable[[str, dict, str], None] | None = None,
        tool_interceptor: Callable[[str, dict], str | None] | None = None,
    ):
        self.provider, self.model_id = resolve(model)
        self.model_spec = model
        self.system = system
        self.max_tokens = max_tokens
        self.max_steps = max_steps
        # Hook de observabilidad: se llama tras ejecutar cada tool (auditoría/log).
        self.on_tool = on_tool
        # Hook de control: si devuelve un str, ese es el resultado de la tool SIN
        # ejecutarla (para confirmaciones humanas tipo draft/confirm del bot Telegram).
        self.tool_interceptor = tool_interceptor

        tools = tools or []
        self._tools: dict[str, Tool] = {t.name: t for t in tools}
        self._tool_list = list(tools)

    def run(
        self,
        message: str,
        history: list | None = None,
        result_schema: type[BaseModel] | None = None,
        **provider_kwargs: Any,
    ) -> RunResult:
        """
        Ejecuta el agente. Si `result_schema` (un modelo Pydantic) se pasa, el agente
        DEBE terminar llamando a la tool sintética `submit_result` con datos válidos;
        el objeto validado se devuelve en `RunResult.data`. Si los datos no validan,
        se le devuelve el error al modelo para que reintente (robusto con modelos locales).
        """
        messages: list = list(history or []) + [{"role": "user", "content": message}]
        usage = Usage(model=self.model_id)
        final_text = ""
        data: BaseModel | None = None
        steps = 0

        # Con structured output, añadimos la submit tool e instruimos al modelo.
        tools = self._tool_list
        system = self.system
        if result_schema is not None:
            tools = self._tool_list + [self._build_submit_tool(result_schema)]
            system = (system + "\n\n" if system else "") + (
                f"Cuando tengas la respuesta final, DEBES llamar a la tool "
                f"'{_SUBMIT_NAME}' rellenando TODOS sus campos. Es la única forma de "
                f"terminar; no respondas en texto plano."
            )

        done = False
        while steps < self.max_steps and not done:
            turn = self.provider.complete(
                model_id=self.model_id,
                system=system,
                messages=messages,
                tools=tools,
                max_tokens=self.max_tokens,
                **provider_kwargs,
            )
            usage.add(turn.usage)
            steps += 1
            messages.append({"role": "assistant", "content": turn.content_blocks})

            if turn.stop_reason != "tool_use" or not turn.tool_calls:
                final_text = turn.text
                if result_schema is None or data is not None:
                    break
                # Esperábamos submit_result y respondió en texto: se lo recordamos.
                messages.append({"role": "user", "content":
                                 f"Falta la respuesta estructurada: llama a '{_SUBMIT_NAME}'."})
                continue

            result_blocks: list[dict] = []
            for call in turn.tool_calls:
                if result_schema is not None and call.name == _SUBMIT_NAME:
                    try:
                        data = result_schema.model_validate(call.input)
                        final_text = turn.text
                        output, is_error = "Resultado registrado correctamente.", False
                        done = True
                    except ValidationError as e:
                        # Reintento: devolvemos el error para que el modelo corrija.
                        output, is_error = (
                            f"Validación fallida, corrige y vuelve a llamar "
                            f"'{_SUBMIT_NAME}':\n{e}", True,
                        )
                else:
                    output, is_error = self._dispatch(call.name, call.input)

                block = {"type": "tool_result", "tool_use_id": call.id, "content": output}
                if is_error:
                    block["is_error"] = True
                result_blocks.append(block)
                if self.on_tool:
                    self.on_tool(call.name, call.input, output)

            messages.append({"role": "user", "content": result_blocks})

        if steps >= self.max_steps and not final_text and data is None:
            final_text = "[predicta-harness] max_steps alcanzado sin respuesta final."

        return RunResult(
            text=(final_text or "").strip(), usage=usage,
            messages=messages, steps=steps, data=data,
        )

    def _build_submit_tool(self, schema_model: type[BaseModel]) -> Tool:
        """Crea la tool sintética cuyo input es el JSON Schema del modelo Pydantic."""
        js = schema_model.model_json_schema()
        input_schema: dict[str, Any] = {"type": "object", "properties": js.get("properties", {})}
        if js.get("required"):
            input_schema["required"] = js["required"]
        if js.get("$defs"):  # tipos anidados / enums (Literal) viven aquí
            input_schema["$defs"] = js["$defs"]
        fields = ", ".join(js.get("properties", {}).keys())
        desc = f"Entrega la respuesta final estructurada. Rellena todos los campos: {fields}."
        return Tool(_noop, _SUBMIT_NAME, desc, input_schema)

    def _dispatch(self, name: str, inputs: dict) -> tuple[str, bool]:
        """Ejecuta una tool (o la intercepta). Devuelve (output, is_error)."""
        if self.tool_interceptor is not None:
            intercepted = self.tool_interceptor(name, inputs)
            if intercepted is not None:
                return intercepted, False

        tool = self._tools.get(name)
        if tool is None:
            return f"Tool desconocida: {name}", True
        try:
            return tool.run(inputs), False
        except Exception as e:  # una tool que falla no debe tumbar el loop
            return f"Error ejecutando {name}: {type(e).__name__}: {e}", True
