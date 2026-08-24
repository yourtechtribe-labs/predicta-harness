"""Every claim this repository makes about itself, measured against the repository.

A floor file exists because a README is a memory and a measurement is a fact. The
numbers here are produced by running the thing, never by reading a document that
says what the thing does.

Four kinds, because "do not go down" is the wrong gate for three of the five
things worth watching here:

  floor     may rise, may never fall          (tests that pass)
  exact     must equal, both directions       (provider imports, skips)
  ceiling   may fall, may never rise          (suite wall-clock)
  recorded  measured, never gates             (size an agent must hold)

`exact` is the important one and it is deliberate. A count that may only go down
hides the case that matters: a provider import added at module level is a
regression, and a deferred one removed is a change somebody should have to
explain. Both show up in a diff of this file or not at all.

Usage:

    python ratchet.py --check    # measure, compare, exit 1 on any regression
    python ratchet.py --raise    # write the measurement back as the new floor,
                                 # refusing to lower anything

Standard library only, on purpose: the file that guards the dependencies cannot
be the file that needs them.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent
FLOOR_FILE = REPO / "RATCHET.json"

#: Distribution names whose import inside `src/` is what this repo promises not to
#: do at module level. They are optional extras; a module-level import turns an
#: extra into a requirement for anybody who installs the base package.
PROVIDER_DISTRIBUTIONS = ("anthropic", "openai")

#: How much slower than the recorded baseline the suite may get before the ceiling
#: fires. Wall-clock is noisy — a laptop on battery, a cold filesystem — and a gate
#: that flaps is a gate somebody switches off. 3x is wide enough to never flap and
#: narrow enough to catch the failure that matters: a test that started reaching
#: the network. If this fires, make the suite faster; never widen the tolerance.
SUITE_SECONDS_TOLERANCE = 3.0


# --------------------------------------------------------------------------- #
# Measuring
# --------------------------------------------------------------------------- #

def _provider_imports() -> tuple[int, int]:
    """Count imports of a provider SDK under `src/`, split by module level or not.

    Walks the AST rather than grepping, because the deferred imports this repo
    relies on are written inside functions and a reader that only looks at the top
    of each file would report zero and be wrong in the reassuring direction.
    """
    module_level = 0
    deferred = 0
    for path in sorted((REPO / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            if isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
            else:
                names = [alias.name for alias in node.names]
            for name in names:
                if not name or name.split(".")[0] not in PROVIDER_DISTRIBUTIONS:
                    continue
                if node.col_offset == 0:
                    module_level += 1
                else:
                    deferred += 1
    return module_level, deferred


def _tracked() -> tuple[int, int]:
    """Files and bytes an agent has to hold to work on this repo.

    `git ls-files`, so generated output and virtualenvs do not flatter the number.
    """
    listed = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    files = [REPO / name for name in listed]
    present = [p for p in files if p.is_file()]
    return len(present), sum(p.stat().st_size for p in present)


_SUMMARY = re.compile(r"(?:(\d+) passed)?(?:, )?(?:(\d+) skipped)?(?:, )?(?:(\d+) failed)?")


def _suite() -> tuple[int, int, int, float]:
    """Run the suite and return (passed, skipped, failed, seconds).

    The suite is run with whatever is installed in the current interpreter. That is
    the point rather than a limitation: the provider extras being absent is the
    condition CI runs in, and the numbers below are only meaningful next to it.
    """
    started = time.monotonic()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        cwd=REPO, capture_output=True, text=True,
    )
    seconds = time.monotonic() - started
    output = completed.stdout + completed.stderr

    passed = skipped = failed = 0
    for line in output.splitlines():
        if " passed" in line or " failed" in line or " error" in line:
            for count, word in re.findall(r"(\d+) (passed|skipped|failed|error[s]?)", line):
                if word == "passed":
                    passed = int(count)
                elif word == "skipped":
                    skipped = int(count)
                else:
                    failed += int(count)
    if passed == 0 and failed == 0:
        raise SystemExit(
            "ratchet: could not read a result out of pytest. This is a hard stop and "
            "not a zero, because a floor computed from an unreadable run is a floor "
            "that always passes.\n\n" + output[-2000:]
        )
    return passed, skipped, failed, round(seconds, 2)


def measure() -> dict[str, Any]:
    passed, skipped, failed, seconds = _suite()
    module_level, deferred = _provider_imports()
    files, size = _tracked()
    return {
        "tests_passing": passed,
        "tests_failing": failed,
        "tests_skipped_without_provider_extras": skipped,
        "provider_imports_module_level": module_level,
        "provider_imports_deferred": deferred,
        "suite_seconds": seconds,
        "tracked_files": files,
        "tracked_bytes": size,
    }


# --------------------------------------------------------------------------- #
# Comparing
# --------------------------------------------------------------------------- #

def _load() -> dict[str, Any]:
    return json.loads(FLOOR_FILE.read_text(encoding="utf-8"))


def _kinds(declared: dict[str, Any]) -> dict[str, str]:
    return declared["kinds"]


def regressions(measured: dict[str, Any], declared: dict[str, Any]) -> list[str]:
    kinds = _kinds(declared)
    floor = declared["floor"]
    found: list[str] = []

    if measured["tests_failing"]:
        found.append(
            f"tests_failing is {measured['tests_failing']}; a floor measured against a "
            f"red suite measures nothing"
        )

    for name, kind in kinds.items():
        if name not in floor or name not in measured:
            continue
        was, now = floor[name], measured[name]
        if kind == "floor" and now < was:
            found.append(f"{name}: {was} -> {now} (a floor may not fall)")
        elif kind == "exact" and now != was:
            found.append(
                f"{name}: {was} -> {now} (an exact count must be explained, in either "
                f"direction — raise it deliberately with --raise)"
            )
        elif kind == "ceiling":
            limit = was * SUITE_SECONDS_TOLERANCE
            if now > limit:
                found.append(
                    f"{name}: {was} -> {now}, past the {SUITE_SECONDS_TOLERANCE}x "
                    f"tolerance of {limit:.1f}. Make it faster; do not widen this."
                )
    return found


def raise_floors(measured: dict[str, Any], declared: dict[str, Any]) -> dict[str, Any]:
    """Write the measurement back, in the strict direction only.

    A `floor` is only ever raised and a `ceiling` is only ever lowered — the same
    rule seen from its two sides, and the reason is that `--raise` must not become
    the way a gate gets relaxed. Re-running it on a slow afternoon would otherwise
    buy the suite a bigger time budget without anybody deciding to spend it, which
    is *"never lower a floor to unblock yourself"* wearing a different sign.

    `exact` is written as measured, because for an exact count that is what
    "deliberately" means: the diff of this file is the record, and the note beside
    the number is where the explanation goes.
    """
    kinds = _kinds(declared)
    updated = dict(declared["floor"])
    for name, kind in kinds.items():
        if name not in measured:
            continue
        if kind == "recorded" or kind == "exact":
            updated[name] = measured[name]
        elif kind == "floor":
            updated[name] = max(updated.get(name, measured[name]), measured[name])
        elif kind == "ceiling":
            updated[name] = min(updated.get(name, measured[name]), measured[name])
    declared["floor"] = updated
    return declared


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="measure and compare")
    parser.add_argument("--raise", dest="raise_", action="store_true",
                        help="write the measurement back, lowering nothing")
    args = parser.parse_args(argv)

    declared = _load()
    measured = measure()
    found = regressions(measured, declared)

    if args.raise_:
        if measured["tests_failing"]:
            print("refusing to raise a floor from a red suite", file=sys.stderr)
            print(json.dumps({"measured": measured}, indent=2))
            return 1
        declared = raise_floors(measured, declared)
        FLOOR_FILE.write_text(json.dumps(declared, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"measured": measured, "floor": declared["floor"]}, indent=2))
        return 0

    print(json.dumps(
        {"measured": measured, "floor": declared["floor"], "regressions": found},
        indent=2,
    ))
    if found:
        print(f"{len(found)} regression(s)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
