"""What this project publishes about itself, so an orchestrator can answer
"where are we" without reading the project.

The contract is twin's ``engine/state.schema.json``. Twin owns the schema, every
project owns its own writer, and no repository depends on another for this — so
this file imports nothing from twin and nothing from the consumer project, which
has its own writer in Python that shares not a line with this one. What crosses the
boundary is a checkable artifact, never an import.

Two halves, and the difference between them is the whole point:

* **derived** — recomputed here on every run. Git facts, the floor, the gate's own
  exit code, the identifier index. If it cannot be recomputed it does not belong
  in this half.
* **stated** — judgements, read from ``STATED.json`` and passed through unchanged.
  They carry the commit they were written at, and a reader whose ``head`` has moved
  past it renders them as stale rather than as fact.

Written by ``ratchet.py --check``, which is the command this repo already runs to
verify itself. Nothing else writes it and it is never written by hand: a file that
claims to be current and is maintained by whoever remembers is exactly the artifact
this replaces.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent
STATE_FILE = REPO / "state.json"
STATED_FILE = REPO / "STATED.json"
NAMESPACES_FILE = REPO / "NAMESPACES.json"

SCHEMA_VERSION = 1

PROJECT = {
    "name": "predicta-harness",
    "kind": "development",
    "root": "~/dev/predicta-harness",
    "repo": "yourtechtribe-labs/predicta-harness",
    "one_line": (
        "The provider-agnostic agent runtime, and the base the governed projects are "
        "meant to stand on: mechanism installed, policy copied."
    ),
    "harness": "own",
}

#: Madrid, because every date a human reads in these repos is Madrid and a page that
#: mixes UTC with local time makes two facts look like a contradiction. Fixed offset
#: rather than a tz database: the standard library has no zoneinfo data on Windows
#: without an extra package, and this file may not have dependencies.
_MADRID = timezone(timedelta(hours=2))

# One to four capitals, an optional hyphen, one to three digits. The digit bound is
# what keeps a year out: 2026 cannot be a label, M-7 and DR-12 and T5 can.
_SHAPE = r"[A-Z]{1,4}-?[0-9]{1,3}"

# The shapes the consumer project's writer reads, copied rather than imported on purpose
# (DR-2 of the contract), plus a fifth this corpus needed. All read off real lines:
#
#   - **M-7** — ...          a bold list item
#   - [ ] **AC1 (loop):** …  a bold list item behind a task checkbox
#   ### T1 — ...             a heading
#   | M-9 | ...              a bare table cell
#   | **F0** — ... | ...     a bold table cell
#
# The bold need not CLOSE after the label, and the heading prefix must be lazy: a
# greedy one prefers to consume and captures the LAST label on the line, which
# indexes `## T5 · Parity … — AC-1` under AC-1, pointing at a line about something
# else entirely.
#
# The checkbox is the fifth and it was a real miss, not a precaution. `specs/sandbox/
# SPEC.md:139` defines every acceptance criterion as `- [ ] **AC1 (loop, local):**`,
# and a pattern demanding `**` directly after the bullet reported all six as
# referenced-and-never-defined — which reads on the page as eight dangling labels
# rather than as a scanner that cannot see a checkbox.
_DEFINITION = re.compile(
    rf"^\s*(?:[-*]\s+(?:\[[ xX]\]\s+)?\*\*({_SHAPE})\b"
    rf"|#{{1,6}}\s+(?:[^\n]*?\s)??({_SHAPE})\b"
    rf"|\|\s*({_SHAPE})\s*\|"
    rf"|\|\s*\*\*({_SHAPE})\b)"
)
_MENTION = re.compile(rf"\b{_SHAPE}\b")


def _git(*args: str) -> str | None:
    """A git fact, or None. A thing that could not be measured is never a zero."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=REPO,
            capture_output=True,
            # `encoding="utf-8"` and NOT `text=True`. On Windows `text=True` decodes
            # with the ANSI codepage, and `git blame --porcelain` returns the source
            # line — which in these repos is full of em-dashes. The decode fails
            # inside subprocess, the call returns `stdout=None`, and the error
            # surfaces three frames later as an AttributeError that looks like a git
            # problem. Learned once in a sibling project and paid for there.
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except (subprocess.CalledProcessError, OSError, UnicodeDecodeError):
        return None
    return (out.stdout or "").strip()


