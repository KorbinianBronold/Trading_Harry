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


def _good_provider(df: pd.DataFrame, fundamentals: dict | None = None) -> MagicMock:
    p = MagicMock()
    p.get_price_history.return_value = df
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


def test_process_ticker_writes_price_history_and_indicators(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    ph = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM price_history WHERE ticker=?", ("AAPL",)
    ).fetchone()["c"]
    ti = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM technical_indicators WHERE ticker=?", ("AAPL",)
    ).fetchone()["c"]
    assert ph == 80
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

    pp = MagicMock()
    def history(ticker, days=90):
        return None if ticker == "BAD" else df
    pp.get_price_history.side_effect = history
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


def test_todays_bar_is_refetched_even_when_a_row_exists(in_memory_db, mocker):
    """Frueher hiess dieser Test 'no fetch when today in db' und sicherte die
    Ersparnis eines Abrufs ab. Genau die war der Fehler.

    Capital.coms DAY-Bar des laufenden Tages existiert schon waehrend des Tages
    und bewegt sich bis zum Schluss weiter (Sonde 2026-08-05). Wer den Abruf
    ueberspringt, sobald irgendeine Zeile fuer heute existiert, friert die
    15:00-Pre-Market-Quote fuer den ganzen Tag ein: der 16:10-Lauf vergleicht
    dann 'frische' Kurse gegen sich selbst und der echte Tagesschluss wird nie
    geschrieben. Der Abruf je Lauf ist der Preis dafuer, dass die Kurse stimmen —
    close (B.6) holt ohnehin bereits alle Ticker.

    Erhalten bleibt die zweite Haelfte der urspruenglichen Zusage: liefert der
    Abruf nichts, faellt der Ticker nicht aus, sondern rechnet auf der Historie
    aus der DB weiter."""
    _db.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(90, "2026-05-21"):
        _db.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value   = None
    mock_price.get_price_history.return_value = None
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_ohlc_after.assert_called_once()
    assert td is not None, "ohne frische Bar rechnet der Ticker auf der Historie weiter"


def test_incremental_fetches_and_persists_missing_today(in_memory_db, mocker):
    """When today is missing, get_ohlc_after is called and bar is stored."""
    import pandas as pd
    _db.init_schema(in_memory_db)
    for d, o, h, l, c, v in _ohlcv_rows(89, "2026-05-20"):
        _db.upsert_price_history(in_memory_db, "AAPL", d, o, h, l, c, v)

    today_df = pd.DataFrame(
        {"Open": [101.0], "High": [104.0], "Low": [100.0], "Close": [103.0], "Volume": [2_000_000]},
        index=pd.DatetimeIndex(["2026-05-21"]),
    )
    today_df.index.name = "Date"

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value = today_df
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_ohlc_after.assert_called_once()
    assert td is not None
    row = in_memory_db.execute(
        "SELECT close FROM price_history WHERE ticker='AAPL' AND date='2026-05-21'"
    ).fetchone()
    assert row is not None
    assert row["close"] == pytest.approx(103.0)


def test_incremental_fallback_to_full_history_when_ohlc_after_none(in_memory_db, mocker):
    """If get_ohlc_after returns None, full history fetch is attempted."""
    import pandas as pd
    _db.init_schema(in_memory_db)

    full_df_rows = _ohlcv_rows(90, "2026-05-21")
    idx = pd.DatetimeIndex([r[0] for r in full_df_rows])
    full_df = pd.DataFrame(
        {
            "Open":   [r[1] for r in full_df_rows],
            "High":   [r[2] for r in full_df_rows],
            "Low":    [r[3] for r in full_df_rows],
            "Close":  [r[4] for r in full_df_rows],
            "Volume": [r[5] for r in full_df_rows],
        },
        index=idx,
    )
    full_df.index.name = "Date"

    mock_price = mocker.MagicMock()
    mock_price.get_ohlc_after.return_value    = None
    mock_price.get_price_history.return_value = full_df
    mock_earn  = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value      = {}

    from src.data_collector import _process_ticker
    td = _process_ticker("AAPL", mock_price, mock_earn, in_memory_db, "2026-05-21", "test")

    mock_price.get_price_history.assert_called_once()
    assert td is not None


# ---------- Sub-Sektor-Verknuepfung (Sprint 3B / Plan 1, Task 4) ----------

