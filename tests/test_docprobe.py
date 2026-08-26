import subprocess
from pathlib import Path

import pytest

from predicta_harness.docprobe import Claim, check_all, require_control

REPO_ROOT = str(Path(__file__).resolve().parents[1])


def _current_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8").strip()


# Self-referential: cites docprobe.py's own docstring (doc) and its own code (code).
AGREEING_CLAIM = Claim(
    ref_id="grounding-not-judgement",
    doc_path="src/predicta_harness/docprobe.py",
    doc_quote="Grounding is not judgement",
    code_path="src/predicta_harness/docprobe.py",
    code_quote="def require_control(claims: tuple[Claim, ...]) -> None:",
    contradicts=False,
    why="Both exist in the real file — the control every claim set needs.",
)

# Both quotes are REAL (both resolve) but describe different things — this is what a
# genuine contradiction looks like: grounded, not missing.
DISAGREEING_CLAIM = Claim(
    ref_id="control-vs-negative-control-name",
    doc_path="src/predicta_harness/docprobe.py",
    doc_quote="The negative control",
    code_path="src/predicta_harness/docprobe.py",
    code_quote="def check_all(claims: tuple[Claim, ...], repo_root: str, sha: str) -> list[Checked]:",
    contradicts=True,
    why=(
        "The section header talks about the negative control (require_control); the "
        "cited function is check_all, a different function — deliberately mismatched "
        "on purpose to exercise a real, grounded 'these are not the same thing' claim."
    ),
)


def test_require_control_passes_with_at_least_one_agreeing_claim():
    require_control((AGREEING_CLAIM, DISAGREEING_CLAIM))  # must not raise


def test_require_control_raises_when_every_claim_disagrees():
    with pytest.raises(ValueError):
        require_control((DISAGREEING_CLAIM,))


def test_check_all_resolves_a_real_agreeing_pair():
    sha = _current_head()

    checked = check_all((AGREEING_CLAIM, DISAGREEING_CLAIM), repo_root=REPO_ROOT, sha=sha)

    item = next(c for c in checked if c.claim.ref_id == "grounding-not-judgement")
    assert item.resolved is True
    assert item.doc_line is not None
    assert item.code_line is not None


def test_check_all_resolves_a_real_disagreeing_pair_because_both_quotes_exist():
    """The fix this module exists for: contradicts=True does NOT mean 'expect this not
    to resolve'. Both quotes are real text, so both resolve — the disagreement is in
    what they MEAN, which check_all never evaluates."""
    sha = _current_head()

    checked = check_all((AGREEING_CLAIM, DISAGREEING_CLAIM), repo_root=REPO_ROOT, sha=sha)

    item = next(c for c in checked if c.claim.ref_id == "control-vs-negative-control-name")
    assert item.resolved is True


def test_check_all_raises_on_a_fabricated_quote_even_when_contradicts_is_true():
    """The exact bug this redesign fixes: a fabricated (non-existent) quote must fail
    LOUDLY regardless of the claim's `contradicts` value — never silently pass as 'the
    expected non-match'."""
    sha = _current_head()
    fabricated = Claim(
        ref_id="fabricated",
        doc_path="src/predicta_harness/docprobe.py",
        doc_quote="Grounding is not judgement",
        code_path="src/predicta_harness/docprobe.py",
        code_quote="this string does not exist anywhere in the file",
        contradicts=True,  # even marked as an expected mismatch, it must still raise
        why="Fabricated on purpose to prove check_all cannot treat 'missing' as evidence.",
    )

    with pytest.raises(ValueError, match="not found"):
        check_all((AGREEING_CLAIM, fabricated), repo_root=REPO_ROOT, sha=sha)


def test_check_all_raises_on_a_broken_positive_claim_too():
    sha = _current_head()
    broken = Claim(
        ref_id="broken",
        doc_path="src/predicta_harness/docprobe.py",
        doc_quote="this text does not exist in this file either",
        code_path="src/predicta_harness/docprobe.py",
        code_quote="def check_all(claims: tuple[Claim, ...], repo_root: str, sha: str) -> list[Checked]:",
        contradicts=False,
        why="Broken doc quote, on purpose.",
    )

    with pytest.raises(ValueError, match="not found"):
        check_all((AGREEING_CLAIM, broken), repo_root=REPO_ROOT, sha=sha)
