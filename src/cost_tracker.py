from dataclasses import dataclass, field
import config

USD_PER_EUR = 1.10

# Per million tokens, USD. Use Anthropic published rates (May 2026).
MODEL_PRICING = {
    "claude-opus-4-7":   {"input": 15.00, "output": 75.00, "cache_read": 1.50, "cache_write": 18.75},
    "claude-sonnet-4-6": {"input":  3.00, "output": 15.00, "cache_read": 0.30, "cache_write":  3.75},
    "claude-haiku-4-5":  {"input":  1.00, "output":  5.00, "cache_read": 0.10, "cache_write":  1.25},
}

WEB_SEARCH_USD_PER_CALL = 0.01  # Approx Anthropic web search billing


class CostCapExceeded(Exception):
    pass


@dataclass
class CostTracker:
    hard_cap_eur: float = config.MAX_COST_PER_RUN_EUR
    warn_threshold_eur: float = config.COST_WARN_THRESHOLD_EUR

    total_eur: float = 0.0
    claude_eur: float = 0.0
    web_search_eur: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    web_search_calls: int = 0
    aborted_at_phase: str | None = None
    _warned: bool = field(default=False, repr=False)

    def add_call(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_creation_tokens: int = 0,
        web_search_calls: int = 0,
    ) -> None:
        pricing = MODEL_PRICING.get(model)
        if pricing is None:
            raise ValueError(f"Unknown model pricing: {model}")

        fresh_input = max(0, input_tokens - cache_read_tokens)
        usd_input  = fresh_input          / 1_000_000 * pricing["input"]
        usd_output = output_tokens         / 1_000_000 * pricing["output"]
        usd_cache_read   = cache_read_tokens     / 1_000_000 * pricing["cache_read"]
        usd_cache_write  = cache_creation_tokens / 1_000_000 * pricing["cache_write"]
        usd_web    = web_search_calls * WEB_SEARCH_USD_PER_CALL

        usd_total = usd_input + usd_output + usd_cache_read + usd_cache_write + usd_web
        eur_total = usd_total / USD_PER_EUR

        self.claude_eur     += (usd_input + usd_output + usd_cache_read + usd_cache_write) / USD_PER_EUR
        self.web_search_eur += usd_web / USD_PER_EUR
        self.total_eur      += eur_total

        self.input_tokens      += input_tokens
        self.output_tokens     += output_tokens
        self.cache_read_tokens += cache_read_tokens
        self.web_search_calls  += web_search_calls

        if self.total_eur > self.hard_cap_eur:
            raise CostCapExceeded(
                f"Run cost {self.total_eur:.2f} EUR > cap {self.hard_cap_eur:.2f} EUR"
            )
        if not self._warned and self.total_eur > self.warn_threshold_eur:
            self._warned = True

    def add_from_result(self, result) -> None:
        """Shortcut for the 4 Claude callers — forwards every field from a
        utils.ClaudeResult into add_call(). Avoids 6-kwarg boilerplate."""
        self.add_call(
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_read_tokens=result.cache_read_tokens,
            cache_creation_tokens=result.cache_creation_tokens,
            web_search_calls=result.web_search_calls,
        )

    def summary(self, run_type: str, date: str) -> dict:
        hit_rate = 0.0
        if self.input_tokens > 0:
            hit_rate = self.cache_read_tokens / self.input_tokens
        return {
            "date": date, "run_type": run_type,
            "total_eur": round(self.total_eur, 4),
            "claude_eur": round(self.claude_eur, 4),
            "web_search_eur": round(self.web_search_eur, 4),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_hit_rate": round(hit_rate, 4),
            "web_search_calls": self.web_search_calls,
            "aborted_at_phase": self.aborted_at_phase,
        }
