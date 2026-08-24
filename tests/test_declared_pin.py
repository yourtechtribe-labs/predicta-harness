"""The ceiling as *declared*, checked in an environment that installs no provider.

`test_anthropic_sdk_pin.py` is the better test and it checks the better thing: it
introspects `messages.create` on the SDK that is actually installed. But it can
only speak about this machine, and it needs the SDK present to say anything at all.

The string in `pyproject.toml` is what `pip` reads in every environment neither
this repo nor its CI ever sees — a production image built from the base package, a
consumer resolving the `all` extra six months from now. Nothing checked that string
until this file, and it is the one that let anthropic 1.0 into a client-facing job
on 2026-08-21.

So: one guard for what is installed here, one for what is declared for everybody
else. This is the second, and it deliberately imports nothing but the standard
library, so it can never be the test that skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"

#: The distribution whose upper bound was bought by an incident rather than chosen.
#: `openai` is deliberately absent: it has no ceiling today, and adding one is a
#: change with its own measurement, not something this test should smuggle in.
CAPPED = "anthropic"


def _declared_specifiers(distribution: str) -> list[str]:
    """Every dependency string in the file that constrains `distribution`.

    Deliberately not a TOML parse: `tomllib` is 3.11+ and this package supports
    3.10, and a guard that is unavailable on a supported interpreter is the exact
    failure this file exists to stop repeating.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    # Only inside quoted dependency strings, so the 14 lines of prose above the
    # extras — which mention the distribution by name — are not mistaken for pins.
    return [
        found
        for found in re.findall(r'"([^"]+)"', text)
        if re.match(rf"^{re.escape(distribution)}\s*[<>=!~]", found)
    ]


def test_every_declaration_of_the_capped_sdk_carries_an_upper_bound():
    specifiers = _declared_specifiers(CAPPED)
    assert specifiers, (
        f"no dependency string constrains {CAPPED} in {PYPROJECT.name}. Either the "
        f"extra was removed and this test should go with it, or the pin was lost."
    )
    for specifier in specifiers:
        assert "<" in specifier, (
            f"{specifier!r} has no upper bound. On 2026-08-21 an unbounded "
            f"{CAPPED}>=0.40 let 1.0 into a production image; messages.create had "
            f"dropped `temperature` and the reconciliation triage judged 0 of 1798 "
            f"matches before dying on its first call. Restore the ceiling, or port "
            f"the provider and lower it deliberately."
        )


def test_the_two_places_the_pin_is_written_cannot_drift_apart():
    """`anthropic` and `all` both declare it, which is how half a ceiling gets lifted.

    Duplication is the mechanism: somebody bumps the extra they are working on and
    the other one keeps the old bound, so which ceiling applies depends on which
    extra the consumer happened to install.
    """
    specifiers = set(_declared_specifiers(CAPPED))
    assert len(specifiers) == 1, (
        f"{CAPPED} is declared {len(specifiers)} different ways: {sorted(specifiers)}. "
        f"Which bound applies then depends on which extra the consumer installed."
    )
