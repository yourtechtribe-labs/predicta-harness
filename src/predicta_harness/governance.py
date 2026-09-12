"""
governance.py — Model-risk governance for the things that change an agent's behaviour.

Banking learned this the hard way: a model is not governed by being good, it is governed
by being *registered, tiered, independently validated, approved, change-controlled and
monitored*. That is the shape of a Model Risk Management framework (the discipline
codified in the Fed's SR 11-7 and run in practice over three lines of defence: the team
that builds, an independent function that challenges it, and audit).

An agent's prompt IS a model artifact. Its system prompt, its operating manual, its
accumulated "learnings" and its tool set decide what it does, and all four are a text
file somebody can edit in ten seconds with nobody looking. This module applies the same
six controls to them.

    from predicta_harness.governance import Manifest, Governance

    manifest = Manifest("governance/manifest.json")
    manifest.register("system", kind="system", text=SYSTEM)
    manifest.approve("system", by="albert",
                     validation_ref="replay:test:2026-09-12:24/24")

    agent = Agent(model="anthropic/claude-sonnet-5", system=SYSTEM, tools=TOOLS,
                  governance=Governance(manifest, env="prod",
                                        protected=["skills/crm-operator/SKILL.md"]))

What that buys, and none of it relies on remembering anything:

1. INVENTORY     every governed artifact is in the manifest, by content hash.
2. TIERING       a tool's tier is DERIVED from the effects it declares; silence means
                 the higher tier, never the lower one.
3. VALIDATION    an approval without a validation reference is refused.
4. APPROVAL      in `env="prod"` the Agent REFUSES to start on an unapproved prompt.
5. CHANGE CTRL   editing an artifact changes its hash, which closes the gate by itself.
6. MONITORING    `review_flags()` derives, from a call ledger, which tools nobody uses.

Plus the two hard guarantees: no registered tool may declare write access to a governed
artifact (checked when the Agent is built), and a call that smuggles a governed path
through its arguments is refused at run time (the interceptor, as a backstop).

The module knows nothing about any particular domain. "Proposals get promoted by a
human" is not policy written here: it is what happens when the promotion target is a
governed artifact and no tool can write it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import warnings
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

logger = logging.getLogger("predicta_harness.governance")

# Tiers, most severe first. Two is enough: the point of a tier is to decide how much
# scrutiny an artifact needs, and a scale with five rungs just moves the argument to
# which rung something sits on.
TIERS = ("critical", "standard")

# Declared tool effects -> tier. An effect that is not in this map (including the
# absence of any declaration) is treated as `critical`: silence is not a claim of
# harmlessness, and the failure being protected against is exactly the tool whose
# author never thought about it.
_EFFECT_TIERS = {
    "read": "standard",
    "none": "standard",
    "write": "critical",
    "outward": "critical",
}


class GovernanceError(RuntimeError):
    """A governance control was violated. Never caught internally: it must reach the caller."""


def digest(text: Any) -> str:
    """Content hash of an artifact.

    Accepts a string or a structured prompt (the list of system blocks that providers
    take), so the same function can hash "the prompt" whatever shape the caller uses.
    Structured input is serialised with sorted keys, so an equivalent prompt hashes the
    same regardless of dict ordering.
    """
    if not isinstance(text, str):
        text = json.dumps(text, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def tier_for(t: Any) -> str:
    """The tier of a tool, DERIVED from the effects it declares (never hand-assigned)."""
    return _EFFECT_TIERS.get(getattr(t, "effects", None) or "", "critical")


@dataclass(frozen=True)
class Artifact:
    """One entry of the inventory: a piece of text that changes what the agent does."""

    id: str
    kind: str  # "system" | "skill" | "learnings" | "toolset" | whatever the caller means
    sha256: str
    tier: str = "critical"
    approved_by: str | None = None
    approved_at: str | None = None
    validation_ref: str | None = None  # where the evidence lives, e.g. "replay:test:24/24"
    review_by: str | None = None  # ISO date: periodic re-validation, MRM style

    @property
    def approved(self) -> bool:
        return bool(self.approved_by and self.validation_ref)

    @property
    def review_due(self) -> bool:
        if not self.review_by:
            return False
        # UTC on purpose: `approved_at` is stamped in UTC, so the due date is read in
        # the same frame. A naive `date.today()` would answer differently depending on
        # the timezone of the machine running the check.
        return date.fromisoformat(self.review_by) < datetime.now(timezone.utc).date()


class Manifest:
    """The inventory, on disk, with an append-only ledger beside it.

    Two files: `<path>` is the current state (what is registered and approved) and
    `<path stem>.ledger.jsonl` records every transition. The ledger is append-only on
    purpose: an approval you can quietly rewrite is not an approval. Same reasoning as
    the frozen verdict in the AI-first rules.
    """

    def __init__(self, path: str | os.PathLike):
        self.path = Path(path)
        self.ledger_path = self.path.with_suffix(".ledger.jsonl")
        self._artifacts: dict[str, Artifact] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._artifacts = {k: Artifact(**v) for k, v in raw.get("artifacts", {}).items()}

    # --- state -------------------------------------------------------------------

    def get(self, artifact_id: str) -> Artifact | None:
        return self._artifacts.get(artifact_id)

    def __iter__(self):
        return iter(self._artifacts.values())

    @property
    def approved_hashes(self) -> set[str]:
        return {a.sha256 for a in self._artifacts.values() if a.approved}

    def status(self, artifact_id: str, text: Any) -> str:
        """One of: `unregistered`, `changed`, `unapproved`, `review_due`, `approved`.

        `changed` beats everything else: an artifact whose content no longer matches the
        hash that was approved is, for governance purposes, a different artifact.
        """
        a = self._artifacts.get(artifact_id)
        if a is None:
            return "unregistered"
        if a.sha256 != digest(text):
            return "changed"
        if not a.approved:
            return "unapproved"
        return "review_due" if a.review_due else "approved"

    # --- transitions -------------------------------------------------------------

    def register(
        self, artifact_id: str, *, kind: str, text: Any, tier: str = "critical"
    ) -> Artifact:
        """Put an artifact in the inventory (unapproved).

        Re-registering new content drops any previous approval: that is control 5, not a
        side effect.
        """
        if tier not in TIERS:
            raise GovernanceError(f"unknown tier {tier!r}; expected one of {TIERS}")
        a = Artifact(id=artifact_id, kind=kind, sha256=digest(text), tier=tier)
        self._artifacts[artifact_id] = a
        self._write("register", a)
        return a

    def approve(
        self,
        artifact_id: str,
        *,
        by: str,
        validation_ref: str | None,
        review_by: str | None = None,
    ) -> Artifact:
        """Approve the artifact's CURRENT hash.

        `validation_ref` is mandatory and is the whole point: it says where the evidence
        lives (a replay verdict on a held-out split, a review, a measurement). An
        approval that cites nothing is a signature on an empty page, so it is refused
        rather than recorded.
        """
        a = self._artifacts.get(artifact_id)
        if a is None:
            raise GovernanceError(f"cannot approve {artifact_id!r}: not in the inventory")
        if not validation_ref:
            raise GovernanceError(
                f"cannot approve {artifact_id!r} without a validation reference "
                "(independent validation is control 3; cite the evidence)"
            )
        approved = Artifact(
            id=a.id,
            kind=a.kind,
            sha256=a.sha256,
            tier=a.tier,
            approved_by=by,
            approved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            validation_ref=validation_ref,
            review_by=review_by,
        )
        self._artifacts[artifact_id] = approved
        self._write("approve", approved)
        return approved

    def _write(self, event: str, a: Artifact) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = {"artifacts": {k: asdict(v) for k, v in self._artifacts.items()}}
        self.path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        entry = {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event,
            **asdict(a),
        }
        with self.ledger_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


@dataclass
class Governance:
    """The gate an `Agent` consults when it is built, and again on every tool call.

    `env="prod"` enforces (raises). Anything else warns: a laboratory has to be able to
    iterate on an unapproved prompt, which is precisely what it is for.
    """

    manifest: Manifest
    env: str = "dev"
    protected: Sequence[str] = field(default_factory=tuple)
    artifact_id: str = "system"

    @property
    def enforcing(self) -> bool:
        return self.env == "prod"

    def _fail(self, msg: str) -> None:
        if self.enforcing:
            raise GovernanceError(msg)
        logger.warning("governance (env=%s, not enforcing): %s", self.env, msg)
        warnings.warn(f"governance: {msg}", stacklevel=3)

    def check_prompt(self, text: Any) -> str:
        """Control 4 + 5. Returns the status; raises in prod when it is not `approved`."""
        status = self.manifest.status(self.artifact_id, text)
        if status == "approved":
            return status
        self._fail(
            f"system prompt {self.artifact_id!r} is {status}: it is not approved for "
            f"env={self.env!r}. Register it, validate it and approve its hash "
            f"({digest(text)[:12]}...) before running in production."
        )
        return status

    def check_tools(self, tools: Iterable[Any]) -> None:
        """Hard guarantee 1, checked at construction.

        A tool that declares it writes a governed artifact never gets to run in the
        first place. Structural, not a judgement about what a tool "looks like" it does:
        it compares declared write paths against governed paths.
        """
        governed = {str(Path(p).resolve()) for p in self.protected}
        for t in tools:
            for w in getattr(t, "writes", ()) or ():
                if str(Path(w).resolve()) in governed:
                    raise GovernanceError(
                        f"tool {getattr(t, 'name', t)!r} declares write access to a "
                        f"governed artifact ({w}). A governed artifact is changed by a "
                        "human through the manifest, never by the agent."
                    )

    def interceptor(self) -> Callable[[str, dict], str | None]:
        """Hard guarantee 2, at run time.

        Refuse a call whose arguments point at a governed path. A backstop for the
        construction check above, not a substitute for it: it compares paths, and that
        is all it will ever do.
        """
        governed = {str(Path(p).resolve()) for p in self.protected}

        def interceptor(name: str, tool_input: dict) -> str | None:
            for value in tool_input.values():
                if not isinstance(value, str):
                    continue
                try:
                    resolved = str(Path(value).resolve())
                except (OSError, ValueError):
                    continue
                if resolved in governed:
                    logger.warning("governance: refused tool=%s path=%s", name, value)
                    return (
                        f"Refused: {value} is a governed artifact. Changes to it go "
                        "through a human review, not through a tool call."
                    )
            return None

        return interceptor


def call_counts(calls: Iterable[tuple[str, dict]]) -> dict[str, int]:
    """Tool call counts from a ledger of `(name, input)` pairs, which is exactly what
    `replay.Verdict.tool_calls` already collects."""
    counts: dict[str, int] = {}
    for name, _ in calls:
        counts[name] = counts.get(name, 0) + 1
    return counts


def review_flags(
    tool_names: Iterable[str],
    calls: Iterable[tuple[str, dict]],
    *,
    min_calls_total: int = 100,
) -> dict[str, str]:
    """Control 6. Which tools does the evidence say nobody uses?

    Below `min_calls_total` observed calls it returns nothing: a tool with zero calls
    across five turns is not a finding, it is a small sample. This is the difference
    between a monitored metric and a sentence in a document that ages badly, and it is
    why the threshold is an argument rather than a comment.
    """
    counts = call_counts(calls)
    if sum(counts.values()) < min_calls_total:
        return {}
    return {n: "never_called" for n in tool_names if counts.get(n, 0) == 0}