def git_facts() -> dict[str, Any]:
    status = _git("status", "--porcelain")
    last = _git("log", "-1", "--format=%cs\t%s")
    date, _, subject = (last or "").partition("\t")
    return {
        "head": _git("rev-parse", "--short", "HEAD") or None,
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD") or None,
        "uncommitted": None if status is None else (len(status.splitlines()) if status else 0),
        "last_commit": {"date": date, "subject": subject} if last else None,
    }


def _corpus() -> dict[str, list[str]]:
    """Every markdown document this repo governs itself with, by relative path."""
    files: dict[str, list[str]] = {}
    for path in sorted(REPO.glob("*.md")) + sorted(REPO.glob("specs/**/*.md")):
        relative = path.relative_to(REPO).as_posix()
        files[relative] = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return files


def _scope_of(relative: str) -> str:
    """The directory a document lives in, which is the scope its labels belong to.

    `T5` means "the fifth task of this spec" and is defined once per spec; an index
    that flattens them into one entry has a wrong model, not a duplicate.
    """
    parent = Path(relative).parent.as_posix()
    return "" if parent == "." else parent


def _blame_date(relative: str, line: int) -> str | None:
    out = _git("blame", "--porcelain", "-L", f"{line},{line}", "--", relative)
    if not out:
        return None
    found = re.search(r"^author-time (\d+)$", out, re.MULTILINE)
    return (
        datetime.fromtimestamp(int(found.group(1)), tz=timezone.utc).date().isoformat()
        if found
        else None
    )


def namespace_of(label: str) -> str:
    """The prefix of a label. `AC1` is an AC, `DR-12` is a DR."""
    return re.match(r"^([A-Z]{1,4})", label).group(1)


def declared_namespaces() -> dict[str, dict[str, Any]]:
    """What `NAMESPACES.json` says this project's label prefixes are.

    Empty when the file is absent, and that is deliberately a LOUD state rather
    than a convenient one: with no declaration `identifiers()` indexes every
    label-shaped string it finds, so a fresh copy of this writer shows its
    `UTF-8`s on the first run instead of quietly behaving as if somebody had
    decided something.
    """
    if not NAMESPACES_FILE.exists():
        return {}
    try:
        return json.loads(NAMESPACES_FILE.read_text(encoding="utf-8")).get("namespaces", {})
    except (json.JSONDecodeError, OSError):
        return {}


def corpus_namespaces() -> dict[str, int]:
    """Every label-shaped prefix these documents contain, and how often.

    Mentions, not definitions. A prefix this repository only ever cites still has
    to be accounted for — that is the whole case of a label owned by another
    repository, and the case a rule derived from local definitions cannot see.
    """
    found: dict[str, int] = {}
    for lines in _corpus().values():
        for line in lines:
            for label in _MENTION.findall(line):
                prefix = namespace_of(label)
                found[prefix] = found.get(prefix, 0) + 1
    return found


def definition_sites() -> dict[str, set[str]]:
    """Namespace -> the files that define at least one of its labels."""
    sites: dict[str, set[str]] = {}
    for relative, lines in _corpus().items():
        for line in lines:
            found = _DEFINITION.match(line)
            if not found:
                continue
            label = next(group for group in found.groups() if group)
            sites.setdefault(namespace_of(label), set()).add(relative)
    return sites