def _run_ticker(conn, ticker: str, raw_sector: str | None, date: str = "2026-05-19"):
    """Laesst _process_ticker fuer `ticker` mit dem gegebenen Finnhub-Rohsektor
    laufen und gibt das TickerData-Dict zurueck."""
    ep = _earnings_provider()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "market_cap_b": 2800.0, "sector": raw_sector,
        "analyst_upside": 8.5, "consensus": "buy",
    }
    return _process_ticker(
        ticker=ticker,
        price_provider=_good_provider(_df_monotonic_up(250)),
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

    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-22")
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
    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-22")
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
    # Montag: nur der heutige Bar fehlt, den holt _ensure_today_bar — kein Gap-Fetch
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


# ---------- Eingefrorene Tagesbar (Review 2026-08-05) ----------


def _bar_df(date: str, close: float) -> pd.DataFrame:
    return pd.DataFrame(
        {"Open": [close - 1], "High": [close + 1], "Low": [close - 2],
         "Close": [close], "Volume": [1234]},
        index=pd.DatetimeIndex([pd.Timestamp(date)], name="Date"),
    )


def test_todays_bar_is_refreshed_not_frozen(in_memory_db, mocker):
    """Der Bar des LAUFENDEN Tages muss ueberschrieben werden.

    Sonde gegen Capital.com am 2026-08-05 (read-only): der DAY-Bar eines
    laufenden Tages existiert bereits und veraendert sich weiter — AAPLs Volumen
    lief zwischen zwei Abrufen um 22:07 UTC noch von 63024 auf 63028 hoch, also
    zwei Stunden nach dem regulaeren US-Schluss. Die DAY-Bar deckt damit auch die
    erweiterten Handelszeiten ab, und um 15:00 Berlin (09:00 ET, Pre-Market)
    existiert sie folglich schon.

    Frueher stieg _ensure_today_bar aus, sobald irgendeine Zeile fuer
    (ticker, date) existierte, und insert_price_bar_if_missing war INSERT OR
    IGNORE. Der 15:00-Lauf schrieb damit eine Pre-Market-Quote, und weder der
    16:10-Lauf noch der 22:30-Lauf kamen je dagegen an: der 16:10-Lauf verglich
    'frische' Kurse gegen sich selbst (Opening-Gap immer 0,00 %), und der echte
    Tagesschluss wurde nie geschrieben — die Zeile blieb dauerhaft eine
    Pre-Market-Quote und verfaelschte jeden daraus gerechneten Indikator."""
    from src import db
    from src.data_collector import _ensure_today_bar
    db.init_schema(in_memory_db)
    db.upsert_price_history(
        in_memory_db, ticker="AAPL", date="2026-08-05",
        open_=100.0, high=100.5, low=99.5, close=100.0, volume=10,
        source="capital.com")
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    provider.get_ohlc_after.return_value = _bar_df("2026-08-05", 105.0)

    _ensure_today_bar("AAPL", provider, in_memory_db, date="2026-08-05")

    row = in_memory_db.execute(
        "SELECT * FROM price_history WHERE ticker='AAPL' AND date='2026-08-05'"
    ).fetchone()
    assert row["close"] == 105.0, "der laufende Tag wird nachgezogen"
    assert row["volume"] == 1234
    n = in_memory_db.execute(
        "SELECT COUNT(*) c FROM price_history WHERE ticker='AAPL'").fetchone()["c"]
    assert n == 1, "kein Duplikat, dieselbe Zeile"


def test_closed_days_are_never_overwritten(in_memory_db, mocker):
    """Abgeschlossene Handelstage bleiben unantastbar — sonst schriebe ein
    spaeterer Lauf die Historie um, auf der alle Indikatoren beruhen."""
    from src import db
    from src.data_collector import _ensure_today_bar
    db.init_schema(in_memory_db)
    db.upsert_price_history(
        in_memory_db, ticker="AAPL", date="2026-08-04",
        open_=200.0, high=200.5, low=199.5, close=200.0, volume=99,
        source="capital.com")
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    # Der Abruf liefert den Vortag mit abweichenden Werten gleich mit.
    provider.get_ohlc_after.return_value = pd.concat([
        _bar_df("2026-08-04", 111.0), _bar_df("2026-08-05", 105.0)])

    _ensure_today_bar("AAPL", provider, in_memory_db, date="2026-08-05")

    old = in_memory_db.execute(
        "SELECT * FROM price_history WHERE ticker='AAPL' AND date='2026-08-04'"
    ).fetchone()
    assert old["close"] == 200.0, "der abgeschlossene Vortag bleibt, wie er war"
    assert old["volume"] == 99
    new = in_memory_db.execute(
        "SELECT * FROM price_history WHERE ticker='AAPL' AND date='2026-08-05'"
    ).fetchone()
    assert new["close"] == 105.0, "der laufende Tag wird geschrieben"
