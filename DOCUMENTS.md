# The documents a governed project carries

This file is at the root rather than in a `docs/` directory because the document set *is* a
root-level fact about a repository — the point is that you see it on arrival, and a project
copying this arrangement should not have to decide where the description of the arrangement
lives before it can read it.

**Everything below describes what this repository already does.** Where a piece is missing it
is named as missing rather than described as if it were there. A document standard that
describes an intention is the failure it exists to prevent: it reads exactly like one that
describes a fact.

---

## The set

| File | Kind | What it answers | Here? |
|---|---|---|---|
| `README.md` | prose | what this is, and how somebody uses it | yes |
| `CLAUDE.md` | prose | what the repository promises about **itself**, and what breaks when a promise quietly stops holding | yes |
| `DOCUMENTS.md` | prose | this file: which documents exist and what each is for | yes |
| `RATCHET.json` | data | every claim the repository makes about itself, as numbers, with the kind of each | yes |
| `NAMESPACES.json` | data | what each label prefix means, where its definitions live, who owns it | yes |
| `STATED.json` | data | where the work stands, written by a person | yes, **gitignored** |
| `state.json` | derived | the whole published state: facts recomputed, judgements passed through | yes, **gitignored** |
| `specs/<name>/SPEC.md` | prose | one problem: what was measured, the rules that follow, what would make it wrong | one, `specs/sandbox/` |
| `specs/<name>/TASKS.md` | prose | that spec's work, one task per commit, each with a check that fails before | one, `specs/sandbox/` |
| `DOCTRINE.md` | prose | a rule and the incident that bought it | **absent.** The two rules of that kind here live in `CLAUDE.md` § Hard rules and in the comment above the extras in `pyproject.toml` |
| `PLAN.md` | prose | the phases and their order | **absent.** This repository has tasks and no phases yet |
| a decision ledger | data | what was decided and why, append-only | **absent** |

Two of these are produced, never edited: `state.json` is written by the gate, and `RATCHET.json`
is rewritten by `ratchet.py --raise`. Editing either by hand is a bug, not a shortcut — the
number stops being a measurement the moment a person can type it.

---

## Labels, and why the scope is the file

The specs cite themselves by short labels — a capital prefix and a number. They are how one
document refers to a decision in another: *"the workspace jail rule"*, *"blocked on the
bubblewrap task"*. Four prefixes are in use across these repositories:

| Prefix | Means | Lives in |
|---|---|---|
| `M-<n>` | a measurement — a number somebody took, with how they took it | `SPEC.md` |
| `DR-<n>` / `R-<n>` | a domain rule that follows from the measurements | `SPEC.md` |
| `AC-<n>` | an acceptance criterion | `SPEC.md` |
| `T-<n>` | a task, one per commit | `TASKS.md` |

**This repository writes its domain rules `R-<n>`, not `DR-<n>`** — `specs/sandbox/SPEC.md` § 5
*Domain rules & constraints*. That is a divergence from the convention, it is recorded in
`NAMESPACES.json` as what it is, and it is deliberately **not** renamed: the labels are cited
from `DESIGN.md` and `TASKS.md`, and a rename to tidy a table breaks every reference that made
the label worth having.

**The scope of a label is the file it is defined in**, and this is the whole reason no
`TASKS`/`SPECS` category layer is needed on top. A bare task label identifies nothing: it means
*"the fifth task of this spec"*, and there can be many specs. The directory already carries that
— `specs/sandbox/TASKS.md` — so the pair *(directory, label)* is the key, and a category system
naming the same thing a second time would only give the two names a chance to disagree.

`NAMESPACES.json` is the declaration, and `tests/test_namespaces.py` is what keeps it true:

- a prefix the documents use and nobody declared → **red**;
- a prefix claimed as this repository's that nothing here defines, **or** whose definitions
  turn out to sit outside the globs it declared → **red**;
- a prefix declared that no document ever uses → **red**.

The third looks pedantic and is not. A vocabulary that keeps words nothing uses stops describing
the corpus it is about, and every dead entry makes the live ones look equally load-bearing.

A string can match the label shape and not be a label — the encoding name `UTF-8` does, exactly.
Those are declared with `"authority": "none"`, which names them. The alternative, and what this
repository did until the declaration existed, is to infer: drop any prefix the corpus never
defines. That works on the encoding and fails on the case that matters, because a label whose
definition lives in *another* repository is indistinguishable from a typo when the only evidence
considered is this one — and it disappears silently rather than showing up as something to
resolve.

---

## Two halves: what is measured, and what somebody says

`state.json` has exactly two parts, and keeping them apart is the design.

**`derived`** is recomputed on every run of the gate: the git facts, the floor, the gate's own
exit code, the identifier index. The rule for belonging here is mechanical — *if it cannot be
recomputed, it does not go in this half.*

**`stated`** is judgement. Where the work is, what is next, what is blocked, what is waiting on
somebody. No tool can derive it and none tries; it is read from `STATED.json` and passed through
untouched.

The join between them is `at_commit`, and it is the only thing that makes the second half
falsifiable. `STATED.json` records the commit it was written at. A reader whose `derived.head`
has moved past that commit renders every judgement as **stale** instead of as fact. Without it,
a hand-written status section is the most authoritative-looking and least trustworthy thing in a
repository — it is confident, undated in any checkable way, and wrong by an unknown amount.

Stale is a visible state; a wrong answer is not. So the honest move when the judgements are out
of date is to update them, and the honest move when there is nothing to say is to leave them
alone.

Neither file is committed here. See `CLAUDE.md` § Hard rules, rule 6.

---

## Floors, and the four kinds

`RATCHET.json` holds what the repository can prove about itself. Each entry declares its *kind*,
because *"may not go down"* is the wrong gate for most of them:

| Kind | Rule | Example here |
|---|---|---|
| `floor` | may rise, may never fall | tests that pass |
| `exact` | must equal, and a change in **either** direction has to be explained | provider imports at module level, and skipped tests |
| `ceiling` | may fall, may never rise past the tolerance | suite wall-clock |
| `recorded` | measured every run, gates nothing | tracked files and bytes |

`exact` is the one that earns its place. A count that may only go down hides the case that
matters: a module-level provider import appearing is a regression, and a deferred one being
removed is a change somebody should have to explain. Only an exact count puts both directions in
a diff.

`--raise` moves a floor up and a ceiling down, never the reverse. Written the other way first,
it let a slow afternoon buy the suite a bigger time budget with nobody deciding to spend it —
which is *"never lower a floor to unblock yourself"* wearing the opposite sign.

An `exact` counter that moves wants its explanation written next to the number in `RATCHET.json`,
not only in the commit message. The commit is where the change is argued once; the file is where
the next reader finds it.
