# predicta-harness

**A provider-agnostic agent harness for Python.** The Claude Code / Flue pattern
(agent loop + tools + sessions), but in **Python** and **not tied to a single model
provider**: the same agent runs over Claude, OpenAI or a local LLM by changing one
string.

> Built to stop rewriting the tool-use `while True` loop by hand in every project.

## Why it exists (the gap)

| | Tied to | Language | Provider-agnostic |
|---|---|---|---|
| **Claude Agent SDK** | Claude | Python / TS | ❌ (Claude-centric) |
| **Flue** | — | TypeScript | ✅ |
| **predicta-harness** | — | **Python** | **✅** |

Neither the Agent SDK (tied to Claude) nor Flue (TypeScript) cover *"multi-provider
harness in Python"*. That's this.

## Governance: the prompt is a model artifact

An agent's system prompt, operating manual, accumulated "learnings" and tool set decide
what it does, and all four are text files anyone can edit in ten seconds. `governance.py`
applies the six controls a bank applies to a model (the Model Risk Management discipline
codified in the Fed's SR 11-7, run over three lines of defence) to those files instead:

```python
from predicta_harness import Agent
from predicta_harness.governance import Governance, Manifest

manifest = Manifest("governance/manifest.json")
manifest.register("system", kind="system", text=SYSTEM)
manifest.approve("system", by="albert", validation_ref="replay:test:24/24",
                 review_by="2026-12-12")            # an approval MUST cite its evidence

agent = Agent(model="anthropic/claude-sonnet-5", system=SYSTEM, tools=TOOLS,
              governance=Governance(manifest, env="prod",
                                    protected=["skills/operator/SKILL.md"]))
```

| Control | What it does | Fails how |
|---|---|---|
| Inventory | every governed artifact in the manifest, by content hash | `status()` returns `unregistered` |
| Tiering | `tier_for(tool)` **derives** the tier from the effects a tool declares (`@tool(effects="read")`); saying nothing means the higher tier | a tool nobody classified is `critical`, never `standard` |
| Independent validation | `approve()` requires a `validation_ref` | `GovernanceError` on approval |
| Approval | `env="prod"` refuses to build an `Agent` on an unapproved prompt (other envs warn) | `GovernanceError` at construction |
| Change control | an edit changes the hash, which revokes approval by itself | status `changed` |
| Monitoring | `review_flags(tools, calls)` derives which tools nobody calls, above an evidence threshold | a flag, not a sentence in a doc |

Plus two hard guarantees: **no tool may declare write access to a governed artifact**
(checked when the `Agent` is built, by comparing declared `writes` paths — structural,
not a guess about what a tool looks like it does), and a call that smuggles a governed
path through its arguments is **refused at run time** by an interceptor chained ahead of
your own.

Why it exists: an agent that can edit its own instructions optimises the signal it sees.
In a 2026 benchmark of self-improving code agents, 73.8% of Kernel-Bench optimisations
gained on the observed metric without gaining on the task. The fix is not to forbid
learning: it is to let the agent **propose** and keep promotion with a human, and to make
that a property of the code rather than a line in a document. Everything above is opt-in:
without `governance=`, `Agent` behaves exactly as before.

## Install

```bash
pip install -e ".[all]"          # editable, with anthropic + openai
# or per provider: pip install -e ".[anthropic]"
```

## Quickstart

```python
from predicta_harness import Agent, tool

@tool
def get_balance(account: str) -> str:
    "Return the balance of an account."
    return {"SAVINGS": "12,450 EUR"}.get(account.upper(), "not found")

agent = Agent(
    model="anthropic/claude-sonnet-4-6",   # or "openai/gpt-4o", or "local/llama3.1:8b"
    system="You are a banking assistant. Use the tools, don't invent figures.",
    tools=[get_balance],
)
r = agent.run("How much do I have in savings?")
print(r.text, r.usage)            # the tool-use loop is automatic
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

Validated end-to-end on three backends: **Anthropic (Claude)**, an **OpenAI-compatible
vLLM** endpoint, and **Ollama** (gemma) — same agent code, only the model string changes.

## Concepts

- **`@tool`** — decorate a function with type hints; the JSON schema is inferred.
- **`Agent`** — model + system + tools. `run(message, history=None)` executes the loop.
- **`Provider`** — backend abstraction. Built-in: `anthropic`, `openai` (+ compatible).
- **`RunResult`** — `.text`, `.usage` (tokens + cost), `.messages` (history), `.steps`, `.data`.
- **Hooks**: `on_tool(name, inputs, output)` for audit; `tool_interceptor(name, inputs)`
  to step in on a tool without running it (e.g. ask for human confirmation).

## Structured output

```python
from pydantic import BaseModel

class Invoice(BaseModel):
    vendor: str
    amount_eur: float
    payment_priority: str

r = agent.run("Extract the invoice fields: ...", result_schema=Invoice)
print(r.data.vendor)   # validated Invoice object; retries only if the model is wrong
```

The schema is forced via tool-calling (a synthetic `submit_result` tool) and the
harness retries if validation fails — robust even with small local models.

## Status / roadmap

- [x] **v0.1** — agent loop, `@tool`, Anthropic + OpenAI(-compatible) providers, usage/cost, hooks.
- [x] **v0.2** — structured output: `run(..., result_schema=Model)` -> validated `RunResult.data`.
- [ ] v0.3 — persistent sessions + automatic context compaction.
- [ ] v0.4 — optional sandbox (isolated code execution) and MCP.

## Examples

- `examples/quickstart.py` — same agent + tool over Claude and a local model.
- `examples/structured.py` — structured extraction (invoice -> validated Pydantic object).

## License

MIT.
