"""The Anthropic SDK this harness passes kwargs to must accept them.

`AnthropicProvider.complete` forwards `**kwargs` straight into
`messages.create`. That is the right design — the harness should not have to
know every sampling knob — but it means an SDK that removes a parameter turns a
caller's kwarg into a TypeError at call time, in whatever process happens to run
first.

On 2026-08-21 that process was a client-facing job. The Anthropic SDK released
1.0.0 and dropped `temperature` from `messages.create`; the dependency said
`anthropic>=0.40` with no ceiling, so a production image picked it up silently.
The reconciliation triage died on its first call:

    TypeError: Messages.create() got an unexpected keyword argument 'temperature'

having judged 0 of 1.798 matches. The same code worked on every developer
machine, all of which had 0.122.0.

So the pin has a test, and the test checks the thing the pin exists for: that
the installed SDK really accepts what callers pass.
"""
import inspect
import os

import pytest

#: Set by the CI job that installs the provider extras on purpose.
#:
#: Without it this module skips, which is correct on a machine that installed the
#: base package — there is no SDK to introspect. It is NOT correct in the job whose
#: whole reason to exist is running this file: a skip there is green for the same
#: reason a deleted test is green, and this guard is the one that stands between a
#: silent SDK major and a client-facing job dying on its first call.
REQUIRE = os.environ.get("HARNESS_REQUIRE_PROVIDER_EXTRAS") == "1"

try:
    import anthropic
except ImportError:  # pragma: no cover - exercised by the two CI jobs, oppositely
    if REQUIRE:
        raise AssertionError(
            "HARNESS_REQUIRE_PROVIDER_EXTRAS=1 but the anthropic extra is not "
            "installed. This job exists to run this file; skipping it would report "
            "green for a guard that did not run."
        )
    anthropic = None

pytestmark = pytest.mark.skipif(
    anthropic is None,
    reason="the anthropic extra is not installed in this environment",
)

#: Kwargs this repo's callers forward through `complete(**kwargs)`. Add one when
#: a caller starts passing it — that is the moment it becomes load-bearing.
KWARGS_QUE_SE_PASAN = ["temperature"]


def _parametros_de_create() -> set[str]:
    cliente = anthropic.Anthropic(api_key="not-a-real-key")
    return set(inspect.signature(cliente.messages.create).parameters)


@pytest.mark.parametrize("kwarg", KWARGS_QUE_SE_PASAN)
def test_the_installed_sdk_accepts_what_callers_forward(kwarg: str):
    parametros = _parametros_de_create()
    assert kwarg in parametros, (
        f"anthropic {anthropic.__version__} has no '{kwarg}' on messages.create, "
        f"so any caller passing it raises TypeError at call time. Its parameters "
        f"are: {sorted(parametros)}. Either pin the SDK below the version that "
        f"removed it, or port the provider to wherever it moved."
    )


def test_the_sdk_is_below_the_major_that_reorganised_the_signature():
    """The ceiling itself, stated as a version rather than as a symptom.

    1.0.0 did not only drop `temperature`: `cache_control` and `output_config`
    became top-level parameters and `thinking` appeared. Porting is a deliberate
    change with its own measurement, not something to discover from a job that
    ran overnight.
    """
    mayor = int(anthropic.__version__.split(".")[0])
    assert mayor < 1, (
        f"anthropic {anthropic.__version__} is 1.x, which reorganised "
        "messages.create. Port AnthropicProvider before lifting the pin."
    )
