"""
usage.py — Per-model cost calculation (USD per 1M tokens).

Three things this module refuses to do, each for a reason that has already cost
somebody time:

1. **It never reports 0.0 for a model it does not know.** A local model
   (Ollama, vLLM, LM Studio) legitimately costs zero, so a silent zero for an
   unknown model is indistinguishable from a correct one — and the wrong one is
   the cheaper-looking of the two, which is exactly the direction nobody
   double-checks. `cost_for()` returns `None` for "I have no price for this",
   and callers are expected to carry that through rather than coerce it.

2. **It does not hand-maintain numbers it can derive.** Anthropic's cache rates
   are a fixed multiple of the input price (write 1.25x at the 5-minute TTL,
   read 0.10x), so they are computed from it. Four hand-typed columns per model
   is four chances for the cache rate to disagree with the input rate after an
   edit; one is zero.

3. **It does not bury a promotional price as a plain number.** An introductory
   rate with an end date, written as a bare figure with a comment, silently
   overcharges — or undercharges — from the day it lapses. `INTRODUCTORY`
   carries the expiry in the data, and `cost_for(..., on=...)` selects against a
   date the caller can pin.

Prices verified against the Anthropic pricing table on the date below. This
table is a snapshot; the price of a model is not a fact about the code, and the
previous version of this file sat two model generations behind (`claude-opus-4-8`
as the newest Opus, no Opus 5, no Sonnet 5) with nothing to signal it.
"""

from __future__ import annotations

from datetime import date, datetime, timezone


def _today() -> date:
    """Today in UTC — never the machine's local date.

    A bare `date.today()` reads whatever timezone the host happens to be in, so
    two machines running the same code an hour apart can disagree about which
    side of a price change they are on. UTC is not certainly the timezone
    Anthropic switches prices in (they do not publish one), so the boundary DAY
    of a promotional rate is approximate either way — but approximate and
    identical everywhere beats approximate and host-dependent.
    """
    return datetime.now(timezone.utc).date()

PRICING_VERIFIED_ON = date(2026, 8, 8)
"""When the figures below were last checked against the published table.

Deliberately a constant and not a test that goes red after N days: a floor that
fires on innocent work is one somebody switches off. It is here to be read by
whoever next doubts a number.
"""

# Anthropic publishes cache pricing as a multiple of the input rate, so these are
# derived rather than typed per model. The 1-hour cache TTL is 2.00x instead of
# 1.25x and is NOT modelled here — a run that uses it will be under-reported, and
# that is a known gap rather than a silent one.
_ANTHROPIC_CACHE_WRITE = 1.25
_ANTHROPIC_CACHE_READ = 0.10


def _anthropic(input_: float, output: float) -> dict[str, float]:
    """One Anthropic row from the two numbers that are actually published."""
    return {
        "input": input_,
        "output": output,
        "cache_write": input_ * _ANTHROPIC_CACHE_WRITE,
        "cache_read": input_ * _ANTHROPIC_CACHE_READ,
    }


# Prices in USD per 1,000,000 tokens. Keys = model-id (without the provider/ prefix).
PRICING: dict[str, dict[str, float]] = {
    # Anthropic — list prices.
    "claude-fable-5":    _anthropic(10.00, 50.00),
    "claude-mythos-5":   _anthropic(10.00, 50.00),
    "claude-opus-5":     _anthropic(5.00, 25.00),
    "claude-opus-4-8":   _anthropic(5.00, 25.00),
    "claude-opus-4-7":   _anthropic(5.00, 25.00),
    "claude-opus-4-6":   _anthropic(5.00, 25.00),
    "claude-sonnet-5":   _anthropic(3.00, 15.00),
    "claude-sonnet-4-6": _anthropic(3.00, 15.00),
    "claude-haiku-4-5":  _anthropic(1.00, 5.00),
    # OpenAI (indicative)
    "gpt-4o":            {"input": 2.50, "output": 10.00, "cache_write": 0.0, "cache_read": 1.25},
    # Local models (Ollama, vLLM, LM Studio...): no API cost. This zero is a
    # PRICE, not a missing entry — which is the whole reason an unknown model
    # returns None instead of joining it here by accident.
    "llama3.1:8b":       {"input": 0.0, "output": 0.0, "cache_write": 0.0, "cache_read": 0.0},
}

INTRODUCTORY: dict[str, tuple[date, dict[str, float]]] = {
    # Sonnet 5 launched at a promotional rate. `until` is the LAST day it applies.
    "claude-sonnet-5": (date(2026, 8, 31), _anthropic(2.00, 10.00)),
}
"""Promotional rates that lapse on a known date.

The expiry lives in the data so the lapse is a computation, not something
somebody has to remember. When an entry's date has passed it stops being
selected on its own; deleting it afterwards is tidying, not a fix.
"""


def rates_for(model_id: str, on: date | None = None) -> dict[str, float] | None:
    """The rate card in force for `model_id` on `on` (default: today).

    Returns None when the model is unknown — see the module docstring on why
    that is not 0.0.
    """
    intro = INTRODUCTORY.get(model_id)
    if intro is not None:
        until, rates = intro
        if (on or _today()) <= until:
            return rates
    return PRICING.get(model_id)


def cost_for(
    model_id: str,
    input_tok: int,
    output_tok: int,
    cache_write: int,
    cache_read: int,
    *,
    on: date | None = None,
) -> float | None:
    """Cost in USD, or None if there is no price for this model.

    `on` exists so a test never has to read the wall clock to assert a figure
    that depends on a date. Left None in production, where "now" is the right
    answer: the price you pay is the price in force when you call.
    """
    p = rates_for(model_id, on)
    if p is None:
        return None
    return (
        input_tok * p["input"]
        + output_tok * p["output"]
        + cache_write * p["cache_write"]
        + cache_read * p["cache_read"]
    ) / 1_000_000