def identifiers(dated: bool = True) -> list[dict[str, Any]]:
    """Every label these documents define or mention, and where it is defined.

    No `text` snippet, and the reason is the consumer project's rather than this one's: a
    snippet lifted off a defining line is free prose, and in a repo that names
    clients it can carry one. Nothing here names a client today — but a field whose
    safety depends on which repo it is in is a field that travels wrong the first
    time this writer is copied, and copying is how the contract spreads. The
    location is the answer the resolver exists to give; the prose was a convenience.
    """
    corpus = _corpus()

    definitions: dict[tuple[str, str], list[dict[str, Any]]] = {}
    scopes: dict[str, set[str]] = {}
    for relative, lines in corpus.items():
        scope = _scope_of(relative)
        for number, line in enumerate(lines, start=1):
            found = _DEFINITION.match(line)
            if not found:
                continue
            label = next(group for group in found.groups() if group)
            definitions.setdefault((scope, label), []).append(
                {"file": relative, "line": number}
            )
            scopes.setdefault(label, set()).add(scope)

    mentions: dict[tuple[str, str], int] = {}
    for relative, lines in corpus.items():
        scope = _scope_of(relative)
        for line in lines:
            for label in _MENTION.findall(line):
                where = scopes.get(label, set())
                # A mention resolves to a definition in its own scope when there is
                # one, and to the only definition there is when there is exactly one.
                # Anything else stays where it was said.
                home = scope if scope in where else (next(iter(where)) if len(where) == 1 else scope)
                mentions[(home, label)] = mentions.get((home, label), 0) + 1

    # What counts as a namespace is DECLARED, in NAMESPACES.json, and not inferred
    # here.
    #
    # This used to be inferred: a namespace nothing defined locally was dropped,
    # which did keep `UTF-8` out of the index. It was a patch. The same rule drops a
    # label whose definition lives in ANOTHER repository, and it drops it silently —
    # a foreign label and a typo look identical when the only evidence considered is
    # this repository's own definitions, and one of those two is a fact worth seeing
    # on the page.
    #
    # So the declaration decides, and `tests/test_namespaces.py` is what makes an
    # undeclared prefix a red rather than a vanishing act. `authority: "none"` is how
    # a string that merely matches the shape gets named as not-a-label instead of
    # being disappeared by a rule nobody wrote down.
    declared = declared_namespaces()
    indexable = {
        prefix for prefix, entry in declared.items() if entry.get("authority") != "none"
    }

    index: list[dict[str, Any]] = []
    for (scope, label) in sorted(set(definitions) | set(mentions)):
        # No declaration at all indexes everything, on purpose: see
        # `declared_namespaces`. An absence should be loud, not tidy.
        if declared and namespace_of(label) not in indexable:
            continue
        sites = definitions.get((scope, label), [])
        first = sites[0] if sites else None
        total = mentions.get((scope, label), 0)
        index.append(
            {
                "id": label,
                "namespace": re.match(r"^([A-Z]{1,4})", label).group(1),
                "scope": scope,
                "file": first["file"] if first else None,
                "line": first["line"] if first else None,
                # The mention on the definition line is not a reference to it.
                "references": total - len(sites),
                "defined": _blame_date(first["file"], first["line"]) if (first and dated) else None,
                # Not "this is a defect": a label legitimately exists in several
                # specs. It warns that the bare label identifies nothing on its own.
                "ambiguous": True if (len(sites) > 1 or len(scopes.get(label, ())) > 1) else None,
            }
        )
    return index


def judgements() -> dict[str, Any] | None:
    """The stated half, passed through unchanged, or absent.

    Absent rather than empty when there is nothing to say, and absent rather than a
    crash when the file does not parse: a reader can render "no judgements" honestly
    and cannot render a guess honestly.
    """
    if not STATED_FILE.exists():
        return None
    try:
        stated = json.loads(STATED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    stated.pop("_", None)
    return stated or None


def build(measured: dict[str, Any], gate: dict[str, Any]) -> dict[str, Any]:
    state = {
        "schema": SCHEMA_VERSION,
        "project": dict(PROJECT),
        "derived": {
            "written_at": datetime.now(_MADRID).isoformat(timespec="seconds"),
            "written_by": "python ratchet.py --check",
            **git_facts(),
            "gate": gate,
            "floor": measured,
            # The legend for the index below it, passed through from NAMESPACES.json
            # unchanged rather than summarised. Until this field a reader of the state
            # file could see that `R3` exists and had no way to learn that an `R` is a
            # requirement — the convention lived only in whoever wrote the last spec.
            #
            # It also carries the distinction the index alone cannot make: a prefix
            # owned by another repository is not an undefined label, and `UTF-8` is
            # not a label at all.
            "namespaces": declared_namespaces() or None,
            "identifiers": identifiers(),
        },
    }
    stated = judgements()
    if stated:
        state["stated"] = stated
    return state


def write(measured: dict[str, Any], gate: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    state = build(measured, gate)
    target = path or STATE_FILE
    target.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return state
