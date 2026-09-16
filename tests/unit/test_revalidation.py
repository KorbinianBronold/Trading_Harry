"""Tests fuer src/revalidation.py — der billige 16:10-Check (Entscheidung E1)."""
import json
from unittest.mock import MagicMock
import pytest

import config
from src.cost_tracker import CostTracker


def _claude(text: str) -> MagicMock:
    return MagicMock(text=text, model=config.CLAUDE_MODEL_SONNET,
                     input_tokens=800, output_tokens=200,
                     cache_read_tokens=0, cache_creation_tokens=0,
                     web_search_calls=0)


PRED = {"id": 7, "ticker": "AAPL", "direction": "long", "entry_price": 178.0,
        "tp_price": 184.0, "sl_price": 176.0, "probability_pct": 65,
        "confidence": "high", "summary": "Momentum-Setup"}
OK_JSON = ('{"verdict": "bestaetigt", "probability_pct": 71, '
           '"entry_window_low": 178.2, "entry_window_high": 179.0, '
           '"reason": "haelt nach Opening"}')


def test_revalidation_uses_no_web_search(mocker):
    """E1: die 27 Einzelrecherchen sind gestrichen — genau das spart die Kosten."""
    call = mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                   checks=[], relative_strength=1.4, policy_context={},
                   cost_tracker=CostTracker())
    assert call.call_args.kwargs["tools"] == []


def test_revalidation_returns_verdict_and_probability(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    out = revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                         checks=[], relative_strength=1.4, policy_context={},
                         cost_tracker=CostTracker())
    assert out["verdict"] == "bestaetigt"
    assert out["probability_pct"] == 71
    assert out["entry_window_low"] == 178.2
    assert out["ticker"] == "AAPL"


def test_revalidation_rejects_an_unknown_verdict(mocker):
    """Ein erfundenes Urteil darf nicht still als 'bestaetigt' durchgehen."""
    mocker.patch("src.utils.call_claude",
                 return_value=_claude('{"verdict": "super", "probability_pct": 71}'))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_raises_on_unparseable_output(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude("kein JSON"))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={}, checks=[],
                       relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


