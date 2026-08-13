import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

import config
from src.cost_tracker import CostTracker
from src.broad_scan import broad_scan_batch, BroadScanError, MAX_TOKENS
from src.utils import WEB_SEARCH_TOOL


FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mock_broad_scan_response.json"

# R23: die 19 td-Schluessel, die es gibt, aber NICHT in die Phase-2-Nutzlast
# gehoeren (Grundlage des Ausschluss-Tests). Bewusst NICHT die 29
# Zusatzindikatoren (adx_14, macd_line, obv, ...) -- die stehen seit Plan 1
# nie in td, sondern in extra_indicators.
EXCLUDED_TD_FIELDS = (
    "rsi_trend", "macd_signal", "bb_position", "above_sma20", "above_sma50",
    "above_sma200", "volume_ratio", "intraday_range_pct", "price_change_1m",
    "price_change_3m", "pe_ratio", "forward_pe", "market_cap_b", "debt_equity",
    "analyst_target_upside", "analyst_consensus", "earnings_in_days",
    "earnings_beat_pct", "data_quality",
)


def _fake_sonnet_result(text: str, web_search_calls: int = 4) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.input_tokens = 8000
    r.output_tokens = 3000
    r.cache_read_tokens = 0
    r.cache_creation_tokens = 0
    r.model = config.CLAUDE_MODEL_SONNET
    r.web_search_calls = web_search_calls
    return r


def _td(ticker: str, **overrides) -> dict:
    """Voller td-Schnappschuss wie ihn data_collector liefert -- alle 26
    Felder, damit der Ausschluss-Test etwas zu pruefen hat."""
    base = {
        "ticker": ticker, "price": 178.50,
        "price_change_1d": 1.2, "price_change_5d": 3.4,
        "price_change_1m": 5.6, "price_change_3m": 12.3,
        "rsi_14": 58.4, "rsi_trend": "rising",
        "macd_signal": "bullish_cross", "atr_pct": 1.8,
        "bb_position": 0.62, "above_sma20": 2.1, "above_sma50": 5.4,
        "above_sma200": 12.8, "volume_ratio": 1.15,
        "intraday_range_pct": 1.5,
        "pe_ratio": 28.4, "forward_pe": 26.2, "market_cap_b": 2800.0,
        "debt_equity": 1.45, "sector": "Technology",
        "analyst_target_upside": 8.5, "analyst_consensus": "Buy",
        "earnings_in_days": 14, "earnings_beat_pct": 4.2,
        "data_quality": "high",
    }
    base.update(overrides)
    return base


def _sidecar(**per_ticker) -> dict:
    base = {
        "AAPL": {"premarket_change_pct": 0.8, "tech_direction": "long"},
        "MSFT": {"premarket_change_pct": -0.3, "tech_direction": "none"},
    }
    base.update(per_ticker)
    return base


def _trend_context() -> dict:
    return {
        "trends": [{"name": "ai-capex-acceleration", "strength": 8}],
        "trend_summary": "Risk-on, AI leading.",
    }


def _market_context() -> dict:
    return {"vix_level": 15.4, "market_regime": "risk-on"}


def test_broad_scan_returns_one_result_per_ticker():
    """Genau ein Ergebnis je Input-Ticker, in Eingabereihenfolge -- auch wenn
    die Modellantwort eine andere Reihenfolge liefert."""
    payload = FIXTURE_PATH.read_text()
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("AAPL"), _td("MSFT")]

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=batch,
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 2
    assert [r["ticker"] for r in out] == ["AAPL", "MSFT"]
    assert out[0]["news_strength"] == 2
    assert out[0]["news_note"]
    assert out[1]["news_strength"] == 1
    assert out[1]["news_note"]


def test_broad_scan_zeroes_strength_without_note():
    """Staerke >= 1 ohne news_note -> auf 0 gezogen. Code-Regel, nicht
    Prompt-Wunsch: muss auch greifen, wenn das Modell den news_note-Key ganz
    weglaesst (Spec 4.6)."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 2, "news_note": ""},
        {"ticker": "MSFT", "news_strength": 1},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    by_ticker = {r["ticker"]: r for r in out}
    assert by_ticker["AAPL"]["news_strength"] == 0
    assert by_ticker["MSFT"]["news_strength"] == 0


def test_broad_scan_missing_ticker_defaults_to_zero():
    """Ticker fehlt in der Antwort -> news_strength 0, kein Abbruch (anders als
    quick_filter, wo das hart fehlschlaegt)."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 2, "news_note": "Earnings beat."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 2
    by_ticker = {r["ticker"]: r for r in out}
    assert by_ticker["MSFT"]["news_strength"] == 0
    assert by_ticker["MSFT"]["news_note"] == ""


