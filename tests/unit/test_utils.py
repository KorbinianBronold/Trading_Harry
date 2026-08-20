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
    # server_tool_use kommt von der echten API als PLAIN DICT zurueck
    # (Usage.model_config hat extra="allow", Pydantic reicht unbekannte
    # Felder als rohes JSON durch, nicht als Objekt mit Attributen) -- ein
    # MagicMock hier haette den getattr()-Bug maskiert, der in Prod
    # web_search_calls immer auf 0 hielt (s. C.9-Befund).
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="ok")]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = {"web_search_requests": 3, "web_fetch_requests": 0}

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6",
            system="s", user="u",
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
        )

    assert result.web_search_calls == 3


def test_web_search_calls_counted_from_blocks_when_usage_field_is_missing():
    """Gestreamte Antworten tragen KEIN usage.server_tool_use -- verifiziert
    gegen die echte API: beide Pfade liefern server_tool_use-Content-Bloecke,
    aber get_final_message() laesst das usage-Feld leer. Ohne diesen Fallback
    zaehlen genau die beiden gestreamten Aufrufer (broad_scan, deep_analysis)
    dauerhaft 0 Websuchen, und ihre Kosten sind zu niedrig ausgewiesen."""
    def _block(btype, name=None, text=None):
        b = MagicMock()
        b.type = btype
        b.name = name
        b.text = text
        return b

    fake_response = MagicMock()
    fake_response.content = [
        _block("server_tool_use", name="web_search"),
        _block("web_search_tool_result"),
        _block("server_tool_use", name="web_search"),
        _block("web_search_tool_result"),
        _block("text", text="ok"),
    ]
    fake_response.usage.input_tokens = 100
    fake_response.usage.output_tokens = 50
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    del fake_response.usage.server_tool_use          # wie im Streaming-Pfad

    fake_client = MagicMock()
    fake_stream = MagicMock()
    fake_stream.__enter__ = lambda s: s
    fake_stream.__exit__ = lambda s, *a: False
    fake_stream.get_final_message.return_value = fake_response
    fake_client.messages.stream.return_value = fake_stream

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6", system="s", user="u", stream=True,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )

    assert result.web_search_calls == 2
    assert result.text == "ok"


def test_usage_field_wins_over_block_count_when_present():
    """Wo die API zaehlt, gilt ihre Zahl -- der Block-Fallback ist nur fuer den
    Fall gedacht, dass das Feld fehlt."""
    def _block(btype, name=None, text=None):
        b = MagicMock()
        b.type = btype
        b.name = name
        b.text = text
        return b

    fake_response = MagicMock()
    fake_response.content = [_block("server_tool_use", name="web_search"),
                             _block("text", text="ok")]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = {"web_search_requests": 7}

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(model="claude-sonnet-4-6", system="s", user="u")

    assert result.web_search_calls == 7


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
    with pytest.raises(_DemoError):
        extract_json_blob("{invalid json}", _DemoError)


def test_extract_json_blob_raises_on_no_opening_brace():
    with pytest.raises(_DemoError, match="No JSON object found"):
        extract_json_blob("just text without any braces", _DemoError)


def test_extract_json_blob_ignores_trailing_commentary():
    # Simulates Claude appending explanation text after the JSON
    text = (
        '{"ticker": "NVDA", "score": 8.5}\n\n'
        "Note: Based on web search, I found additional context that "
        "supports the above analysis."
    )
    result = extract_json_blob(text, _DemoError)
    assert result == {"ticker": "NVDA", "score": 8.5}


def test_extract_json_blob_ignores_trailing_json_like_content():
    # Simulates 'Extra data' scenario: valid JSON followed by more text
    text = '{"a": 1}\n{"b": 2}'
    result = extract_json_blob(text, _DemoError)
    assert result == {"a": 1}  # only first object parsed, second ignored


def test_call_claude_streaming_path_uses_messages_stream():
    """stream=True geht ueber messages.stream(), nicht messages.create()."""
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="streamed answer")]
    fake_message.usage.input_tokens = 200
    fake_message.usage.output_tokens = 9000
    fake_message.usage.cache_read_input_tokens = 0
    fake_message.usage.cache_creation_input_tokens = 0
    fake_message.usage.server_tool_use = None
    fake_message.stop_reason = "end_turn"

    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value.get_final_message.return_value = fake_message

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = stream_ctx

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(
            model="claude-sonnet-4-6", system="sys", user="usr",
            max_tokens=9200, stream=True,
        )

    assert fake_client.messages.create.call_count == 0
    assert fake_client.messages.stream.call_count == 1
    assert fake_client.messages.stream.call_args.kwargs["max_tokens"] == 9200
    assert result.text == "streamed answer"
    assert result.output_tokens == 9000
    assert result.stop_reason == "end_turn"


