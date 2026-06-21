# predicta-harness

**A provider-agnostic agent harness for Python.** El patrón de Claude Code / Flue
(agent loop + tools + sesiones), pero en **Python** y **sin atarte a un proveedor
de modelo**: el mismo agente corre sobre Claude, OpenAI o un LLM local con solo
cambiar un string.

> Nace para dejar de reescribir a mano el `while True` de tool-use en cada proyecto.

## Por qué existe (el hueco)

| | Atado a | Lenguaje | Provider-agnostic |
|---|---|---|---|
| **Claude Agent SDK** | Claude | Python / TS | ❌ (centrado en Claude) |
| **Flue** | — | TypeScript | ✅ |
| **predicta-harness** | — | **Python** | **✅** |

Ni el Agent SDK (atado a Claude) ni Flue (TypeScript) cubren *"harness multi-proveedor
en Python"*. Eso es esto.

## Instalación

```bash
pip install -e ".[all]"          # editable, con anthropic + openai
# o por proveedor: pip install -e ".[anthropic]"
```

## Quickstart

```python
from predicta_harness import Agent, tool

@tool
def get_saldo(cuenta: str) -> str:
    "Devuelve el saldo de una cuenta bancaria."
    return {"AHORROS": "12.450 €"}.get(cuenta.upper(), "no encontrada")

agent = Agent(
    model="anthropic/claude-sonnet-4-6",   # or "openai/gpt-4o", or "local/llama3.1:8b"
    system="Eres un asistente bancario. Usa las tools, no inventes cifras.",
    tools=[get_saldo],
)
r = agent.run("¿Cuánto tengo en ahorros?")
print(r.text, r.usage)            # el loop de tool-use es automático
```

### Local models / other providers (OpenAI-compatible)

```python
from predicta_harness import register_provider
from predicta_harness.providers.openai import OpenAIProvider

register_provider("local", OpenAIProvider(
    base_url="http://localhost:11434/v1",   # Ollama
    api_key="ollama",
))
agent = Agent(model="local/llama3.1:8b", tools=[get_balance], system="...")
```

Same pattern for vLLM, LM Studio, DeepSeek, OpenRouter, etc. (point `base_url`
at any OpenAI-compatible endpoint; pass a custom `http_client` for self-signed TLS).

## Conceptos

- **`@tool`** — decora una función con type hints; el schema JSON se infiere solo.
- **`Agent`** — modelo + system + tools. `run(message, history=None)` ejecuta el loop.
- **`Provider`** — abstracción del backend. Built-in: `anthropic`, `openai` (+ compatibles).
- **`RunResult`** — `.text`, `.usage` (tokens + coste), `.messages` (historial), `.steps`.
- **Hooks**: `on_tool(name, inputs, output)` para auditoría; `tool_interceptor(name, inputs)`
  para intervenir una tool sin ejecutarla (p.ej. pedir confirmación humana).

## Estado / roadmap

- [x] **v0.1** — agent loop, `@tool`, providers Anthropic + OpenAI(-compatible), usage/coste, hooks.
- [x] **v0.2** — structured output: `run(..., result_schema=Modelo)` → `RunResult.data` validado.
  Forzado vía tool-calling (`submit_result`) + reintento si la validación falla. Robusto con
  modelos locales (donde Mastra dejaba campos vacíos). Ejemplo: `examples/structured.py`.
- [ ] v0.3 — sesiones persistentes + compactación de contexto automática.
- [ ] v0.4 — sandbox opcional (ejecución de código aislada) y MCP.

### Structured output (v0.2)

```python
from pydantic import BaseModel
class Brief(BaseModel):
    asunto: str
    acciones: list[str]
    prioridad: str

r = agent.run("Resume este correo: ...", result_schema=Brief)
print(r.data.prioridad)   # objeto Brief validado; reintenta solo si el modelo se equivoca
```

## Licencia

MIT.