def test_revalidation_books_its_cost(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    tracker = CostTracker()
    revalidate_one(prediction=PRED, snapshot={}, checks=[],
                   relative_strength=None, policy_context={},
                   cost_tracker=tracker)
    assert tracker.total_eur > 0


def test_fired_checks_reach_the_model(mocker):
    """Der Prompt muss die Warnungen kennen, sonst kann er sie nicht wuerdigen."""
    call = mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    from src.signal_checks import CheckResult
    revalidate_one(
        prediction=PRED, snapshot={}, relative_strength=None, policy_context={},
        checks=[CheckResult("vix_high_confidence_only", "VIX 28.4 zu hoch", False)],
        cost_tracker=CostTracker(),
    )
    assert "VIX 28.4 zu hoch" in call.call_args.kwargs["user"]


# ---------- C.49 / F67 + F70 + F71: feste Nutzlast, Datumsanker, Pruefung der Modellwerte ----------

import sqlite3 as _sqlite3

FULL_PRED = {
    "id": 15, "date": "2026-09-16", "run_type": "pre_market", "asset_class": "crypto",
    "ticker": "BTCUSD", "direction": "short", "entry_price": 75840.1,
    "tp_price": 74323.3, "tp_pct": 2.0, "sl_price": 76598.5, "sl_pct": 1.0, "rr_ratio": 2.0,
    "total_score": 5.7, "probability_pct": 52, "confidence": "low", "score_momentum": 3.5,
    "summary": "BTC sits near $75.8K ...", "learnable": 1, "status": "open",
    "hold_days_recommended": 1, "intraday_range_pct": 3.036, "created_at": "2026-09-16 10:37:06",
    "superseded_by": None, "revision_verdict": None, "price_premarket": 75840.1,
    "price_open": None, "price_1610": None, "is_premarket": 1, "candidate_class": "core",
    "tech_direction": "short", "tech_agreement": 2, "tech_adx_band": "strong",
    "tech_strength": 3, "analysis_strength": 5, "rank_score": 15, "news_strength": None,
    "pe_ratio": None, "relative_strength": None,
}
FULL_SNAP = {
    "ticker": "BTCUSD", "price": 75452.25, "price_change_1d": -0.51, "price_change_5d": -1.2,
    "price_change_1m": -3.7, "price_change_3m": 16.3, "rsi_14": 46.1, "rsi_trend": "falling",
    "macd_signal": "bearish", "atr_pct": 2.99, "bb_position": 0.03, "above_sma20": -3.9,
    "above_sma50": 4.9, "above_sma200": 7.0, "volume_ratio": 0.89, "intraday_range_pct": 3.04,
    "pe_ratio": None, "forward_pe": None, "market_cap_b": None, "debt_equity": None,
    "sector": "Unknown", "analyst_target_upside": None, "analyst_consensus": None,
    "analyst_consensus_period": None, "earnings_in_days": None, "earnings_beat_pct": None,
    "data_quality": "medium", "price_open": None,
}


def _row(d: dict) -> _sqlite3.Row:
    conn = _sqlite3.connect(":memory:")
    conn.row_factory = _sqlite3.Row
    cols = ", ".join(d)
    return conn.execute(f"SELECT {', '.join(f'? AS {k}' for k in d)}", list(d.values())).fetchone()


def test_prediction_view_carries_only_the_thesis_not_the_pipeline_row():
    """F67: bis C.49 ging die komplette predictions-Zeile (SELECT *, ~60 Spalten
    mit id, status, learnable, rank_score, candidate_class, created_at) als
    ORIGINAL PREDICTION in den bezahlten Prompt -- F48-Klasse."""
    from src.revalidation import prediction_view, PREDICTION_KEYS
    view = prediction_view(_row(FULL_PRED))
    assert set(view) == set(PREDICTION_KEYS)
    for leaked in ("id", "status", "learnable", "rank_score", "candidate_class",
                   "created_at", "superseded_by", "analysis_strength", "score_momentum"):
        assert leaked not in view, leaked
    assert view["entry_price"] == 75840.1 and view["summary"].startswith("BTC")


def test_snapshot_view_uses_the_4a_technical_keys_plus_open():
    from src.revalidation import snapshot_view
    from src.portfolio_check import TECHNICAL_KEYS
    view = snapshot_view({**FULL_SNAP, "price_open": 75600.0})
    assert set(view) == set(TECHNICAL_KEYS) | {"price_open"}
    for leaked in ("pe_ratio", "sector", "data_quality", "analyst_consensus"):
        assert leaked not in view, leaked


def test_user_message_starts_with_date_and_names_both_technical_signals():
    """F47-Klasse: Datumsanker und Run-Type; F67: Technik-Signal Morgen -> jetzt
    mit seiner Skala (0-4), Levels gegen den aktuellen Kurs."""
    from src.revalidation import _build_user_message
    msg = _build_user_message(
        _row(FULL_PRED), FULL_SNAP, [], relative_strength=None, policy_context={},
        tech={"tech_direction": "short", "tech_strength": 2}, date="2026-09-16",
        now_utc="2026-09-16T14:10:00")
    assert msg.startswith("Today is 2026-09-16, 10:10 ET (40 minutes after the 09:30 open). "
                          "Run type: trade_proposals")
    assert "TECHNICAL SIGNAL" in msg and "short/3" in msg and "short/2" in msg
    assert "LEVELS AT CURRENT PRICE" in msg and "0.98" in msg, "R/R gegen den 16:10-Kurs"
    assert '"rank_score"' not in msg and '"created_at"' not in msg


def test_revalidate_one_rejects_a_probability_outside_0_100(mocker):
    """F71: probability_pct wurde ungeprueft persistiert."""
    mocker.patch("src.utils.call_claude", return_value=_claude(
        '{"verdict": "bestaetigt", "probability_pct": 140, "entry_window_low": 178.2, '
        '"entry_window_high": 179.0, "reason": "x"}'))
    from src.revalidation import revalidate_one, RevalidationError
    with pytest.raises(RevalidationError):
        revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                       checks=[], relative_strength=None, policy_context={},
                       cost_tracker=CostTracker())


