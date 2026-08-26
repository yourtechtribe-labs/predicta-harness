from predicta_harness.agent import Agent
from predicta_harness.providers.base import register_provider
from predicta_harness.replay import Case, load_corpus, replay

from _mock_provider import ScriptedProvider


class FailingAgent:
    """A duck-typed double that always raises — no real Agent needed to test that a
    failing case does not sink the corpus."""

    def run(self, message, history=None):
        raise RuntimeError("boom")


TOY_CORPUS = load_corpus(
    [
        {"case_id": "c1", "message": "hello"},
        {"case_id": "c2", "message": "boom", "context": {"expected": "failure"}},
    ]
)


def test_produces_one_verdict_per_case_against_a_real_agent():
    register_provider("replay-scripted-1", ScriptedProvider([("text", "hi there")]))
    agent = Agent(model="replay-scripted-1/test-model")

    verdicts = replay(agent, load_corpus([{"case_id": "c1", "message": "hello"}]))

    assert len(verdicts) == 1
    assert verdicts[0].case_id == "c1"
    assert verdicts[0].outcome == "ok"
    assert verdicts[0].response == "hi there"  # unwrapped from RunResult.text


def test_a_failing_case_does_not_sink_the_rest_of_the_corpus():
    verdicts = replay(FailingAgent(), TOY_CORPUS)

    by_id = {v.case_id: v for v in verdicts}
    assert by_id["c2"].outcome == "failed"
    assert by_id["c2"].error == "boom"


def test_load_corpus_builds_case_objects_with_defaults():
    corpus = load_corpus([{"case_id": "x1", "message": "hi"}])

    assert len(corpus) == 1
    assert isinstance(corpus[0], Case)
    assert corpus[0].history == []
    assert corpus[0].context == {}
