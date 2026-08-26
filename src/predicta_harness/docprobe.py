"""Claims a document makes about the code, checked against the code at a pinned commit.

Grounding, and why a quote is the unit
---------------------------------------
A claim carries the **exact text** of both sides, and `check_all` refuses any claim set
where a quote does not resolve verbatim — normalizing only whitespace, never content. A
citation that resolves to nothing is a hallucination, and it is rejected rather than
softened. Line numbers are **derived** from the fetched content, never typed: a verdict
that says "line 12" and means it is reproducible; one written from memory is decoration.

Grounding is not judgement
---------------------------
`check_all` answers exactly one question per claim: *does this exact text exist at this
commit?* It never decides whether two grounded quotes **agree** — that is `contradicts`,
a label the caller writes down for its own reasoning, not something this module computes.
Using "the quote does not resolve" as a proxy for "these two things disagree" conflates a
missing citation (someone typed a quote from memory, or it changed) with a real semantic
contradiction between two texts that both genuinely exist. This module only does the
former; the latter is a judgement call for whoever reads `Checked` and writes it up.

The negative control
---------------------
A claim set that only ever contains contradictions is indistinguishable from one whose
author never checked an agreeing pair. `require_control` refuses a set with no claim
where `contradicts=False` — the same reasoning as any other control: a positive result on
its own is compatible with the instrument being broken.
"""

import subprocess
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Claim:
    """One assertion a document makes, and the code that settles it."""

    ref_id: str

    doc_path: str
    doc_quote: str
    """Verbatim from the document. Must resolve, or the claim set is rejected."""

    code_path: str
    code_quote: str
    """Verbatim from the code. The fact the document is measured against."""

    contradicts: bool
    """What the caller believes about this pair: that they disagree, or that they agree.

    Not evaluated here — both are grounded the same way. A claim that says "these agree"
    is the control, written in the same form as the rest so it cannot be special-cased.
    """

    why: str
    """What the disagreement (or agreement) means, in a sentence."""


@dataclass(frozen=True, slots=True)
class Checked:
    """A claim after both sides were fetched. `resolved=False` means it proved nothing."""

    claim: Claim
    sha: str
    doc_line: int | None
    code_line: int | None

    @property
    def resolved(self) -> bool:
        return self.doc_line is not None and self.code_line is not None


def _read_file_at_commit(repo_root: str, path: str, sha: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{sha}:{path}"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return result.stdout.decode("utf-8")


def _line_of(haystack: str, needle: str) -> int | None:
    """The 1-based line where a quote starts, or None when it is not there.

    Whitespace is normalized per line before comparing (a paste differs from the
    original in trailing spaces and nothing that matters); everything else must match
    exactly — this is the step that makes a citation binding.
    """
    lines = haystack.splitlines()
    wanted = [" ".join(part.split()) for part in needle.strip().splitlines() if part.strip()]
    if not wanted:
        return None
    normalized = [" ".join(line.split()) for line in lines]

    for index in range(len(normalized) - len(wanted) + 1):
        if all(normalized[index + offset] == wanted[offset] for offset in range(len(wanted))):
            return index + 1
    return None


def check(claim: Claim, repo_root: str, sha: str) -> Checked:
    """Fetch both sides at `sha` and locate both quotes."""
    document = _read_file_at_commit(repo_root, claim.doc_path, sha)
    code = _read_file_at_commit(repo_root, claim.code_path, sha)
    return Checked(
        claim=claim,
        sha=sha,
        doc_line=_line_of(document, claim.doc_quote),
        code_line=_line_of(code, claim.code_quote),
    )


def require_control(claims: tuple[Claim, ...]) -> None:
    """Refuse a claim set with no agreeing pair in it.

    Checked before anything is fetched: a run that is going to be rejected should not
    spend a round of git calls first, and a precondition that only fires at the end
    tends to get moved rather than satisfied.
    """
    if not any(not claim.contradicts for claim in claims):
        raise ValueError(
            "No agreeing pair (contradicts=False) in this claim set. A comparator that "
            "only ever finds contradictions cannot be told apart from a broken one that "
            "always says 'no match' — the control is what makes a confirmation worth "
            "anything."
        )


def check_all(claims: tuple[Claim, ...], repo_root: str, sha: str) -> list[Checked]:
    """Check every claim, and refuse to return if any quote failed to resolve.

    Failing loudly rather than dropping the unresolved ones is the point: a quote that
    stopped resolving is either a document that changed — which is news — or a citation
    typed from memory, which is worse. Both deserve to stop the run rather than silently
    produce a `Checked(resolved=False)` nobody looks at.
    """
    require_control(claims)
    checked = [check(claim, repo_root, sha) for claim in claims]

    unresolved = [
        f"{item.claim.ref_id}: "
        + " and ".join(
            label for label, missing in (
                ("doc quote", item.doc_line is None),
                ("code quote", item.code_line is None),
            ) if missing
        )
        + f" not found at {sha[:8]}"
        for item in checked if not item.resolved
    ]
    if unresolved:
        raise ValueError("Quotes that do not resolve are not evidence:\n  " + "\n  ".join(unresolved))
    return checked
