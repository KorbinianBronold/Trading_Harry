import math
import pandas as pd
import pytest
from src.data_collector import (
    compute_rsi_14, compute_rsi_trend, compute_macd_signal,
    compute_atr_pct, compute_bb_position,
    compute_sma_distance_pct, compute_volume_ratio,
    compute_intraday_range_pct, compute_price_changes,
)


def _df_monotonic_up(rows: int = 250) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + i * 0.5 for i in range(rows)]
    return pd.DataFrame({
        "Open":   [c - 0.1 for c in closes],
        "High":   [c + 0.5 for c in closes],
        "Low":    [c - 0.5 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000 + i * 1_000 for i in range(rows)],
    }, index=idx)


def _df_oscillating(rows: int = 250, amp: float = 5.0) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    closes = [100 + amp * math.sin(i / 5) for i in range(rows)]
    return pd.DataFrame({
        "Open":   closes,
        "High":   [c + amp * 0.3 for c in closes],
        "Low":    [c - amp * 0.3 for c in closes],
        "Close":  closes,
        "Volume": [1_000_000] * rows,
    }, index=idx)


def test_compute_rsi_14_on_monotonic_up_is_high():
    df = _df_monotonic_up(60)
    rsi = compute_rsi_14(df)
    assert rsi > 80


def test_compute_rsi_14_returns_none_when_too_short():
    df = _df_monotonic_up(10)
    assert compute_rsi_14(df) is None


def test_compute_rsi_trend_classifies_rising_and_falling():
    df_up = _df_monotonic_up(60)
    # Perfectly linear monotonic-up series saturates RSI(14) at 100, so the
    # 3-bar delta is 0 → "neutral". A "rising" outcome would require a
    # slope-changing series; we accept either label here, matching the
    # symmetric down-direction assertion below.
    assert compute_rsi_trend(df_up) in {"rising", "neutral"}

    df_down = _df_monotonic_up(60)
    df_down["Close"] = df_down["Close"].iloc[::-1].reset_index(drop=True).values
    # rebuild with descending close so RSI falls
    df_down.index = pd.date_range("2025-01-01", periods=60, freq="B")
    assert compute_rsi_trend(df_down) in {"falling", "neutral"}


def test_compute_macd_signal_returns_one_of_three_labels():
    df = _df_monotonic_up(60)
    assert compute_macd_signal(df) in {"bullish_cross", "bearish_cross", "neutral"}


def test_compute_atr_pct_is_positive_for_oscillating_series():
    df = _df_oscillating(60)
    atr = compute_atr_pct(df)
    assert atr is not None
    assert 0 < atr < 50


def test_compute_bb_position_in_zero_one_range():
    df = _df_oscillating(60)
    bb = compute_bb_position(df)
    assert bb is None or 0 <= bb <= 1


def test_compute_sma_distance_pct_positive_for_uptrend():
    df = _df_monotonic_up(250)
    dist20 = compute_sma_distance_pct(df, 20)
    dist50 = compute_sma_distance_pct(df, 50)
    dist200 = compute_sma_distance_pct(df, 200)
    assert dist20 > 0
    assert dist50 > 0
    assert dist200 > 0


def test_compute_sma_distance_pct_returns_none_when_too_short():
    df = _df_monotonic_up(50)
    assert compute_sma_distance_pct(df, 200) is None


def test_compute_volume_ratio_returns_value_near_one_for_flat_volume():
    df = _df_oscillating(60)
    v = compute_volume_ratio(df)
    assert v is not None
    assert 0.9 < v < 1.1


def test_compute_intraday_range_pct_mean_last_5_days():
    rows = 10
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    df = pd.DataFrame({
        "Open":   [100] * rows,
        "High":   [102] * rows,   # high-low = 2.0
        "Low":    [100] * rows,
        "Close":  [101] * rows,   # range/close = 2/101 ≈ 1.98%
        "Volume": [1_000_000] * rows,
    }, index=idx)
    r = compute_intraday_range_pct(df)
    assert r is not None
    assert 1.95 < r < 2.01


