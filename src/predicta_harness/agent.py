"""
agent.py — The Agent and the run-loop. The heart of the harness.

This is what in a hand-rolled client was the `while True` with `messages.create` +
`stop_reason` + a manual tool dispatch: it now lives here, once, provider-agnostic.
The user only defines tools and a system prompt.
"""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from .providers.base import Provider, resolve
from .tool import Tool, object_input_schema
from .types import RunResult, Usage

_SUBMIT_NAME = "submit_result"


def _noop(**_kwargs: Any) -> str:  # the submit tool is never executed; it is intercepted
    return ""


class Agent:
    """
    An agent = model + system prompt + tools. Its `run()` method executes the
    tool-use loop automatically until the model produces a final answer.

        agent = Agent(model="anthropic/claude-sonnet-4-6", system="...", tools=[...])
        result = agent.run("do X")
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
        # Observability hook: called after each tool runs (audit/log).
        self.on_tool = on_tool
        # Control hook: if it returns a str, that becomes the tool result WITHOUT
        # running the tool (for human confirmations such as draft/confirm flows).
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
        Run the agent. If `result_schema` (a Pydantic model) is passed, the agent
        MUST finish by calling the synthetic `submit_result` tool with valid data;
        the validated object is returned in `RunResult.data`. If the data does not
        validate, the error is sent back to the model so it retries (robust with
        small local models).
        """
        messages: list = list(history or []) + [{"role": "user", "content": message}]
        usage = Usage(model=self.model_id)
        final_text = ""
        data: BaseModel | None = None
        steps = 0

        # With structured output, add the submit tool and instruct the model.
        tools = self._tool_list
        system = self.system
        if result_schema is not None:
            tools = self._tool_list + [self._build_submit_tool(result_schema)]
            system = (system + "\n\n" if system else "") + (
                f"When you have the final answer, you MUST call the '{_SUBMIT_NAME}' "
                f"tool filling in ALL its fields. It is the only way to finish; "
                f"do not answer in plain text."
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
                # We expected submit_result but it answered in text: remind it.
                messages.append({"role": "user", "content":
                                 f"Missing the structured answer: call '{_SUBMIT_NAME}'."})
                continue

            result_blocks: list[dict] = []
            for call in turn.tool_calls:
                if result_schema is not None and call.name == _SUBMIT_NAME:
                    try:
                        data = result_schema.model_validate(call.input)
                        final_text = turn.text
                        output, is_error = "Result recorded successfully.", False
                        done = True
                    except ValidationError as e:
                        # Retry: hand the error back so the model can fix it.
                        output, is_error = (
                            f"Validation failed, fix it and call '{_SUBMIT_NAME}' "
                            f"again:\n{e}", True,
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
            final_text = "[predicta-harness] max_steps reached without a final answer."

        return RunResult(
            text=(final_text or "").strip(), usage=usage,
            messages=messages, steps=steps, data=data,
        )

    def _build_submit_tool(self, schema_model: type[BaseModel]) -> Tool:
        """Create the synthetic tool whose input is the Pydantic model's JSON Schema."""
        js = schema_model.model_json_schema()
        input_schema = object_input_schema(js)
        fields = ", ".join(js.get("properties", {}).keys())
        desc = f"Submit the final structured answer. Fill in all fields: {fields}."
        return Tool(_noop, _SUBMIT_NAME, desc, input_schema)

    def _dispatch(self, name: str, inputs: dict) -> tuple[str, bool]:
        """Run a tool (or intercept it). Returns (output, is_error)."""
        if self.tool_interceptor is not None:
            intercepted = self.tool_interceptor(name, inputs)
            if intercepted is not None:
                return intercepted, False

        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown tool: {name}", True
        try:
            return tool.run(inputs), False
        except Exception as e:  # a failing tool must not crash the loop
            return f"Error running {name}: {type(e).__name__}: {e}", True
