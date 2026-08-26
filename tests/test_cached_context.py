from predicta_harness.cached_context import build_cached_system


def test_returns_a_list_with_ephemeral_cache_control():
    result = build_cached_system("some context")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["cache_control"] == {"type": "ephemeral"}


def test_never_returns_a_plain_string():
    result = build_cached_system("some context")

    assert not isinstance(result, str)
    for block in result:
        assert isinstance(block, dict)
        assert "cache_control" in block


def test_preserves_the_text_verbatim():
    text = "domain rules for the agent"

    result = build_cached_system(text)

    assert result[0]["text"] == text
    assert result[0]["type"] == "text"


def test_empty_text_still_gets_cache_control():
    result = build_cached_system("")

    assert result[0]["cache_control"] == {"type": "ephemeral"}