def test_broad_scan_bad_json():
    """R26: unparsebare Antwort ist NICHT fatal -- broad_scan_batch degradiert
    auf news_strength=0 fuer den ganzen Batch statt zu werfen. Ein Ergebnis je
    Ticker bleibt garantiert, der Lauf laeuft weiter (Spec Section 10)."""
    fake = _fake_sonnet_result("this is not JSON at all, just prose.")
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 2
    assert [r["ticker"] for r in out] == ["AAPL", "MSFT"]
    assert all(r["news_strength"] == 0 for r in out)
    assert all(r["news_note"] == "" for r in out)


def test_broad_scan_missing_news_strength_key_defaults_to_zero():
    """Ein Eintrag ohne news_strength-Key (nicht nur ohne news_note) darf
    nicht crashen -- .get() liefert None, das ist kein int/float und wird
    auf 0 normalisiert."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_note": "some stray note without a strength"},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert out[0]["news_strength"] == 0


def test_broad_scan_news_strength_above_range_zeroed(caplog):
    """news_strength ausserhalb der dokumentierten Domaene (0-3, Prompt-Zeile
    20) wird auf 0 gezogen statt an die Obergrenze geklemmt -- konsistent mit
    jeder anderen Validierung in _apply_note_rule, die auf einen
    unvertrauenswuerdigen Wert mit 0 statt mit einer Vermutung reagiert. Muss
    zusaetzlich eine WARNING loggen, wie die benachbarte Note-Regel."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 7, "news_note": "Huge rally."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        with caplog.at_level("WARNING", logger="shares_future.broad_scan"):
            out = broad_scan_batch(
                ticker_datas=[_td("AAPL")],
                sidecar=_sidecar(),
                trend_context=_trend_context(),
                market_context=_market_context(),
                cost_tracker=tracker,
            )

    assert out[0]["news_strength"] == 0
    assert any("7" in r.message and "Domaene" in r.message for r in caplog.records)


def test_broad_scan_news_strength_below_range_zeroed(caplog):
    """Symmetrisch zum Obergrenzen-Test: ein negativer Wert ist genauso
    ausserhalb der Domaene 0-3 und wird auf 0 gezogen, nicht an die
    Untergrenze geklemmt."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": -2, "news_note": "Odd value."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        with caplog.at_level("WARNING", logger="shares_future.broad_scan"):
            out = broad_scan_batch(
                ticker_datas=[_td("AAPL")],
                sidecar=_sidecar(),
                trend_context=_trend_context(),
                market_context=_market_context(),
                cost_tracker=tracker,
            )

    assert out[0]["news_strength"] == 0
    assert any("-2" in r.message and "Domaene" in r.message for r in caplog.records)


def test_broad_scan_news_strength_non_integer_zeroed(caplog):
    """news_strength=2.5 liegt zwar rechnerisch im Bereich 0-3, verletzt aber
    die Ganzzahl-Vorgabe des Prompts ('integer 0-3') -- wird ebenfalls auf 0
    gezogen statt stillschweigend gerundet, denn Runden waere ein Raten der
    Modell-Absicht."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 2.5, "news_note": "Fractional."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        with caplog.at_level("WARNING", logger="shares_future.broad_scan"):
            out = broad_scan_batch(
                ticker_datas=[_td("AAPL")],
                sidecar=_sidecar(),
                trend_context=_trend_context(),
                market_context=_market_context(),
                cost_tracker=tracker,
            )

    assert out[0]["news_strength"] == 0
    assert any("2.5" in r.message and "Domaene" in r.message for r in caplog.records)


