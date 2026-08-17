"""Pricing: the unknown-model distinction, derived cache rates, promo expiry.

The assertion this file exists for is the first one: an unknown model must not
report 0.0. A local model genuinely costs zero, so a silent zero for a model
nobody priced is indistinguishable from a correct one — and it is the cheaper
of the two readings, which is the one nobody goes back to check.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from predicta_harness import usage
from predicta_harness.types import Usage
from predicta_harness.usage import INTRODUCTORY, PRICING, cost_for, rates_for

# Pinned so nothing here reads the wall clock. Every test that could depend on
# "when it ran" passes a date explicitly instead. Two arbitrary dates either
# side of a month boundary — they were named after Sonnet 5's introductory
# window until that window stopped existing, which is the same stale-name trap
# the promo tests below now avoid.
AN_EARLIER_DATE = date(2026, 8, 15)
A_LATER_DATE = date(2026, 9, 1)


# --------------------------------------------------------------------------
# The distinction between "costs nothing" and "no idea what this costs"
# --------------------------------------------------------------------------


def test_unknown_model_returns_none_not_zero():
    cost = cost_for("gpt-9-turbo-ultra", 1_000_000, 1_000_000, 0, 0)
    assert cost is None, "an unpriced model must not be reported as free"


def test_local_model_returns_an_explicit_zero():
    # The mirror image of the test above, and the reason it has to be None
    # rather than 0.0: this zero is a price somebody wrote down.
    cost = cost_for("llama3.1:8b", 1_000_000, 1_000_000, 500, 500)
    assert cost is not None, "a priced model must never come back as unknown"
    assert cost == 0.0


def test_a_priced_model_computes_from_its_rate_card():
    # 1M input + 1M output on Opus 5 == its two headline numbers, added.
    assert cost_for("claude-opus-5", 1_000_000, 1_000_000, 0, 0) == pytest.approx(30.00)


# --------------------------------------------------------------------------
# Cache rates are derived, so they cannot drift from the input price
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "model_id", [m for m in PRICING if m.startswith("claude-")]
)
def test_anthropic_cache_rates_stay_tied_to_the_input_rate(model_id):
    rates = PRICING[model_id]
    assert rates["cache_write"] == pytest.approx(rates["input"] * 1.25)
    assert rates["cache_read"] == pytest.approx(rates["input"] * 0.10)


def test_the_parametrisation_above_is_not_empty():
    # A parametrised test over an empty list passes by running zero times, and
    # looks identical in the output to one that checked every model.
    assert len([m for m in PRICING if m.startswith("claude-")]) >= 5


# --------------------------------------------------------------------------
# A promotional rate that lapses on a date the data knows about
# --------------------------------------------------------------------------


# These three pinned the mechanism to Sonnet 5, the only real entry there was.
# On 2026-08-17 Anthropic made that rate permanent, INTRODUCTORY emptied, and all
# three went red — not because the expiry logic broke, but because the example
# stopped being an example. The mechanism is now exercised against a model that
# does not exist, so a third party's pricing decision can never turn coverage of
# it red again. What Sonnet 5 costs is asserted separately, below.

PROMO_MODEL = "test-promo-model"
PROMO_ENDS = date(2026, 8, 31)


@pytest.fixture
def promo_model(monkeypatch):
    """A synthetic model on promo: 2.00 until PROMO_ENDS, 3.00 after."""
    monkeypatch.setitem(PRICING, PROMO_MODEL, usage._anthropic(3.00, 15.00))
    monkeypatch.setitem(
        INTRODUCTORY, PROMO_MODEL, (PROMO_ENDS, usage._anthropic(2.00, 10.00))
    )
    return PROMO_MODEL


def test_introductory_rate_applies_before_its_end_date(promo_model):
    assert cost_for(
        promo_model, 1_000_000, 0, 0, 0, on=PROMO_ENDS - timedelta(days=1)
    ) == pytest.approx(2.00)


def test_list_rate_applies_once_the_introductory_period_has_lapsed(promo_model):
    assert cost_for(
        promo_model, 1_000_000, 0, 0, 0, on=PROMO_ENDS + timedelta(days=1)
    ) == pytest.approx(3.00)


def test_the_last_day_of_the_introductory_period_is_inclusive(promo_model):
    until, _ = INTRODUCTORY[promo_model]
    assert cost_for(promo_model, 1_000_000, 0, 0, 0, on=until) == pytest.approx(2.00)


def test_sonnet_5_does_not_revert_to_the_list_rate_in_september():
    # The regression this file now exists to prevent. Sonnet 5 sat in
    # INTRODUCTORY with `until = 2026-08-31`; Anthropic made 2.00/10.00
    # permanent on 2026-08-12 and cancelled the 3.00/15.00 that was to start on
    # September 1. Left alone, every Sonnet 5 figure would have been 50% high
    # from that date, silently. The date here is deliberately past the old
    # expiry: a future price for Sonnet 5 that is not 2.00 has to be a decision
    # somebody makes, not one a stale `until` makes for them.
    assert cost_for(
        "claude-sonnet-5", 1_000_000, 0, 0, 0, on=date(2026, 9, 1)
    ) == pytest.approx(2.00)
    assert "claude-sonnet-5" not in INTRODUCTORY


def test_a_model_with_no_promotion_ignores_the_date_entirely():
    before = cost_for("claude-opus-5", 1_000_000, 0, 0, 0, on=AN_EARLIER_DATE)
    after = cost_for("claude-opus-5", 1_000_000, 0, 0, 0, on=A_LATER_DATE)
    assert before == after == pytest.approx(5.00)


def test_rates_for_reports_unknown_models_as_none():
    assert rates_for("no-such-model", on=AN_EARLIER_DATE) is None


def test_omitting_the_date_goes_through_the_utc_clock(monkeypatch):
    # Not decoration: the first version of this module defined `_today()` and
    # then never called it — `rates_for` still read the host's local date, and
    # every other test in this file passes `on=` explicitly, so all of them
    # stayed green over the dead code. Patching the clock is what proves the
    # default path is wired to it.
    monkeypatch.setitem(PRICING, PROMO_MODEL, usage._anthropic(3.00, 15.00))
    monkeypatch.setitem(
        INTRODUCTORY, PROMO_MODEL, (PROMO_ENDS, usage._anthropic(2.00, 10.00))
    )

    monkeypatch.setattr(usage, "_today", lambda: PROMO_ENDS + timedelta(days=1))
    assert rates_for(PROMO_MODEL)["input"] == pytest.approx(3.00)

    monkeypatch.setattr(usage, "_today", lambda: PROMO_ENDS - timedelta(days=1))
    assert rates_for(PROMO_MODEL)["input"] == pytest.approx(2.00)


def test_the_default_clock_is_utc_and_not_the_host_timezone():
    assert usage._today() == datetime.now(timezone.utc).date()


# --------------------------------------------------------------------------
# Usage carries the unknown through instead of absorbing it
# --------------------------------------------------------------------------


def test_usage_counts_an_unpriced_call_rather_than_charging_it_zero():
    u = Usage.for_call("gpt-9-turbo-ultra", 1_000_000, 1_000_000)
    assert u.cost_usd == 0.0
    assert u.unpriced_calls == 1, "the missing price has to survive into the total"


def test_usage_for_a_priced_call_reports_no_unpriced_calls():
    u = Usage.for_call("claude-opus-5", 1_000_000, 0)
    assert u.cost_usd == pytest.approx(5.00)
    assert u.unpriced_calls == 0


def test_adding_usages_accumulates_the_unpriced_count():
    total = Usage.for_call("claude-opus-5", 1_000_000, 0)
    total.add(Usage.for_call("gpt-9-turbo-ultra", 1_000_000, 0))
    total.add(Usage.for_call("also-unknown", 1_000_000, 0))
    assert total.calls == 3
    assert total.cost_usd == pytest.approx(5.00)
    assert total.unpriced_calls == 2


def test_a_total_with_unpriced_calls_prints_as_a_floor():
    total = Usage.for_call("claude-opus-5", 1_000_000, 0)
    total.add(Usage.for_call("gpt-9-turbo-ultra", 1_000_000, 0))
    rendered = str(total)
    assert ">=" in rendered, "a lower bound must not read like an exact figure"
    assert "1 unpriced" in rendered


def test_a_fully_priced_total_prints_without_the_floor_marker():
    # Guards the assertion above from passing for the wrong reason: if the
    # marker were unconditional, both tests would still be green.
    rendered = str(Usage.for_call("claude-opus-5", 1_000_000, 0))
    assert ">=" not in rendered
    assert "unpriced" not in rendered
