# predicta-harness

A provider-agnostic agent harness for Python: the agent loop, `@tool`, structured output,
sandboxed code execution and a small service, over Claude, OpenAI-compatible endpoints or a
local model — the same agent code, one string changed. `README.md` is the user-facing
description and stays the place to start.

This file is the other half: what this repository promises about **itself**, and what breaks
if a change quietly stops one of those promises being true.

---

## What it is becoming

A **base for governed development projects**, with two ways to drive it — under Claude Code
(hooks, skills, subagents), or through this package's own loop over any provider — and no
logic that belongs to only one of them.

Two consequences, and they are load-bearing rather than aspirational:

- **Nothing in this package may name a consumer.** Not a project, not a domain, not a metric,
  not a company. A package that knows its consumer's vocabulary is a monolith with a version
  number on it.
- **What is *installed* here is mechanism; what a project writes for itself is policy.** A
  floor, a set of actions, a doctrine and a `CLAUDE.md` belong to the project that measured
  them. The runner that enforces them belongs here.

The spec driving that direction is `specs/harness-base/` in the private `predicta-lite`
repository; the tasks that land here are marked so.

---

## The boundary, and it is a number rather than a rule

`anthropic` and `openai` are **optional extras**. The base package must import neither at
module level — a module-level import turns an extra into a requirement for everybody who
installs the base package, and it does it silently: the failure surfaces at import time, in
whatever process happens to run first.

Measured by walking the AST of every file under `src/`, deferred imports included:

| | Count |
|---|---:|
| Provider imports at module level | **0** |
| Provider imports deferred inside a function | **4** |

Both are **exact** in `RATCHET.json`, not floors. A module-level import appearing is a
regression; a deferred one disappearing is a change somebody should have to explain. Only an
exact count makes both directions show up in a diff.

---

## Hard rules

1. **The base install imports no provider SDK.** `python ratchet.py --check` walks the AST and
   goes red on the first module-level import. It is not a review comment.

2. **The Anthropic ceiling is not lifted without a port.** `pyproject.toml` caps
   `anthropic>=0.40,<1.0`. The SDK's 1.0 removed `temperature` from `messages.create` and
   reorganised the signature; an unbounded `>=0.40` let it into a production image on
   2026-08-21 and a client-facing job judged 0 of 1 798 matches before dying on its first call.

   **Two guards, because one of them cannot run everywhere:**

   - `tests/test_anthropic_sdk_pin.py` introspects `messages.create` on the **installed** SDK.
     It is the better test and it needs the extra present, so it skips on a base install — and
     it used to skip in CI too, which is green for the same reason a deleted test is green.
     The `providers` job installs the extra and sets `HARNESS_REQUIRE_PROVIDER_EXTRAS=1`, which
     turns that skip into a failure.
   - `tests/test_declared_pin.py` checks the **declared** string in `pyproject.toml`, imports
     nothing but the standard library, and therefore can never be the test that skipped. It
     also refuses to let the two places the pin is written drift apart — `anthropic` and `all`
     both declare it, and half a lifted ceiling is how the bound stops depending on the pin and
     starts depending on which extra the consumer installed.

3. **Never lower a floor to unblock yourself.** Not a test, not a threshold, not the suite's
   time ceiling. `RATCHET.json` documents the tolerance and where it came from; if the ceiling
   fires, make the suite faster. Report it and stop.

4. **A skip is not a pass.** `tests_skipped_without_provider_extras` is an **exact** count with
   every skip named in `RATCHET.json`, because an unnamed skip is how a guard stops running
   without anybody deciding it should.

---

## Language

**English** — code, identifiers, comments, docstrings, docs, commit messages. This repository
is public and its audience is not only its author.

Three places do not comply today, measured rather than assumed, and they are **not** silently
rewritten:

| Where | What | Why it is still here |
|---|---|---|
| `src/predicta_harness/sandbox/tools.py:77` | a Spanish string returned by `delete_file` | it is tool output a model reads; changing it changes behaviour and wants its own measurement |
| `src/predicta_harness/service/app.py:54` | a Spanish fragment of the work system prompt | same — prompt text is behaviour |
| `tests/test_anthropic_sdk_pin.py` | Spanish identifiers | free to rename, and the only one of the three that is purely cosmetic |

New code is English. These three are a debt with a reason, not a precedent.

---

## Running it

```bash
pip install -e ".[test]"        # base install: pydantic + pytest, NO provider SDK
python ratchet.py --check       # runs the suite AND checks every floor against it
python ratchet.py --raise       # write the measurement back; refuses to lower a floor
```

`--check` subsumes `pytest`: it runs the suite itself and then measures. Running both runs the
same suite twice.

With the providers, which is a different environment and a different set of numbers:

```bash
pip install -e ".[all,test]"
HARNESS_REQUIRE_PROVIDER_EXTRAS=1 pytest tests/test_anthropic_sdk_pin.py -q
```

CI runs all three environments — base, providers, and the interpreters `requires-python`
claims — in `.github/workflows/ci.yml`.

---

## Where the truth lives

| Question | Source |
|---|---|
| What the package does, and how to use it | `README.md` |
| What it can prove about itself, in numbers | `RATCHET.json`, produced by `ratchet.py` |
| Why the Anthropic dependency has a ceiling | the comment above the extras in `pyproject.toml`, and the two tests that enforce it |
| What the sandbox is for and what it refuses | `specs/sandbox/` |
| What runs, in which environment, and why those are separate | `.github/workflows/ci.yml` |
