"""Live-Integrationstest fuer Phase 2 (src/broad_scan.py).

Ruft die echte Anthropic-API mit Websuche auf -- read-only: kein DB-Schreiben,
kein Mailversand, nur die Vertragsform der Antwort wird geprueft, nicht ihre
inhaltliche Qualitaet. Laeuft nur mit `--run-live` (s. tests/conftest.py).

Kosten: ein Sonnet-Call mit bis zu 6 Websuchen fuer zwei Ticker -- deutlich
teurer als die Ein-Token-Pings in test_api_connectivity.py, aber weit unter
einem vollen Pipeline-Lauf."""
import pytest

import config
from src.broad_scan import broad_scan_batch
from src.cost_tracker import CostTracker


@pytest.mark.live_api
def test_broad_scan_batch_against_real_api(report, key_source):
    """Ein echter Zwei-Ticker-Scan. Prueft nur, dass die Antwort parsebar ist
    und die Vertragsform haelt (ein Ergebnis je Ticker, gueltige
    news_strength, news_note bei Staerke >= 1) -- keine Aussage darueber, ob
    die gefundenen Nachrichten inhaltlich zutreffen."""
    if not config.ANTHROPIC_API_KEY:
        report(f"❌ broad_scan: kein ANTHROPIC_API_KEY aus {key_source}")
        pytest.fail(f"ANTHROPIC_API_KEY fehlt in {key_source}")

    ticker_datas = [
        {"ticker": "AAPL", "price": 230.0, "price_change_1d": 0.5,
         "price_change_5d": 1.2, "rsi_14": 55.0, "atr_pct": 1.8,
         "sector": "Technology"},
        {"ticker": "MSFT", "price": 430.0, "price_change_1d": -0.3,
         "price_change_5d": 0.8, "rsi_14": 48.0, "atr_pct": 1.5,
         "sector": "Technology"},
    ]
    sidecar = {
        "AAPL": {"premarket_change_pct": 0.4},
        "MSFT": {"premarket_change_pct": -0.1},
    }
    tracker = CostTracker(hard_cap_eur=1.0)

    try:
        out = broad_scan_batch(
            ticker_datas=ticker_datas,
            sidecar=sidecar,
            trend_context={"trend_summary": "Live smoke test, no real trend data."},
            market_context={"vix_level": 15.0},
            cost_tracker=tracker,
        )
    except Exception as e:
        report(f"❌ broad_scan FEHLGESCHLAGEN ({key_source}): {type(e).__name__}: {e}")
        raise

    assert len(out) == 2, f"Erwartet 2 Ergebnisse, bekam {len(out)}: {out}"
    assert {r["ticker"] for r in out} == {"AAPL", "MSFT"}
    for r in out:
        assert r["news_strength"] in (0, 1, 2, 3), r
        if r["news_strength"] >= 1:
            assert r["news_note"], f"{r['ticker']}: Staerke >= 1 ohne news_note"

    report(
        f"✅ broad_scan erreichbar ({key_source}), "
        f"cost={tracker.total_eur:.4f} EUR, web_search_calls={tracker.web_search_calls}"
    )
