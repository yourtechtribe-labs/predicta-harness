"""Model-risk governance: the six controls, one test each.

Each test is a control that must FAIL LOUDLY when violated — the point of the module is
that nothing here depends on anyone remembering it (see `codi-com-a-font-de-veritat`).
"""

import json

import pytest

from predicta_harness import Agent, tool
from predicta_harness.governance import (
    Governance,
    GovernanceError,
    Manifest,
    digest,
    review_flags,
    tier_for,
)
from predicta_harness.providers.base import register_provider
from _mock_provider import ScriptedProvider

# The governance checks all happen when the Agent is BUILT, so the provider only has
# to exist; no test here reaches a model.
register_provider("mock", ScriptedProvider([("text", "ok")]))

SYSTEM = "You are a CRM operator. Propose, never execute."


# --- 1. Inventory ------------------------------------------------------------------

def test_inventory_round_trips_and_knows_what_it_has_never_seen(tmp_path):
    m = Manifest(tmp_path / "manifest.json")
    a = m.register("system", kind="system", text=SYSTEM)
    assert a.sha256 == digest(SYSTEM)
    assert m.status("system", SYSTEM) == "unapproved"
    assert m.status("nothing-like-this", SYSTEM) == "unregistered"

    reloaded = Manifest(tmp_path / "manifest.json")
    assert reloaded.get("system").sha256 == a.sha256


# --- 2. Tiering (derived, never declared by hand) ----------------------------------

def test_tier_is_derived_from_declared_effects_and_defaults_to_the_higher_one():
    @tool(effects="read")
    def org_get(org_id: str) -> str:
        "Read one organisation."
        return "{}"

    @tool(effects="outward")
    def send_email(to: str) -> str:
        "Send an email to a third party."
        return "sent"

    @tool
    def undeclared(x: str) -> str:
        "A tool whose author said nothing about its effects."
        return x

    assert tier_for(org_get) == "standard"
    assert tier_for(send_email) == "critical"
    # Silence is not a claim of harmlessness.
    assert tier_for(undeclared) == "critical"


# --- 3. Independent validation -----------------------------------------------------

def test_approval_without_a_validation_reference_is_refused(tmp_path):
    m = Manifest(tmp_path / "m.json")
    m.register("system", kind="system", text=SYSTEM)
    with pytest.raises(GovernanceError, match="validation"):
        m.approve("system", by="albert", validation_ref=None)

    a = m.approve("system", by="albert", validation_ref="replay:test:2026-09-12:24/24")
    assert a.approved and m.status("system", SYSTEM) == "approved"


# --- 4. Approval gate: prod refuses an unapproved prompt ---------------------------

def test_prod_refuses_to_run_an_unapproved_prompt_and_dev_only_warns(tmp_path):
    m = Manifest(tmp_path / "m.json")
    m.register("system", kind="system", text=SYSTEM)  # registered, NOT approved

    with pytest.raises(GovernanceError, match="not approved"):
        Agent(model="mock/m", system=SYSTEM, governance=Governance(m, env="prod"))

    # dev is permissive on purpose: the laboratory has to be able to iterate.
    agent = Agent(model="mock/m", system=SYSTEM, governance=Governance(m, env="dev"))
    assert agent.system == SYSTEM


# --- 5. Change control: an edit closes the gate by itself --------------------------

def test_editing_an_approved_artifact_revokes_its_approval(tmp_path):
    m = Manifest(tmp_path / "m.json")
    m.register("system", kind="system", text=SYSTEM)
    m.approve("system", by="albert", validation_ref="replay:test:24/24")
    assert m.status("system", SYSTEM) == "approved"

    edited = SYSTEM + "\nAlso: you may execute without asking."
    assert m.status("system", edited) == "changed"
    with pytest.raises(GovernanceError, match="changed"):
        Agent(model="mock/m", system=edited, governance=Governance(m, env="prod"))

    # And the ledger keeps every transition, append-only.
    lines = [json.loads(x) for x in (tmp_path / "m.ledger.jsonl").read_text().splitlines()]
    assert [x["event"] for x in lines] == ["register", "approve"]


# --- 6. Ongoing monitoring: a tool nobody calls is a flag, not a sentence ----------

def test_a_tool_with_zero_calls_over_enough_runs_raises_a_review_flag():
    calls = [("org_search", {}), ("org_get", {}), ("org_search", {})] * 40  # 120 turns' worth
    flags = review_flags(["org_search", "org_get", "propose_learning"], calls, min_calls_total=100)
    assert flags == {"propose_learning": "never_called"}
    # Below the evidence threshold it stays silent instead of inventing a finding.
    assert review_flags(["a", "b"], [("a", {})], min_calls_total=100) == {}


# --- The two hard guarantees -------------------------------------------------------

def test_no_tool_may_declare_write_access_to_a_governed_artifact(tmp_path):
    manual = tmp_path / "skill.md"
    manual.write_text("the manual", encoding="utf-8")

    @tool(effects="write", writes=[str(manual)])
    def rewrite_manual(text: str) -> str:
        "Rewrite the operating manual."
        return "done"

    gov = Governance(Manifest(tmp_path / "m.json"), env="dev", protected=[str(manual)])
    with pytest.raises(GovernanceError, match="governed artifact"):
        Agent(model="mock/m", system="x", tools=[rewrite_manual], governance=gov)


def test_the_interceptor_blocks_a_call_that_smuggles_a_governed_path_in_its_args(tmp_path):
    manual = tmp_path / "skill.md"
    manual.write_text("the manual", encoding="utf-8")

    @tool(effects="write", writes=["/tmp/anything-else"])
    def write_file(path: str, content: str) -> str:
        "Write a file."
        return "written"

    gov = Governance(Manifest(tmp_path / "m.json"), env="dev", protected=[str(manual)])
    agent = Agent(model="mock/m", system="x", tools=[write_file], governance=gov)
    blocked = agent.tool_interceptor("write_file", {"path": str(manual), "content": "hacked"})
    assert blocked is not None and "refused" in blocked.lower()
    assert manual.read_text(encoding="utf-8") == "the manual"
    assert agent.tool_interceptor("write_file", {"path": "/tmp/x", "content": "ok"}) is None