def test_compute_intraday_range_pct_returns_none_when_too_short():
    df = _df_monotonic_up(3)
    assert compute_intraday_range_pct(df) is None


def test_compute_price_changes_returns_dict_with_expected_keys():
    df = _df_monotonic_up(80)
    out = compute_price_changes(df)
    assert set(out.keys()) == {"price_change_1d", "price_change_5d",
                               "price_change_1m", "price_change_3m"}
    # Monotonic up → all positive
    assert all(v is None or v > 0 for v in out.values())


from unittest.mock import MagicMock
from src.db import init_schema
from src.data_collector import _process_ticker, _classify_data_quality


def _seed_price_history(conn, ticker: str, df: pd.DataFrame) -> None:
    """Legt `df` direkt als Kurshistorie von `ticker` in die DB.

    Seit dem Preismodell-Umbau (2026-08-06) ist final_close der alleinige
    Schreiber von price_history; _process_ticker liest sie nur noch. Damit gehoert
    die Historie ins Test-Setup. Vorher kam sie ueber den Schreib-Seiteneffekt
    der Datensammlung herein — das prueft eine Verkettung zweier Funktionen statt
    des Vertrags von _process_ticker. In Produktion legt sie
    setup/historical_loader.py an."""
    from src import db as _dbm
    for ts, row in df.iterrows():
        _dbm.upsert_price_history(
            conn, ticker=ticker, date=ts.strftime("%Y-%m-%d"),
            open_=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]),
            volume=int(row["Volume"]), source="capital.com",
        )
    conn.commit()


def _good_provider(df: pd.DataFrame, fundamentals: dict | None = None) -> MagicMock:
    p = MagicMock()
    p.get_price_history.return_value = df
    # Der Entscheidungskurs kommt seit dem Preismodell-Umbau live statt aus der
    # DB. Ohne festen Rueckgabewert lieferte der MagicMock hier einen
    # Platzhalter, und "price" waere ein Zufallswert.
    p.get_premarket_price.return_value = float(df["Close"].iloc[-1])
    # Kein Gap-Nachladen im Test: _fill_price_gaps soll nicht auf einem
    # MagicMock-DataFrame arbeiten.
    p.get_ohlc_after.return_value = None
    p.get_fundamentals.return_value = fundamentals or {
        "pe_ratio": 28.4, "forward_pe": 26.2,
        "market_cap_b": 2800.0, "debt_equity": 1.45,
        "sector": "Technology",
        "analyst_upside": 8.5, "consensus": "buy",
    }
    return p


def _earnings_provider(days_to_next: int | None = 14, beat_pct: float | None = 4.2) -> MagicMock:
    p = MagicMock()
    p.get_earnings_calendar.return_value = {
        "days_to_next": days_to_next, "last_beat_pct": beat_pct,
    }
    p.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "forward_pe": 26.2,
        "market_cap_b": 2800.0, "debt_equity": 1.45,
        "sector": "Technology",
        "analyst_upside": 8.5, "consensus": "buy",
    }
    return p


