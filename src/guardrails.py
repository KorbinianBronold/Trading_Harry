"""Quality gate every deep-analysis/commodities-crypto result must pass before it's
eligible for ranking — enforces required fields, evidence counts, R/R ratio, signal
consistency, and CFD-specific hold-day/intraday-range limits."""
from dataclasses import dataclass
import config


@dataclass
class GuardrailsChecker:
    min_sources: int = 2
    min_evidence_per_dim: int = 2
    min_rr_hard: float = config.RR_RATIO_MIN_HARD
    momentum_long_min: float = config.MOMENTUM_LONG_MIN
    momentum_short_max: float = config.MOMENTUM_SHORT_MAX
    max_hold_days: int = config.MAX_HOLD_DAYS
    min_intraday_range_pct: float = 1.0

    REQUIRED_FIELDS = (
        "ticker", "direction", "confidence", "current_price",
        "tp_price", "sl_price", "rr_ratio", "total_score", "summary",
        "sources_used", "signal_consistency_check", "scores",
        "hold_days_recommended", "intraday_range_pct",
    )

    def check_analysis(self, a: dict) -> tuple[bool, list[str]]:
        """Validates one analysis dict against all guardrail rules and returns
        (passed, error_messages). Short-circuits with just the missing-field
        errors if any required field is absent."""
        errors: list[str] = []

        for f in self.REQUIRED_FIELDS:
            if f not in a or a[f] is None:
                errors.append(f"Required field missing: {f}")

        if errors:
            return False, errors

        if len(a.get("sources_used", [])) < self.min_sources:
            errors.append(
                f"Too few sources: {len(a['sources_used'])} < {self.min_sources}"
            )

        scores = a.get("scores", {})
        for dim, sd in scores.items():
            if len(sd.get("evidence", [])) < self.min_evidence_per_dim:
                errors.append(
                    f"Dimension {dim}: too few evidence items "
                    f"({len(sd.get('evidence', []))} < {self.min_evidence_per_dim})"
                )

        p = a["current_price"]
        tp = a["tp_price"]
        sl = a["sl_price"]
        d = a["direction"]
        if d == "long":
            if tp <= p:
                errors.append(f"Long TP {tp} not above entry {p}")
            if sl >= p:
                errors.append(f"Long SL {sl} not below entry {p}")
        elif d == "short":
            if tp >= p:
                errors.append(f"Short TP {tp} not below entry {p}")
            if sl <= p:
                errors.append(f"Short SL {sl} not above entry {p}")

        if a.get("rr_ratio", 0) < self.min_rr_hard:
            errors.append(f"R/R {a['rr_ratio']} below hard minimum {self.min_rr_hard}")

        if a.get("data_quality") == "low" and a.get("confidence") == "high":
            errors.append("Confidence 'high' incompatible with data_quality 'low'")

        momentum = scores.get("momentum", {}).get("value")
        if momentum is not None:
            if d == "long" and momentum < self.momentum_long_min:
                errors.append(
                    f"Signal consistency: long momentum {momentum} < {self.momentum_long_min}"
                )
            if d == "short" and momentum > self.momentum_short_max:
                errors.append(
                    f"Signal consistency: short momentum {momentum} > {self.momentum_short_max}"
                )

        hold_days = a.get("hold_days_recommended")
        if hold_days is not None and hold_days > self.max_hold_days:
            errors.append(
                f"Haltedauer > {self.max_hold_days} Tage – nicht CFD-geeignet "
                f"(hold_days_recommended={hold_days})"
            )

        rng = a.get("intraday_range_pct")
        if rng is not None and rng < self.min_intraday_range_pct:
            errors.append(
                f"Intraday-Range < {self.min_intraday_range_pct:.1f}% – nicht CFD-geeignet "
                f"(intraday_range_pct={rng})"
            )

        return len(errors) == 0, errors
