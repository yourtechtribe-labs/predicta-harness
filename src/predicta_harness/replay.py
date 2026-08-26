"""Run a corpus of cases against an `Agent`, offline, without touching a consumer's
production infrastructure. `Case`/`load_corpus` describe the input; `replay` runs it."""

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Case:
    """One case: the input handed to the agent, nothing more.

    `context` is an opaque bag for the caller — whoever consumes the `Verdict` stores
    whatever it needs there (e.g. an expected outcome), so `replay()` never has to know
    that vocabulary.
    """

    case_id: str
    message: str
    history: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)


def load_corpus(raw_cases: Iterable[dict]) -> tuple[Case, ...]:
    """Build a corpus from raw dicts (e.g. read from JSON/JSONL)."""
    return tuple(Case(**raw) for raw in raw_cases)


@dataclass(frozen=True, slots=True)
class Verdict:
    """The result of running one `Case`. `outcome` is deliberately generic
    (`"ok"`/`"failed"`) — the business interpretation (e.g. "responded"/"escalated") is
    for whoever consumes `response`; this module does not know that vocabulary."""

    case_id: str
    outcome: str
    response: str | None = None
    error: str | None = None


def replay(agent, corpus: Iterable[Case]) -> list[Verdict]:
    """Run `agent.run()` for every case and return one verdict per case.

    Opens no network connection of its own: it runs exactly what `agent.run()` does. With
    a fake/stub in a test, the whole replay runs offline.
    """
    verdicts = []
    for case in corpus:
        try:
            result = agent.run(case.message, history=case.history)
            # `Agent.run()` returns a `RunResult`; a duck-typed test double may just
            # return a string. Accept both without requiring callers to unwrap it.
            response_text = getattr(result, "text", result)
            verdicts.append(Verdict(case_id=case.case_id, outcome="ok", response=response_text))
        except Exception as exc:  # noqa: BLE001 — one bad case must not sink the whole corpus
            verdicts.append(Verdict(case_id=case.case_id, outcome="failed", error=str(exc)))
    return verdicts
