"""A `system` block with prompt caching always on.

`Agent` forwards `system` to the provider untouched (`providers/anthropic.py`), so the
*shape* of this value is what decides whether Anthropic caches it or not. A plain string
here loses the cache silently — no error, just a bill that never explains itself.
"""


def build_cached_system(text: str) -> list[dict]:
    """Wrap `text` in a single cached block for `Agent(system=...)`.

    Never returns a plain string, on purpose: a caller who accidentally does
    `system=str(build_cached_system(text))` gets a Python list repr instead of working
    prose, which fails loudly instead of quietly dropping the cache.
    """
    return [
        {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        }
    ]