def test_call_claude_streaming_passes_tools_and_cache_control():
    """Der Streaming-Pfad verliert weder tools noch das cache_control des
    System-Prompts -- beides sind stille Kostenfallen, wenn sie wegfallen."""
    fake_message = MagicMock()
    fake_message.content = [MagicMock(text="ok")]
    fake_message.usage.input_tokens = 10
    fake_message.usage.output_tokens = 5
    fake_message.usage.cache_read_input_tokens = 0
    fake_message.usage.cache_creation_input_tokens = 10
    fake_message.usage.server_tool_use = None
    fake_message.stop_reason = "end_turn"

    stream_ctx = MagicMock()
    stream_ctx.__enter__.return_value.get_final_message.return_value = fake_message

    fake_client = MagicMock()
    fake_client.messages.stream.return_value = stream_ctx

    with patch("src.utils._anthropic_client", fake_client):
        call_claude(
            model="claude-sonnet-4-6", system="long static prompt",
            user="q", tools=[{"type": "web_search_20250305", "name": "web_search"}],
            stream=True,
        )

    kwargs = fake_client.messages.stream.call_args.kwargs
    assert kwargs["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kwargs["tools"][0]["name"] == "web_search"


def test_call_claude_non_streaming_still_default_and_carries_stop_reason():
    """Default bleibt messages.create() -- kein bestehender Aufrufer aendert
    sein Verhalten. stop_reason wird auch dort durchgereicht."""
    fake_response = MagicMock()
    fake_response.content = [MagicMock(text="hi")]
    fake_response.usage.input_tokens = 1
    fake_response.usage.output_tokens = 2
    fake_response.usage.cache_read_input_tokens = 0
    fake_response.usage.cache_creation_input_tokens = 0
    fake_response.usage.server_tool_use = None
    fake_response.stop_reason = "max_tokens"

    fake_client = MagicMock()
    fake_client.messages.create.return_value = fake_response

    with patch("src.utils._anthropic_client", fake_client):
        result = call_claude(model="m", system="s", user="u")

    assert fake_client.messages.stream.call_count == 0
    assert result.stop_reason == "max_tokens"


# --- call_claude_retry_on_truncation ---------------------------------------
# Sonnet 5 denkt standardmaessig (adaptiv) und teilt sich die max_tokens-Decke
# zwischen Denk- und Antworttokens. Die drei Einzelcall-Module (trend_analyzer,
# market_context, revalidation) hatten dafuer bis zur 2026-08-20-Migration
# KEINE Erkennung: eine Kappung kam bei ihnen als JSONDecodeError an.

from src.utils import call_claude_retry_on_truncation, ClaudeTruncatedError


def _result(text: str, stop_reason: str, output_tokens: int = 100) -> ClaudeResult:
    return ClaudeResult(
        text=text, input_tokens=10, output_tokens=output_tokens,
        cache_read_tokens=0, cache_creation_tokens=0, model="claude-sonnet-5",
        web_search_calls=0, stop_reason=stop_reason,
    )


def test_truncation_retry_passes_clean_result_through_untouched():
    """Der Normalfall darf sich nicht aendern: ein Call, ein Billing."""
    tracker = MagicMock()
    clean = _result("{}", "end_turn")

    with patch("src.utils.call_claude", return_value=clean) as mock_call:
        out = call_claude_retry_on_truncation(
            model="m", system="s", user="u", max_tokens=1024, cost_tracker=tracker)

    assert out is clean
    assert mock_call.call_count == 1
    assert tracker.add_from_result.call_count == 1


def test_truncation_retry_repeats_with_doubled_ceiling():
    """Eine identische Wiederholung kaeme identisch zurueck -- die Decke steigt."""
    tracker = MagicMock()
    results = [_result("{trunc", "max_tokens"), _result("{}", "end_turn")]

    with patch("src.utils.call_claude", side_effect=results) as mock_call:
        out = call_claude_retry_on_truncation(
            model="m", system="s", user="u", max_tokens=1024, cost_tracker=tracker)

    assert out is results[1]
    assert mock_call.call_count == 2
    assert mock_call.call_args_list[0].kwargs["max_tokens"] == 1024
    assert mock_call.call_args_list[1].kwargs["max_tokens"] == 2048


def test_truncation_retry_bills_the_discarded_attempt_too():
    """Die gekappte Antwort ist bezahlt, auch wenn sie verworfen wird. Sie NICHT
    zu buchen waere genau der Fehler-Typ, der hier zweimal Kosten verschleiert
    hat (cache-Doppelabzug, web_search_calls)."""
    tracker = MagicMock()
    results = [_result("{trunc", "max_tokens", output_tokens=999),
               _result("{}", "end_turn", output_tokens=111)]

    with patch("src.utils.call_claude", side_effect=results):
        call_claude_retry_on_truncation(
            model="m", system="s", user="u", max_tokens=1024, cost_tracker=tracker)

    billed = [c.args[0] for c in tracker.add_from_result.call_args_list]
    assert [r.output_tokens for r in billed] == [999, 111]


def test_truncation_retry_raises_when_the_retry_also_truncates():
    """Sonst faellt eine doppelt gekappte Antwort wieder als JSONDecodeError
    an -- die Diagnose-Falle, die den Verifikationslauf gekostet hat."""
    tracker = MagicMock()
    results = [_result("{trunc", "max_tokens"), _result("{still", "max_tokens")]

    with patch("src.utils.call_claude", side_effect=results):
        with pytest.raises(ClaudeTruncatedError, match="2048"):
            call_claude_retry_on_truncation(
                model="m", system="s", user="u", max_tokens=1024, cost_tracker=tracker)


def test_truncation_retry_forwards_tools_and_stream():
    tracker = MagicMock()
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    with patch("src.utils.call_claude", return_value=_result("{}", "end_turn")) as mock_call:
        call_claude_retry_on_truncation(
            model="m", system="s", user="u", max_tokens=1024,
            cost_tracker=tracker, tools=tools, stream=True)

    kwargs = mock_call.call_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["stream"] is True
