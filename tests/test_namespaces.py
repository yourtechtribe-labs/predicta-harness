"""The label vocabulary is declared, and the declaration is checked against the documents.

`NAMESPACES.json` says what an `R` or an `AC` is. Three ways it can stop being true,
and all three are silent without a test:

  R1  a document starts using a prefix nobody declared
  R2  a prefix is claimed as ours and nothing here defines it, or its definitions
      turn out to live somewhere other than where the file says
  R3  a prefix is declared and no document ever uses it

R1 is the one that pays for the rest. Before this file, `state.py` dropped any
namespace the corpus never defined, which kept `UTF-8` out of the index and would
have kept a real label owned by another repository out of it in exactly the same
silent way — a foreign label and a typo are indistinguishable when the only
evidence considered is this repository. Now the declaration decides what is
indexed, and this suite is what makes an undeclared prefix loud.

These are guards over the real repository rather than unit tests over a fixture:
the thing being protected is this corpus and this declaration, not the shape of a
function.
"""
from __future__ import annotations

import json
from pathlib import PurePosixPath

import pytest

import state


@pytest.fixture(scope="module")
def declared() -> dict:
    return state.declared_namespaces()


def test_the_declaration_exists_and_parses(declared):
    """Absent, `identifiers()` indexes every label-shaped string it can find.

    That fallback is deliberate — an absence should be loud — but it is a fallback,
    and this repository has a declaration.
    """
    assert state.NAMESPACES_FILE.exists(), f"{state.NAMESPACES_FILE.name} is missing"
    raw = json.loads(state.NAMESPACES_FILE.read_text(encoding="utf-8"))
    assert raw.get("namespaces"), "the declaration has no `namespaces` object"
    for prefix, entry in declared.items():
        assert entry.get("means"), f"{prefix} is declared without saying what it means"
        assert entry.get("authority"), f"{prefix} is declared without an authority"


def test_R1_every_prefix_the_documents_use_is_declared(declared):
    """A document that invents a prefix has to say so here first."""
    used = state.corpus_namespaces()
    undeclared = sorted(set(used) - set(declared))
    assert not undeclared, (
        f"these label prefixes appear in the documents and are declared nowhere: "
        f"{ {p: used[p] for p in undeclared} }. Either add them to "
        f"{state.NAMESPACES_FILE.name} with what they mean and who owns them, or — if "
        f"the string only happens to match the label shape, the way UTF-8 does — "
        f'declare it with `\"authority\": \"none\"` so it is named rather than ignored.'
    )


def test_R2_a_namespace_claimed_as_ours_is_defined_where_it_says(declared):
    """`authority: self` is a claim about this repository, checked both halves.

    Nothing defined at all means the claim is wrong. Definitions outside the
    declared globs mean `defined_in` has rotted into decoration, which is the
    failure mode of every field nothing reads.
    """
    sites = state.definition_sites()
    for prefix, entry in sorted(declared.items()):
        if entry.get("authority") != "self":
            continue

        globs = entry.get("defined_in")
        assert globs, f"{prefix} claims `authority: self` and declares no `defined_in`"

        found = sites.get(prefix, set())
        assert found, (
            f"{prefix} is declared as defined here and no document defines one. "
            f"Either it belongs to another repository — say so in `authority` — or "
            f"the definitions are written in a shape the scanner cannot see."
        )

        stray = sorted(
            f for f in found
            if not any(PurePosixPath(f).match(g) for g in globs)
        )
        assert not stray, (
            f"{prefix} is declared as defined in {globs} and is also defined in "
            f"{stray}. Widen the globs deliberately or move the definition."
        )


def test_R3_a_declared_namespace_is_one_the_documents_actually_use(declared):
    """A word nothing ever uses should be visible, not look as load-bearing as the rest."""
    used = state.corpus_namespaces()
    dead = sorted(set(declared) - set(used))
    assert not dead, (
        f"these prefixes are declared and appear in no document: {dead}. A vocabulary "
        f"that keeps words nothing uses stops describing the corpus it is about."
    )
