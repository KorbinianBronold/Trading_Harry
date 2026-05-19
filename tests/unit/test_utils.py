import time
import pytest
from src.utils import retry_with_backoff


def test_retry_succeeds_on_first_try():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def f():
        calls.append(1)
        return "ok"

    assert f() == "ok"
    assert len(calls) == 1


def test_retry_succeeds_after_failures():
    calls = []

    @retry_with_backoff(max_retries=3, base_delay=0.01)
    def f():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return "ok"

    assert f() == "ok"
    assert len(calls) == 3


def test_retry_raises_after_exhaustion():
    @retry_with_backoff(max_retries=2, base_delay=0.01)
    def f():
        raise ValueError("permanent")

    with pytest.raises(ValueError, match="permanent"):
        f()


from unittest.mock import MagicMock, patch
from src.utils import call_claude, ClaudeResult


def test_call_claude_returns_text_and_usage():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="hello world")]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 80
    fake_response.usage.cache_creation_input_tokens = 0

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6",
            system="you are a helpful assistant",
            user="say hello",
        )

    assert isinstance(result, ClaudeResult)
    assert result.text == "hello world"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cache_read_tokens == 80


def test_call_claude_uses_cache_control_for_system_prompt():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 10

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        call_claude(
            model="claude-haiku-4-5",
            system="long static system prompt",
            user="dynamic question",
        )

    kwargs = fake_client.messages.create.call_args.kwargs
    assert kwargs["model"] == "claude-haiku-4-5"
    assert isinstance(kwargs["system"], list)
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["system"][0]["text"] == "long static system prompt"


def test_call_claude_extracts_web_search_calls():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = MagicMock(web_search_requests=3)

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6",
            system="s", user="u",
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        )

    assert result.web_search_calls == 3


def test_call_claude_web_search_calls_zero_when_absent():
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    # No server_tool_use attribute → 0
    del fake_response.usage.server_tool_use

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(model="claude-haiku-4-5", system="s", user="u")

    assert result.web_search_calls == 0


import pytest
from src.utils import extract_json_blob


class _DemoError(RuntimeError):
    pass


def test_extract_json_blob_parses_plain_json():
    assert extract_json_blob('{"a": 1}', _DemoError) == {"a": 1}


def test_extract_json_blob_strips_markdown_fences():
    text = "```json\n{\"a\": 2}\n```"
    assert extract_json_blob(text, _DemoError) == {"a": 2}


def test_extract_json_blob_extracts_outermost_braces_on_prose():
    text = "Sure, here is the result:\n{\"a\": 3}\nLet me know if you need more."
    assert extract_json_blob(text, _DemoError) == {"a": 3}


def test_extract_json_blob_raises_provided_error_class():
    with pytest.raises(_DemoError, match="Could not parse JSON"):
        extract_json_blob("not json at all and no braces", _DemoError)