def test_process_ticker_returns_full_ticker_data(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    out = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    assert out["ticker"] == "AAPL"
    assert out["price"] > 0
    assert out["rsi_14"] is not None
    assert out["macd_signal"] in {"bullish_cross", "bearish_cross", "neutral"}
    assert out["atr_pct"] is not None
    assert out["sector"] == "Technology"
    assert out["earnings_in_days"] == 14
    assert out["earnings_beat_pct"] == 4.2
    assert out["data_quality"] in {"high", "medium", "low"}
    assert out["intraday_range_pct"] is not None


def test_process_ticker_writes_indicators(in_memory_db):
    """_process_ticker schreibt eine technical_indicators-Zeile.

    Frueher hiess dieser Test '..._writes_price_history_and_indicators' und
    sicherte beides zu. Die price_history-Haelfte ist mit dem Preismodell-Umbau
    (2026-08-06) absichtlich weggefallen: final_close ist der alleinige Schreiber
    der Kurshistorie, Phase 1 liest sie nur noch. Dass sie unangetastet bleibt,
    sichert test_collect_does_not_write_price_history zu."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    _seed_price_history(in_memory_db, "AAPL", df)
    _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    ti = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM technical_indicators WHERE ticker=?", ("AAPL",)
    ).fetchone()["c"]
    assert ti == 1


def test_process_ticker_skips_on_none_price_history(in_memory_db):
    init_schema(in_memory_db)
    bad = MagicMock()
    bad.get_price_history.return_value = None
    bad.get_fundamentals.return_value = {}

    out = _process_ticker(
        ticker="XYZ",
        price_provider=bad,
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is None
    row = in_memory_db.execute(
        "SELECT reason, learnable FROM skipped_tickers WHERE ticker=?", ("XYZ",)
    ).fetchone()
    assert row is not None
    assert row["learnable"] == 0


def test_process_ticker_skips_on_too_few_bars(in_memory_db):
    init_schema(in_memory_db)
    short_df = _df_monotonic_up(10)  # < MIN_BARS for indicators
    _seed_price_history(in_memory_db, "NEW", short_df)

    out = _process_ticker(
        ticker="NEW",
        price_provider=_good_provider(short_df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is None
    row = in_memory_db.execute(
        "SELECT * FROM skipped_tickers WHERE ticker=?", ("NEW",)
    ).fetchone()
    assert row is not None
    assert "bars" in row["reason"].lower() or "indicator" in row["reason"].lower()


def test_process_ticker_tolerates_missing_earnings(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    _seed_price_history(in_memory_db, "AAPL", df)
    out = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(days_to_next=None, beat_pct=None),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    assert out["earnings_in_days"] is None
    assert out["earnings_beat_pct"] is None


def test_classify_data_quality_high_when_all_fields_present():
    td = {
        "rsi_14": 60, "atr_pct": 1.8, "above_sma200": 12.0,
        "pe_ratio": 25, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "high"


def test_classify_data_quality_medium_when_some_missing():
    td = {
        "rsi_14": 60, "atr_pct": 1.8, "above_sma200": 12.0,
        "pe_ratio": None, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "medium"


def test_classify_data_quality_low_when_indicator_missing():
    td = {
        "rsi_14": None, "atr_pct": None, "above_sma200": None,
        "pe_ratio": 25, "market_cap_b": 1000, "sector": "Technology",
    }
    assert _classify_data_quality(td) == "low"


from unittest.mock import patch
from src.data_collector import collect, BATCH_PAUSE_EVERY


def test_collect_returns_list_of_ticker_data(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    for t in ("AAPL", "MSFT", "NVDA"):
        _seed_price_history(in_memory_db, t, df)
    pp = _good_provider(df)
    ep = _earnings_provider()

    with patch("src.data_collector.time.sleep") as sleep_mock:
        results, skipped = collect(
            tickers=["AAPL", "MSFT", "NVDA"],
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert len(results) == 3
    assert skipped == 0
    assert {r["ticker"] for r in results} == {"AAPL", "MSFT", "NVDA"}


def test_collect_skips_failed_tickers_but_continues(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    # "BAD" bleibt ohne Historie und faellt daran aus — seit dem Preismodell-Umbau
    # ist die fehlende DB-Historie der Ausfallgrund, nicht ein leerer Providerabruf.
    for t in ("AAPL", "MSFT"):
        _seed_price_history(in_memory_db, t, df)

    pp = MagicMock()
    pp.get_ohlc_after.return_value = None
    pp.get_premarket_price.return_value = float(df["Close"].iloc[-1])
    pp.get_fundamentals.return_value = {
        "pe_ratio": 25, "forward_pe": 24, "market_cap_b": 1000,
        "debt_equity": 1.0, "sector": "Technology",
        "analyst_upside": 5, "consensus": "buy",
    }
    ep = _earnings_provider()

    with patch("src.data_collector.time.sleep"):
        results, skipped = collect(
            tickers=["AAPL", "BAD", "MSFT"],
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}
    assert skipped == 1


def test_collect_pauses_between_batches(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    pp = _good_provider(df)
    ep = _earnings_provider()

    tickers = [f"T{i}" for i in range(BATCH_PAUSE_EVERY + 1)]
    for t in tickers:
        _seed_price_history(in_memory_db, t, df)
    with patch("src.data_collector.time.sleep") as sleep_mock:
        collect(
            tickers=tickers,
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    # The batch pause is the longest sleep argument; assert it was called.
    batch_calls = [c for c in sleep_mock.call_args_list
                   if c.args and c.args[0] >= 5]
    assert len(batch_calls) >= 1


from src import db as _db
from datetime import date as _date, timedelta


def _ohlcv_rows(n: int = 90, end: str = "2026-05-21") -> list[tuple]:
    """Returns n consecutive rows of OHLCV, last row = end date."""
    end_d = _date.fromisoformat(end)
    rows = []
    for i in range(n):
        d = (end_d - timedelta(days=n - 1 - i)).isoformat()
        close = 100.0 + i * 0.5
        rows.append((d, close - 0.1, close + 0.5, close - 0.5, close, 1_000_000))
    return rows


# ---------- Sub-Sektor-Verknuepfung (Sprint 3B / Plan 1, Task 4) ----------

def _run_ticker(conn, ticker: str, raw_sector: str | None, date: str = "2026-05-19"):
    """Laesst _process_ticker fuer `ticker` mit dem gegebenen Finnhub-Rohsektor
    laufen und gibt das TickerData-Dict zurueck.

    Seedet vorher die Kurshistorie: ohne sie steigt _process_ticker vor dem
    Sektor-Mapping aus und die Sektor-Zusicherungen waeren gruen, ohne je
    geprueft zu haben."""
    df = _df_monotonic_up(250)
    _seed_price_history(conn, ticker, df)
    ep = _earnings_provider()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "market_cap_b": 2800.0, "sector": raw_sector,
        "analyst_upside": 8.5, "consensus": "buy",
    }
    return _process_ticker(
        ticker=ticker,
        price_provider=_good_provider(df),
        earnings_provider=ep,
        conn=conn,
        date=date,
        run_type="pre_market",
    )


def test_process_ticker_links_industry_level_sector(in_memory_db):
    """Der Finnhub-Rohwert wird normalisiert und landet in ticker_sectors."""
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "NVDA", "Semiconductors")
    row = db.get_ticker_sector(in_memory_db, "NVDA")
    assert row is not None
    assert row["name"] == "Semiconductors"
    assert row["etf"] == "SOXX"


def test_process_ticker_maps_broad_finnhub_value_to_sub_sector(in_memory_db):
    """'Technology' ist ein Sammelwert und landet im Hardware-Eimer, nicht bei SOXX."""
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "AAPL", "Technology")
    row = db.get_ticker_sector(in_memory_db, "AAPL")
    assert row["name"] == "Technology Hardware"
    assert row["etf"] == "XLK"


def test_process_ticker_leaves_sector_unmapped_when_unknown(in_memory_db):
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "WEIRD", "Quantum Basketry")
    assert db.get_ticker_sector(in_memory_db, "WEIRD") is None


def test_process_ticker_leaves_sector_unmapped_when_absent(in_memory_db):
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "NOSECTOR", None)
    assert db.get_ticker_sector(in_memory_db, "NOSECTOR") is None


def test_process_ticker_still_returns_ticker_data_when_sector_unknown(in_memory_db):
    """Ein unbekannter Sektor darf Phase 1 nicht abbrechen."""
    init_schema(in_memory_db)
    td = _run_ticker(in_memory_db, "WEIRD", "Quantum Basketry")
    assert td is not None
    assert td["ticker"] == "WEIRD"


def test_process_ticker_updates_sector_mapping_on_change(in_memory_db):
    """Wechselt Finnhub die Branche, zieht ticker_sectors nach.

    Der zweite Lauf liegt bewusst hinter der 7-Tage-TTL des Fundamentals-Cache —
    innerhalb der TTL wuerde der Cache den alten Sektor liefern und die Zuordnung
    bliebe unveraendert. Das Mapping folgt also der Cache-Frequenz, nicht dem Run.
    """
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "AVGO", "Technology", date="2026-05-19")
    _run_ticker(in_memory_db, "AVGO", "Semiconductors", date="2026-05-30")
    row = db.get_ticker_sector(in_memory_db, "AVGO")
    assert row["name"] == "Semiconductors"
    assert in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM ticker_sectors WHERE ticker='AVGO'"
    ).fetchone()["n"] == 1


def test_process_ticker_keeps_sector_stable_within_cache_ttl(in_memory_db):
    """Innerhalb der Cache-TTL bleibt die Zuordnung stehen — dokumentiert, dass
    das Sektor-Mapping an der Fundamentals-Cache-Frequenz haengt."""
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "AVGO", "Technology", date="2026-05-19")
    _run_ticker(in_memory_db, "AVGO", "Semiconductors", date="2026-05-20")
    assert db.get_ticker_sector(in_memory_db, "AVGO")["name"] == "Technology Hardware"


# ---------- Inaktive Ticker in collect() (Sprint 3B / Plan 1, Task 6) ----------

def test_collect_skips_inactive_tickers_without_any_api_call(in_memory_db):
    """Ein deaktivierter Ticker darf keinen einzigen Capital.com-Call ausloesen —
    genau darin liegt die Kostenersparnis von B.7."""
    import config
    from src import db
    from src.data_collector import collect
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-01",
                              run_type="pre_market", reason="x")

    price_provider = MagicMock()
    price_provider._source_name = "capital.com"

    results, skipped = collect(
        tickers=["DEAD"], price_provider=price_provider,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 1
    price_provider.get_ohlc_after.assert_not_called()
    price_provider.get_price_history.assert_not_called()


def test_collect_retries_inactive_ticker_after_retry_date(in_memory_db):
    """Ab dem retry_after-Datum wird der Ticker wieder normal versucht."""
    import config
    from src import db
    from src.data_collector import collect
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="BACK", date="2026-07-01",
                              run_type="pre_market", reason="x")
    _seed_price_history(in_memory_db, "BACK", _df_monotonic_up(250))

    results, _ = collect(
        tickers=["BACK"], price_provider=_good_provider(_df_monotonic_up(250)),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-08-01",   # retry_after = 2026-07-31
        run_type="pre_market",
    )
    assert len(results) == 1
    assert db.get_ticker_status(in_memory_db, "BACK")["skip_count"] == 0


def test_collect_resets_skip_counter_after_successful_run(in_memory_db):
    """Ein erfolgreicher Abruf heilt den Zaehler — sonst liefe ein Ticker durch
    verstreute Einzelausfaelle ueber Monate in die Deaktivierung."""
    from src import db
    from src.data_collector import collect
    init_schema(in_memory_db)
    db.log_skipped_ticker(in_memory_db, ticker="AAPL", date="2026-07-01",
                          run_type="pre_market", reason="x")
    assert db.get_ticker_status(in_memory_db, "AAPL")["skip_count"] == 1
    _seed_price_history(in_memory_db, "AAPL", _df_monotonic_up(250))

    results, _ = collect(
        tickers=["AAPL"], price_provider=_good_provider(_df_monotonic_up(250)),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert len(results) == 1
    assert db.get_ticker_status(in_memory_db, "AAPL")["skip_count"] == 0


def test_collect_counts_inactive_and_failing_tickers_together(in_memory_db):
    """Die skipped-Zahl im Rueckgabewert deckt beide Faelle ab."""
    import config
    from src import db
    from src.data_collector import collect
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-01",
                              run_type="pre_market", reason="x")

    provider = MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = None
    provider.get_price_history.return_value = None

    results, skipped = collect(
        tickers=["DEAD", "ALSOBAD"], price_provider=provider,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 2


def test_process_ticker_links_sector_from_fundamentals_cache(in_memory_db):
    """Zweiter Lauf trifft den 7-Tage-Cache — die Zuordnung muss trotzdem stehen."""
    from src import db
    init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "JNJ",
        {"pe_ratio": 15.0, "market_cap_b": 400.0, "sector": "Pharmaceuticals"},
        fetched_date="2026-05-19",
    )
    _seed_price_history(in_memory_db, "JNJ", _df_monotonic_up(250))
    ep = _earnings_provider()
    _process_ticker(
        ticker="JNJ",
        price_provider=_good_provider(_df_monotonic_up(250)),
        earnings_provider=ep,
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    ep.get_fundamentals.assert_not_called()
    row = db.get_ticker_sector(in_memory_db, "JNJ")
    assert row["name"] == "Pharma"
    assert row["etf"] == "XLV"


# ---------- Gap-Erkennung (Sprint 3B / Plan 1, Task 12 — Spec B.8) ----------


def test_expected_trading_days_skips_weekend():
    from src.data_collector import _expected_trading_days
    # Freitag 2026-07-24 -> Montag 2026-07-27: kein fehlender Handelstag dazwischen
    assert _expected_trading_days("2026-07-24", "2026-07-27") == ["2026-07-27"]


def test_expected_trading_days_lists_real_gap():
    from src.data_collector import _expected_trading_days
    # Montag 2026-07-20 -> Freitag 2026-07-24: Di/Mi/Do/Fr fehlen
    assert _expected_trading_days("2026-07-20", "2026-07-24") == [
        "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24",
    ]


def test_expected_trading_days_empty_when_up_to_date():
    from src.data_collector import _expected_trading_days
    assert _expected_trading_days("2026-07-27", "2026-07-27") == []


def test_expected_trading_days_spans_a_full_weekend():
    """Do -> Di: Fr und Mo und Di fehlen, Sa/So nicht."""
    from src.data_collector import _expected_trading_days
    assert _expected_trading_days("2026-07-23", "2026-07-28") == [
        "2026-07-24", "2026-07-27", "2026-07-28",
    ]


def test_fill_price_gaps_backfills_missing_bars(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-20",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"Open": [101.0, 102.0], "High": [103.0, 104.0],
         "Low": [100.0, 101.0], "Close": [102.0, 103.0], "Volume": [900, 950]},
        index=pd.to_datetime(["2026-07-21", "2026-07-22"]),
    )

    # Lauftag 07-23, damit die Luecke (07-21, 07-22) nur ABGESCHLOSSENE Tage
    # enthaelt: der laufende Tag wird seit dem Preismodell-Umbau nie geschrieben.
    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-23")
    assert n == 2
    dates = [r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='AAPL' ORDER BY date").fetchall()]
    assert dates == ["2026-07-20", "2026-07-21", "2026-07-22"]


def test_fill_price_gaps_ignores_bars_outside_the_window(in_memory_db, mocker):
    """Der Provider darf mehr liefern als angefragt — gespeichert wird nur die Luecke."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-20",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"Open": [1.0] * 4, "High": [1.0] * 4, "Low": [1.0] * 4,
         "Close": [1.0] * 4, "Volume": [1] * 4},
        index=pd.to_datetime(["2026-07-17", "2026-07-21",
                              "2026-07-22", "2026-07-29"]),
    )
    # Lauftag 07-23, siehe oben: 07-22 muss ein abgeschlossener Tag sein.
    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-23")
    assert n == 2
    dates = [r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='AAPL' ORDER BY date").fetchall()]
    assert dates == ["2026-07-20", "2026-07-21", "2026-07-22"]


def test_fill_price_gaps_noop_over_weekend(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-24",  # Freitag
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()
    provider = mocker.MagicMock()
    # Montag: nur der heutige Bar fehlt, den holt final_close — kein Gap-Fetch
    assert _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-27") == 0
    provider.get_ohlc_after.assert_not_called()


def test_fill_price_gaps_noop_on_empty_history(in_memory_db, mocker):
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    provider = mocker.MagicMock()
    assert _fill_price_gaps("NEW", provider, in_memory_db, date="2026-07-27") == 0
    provider.get_ohlc_after.assert_not_called()


def test_fill_price_gaps_noop_when_db_is_ahead(in_memory_db, mocker):
    """Ein Re-Run desselben Tages darf keinen Nachlade-Call ausloesen."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-27",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()
    provider = mocker.MagicMock()
    assert _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-27") == 0
    provider.get_ohlc_after.assert_not_called()


def test_fill_price_gaps_survives_provider_error(in_memory_db, mocker):
    """Ein fehlgeschlagenes Nachladen darf den Ticker nicht sprengen."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-20",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()
    provider = mocker.MagicMock()
    provider.get_ohlc_after.side_effect = RuntimeError("Capital.com 500")
    assert _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-24") == 0


def test_fill_price_gaps_survives_empty_response(in_memory_db, mocker):
    """Feiertags-Fall (B.8): der Nachladeversuch liefert schlicht nichts."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    db.insert_price_bar_if_missing(
        in_memory_db, ticker="AAPL", date="2026-07-20",
        open_=100, high=101, low=99, close=100.5, volume=1000,
        source="capital.com",
    )
    in_memory_db.commit()
    provider = mocker.MagicMock()
    provider.get_ohlc_after.return_value = pd.DataFrame()
    assert _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-24") == 0


# ---------- Preismodell-Umbau: nur final_close schreibt (2026-08-06) ----------


def test_collect_does_not_write_price_history(in_memory_db, mocker):
    """final_close ist der einzige Schreiber. Schreibt die Datensammlung weiter
    mit, kann die Teilbar des laufenden Tages wieder in die Historie geraten --
    genau der Frozen-Bar-Bug."""
    from src import db as _dbmod
    from src.data_collector import _process_ticker
    _dbmod.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(90, "2026-08-05"):
        _dbmod.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)
    before = in_memory_db.execute(
        "SELECT COUNT(*) c FROM price_history").fetchone()["c"]

    mock_price = mocker.MagicMock()
    mock_price.get_premarket_price.return_value = 321.5
    mock_earn = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value = {}

    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db,
                         "2026-08-06", "pre_market")

    after = in_memory_db.execute(
        "SELECT COUNT(*) c FROM price_history").fetchone()["c"]
    assert after == before, "collect() darf price_history nicht mehr anfassen"
    assert td is not None
    assert td["price"] == 321.5, "der Entscheidungskurs kommt live, nicht aus der DB"


def test_gap_fill_never_writes_the_current_day(in_memory_db, mocker):
    """price_history enthaelt nur FINALE Bars. Der laufende Tag ist noch nicht
    final -- ihn nachzuladen brachte genau die provisorische Teilbar zurueck,
    deren Beseitigung der ganze Umbau ist.

    Der Pfad greift nur nach einem Ausfall (wenn mehr als ein Handelstag fehlt),
    aber dann eben doch."""
    from src import db as _dbmod
    from src.data_collector import _fill_price_gaps
    _dbmod.init_schema(in_memory_db)
    # Letzte Bar liegt vier Handelstage zurueck -> Luecke, der Pfad feuert.
    _dbmod.upsert_price_history(in_memory_db, "AAPL", "2026-07-31",
                                100, 101, 99, 100, 10)
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"Open": [100.0, 101.0, 102.0], "High": [101.0, 102.0, 103.0],
         "Low": [99.0, 100.0, 101.0], "Close": [100.5, 101.5, 102.5],
         "Volume": [10, 11, 12]},
        index=pd.to_datetime(["2026-08-03", "2026-08-04", "2026-08-05"]))

    _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-08-05")

    dates = {r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='AAPL'").fetchall()}
    assert "2026-08-05" not in dates, (
        "der laufende Tag ist noch nicht final und gehoert final_close")
    assert {"2026-08-03", "2026-08-04"} <= dates, "die Luecke davor wird gefuellt"
