"""Cross-cutting helpers used by every Claude-calling module: retry decorator,
the Anthropic API wrapper with prompt caching, and tolerant JSON extraction from
Claude's text responses."""
import logging
import time
from functools import wraps
from typing import Any, Callable

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("shares_future")


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator factory: retries the wrapped function up to max_retries times with
    exponential backoff, re-raising the last exception if all attempts fail."""
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(max_retries):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        log.warning(
                            f"{fn.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. "
                            f"Retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
            raise last_exc

        return wrapper

    return decorator


from dataclasses import dataclass
from anthropic import Anthropic
import config

_anthropic_client = Anthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None


@dataclass
class ClaudeResult:
    text: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    model: str
    web_search_calls: int = 0
    # Spec 4.8: stop_reason == "max_tokens" ist ein Fehlerfall, kein
    # akzeptables Ergebnis. Bis Plan 3a war das Feld nicht verfuegbar und
    # broad_scan musste output_tokens gegen MAX_TOKENS schaetzen.
    stop_reason: str | None = None


def _result_from_message(response, model: str) -> ClaudeResult:
    """Baut ClaudeResult aus einer fertigen Anthropic-Message. Gemeinsam fuer
    den gestreamten und den nicht gestreamten Pfad -- get_final_message()
    liefert dieselbe Message-Form wie messages.create()."""
    text_parts = [b.text for b in response.content if hasattr(b, "text") and b.text is not None]

    # server_tool_use kommt als PLAIN DICT zurueck, nicht als Objekt mit
    # Attributen (Usage.model_config hat extra="allow", Pydantic reicht
    # unbekannte Felder als rohes JSON durch) -- getattr() liefert auf einem
    # dict immer den Default und hielt web_search_calls damit dauerhaft auf 0.
    #
    # ⚠️ Im GESTREAMTEN Pfad fehlt das Feld ganz: get_final_message() liefert
    # usage.server_tool_use == None, obwohl dieselbe Antwort sehr wohl
    # server_tool_use-Content-Bloecke traegt (gegen die echte API verifiziert).
    # Ohne den Fallback zaehlen genau die beiden gestreamten Aufrufer --
    # broad_scan und die Batch-Tiefenanalyse -- dauerhaft 0 Websuchen, und ihre
    # Kosten sind zu niedrig ausgewiesen. Die Bloecke sind ohnehin die Wahrheit;
    # das usage-Feld hat trotzdem Vorrang, wo es existiert.
    server_tool_use = getattr(response.usage, "server_tool_use", None)
    if server_tool_use is not None:
        web_search_calls = server_tool_use.get("web_search_requests", 0) or 0
    else:
        web_search_calls = sum(
            1 for b in response.content
            if getattr(b, "type", None) == "server_tool_use"
            and getattr(b, "name", "web_search") == "web_search"
        )

    return ClaudeResult(
        text="\n".join(text_parts),
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        model=model,
        web_search_calls=web_search_calls,
        stop_reason=getattr(response, "stop_reason", None),
    )


@retry_with_backoff(max_retries=2, base_delay=2.0)
def call_claude(
    model: str,
    system: str,
    user: str,
    max_tokens: int = 4096,
    tools: list | None = None,
    stream: bool = False,
) -> ClaudeResult:
    """Calls the Anthropic API with the system prompt cached (ephemeral), retries
    on transient failures, and returns a ClaudeResult with text, token, and
    web-search-call counts.

    stream=True nimmt messages.stream() + get_final_message() statt
    messages.create(). Noetig, sobald die erwartete Ausgabe gross wird: der
    nicht gestreamte Pfad haengt am httpx-Default-Timeout von 600s, den eine
    lange Generierung plus mehrere Websuchen reissen kann (Spec 4.8, 20.4).
    Default bleibt False -- kein bestehender Aufrufer aendert sein Verhalten,
    ohne es explizit zu wollen."""
    if _anthropic_client is None:
        raise RuntimeError("ANTHROPIC_API_KEY not configured")

    system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user}],
    )
    if tools:
        kwargs["tools"] = tools

    if stream:
        with _anthropic_client.messages.stream(**kwargs) as s:
            response = s.get_final_message()
    else:
        response = _anthropic_client.messages.create(**kwargs)

    return _result_from_message(response, model)


import json
import re
from typing import Type

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)


def extract_json_blob(text: str, error_cls: Type[Exception]) -> dict:
    """Tolerate ```json ... ``` fences, leading prose, and trailing text/commentary.
    Uses raw_decode so any content after the closing } is silently ignored.
    Raises the caller-provided error_cls on failure."""
    m = _JSON_FENCE_RE.search(text)
    if m:
        text = m.group(1)
    start = text.find("{")
    if start < 0:
        raise error_cls("No JSON object found in response")
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
        return obj
    except json.JSONDecodeError as e:
        raise error_cls(f"Could not parse JSON: {e}") from e


WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}