def test_broad_scan_news_strength_bool_treated_as_non_numeric():
    """bool ist in Python eine int-Unterklasse (isinstance(True, int) ==
    True) -- ohne expliziten Ausschluss wuerde ein boolescher Wert
    stillschweigend als 0/1 durchrutschen. _apply_note_rule schliesst bool
    bewusst aus und behandelt es wie jeden anderen nicht-numerischen Wert
    (auf 0 gezogen, keine Domaenen-Warnung -- Typfehler, nicht Wertfehler)."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": True, "news_note": "Odd type."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert out[0]["news_strength"] == 0


def test_broad_scan_news_strength_in_range_values_untouched():
    """Gegenprobe zu den drei Domaenen-Tests: gueltige Ganzzahlen 0-3 laufen
    unveraendert durch _apply_note_rule -- die neue Grenzpruefung darf am
    dokumentierten Wertebereich selbst nichts aendern."""
    payload = json.dumps({"results": [
        {"ticker": "AAPL", "news_strength": 0, "news_note": ""},
        {"ticker": "MSFT", "news_strength": 1, "news_note": "Minor update."},
        {"ticker": "NVDA", "news_strength": 2, "news_note": "Notable move."},
        {"ticker": "AMZN", "news_strength": 3, "news_note": "Major catalyst."},
    ]})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)
    batch = [_td("AAPL"), _td("MSFT"), _td("NVDA"), _td("AMZN")]

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=batch,
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    by_ticker = {r["ticker"]: r for r in out}
    assert by_ticker["AAPL"]["news_strength"] == 0
    assert by_ticker["MSFT"]["news_strength"] == 1
    assert by_ticker["NVDA"]["news_strength"] == 2
    assert by_ticker["AMZN"]["news_strength"] == 3


def test_broad_scan_valid_json_missing_results_key_degrades_to_zero():
    """R26: die Antwort ist gueltiges JSON, aber ohne 'results'-Liste --
    strukturell kaputt, nicht syntaktisch. Degradiert genauso wie
    unparsebares JSON, statt zu werfen."""
    payload = json.dumps({"unexpected": "shape"})
    fake = _fake_sonnet_result(payload)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        out = broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert len(out) == 2
    assert all(r["news_strength"] == 0 for r in out)


def test_broad_scan_payload_contains_premarket_change_pct():
    """R22/R23: der Sidecar-Wert landet in der Nutzlast, obwohl er nicht in
    td steht."""
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)
    sidecar = {"AAPL": {"premarket_change_pct": 2.7, "tech_direction": "long"},
               "MSFT": {"premarket_change_pct": -1.1, "tech_direction": "none"}}

    with patch("src.broad_scan.call_claude", return_value=fake) as mock_call:
        broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=sidecar,
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    user_msg = mock_call.call_args.kwargs["user"]
    assert "premarket_change_pct" in user_msg
    assert "2.7" in user_msg
    assert "-1.1" in user_msg


def test_broad_scan_payload_excludes_unrelated_td_fields():
    """R23: die 19 td-Felder ausserhalb der expliziten Acht-Felder-Liste
    erreichen den Prompt NICHT -- der Payload wird explizit zusammengesetzt,
    nicht per json.dumps(td)."""
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake) as mock_call:
        broad_scan_batch(
            ticker_datas=[_td("AAPL")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    user_msg = mock_call.call_args.kwargs["user"]
    for field in EXCLUDED_TD_FIELDS:
        assert f'"{field}"' not in user_msg, f"{field} leaked into the Phase-2 payload"


def test_broad_scan_uses_configured_model_and_web_search():
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake) as mock_call:
        broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    kwargs = mock_call.call_args.kwargs
    assert kwargs["model"] == config.CLAUDE_MODEL_SONNET
    assert kwargs["tools"] == [WEB_SEARCH_TOOL]


def test_broad_scan_bills_cost_tracker():
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        broad_scan_batch(
            ticker_datas=[_td("AAPL"), _td("MSFT")],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )

    assert tracker.input_tokens == 8000
    assert tracker.output_tokens == 3000
    assert tracker.web_search_calls == 4
    assert tracker.total_eur > 0


def test_broad_scan_warns_when_output_near_max_tokens(caplog):
    """R27-Fix: eine Antwort nahe MAX_TOKENS koennte abgeschnitten sein. Ohne
    Warnung ist ein wegen Kappung auf news_strength=0 degradierter Batch im
    Log nicht von einem echten ruhigen Nachrichtentag zu unterscheiden --
    genau das Problem, das das Review-Finding benannt hat."""
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    fake.output_tokens = int(MAX_TOKENS * 0.95)
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        with caplog.at_level("WARNING", logger="shares_future.broad_scan"):
            broad_scan_batch(
                ticker_datas=[_td("AAPL"), _td("MSFT")],
                sidecar=_sidecar(),
                trend_context=_trend_context(),
                market_context=_market_context(),
                cost_tracker=tracker,
            )

    assert any("MAX_TOKENS" in r.message and "abgeschnitten" in r.message
               for r in caplog.records)


def test_broad_scan_no_truncation_warning_for_normal_output(caplog):
    """Gegenprobe: eine unauffaellige Antwort (weit unter MAX_TOKENS) loest
    keine Kappungs-Warnung aus -- sonst waere das Log-Signal wertlos."""
    fake = _fake_sonnet_result(FIXTURE_PATH.read_text())
    tracker = CostTracker(hard_cap_eur=10.0)

    with patch("src.broad_scan.call_claude", return_value=fake):
        with caplog.at_level("WARNING", logger="shares_future.broad_scan"):
            broad_scan_batch(
                ticker_datas=[_td("AAPL"), _td("MSFT")],
                sidecar=_sidecar(),
                trend_context=_trend_context(),
                market_context=_market_context(),
                cost_tracker=tracker,
            )

    assert not any("abgeschnitten" in r.message for r in caplog.records)


def test_broad_scan_empty_batch_returns_empty_list():
    tracker = CostTracker(hard_cap_eur=10.0)
    with patch("src.broad_scan.call_claude") as mock_call:
        out = broad_scan_batch(
            ticker_datas=[],
            sidecar=_sidecar(),
            trend_context=_trend_context(),
            market_context=_market_context(),
            cost_tracker=tracker,
        )
    assert out == []
    assert tracker.input_tokens == 0
    mock_call.assert_not_called()
