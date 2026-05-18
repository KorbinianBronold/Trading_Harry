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