@pytest.mark.parametrize("low,high,why", [
    (179.5, 178.5, "low > high"),
    (175.0, 177.0, "unter dem Stop (long)"),
    (184.5, 185.0, "ueber dem TP (long)"),
    (None, 179.0, "halbes Fenster"),
])
def test_revalidate_one_drops_an_implausible_entry_window(mocker, caplog, low, high, why):
    """F71: ein Fenster auf der falschen Seite oder jenseits von TP/SL waere die
    einzige Handlungsanweisung der 16:10-Mail -- und falsch. Es wird verworfen
    (beide None) und geloggt, das Urteil bleibt."""
    import logging
    mocker.patch("src.utils.call_claude", return_value=_claude(
        json.dumps({"verdict": "bestaetigt", "probability_pct": 70,
                    "entry_window_low": low, "entry_window_high": high, "reason": "x"})))
    from src.revalidation import revalidate_one
    with caplog.at_level(logging.WARNING):
        out = revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                             checks=[], relative_strength=None, policy_context={},
                             cost_tracker=CostTracker())
    assert out["verdict"] == "bestaetigt"
    assert out["entry_window_low"] is None and out["entry_window_high"] is None
    assert "Entry-Fenster" in caplog.text, why


def test_revalidate_one_keeps_a_plausible_entry_window(mocker):
    mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    out = revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                         checks=[], relative_strength=None, policy_context={},
                         cost_tracker=CostTracker())
    assert (out["entry_window_low"], out["entry_window_high"]) == (178.2, 179.0)


def test_trade_proposals_prompt_pins_contract():
    """Regel 15: die Schluessel, die revalidate_one() liest, die Skala des
    Technik-Signals und der Bezugsrahmen stehen im aktiven Prompt."""
    from src.revalidation import SYSTEM_PROMPT
    for key in ("verdict", "probability_pct", "entry_window_low", "entry_window_high", "reason"):
        assert f'"{key}"' in SYSTEM_PROMPT, key
    for needle in ("0-4", "TECHNICAL SIGNAL", "LEVELS AT CURRENT PRICE", "POLICY CONTEXT",
                   "laufenden Sitzung", "Morgenrecherche"):
        assert needle in SYSTEM_PROMPT, needle
    assert "48 Stunden" not in SYSTEM_PROMPT


# ---------- C.50 / F77: echter Zeitanker statt festem 10:10 ET ----------

def test_user_message_anchors_the_real_clock_time_in_et():
    """Der Cron feuert 35-40 min zu spaet (F.1), das Notebook laeuft wann es will --
    'about 40 minutes after the open, 10:10 ET' war eine Behauptung, keine Messung."""
    from src.revalidation import _build_user_message
    msg = _build_user_message(
        _row(FULL_PRED), FULL_SNAP, [], relative_strength=None, policy_context={},
        date="2026-09-16", now_utc="2026-09-16T14:47:00")
    assert msg.startswith("Today is 2026-09-16, 10:47 ET (77 minutes after the 09:30 open). "
                          "Run type: trade_proposals"), msg.splitlines()[0]


def test_user_message_says_so_when_the_run_is_before_the_open():
    from src.revalidation import _build_user_message
    msg = _build_user_message(
        _row(FULL_PRED), FULL_SNAP, [], relative_strength=None, policy_context={},
        date="2026-09-16", now_utc="2026-09-16T13:00:00")
    assert "09:00 ET (30 minutes BEFORE the 09:30 open)" in msg.splitlines()[0]


def test_revalidate_one_passes_the_clock_through(mocker):
    call = mocker.patch("src.utils.call_claude", return_value=_claude(OK_JSON))
    from src.revalidation import revalidate_one
    revalidate_one(prediction=PRED, snapshot={"ticker": "AAPL", "price": 179.0},
                   checks=[], relative_strength=None, policy_context={},
                   cost_tracker=CostTracker(), date="2026-09-16",
                   now_utc="2026-09-16T14:47:00")
    assert "10:47 ET" in call.call_args.kwargs["user"]
