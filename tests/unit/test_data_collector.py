import numpy as np
import pandas as pd
import pytest


def _df_seeded_uptrend(seed: int, rows: int = 220) -> pd.DataFrame:
    """Realistischer Aufwaertstrend mit Tagesrauschen (fixer Seed, deterministisch).

    Im Unterschied zu _df_monotonic_up() saettigt hier weder RSI (kein reiner
    Auftage-Lauf) noch MACD -- es gibt echte Auf- und Abtage. Dient dem Test,
    der eine konkret vorhergesagte Signalrichtung ueber echte Indikator-
    Berechnung erzwingt statt nur Wertebereiche zu pruefen (Sprint 3C /
    Analyse-Pipeline-Umbau, Task 6)."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0025, 0.01, rows)
    closes = 100 * np.cumprod(1 + rets)
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    highs = closes * (1 + np.abs(rng.normal(0.003, 0.001, rows)))
    lows = closes * (1 - np.abs(rng.normal(0.003, 0.001, rows)))
    opens = closes * (1 + rng.normal(0, 0.001, rows))
    vols = 1_000_000 + rng.integers(0, 500_000, rows)
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": vols},
        index=idx,
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


from unittest.mock import MagicMock
from src.db import init_schema
from src.data_collector import _process_ticker, _classify_data_quality
from src import data_collector


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
    # Der Entscheidungskurs kommt seit Task 5 aus dem Batch-Sweep
    # (get_premarket_prices_batch), nicht mehr aus einem Einzelabruf. Ohne
    # festen Rueckgabewert lieferte der MagicMock hier einen Platzhalter, und
    # "price" waere kein reales float -- der side_effect liefert fuer jeden
    # angefragten Ticker denselben letzten Close wie frueher get_premarket_price.
    p.get_premarket_prices_batch.side_effect = (
        lambda tickers, chunk_size=20: {t: float(df["Close"].iloc[-1]) for t in tickers}
    )
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


def _seed_fundamentals_cache(
    conn, ticker: str, fetched_date: str, sector: str | None = "Technology",
    earnings_next_date: str | None = None, **overrides,
) -> None:
    """Schreibt einen fundamentals_cache-Eintrag direkt in die DB (Sprint 3C /
    Analyse-Pipeline-Umbau, Task 7: Phase 1 liest den Cache nur noch, ruft
    Finnhub nicht mehr auf -- ein Provider-Mock-Rueckgabewert haette also keine
    Wirkung mehr. Simuliert, was Phase 2b (fetch_missing_fundamentals(), ab
    Task 10 verdrahtet) irgendwann selbst hineinschreibt."""
    from src import db as _dbm
    data = {
        "pe_ratio": 28.4, "forward_pe": 26.2,
        "market_cap_b": 2800.0, "debt_equity": 1.45,
        "sector": sector, "analyst_upside": 8.5, "consensus": "buy",
        "earnings_next_date": earnings_next_date,
        **overrides,
    }
    _dbm.save_fundamentals_cache(conn, ticker, data, fetched_date=fetched_date)


def test_process_ticker_returns_full_ticker_data(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    # Sprint 3C / Analyse-Pipeline-Umbau (Task 7): Phase 1 liest Fundamentals
    # nur noch aus dem Cache -- ohne diesen Eintrag blieben sector/earnings_in_days
    # auf ihren Cache-Miss-Defaults.
    _seed_fundamentals_cache(
        in_memory_db, "AAPL", fetched_date="2026-05-19",
        sector="Technology", earnings_next_date="2026-06-02",  # +14 Tage
    )
    last_close = float(df["Close"].iloc[-1])
    out, sidecar_entry = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
        # 1 % ueber dem letzten Close, wie ihn der Sweep (Phase 1b) liefern wuerde.
        premarket_price=last_close * 1.01,
    )
    assert out is not None
    assert out["ticker"] == "AAPL"
    assert out["price"] > 0
    assert out["rsi_14"] is not None
    assert out["macd_signal"] in {"bullish_cross", "bearish_cross", "neutral"}
    assert out["atr_pct"] is not None
    assert out["sector"] == "Technology"
    assert out["earnings_in_days"] == 14
    # R15: get_earnings_calendar() verschwindet aus dem Tageslauf -- es gibt
    # earnings_beat_pct dort nicht mehr, unabhaengig vom Cache-Inhalt.
    assert out["earnings_beat_pct"] is None
    assert out["data_quality"] in {"high", "medium", "low"}
    assert out["intraday_range_pct"] is not None
    assert sidecar_entry["premarket_change_pct"] == pytest.approx(1.0)


# ---------- Fundamentals ausschliesslich aus dem Cache (Sprint 3C / Task 7) ----------

def test_process_ticker_reads_fundamentals_cache_only(in_memory_db):
    """Die eigentliche Zusicherung dieser Task: Phase 1 macht 0 Finnhub-Calls.

    Faellt, sobald _process_ticker() wieder get_fundamentals() oder
    get_earnings_calendar() auf earnings_provider aufruft -- egal ob Cache-Hit
    oder -Miss, der Provider darf in Phase 1 nie angefasst werden."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    _seed_fundamentals_cache(
        in_memory_db, "AAPL", fetched_date="2026-05-19",
        sector="Technology", earnings_next_date="2026-06-02",  # +14 Tage
    )
    ep = _earnings_provider()

    out, _sidecar = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=ep,
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )

    assert out is not None
    assert out["sector"] == "Technology"
    assert out["pe_ratio"] == 28.4
    assert out["earnings_in_days"] == 14
    ep.get_fundamentals.assert_not_called()
    ep.get_earnings_calendar.assert_not_called()


def test_process_ticker_uses_defaults_on_cache_miss(in_memory_db):
    """Kein Cache-Eintrag -> pe_ratio None, sector 'Unknown', earnings_in_days
    None -- und explizit KEIN Skip (R14: _classify_data_quality stuft 'low'
    nur nach rsi_14/atr_pct ein, ein fehlender Fundamentals-Cache verschiebt
    hoechstens 'high' auf 'medium')."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    ep = _earnings_provider()

    out, _sidecar = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=ep,
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )

    assert out is not None, "ein Cache-Miss darf keinen Skip ausloesen"
    assert out["pe_ratio"] is None
    assert out["sector"] == "Unknown"
    assert out["earnings_in_days"] is None
    assert out["earnings_beat_pct"] is None
    assert out["data_quality"] != "low"
    ep.get_fundamentals.assert_not_called()
    ep.get_earnings_calendar.assert_not_called()


def test_process_ticker_return_shape_excludes_the_29_new_indicator_columns(in_memory_db):
    """Pins the EXACT key set _process_ticker() returns.

    This dict is json.dumps'd verbatim into four Claude prompts (quick_filter.py,
    deep_analysis.py, commodities_crypto.py, and -- via main.py's `snapshots` in
    run_trade_proposals -- portfolio_check.py). Plan 1's explicit promise was "no
    pipeline behaviour changes"; a stray key here changes what the model sees and
    therefore which tickers get selected and how they're scored. The 29 new
    technical_indicators columns are computed in _process_ticker() but must be
    persisted to the DB only, never merged into this dict.

    Deliberately an exact expected-key-set equality, not a count and not a
    "these specific new names are absent" check -- either of those would miss a
    *different*, newly-added key that leaks the same way.
    """
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    out, _premarket_change_pct = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    expected_keys = {
        "ticker", "price",
        "price_change_1d", "price_change_5d", "price_change_1m", "price_change_3m",
        "rsi_14", "rsi_trend", "macd_signal", "atr_pct", "bb_position",
        "above_sma20", "above_sma50", "above_sma200",
        "volume_ratio", "intraday_range_pct",
        "pe_ratio", "forward_pe", "market_cap_b", "debt_equity", "sector",
        "analyst_target_upside", "analyst_consensus",
        # 2026-08-20, Spec E3: BEWUSSTE Erweiterung der Schluesselmenge, kein
        # Leck. Das Feld gehoert zu seinen Geschwistern -- pe_ratio,
        # analyst_consensus und die uebrigen Fundamentaldaten liegen laengst im
        # td und damit im Prompt. Es traegt das Alter der Analystenmeinung, ohne
        # das ein drei Monate alter Konsens nicht von einem taggleichen zu
        # unterscheiden ist. Unterschied zu den 29 Plan-1-Indikatoren, gegen die
        # dieser Test gebaut wurde: die waren ~250 Tokens je Ticker technischer
        # Rohwerte, die der Prompt nie angefordert hat -- das hier ist EIN
        # Datums-String neben Feldern derselben Herkunft.
        "analyst_consensus_period",
        "earnings_in_days", "earnings_beat_pct", "data_quality",
    }
    assert set(out.keys()) == expected_keys


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


def test_process_ticker_persists_the_new_indicators(in_memory_db):
    """Ein Durchlauf muss die neuen Spalten tatsaechlich fuellen -- nicht nur
    die Tabelle anlegen. Prueft alle 29 neuen Spalten, nicht nur eine Auswahl:
    das haette den ichi_chikou-Immer-None-Bug (Fix 2) sofort gefangen.

    Liest bewusst aus der DB, nicht aus dem _process_ticker()-Rueckgabewert --
    seit Fix 1 sind die 29 Spalten dort NICHT mehr enthalten (sie gehen nur
    noch in die Persistierung, nicht in den Claude-Prompt-Payload)."""
    conn = in_memory_db
    init_schema(conn)
    df = _df_monotonic_up(rows=250)
    _seed_price_history(conn, "AAPL", df)
    # Datum aus dem Fixture ableiten statt hart zu setzen: so bleibt der Test
    # unabhaengig davon, welche Kalendertage _df_monotonic_up erzeugt.
    as_of = df.index[-1].strftime("%Y-%m-%d")

    td, _premarket_change_pct = data_collector._process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=conn, date=as_of, run_type="pre_market",
    )

    assert td is not None
    row = conn.execute(
        "SELECT * FROM technical_indicators WHERE ticker=? AND date=?",
        ("AAPL", as_of),
    ).fetchone()
    new_columns = [
        "ema_50_dist_pct",
        "macd_line", "macd_signal_line", "macd_hist",
        "adx_14", "di_plus", "di_minus",
        "psar_value", "psar_dir",
        "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b", "ichi_chikou",
        "stoch_k", "stoch_d",
        "willr_14", "cci_20", "mom_12",
        "trix", "trix_signal",
        "bb_upper", "bb_lower", "bb_width",
        "atr_abs",
        "donch_upper", "donch_mid", "donch_lower",
        "obv",
    ]
    assert len(new_columns) == 29
    for col in new_columns:
        assert row[col] is not None, f"{col} is NULL"


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


# ---------- D1: Skip-Gruende gehoeren ins Log, nicht nur in die DB ----------

def test_skip_reason_is_logged_not_only_persisted(in_memory_db, caplog):
    """Am 2026-08-04 verschwanden 18 Ticker spurlos aus dem Actions-Log; die
    Begruendung stand ausschliesslich in skipped_tickers. Wer nur die Logs hat,
    sah `2 ok, 18 skipped` und keinen Grund — die Ursache war erst nach dem
    Download der CI-Datenbank sichtbar."""
    import logging
    init_schema(in_memory_db)
    short_df = _df_monotonic_up(10)
    _seed_price_history(in_memory_db, "NEW", short_df)

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        _process_ticker(
            ticker="NEW",
            price_provider=_good_provider(short_df),
            earnings_provider=_earnings_provider(),
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    # Bewusst gegen den exakten Grund, nicht gegen "bars": das Wort steht auch
    # in der Gap-Warnung, ein loser Test bestuende ohne die Aenderung.
    skip_lines = [r.message for r in caplog.records
                  if "insufficient bars" in r.message]
    assert skip_lines, f"Kein Skip-Grund geloggt. Log war: {caplog.text}"
    assert "NEW" in skip_lines[0]


def test_collect_summarises_skip_reasons(in_memory_db, caplog):
    """Bei 500 Tickern ist eine Einzelzeile je Skip unlesbar. Die Schlusszeile
    muss die Gruende buendeln, damit `18 skipped` sofort erklaert ist."""
    import logging
    init_schema(in_memory_db)
    short_df = _df_monotonic_up(10)
    for t in ("AAA", "BBB"):
        _seed_price_history(in_memory_db, t, short_df)

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        collect(
            tickers=["AAA", "BBB"],
            price_provider=_good_provider(short_df),
            earnings_provider=_earnings_provider(),
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert "insufficient bars" in caplog.text
    assert "2" in caplog.text


def test_process_ticker_tolerates_missing_earnings_next_date_on_cache_hit(in_memory_db):
    """Fundamentals sind gecacht (Cache-Hit, sector/pe_ratio also gefuellt),
    aber earnings_next_date ist NULL -- z.B. weil der Wochenjob noch nie lief.
    earnings_in_days bleibt None, der Rest der Fundamentals wird trotzdem
    uebernommen -- ein fehlendes Einzelfeld darf die anderen nicht ausreissen."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    _seed_price_history(in_memory_db, "AAPL", df)
    _seed_fundamentals_cache(
        in_memory_db, "AAPL", fetched_date="2026-05-19",
        sector="Technology", earnings_next_date=None,
    )
    out, _premarket_change_pct = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
    )
    assert out is not None
    assert out["sector"] == "Technology"
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


# ---------- _earnings_in_days (Sprint 3C / Analyse-Pipeline-Umbau, Task 7) ----------

from src.data_collector import _earnings_in_days


def test_earnings_in_days_computes_future_delta():
    assert _earnings_in_days("2026-06-02", "2026-05-19") == 14


def test_earnings_in_days_none_when_date_missing():
    assert _earnings_in_days(None, "2026-05-19") is None


def test_earnings_in_days_none_when_date_unparseable():
    """Ein kaputter String darf den Lauf nicht reissen."""
    assert _earnings_in_days("not-a-date", "2026-05-19") is None


def test_earnings_in_days_none_when_date_is_in_the_past():
    """Designentscheidung: ein gelaufener Termin (Cache noch warm) liefert
    None, nicht einen negativen Wert -- das Feld heisst 'Tage bis zum
    NAECHSTEN Termin' und war das schon vor diesem Umbau so (Finnhub lieferte
    nur zukuenftige Termine, nie ein negatives days_to_next)."""
    assert _earnings_in_days("2026-05-10", "2026-05-19") is None


def test_earnings_in_days_zero_on_the_day_itself():
    """Randfall: der Termin ist heute -- 0 ist ein gueltiger, nicht-negativer
    Wert und bleibt erhalten (keine Off-by-one-Falle bei >= 0)."""
    assert _earnings_in_days("2026-05-19", "2026-05-19") == 0


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
        results, skipped, sidecar = collect(
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
    assert set(sidecar.keys()) == {"AAPL", "MSFT", "NVDA"}


def test_collect_skips_failed_tickers_but_continues(in_memory_db):
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    # "BAD" bleibt ohne Historie und faellt daran aus — seit dem Preismodell-Umbau
    # ist die fehlende DB-Historie der Ausfallgrund, nicht ein leerer Providerabruf.
    for t in ("AAPL", "MSFT"):
        _seed_price_history(in_memory_db, t, df)

    pp = MagicMock()
    pp.get_ohlc_after.return_value = None
    pp.get_premarket_prices_batch.side_effect = (
        lambda tickers, chunk_size=20: {t: float(df["Close"].iloc[-1]) for t in tickers}
    )
    pp.get_fundamentals.return_value = {
        "pe_ratio": 25, "forward_pe": 24, "market_cap_b": 1000,
        "debt_equity": 1.0, "sector": "Technology",
        "analyst_upside": 5, "consensus": "buy",
    }
    ep = _earnings_provider()

    with patch("src.data_collector.time.sleep"):
        results, skipped, sidecar = collect(
            tickers=["AAPL", "BAD", "MSFT"],
            price_provider=pp,
            earnings_provider=ep,
            conn=in_memory_db,
            date="2026-05-19",
            run_type="pre_market",
        )

    assert {r["ticker"] for r in results} == {"AAPL", "MSFT"}
    assert skipped == 1
    assert set(sidecar.keys()) == {"AAPL", "MSFT"}, "BAD (uebersprungen) darf kein Sidecar-Eintrag haben"


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
    """Laesst _process_ticker fuer `ticker` mit dem gegebenen Rohsektor laufen
    und gibt das TickerData-Dict zurueck.

    Seedet vorher die Kurshistorie: ohne sie steigt _process_ticker vor dem
    Sektor-Mapping aus und die Sektor-Zusicherungen waeren gruen, ohne je
    geprueft zu haben. Seedet den Rohsektor seit Task 7 direkt in den
    fundamentals_cache statt ueber einen Provider-Mock -- Phase 1 ruft Finnhub
    fuer Fundamentals nicht mehr auf, ein get_fundamentals-Rueckgabewert haette
    also keine Wirkung mehr. `date` ist zugleich das Fetch-Datum des Cache-
    Eintrags (Cache-Hit garantiert, solange der Aufrufer nicht selbst > 7 Tage
    dazwischen legt)."""
    from src import db as _dbm
    df = _df_monotonic_up(250)
    _seed_price_history(conn, ticker, df)
    _dbm.save_fundamentals_cache(
        conn, ticker,
        {"pe_ratio": 28.4, "market_cap_b": 2800.0, "sector": raw_sector,
         "analyst_upside": 8.5, "consensus": "buy"},
        fetched_date=date,
    )
    out = _process_ticker(
        ticker=ticker,
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=conn,
        date=date,
        run_type="pre_market",
    )
    return out[0] if out is not None else None


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


def test_process_ticker_updates_sector_mapping_when_cache_content_changes(in_memory_db):
    """Aendert sich, was im Cache steht, zieht ticker_sectors beim naechsten
    Phase-1-Lauf nach.

    Sprint 3C / Analyse-Pipeline-Umbau (Task 7): FRUEHER (bis HEAD 8351e31)
    loeste das ein interner Finnhub-Refetch nach TTL-Ablauf aus. Phase 1 fetcht
    seit dieser Task gar nicht mehr selbst -- die "neue" Branche kommt hier
    stellvertretend fuer das, was Phase 2b (fetch_missing_fundamentals(), ab
    Task 10 verdrahtet) irgendwann in den Cache schreiben wird. Die
    _run_ticker()-Aufrufe seeden den Cache deshalb bei jedem Aufruf neu."""
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "AVGO", "Technology", date="2026-05-19")
    _run_ticker(in_memory_db, "AVGO", "Semiconductors", date="2026-05-30")
    row = db.get_ticker_sector(in_memory_db, "AVGO")
    assert row["name"] == "Semiconductors"
    assert in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM ticker_sectors WHERE ticker='AVGO'"
    ).fetchone()["n"] == 1


def test_process_ticker_leaves_sector_mapping_untouched_when_cache_goes_stale(in_memory_db):
    """R14: ein Cache-Miss loescht eine bestehende Zuordnung nicht.

    Sprint 3C / Analyse-Pipeline-Umbau (Task 7): ohne den internen Refetch
    liefert ein abgelaufener Cache-Eintrag (> 7 Tage) schlicht nichts mehr --
    fundamentals.get("sector") ist dann None, resolve_sector_id(None) gibt
    fruehzeitig None zurueck und der Upsert entfaellt. Die VORHANDENE
    Zuordnung aus dem ersten (frischen) Lauf bleibt also stehen, statt auf
    'Unknown' zurueckgesetzt zu werden -- das Nachladen sitzt jetzt in
    Phase 2b (Task 10), nicht mehr hier."""
    from src import db
    init_schema(in_memory_db)
    _run_ticker(in_memory_db, "AVGO", "Semiconductors", date="2026-05-19")
    assert db.get_ticker_sector(in_memory_db, "AVGO")["name"] == "Semiconductors"

    # 11 Tage spaeter -- jenseits der 7-Tage-TTL, Cache-Miss. Kein erneutes
    # _seed_fundamentals_cache/_run_ticker-Neuschreiben: _process_ticker direkt,
    # damit der Cache wirklich unangetastet bleibt.
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AVGO", df)
    out, _ = _process_ticker(
        ticker="AVGO", price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-05-30", run_type="pre_market",
    )
    assert out["sector"] == "Unknown", "Cache-Miss -> Default, nicht der alte Wert"
    assert db.get_ticker_sector(in_memory_db, "AVGO")["name"] == "Semiconductors", (
        "die Zuordnung bleibt stehen, auch wenn der Cache abgelaufen ist"
    )


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

    results, skipped, sidecar = collect(
        tickers=["DEAD"], price_provider=price_provider,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 1
    assert sidecar == {}
    price_provider.get_ohlc_after.assert_not_called()
    price_provider.get_price_history.assert_not_called()
    price_provider.get_premarket_prices_batch.assert_not_called()


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

    results, _, _ = collect(
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

    results, _, _ = collect(
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

    results, skipped, _sidecar = collect(
        tickers=["DEAD", "ALSOBAD"], price_provider=provider,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 2


# ---------- Phase 1a/1b: Gate, Sweep (Sprint 3C / Analyse-Pipeline-Umbau, Task 5) ----------


def test_collect_gate_filters_inactive_and_short_history(in_memory_db):
    """Zwei Filter, zwei verschiedene Paesse: Phase 1a (_gate_phase) wirft
    dauerhaft deaktivierte Ticker raus, Phase 1c (_process_ticker) wirft Ticker
    mit zu wenig Bars raus (Spec 18.1a -- die Bar-Zaehlung bleibt bewusst NACH
    dem Luecken-Nachladen, nicht im Gate). collect() muss beide zaehlen, obwohl
    sie an unterschiedlichen Stellen greifen (R5)."""
    import config
    from src import db
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-01",
                              run_type="pre_market", reason="x")
    short_df = _df_monotonic_up(10)  # < MIN_BARS_RSI
    _seed_price_history(in_memory_db, "THIN", short_df)

    results, skipped, sidecar = collect(
        tickers=["DEAD", "THIN"], price_provider=_good_provider(short_df),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-07-27", run_type="pre_market",
    )
    assert results == []
    assert skipped == 2
    assert sidecar == {}, "kein Sidecar-Eintrag fuer Ticker, die es nie in results schaffen"


def test_collect_sweep_adds_premarket_change_pct(in_memory_db):
    """Sweep: der Batch-Kurs speist sowohl td["price"] (R3) als auch die
    Sidecar-Berechnung von premarket_change_pct -- niemals als eigener Key in
    td selbst (R1/Spec 18.1e), weil td unveraendert in vier Claude-Prompts
    json.dumps't wird."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    last_close = float(df["Close"].iloc[-1])
    live = last_close * 1.05

    pp = MagicMock()
    pp.get_ohlc_after.return_value = None
    pp.get_premarket_prices_batch.return_value = {"AAPL": live}

    results, skipped, sidecar = collect(
        tickers=["AAPL"], price_provider=pp,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-05-19", run_type="pre_market",
    )
    assert skipped == 0
    assert results[0]["price"] == pytest.approx(live)
    assert "premarket_change_pct" not in results[0], "R1: niemals als Key in td"
    assert sidecar["AAPL"]["premarket_change_pct"] == pytest.approx(5.0)


# ---------- Technik-Signal im Sidecar (Sprint 3C / Analyse-Pipeline-Umbau, Task 6) ----------

def test_collect_puts_technical_signal_in_sidecar(in_memory_db):
    """Nach collect() traegt jeder Sidecar-Eintrag die vier Signalwerte."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)

    results, skipped, sidecar = collect(
        tickers=["AAPL"], price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-05-19", run_type="pre_market",
    )

    assert skipped == 0
    entry = sidecar["AAPL"]
    assert entry["tech_direction"] in ("long", "short", "neutral")
    assert 0 <= entry["tech_agreement"] <= 3
    assert entry["tech_adx_band"] in ("weak", "normal", "strong")
    assert 0 <= entry["tech_strength"] <= 4


def test_collect_keeps_technical_signal_out_of_td(in_memory_db):
    """R1: die vier Signalwerte duerfen die Prompt-Nutzlast nicht erreichen --
    td wird unveraendert in vier Claude-Prompts json.dumps't (quick_filter.py,
    deep_analysis.py, commodities_crypto.py, portfolio_check.py ueber main.py's
    `snapshots`); ein zusaetzlicher Key dort aenderte Ticker-Auswahl und Scoring."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)

    results, _skipped, _sidecar = collect(
        tickers=["AAPL"], price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-05-19", run_type="pre_market",
    )

    for key in ("tech_direction", "tech_agreement", "tech_adx_band", "tech_strength"):
        assert key not in results[0]


def test_process_ticker_computes_a_concretely_predicted_long_signal(in_memory_db):
    """Konstruierter Aufwaertstrend (Seed 18, 220 Bars, siehe _df_seeded_uptrend)
    mit echten Indikatorwerten: RSI liegt ueber 50 und steigt, die MACD-Linie
    liegt ueber der Signallinie, der Kurs liegt ueber SMA50 UND SMA200 -- alle
    drei Teilindikatoren stimmen long, macht agreement=3. ADX liegt bei rund 23,
    zwischen den Schwellen 20 (weak) und 25 (strong) -- also adx_band='normal'
    und strength bleibt bei agreement=3 (kein Bonus, kein Deckel).

    Die exakten Zahlen wurden einmalig ausserhalb des Tests mit denselben
    Indikatorfunktionen ermittelt (nicht geraten) und liegen bewusst mit
    Sicherheitsabstand innerhalb ihrer jeweiligen Baender, damit kleine
    Bibliotheks-Abweichungen die Zusicherung nicht kippen."""
    init_schema(in_memory_db)
    df = _df_seeded_uptrend(seed=18, rows=220)
    _seed_price_history(in_memory_db, "AAPL", df)
    as_of = df.index[-1].strftime("%Y-%m-%d")

    td, sidecar_entry = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date=as_of,
        run_type="pre_market",
    )

    assert td is not None
    assert sidecar_entry["tech_direction"] == "long"
    assert sidecar_entry["tech_agreement"] == 3
    assert sidecar_entry["tech_adx_band"] == "normal"
    assert sidecar_entry["tech_strength"] == 3


def test_collect_calls_sweep_exactly_once_regardless_of_ticker_count(in_memory_db):
    """Der Sweep ist EIN Aufruf ueber alle Survivors (Spec 4.3.1, '25 Calls
    statt ~500') -- Chunking passiert intern im Provider, nicht durch mehrere
    Sweep-Aufrufe aus collect()."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(80)
    tickers = [f"T{i}" for i in range(5)]
    for t in tickers:
        _seed_price_history(in_memory_db, t, df)
    pp = _good_provider(df)

    with patch("src.data_collector.time.sleep"):
        collect(
            tickers=tickers, price_provider=pp,
            earnings_provider=_earnings_provider(), conn=in_memory_db,
            date="2026-05-19", run_type="pre_market",
        )
    assert pp.get_premarket_prices_batch.call_count == 1


def test_gate_phase_exempts_commodities_and_crypto_from_deactivation(in_memory_db, caplog):
    """Spec 6.1: ein deaktivierter Rohstoff/Krypto-Ticker bleibt Survivor -- nur
    ein WARNING statt des harten Rauswurfs (R7). Das Universum ist hier so klein,
    dass ein dauerhaft fehlender Wert schwerer wiegt als bei 500 Aktien."""
    import logging
    import config
    from src import db
    from src.data_collector import _gate_phase
    init_schema(in_memory_db)
    gold = config.COMMODITY_TICKERS[0]
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker=gold, date="2026-07-01",
                              run_type="pre_market", reason="x")
    assert db.is_ticker_inactive(in_memory_db, gold, today="2026-07-27")

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        survivors = _gate_phase([gold, "AAPL"], in_memory_db, "2026-07-27")

    assert survivors == [gold, "AAPL"]
    assert "Ausnahme" in caplog.text


def test_gate_phase_still_removes_non_exempt_inactive_tickers(in_memory_db):
    """Die Rohstoff/Krypto-Ausnahme darf nicht auf normale Aktien ausstrahlen."""
    import config
    from src import db
    from src.data_collector import _gate_phase
    init_schema(in_memory_db)
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(in_memory_db, ticker="DEAD", date="2026-07-01",
                              run_type="pre_market", reason="x")
    survivors = _gate_phase(["DEAD", "AAPL"], in_memory_db, "2026-07-27")
    assert survivors == ["AAPL"]


def test_sweep_phase_survives_provider_without_batch_support(caplog):
    """base.py wirft NotImplementedError fuer Provider ohne Batch-Methode (heute
    z.B. FinnhubProvider) -- der Sweep faengt das ab, loggt WARNING und liefert
    ein leeres Dict, der Lauf laeuft weiter (R7)."""
    import logging
    from src.data_collector import _sweep_phase
    from src.providers.base import DataProvider

    class _NoBatchProvider(DataProvider):
        def get_price_history(self, ticker, days=90): return None
        def get_fundamentals(self, ticker): return {}
        def get_earnings_calendar(self, ticker): return {}
        def get_last_available_date(self, ticker): return None
        def get_ohlc_after(self, ticker, start_date, end_date): return None

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        result = _sweep_phase(["AAPL"], _NoBatchProvider())

    assert result == {}
    assert "Sweep" in caplog.text, "R7 verlangt ein WARNING, kein stilles Schlucken"


def test_sweep_phase_does_not_call_the_provider_when_there_are_no_survivors():
    """Ein leerer Gate-Rest darf keinen Netzaufruf mehr ausloesen."""
    from src.data_collector import _sweep_phase
    pp = MagicMock()
    assert _sweep_phase([], pp) == {}
    pp.get_premarket_prices_batch.assert_not_called()


def test_sweep_phase_warns_when_over_20_percent_of_survivors_have_no_price(caplog):
    """Spec 4.3, Muster D3: uebersteigt der Anteil der Survivors ohne Live-Kurs
    20 %, warnt der Sweep von sich aus (R7)."""
    import logging
    from src.data_collector import _sweep_phase
    tickers = [f"T{i}" for i in range(10)]
    pp = MagicMock()
    # 3 von 10 (30 %) ohne Kurs -> ueber der 20 %-Schwelle.
    pp.get_premarket_prices_batch.return_value = {
        t: (None if i < 3 else 100.0) for i, t in enumerate(tickers)
    }

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        _sweep_phase(tickers, pp)

    assert "3" in caplog.text and "10" in caplog.text


def test_sweep_phase_silent_when_missing_share_is_at_or_below_20_percent(caplog):
    """Die Schwelle ist '> 20 %', nicht '>= 20 %' -- exakt 20 % warnt noch nicht."""
    import logging
    from src.data_collector import _sweep_phase
    tickers = [f"T{i}" for i in range(10)]
    pp = MagicMock()
    # Genau 2 von 10 (20 %) ohne Kurs.
    pp.get_premarket_prices_batch.return_value = {
        t: (None if i < 2 else 100.0) for i, t in enumerate(tickers)
    }

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        _sweep_phase(tickers, pp)

    assert caplog.text == ""


def test_process_ticker_falls_back_to_close_with_none_pct_when_sweep_has_no_price(in_memory_db):
    """R7: ein fehlender Live-Kurs (Ticker fehlt im Sweep-Dict komplett, oder
    der Wert ist None) faellt auf den letzten finalen Close zurueck --
    premarket_change_pct bleibt dabei None, NIE 0 (eine 0 behauptete
    'eroeffnet unveraendert', eine Beobachtung, die niemand gemessen hat)."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    last_close = float(df["Close"].iloc[-1])

    out, sidecar_entry = _process_ticker(
        ticker="AAPL",
        price_provider=_good_provider(df),
        earnings_provider=_earnings_provider(),
        conn=in_memory_db,
        date="2026-05-19",
        run_type="pre_market",
        premarket_price=None,
    )
    assert out is not None
    assert out["price"] == pytest.approx(last_close)
    assert sidecar_entry["premarket_change_pct"] is None


def test_collect_survives_ticker_missing_entirely_from_sweep_dict(in_memory_db):
    """get_premarket_prices_batch() laesst Ticker aus uebersprungenen oder nie
    erreichten Chunks komplett weg (siehe dessen Docstring) -- collect() muss
    das per .get() statt [] abfangen, sonst reisst ein KeyError den ganzen
    Lauf (R7)."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)

    pp = MagicMock()
    pp.get_ohlc_after.return_value = None
    pp.get_premarket_prices_batch.return_value = {}  # AAPL komplett abwesend

    results, skipped, sidecar = collect(
        tickers=["AAPL"], price_provider=pp,
        earnings_provider=_earnings_provider(), conn=in_memory_db,
        date="2026-05-19", run_type="pre_market",
    )
    assert skipped == 0
    assert results[0]["price"] == pytest.approx(float(df["Close"].iloc[-1]))
    assert sidecar["AAPL"]["premarket_change_pct"] is None


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
    mock_earn = mocker.MagicMock()
    mock_earn.get_earnings_calendar.return_value = {}
    mock_earn.get_fundamentals.return_value = {}

    # Der Entscheidungskurs kommt seit Task 5 aus dem Sweep (collect()), nicht
    # mehr aus einem Einzelabruf in _process_ticker() -- deshalb hier direkt
    # als premarket_price uebergeben statt ueber den Provider gemockt (R3).
    td, _premarket_change_pct = _process_ticker(
        "AAPL", mock_price, mock_earn, in_memory_db,
        "2026-08-06", "pre_market", premarket_price=321.5,
    )

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


# ---------- Innenliegende Luecken (Befund aus dem Smoke-Test 2026-08-08) ----------

def test_fill_price_gaps_closes_a_hole_behind_a_newer_bar(in_memory_db, mocker):
    """Der reale Ausfall-Fall: nach einer Unterbrechung schreibt final_close um
    00:15 die Bar von gestern. MAX(date) ist damit wieder aktuell, und die alte
    Luecke dahinter wurde nie wieder gesehen -- die Erkennung fragte nur, ob der
    LETZTE Bar zu alt ist.

    Nachgestellt aus dem Smoke-Test vom 2026-08-08: AAPL hatte 2026-07-29 und
    2026-08-07, dazwischen sieben Handelstage nichts. Ein kompletter close-Lauf
    danach hat die Luecke nicht angefasst."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    for d in ("2026-07-29", "2026-08-07"):
        db.insert_price_bar_if_missing(
            in_memory_db, ticker="AAPL", date=d,
            open_=100, high=101, low=99, close=100.5, volume=1000,
            source="capital.com")
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"
    fill = ["2026-07-30", "2026-07-31", "2026-08-03",
            "2026-08-04", "2026-08-05", "2026-08-06"]
    provider.get_ohlc_after.return_value = pd.DataFrame(
        {"Open": [1.0] * len(fill), "High": [2.0] * len(fill),
         "Low": [0.5] * len(fill), "Close": [1.5] * len(fill),
         "Volume": [1] * len(fill)},
        index=pd.to_datetime(fill),
    )

    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-08-08")

    assert n == len(fill), "Die innenliegende Luecke muss geschlossen werden"
    dates = [r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='AAPL' ORDER BY date").fetchall()]
    assert "2026-08-03" in dates and "2026-07-30" in dates


def test_fill_price_gaps_does_not_chase_single_holidays(in_memory_db, mocker):
    """35 der 1000 AAPL-Bars in der echten DB fehlen als einzelne Wochentage --
    das sind US-Feiertage, keine Luecken. Ohne Boersenkalender ist der einzige
    belastbare Unterschied die Laenge: ein Ausfall dauert mehrere Tage.

    Ohne diese Regel liefe jeder Lauf fuer jeden Ticker ins Leere nachladen."""
    from src import db
    from src.data_collector import _fill_price_gaps
    db.init_schema(in_memory_db)
    # 2026-07-24 fehlt als einzelner Tag (Feiertag), sonst luckenlos.
    for d in ("2026-07-22", "2026-07-23", "2026-07-27", "2026-07-28"):
        db.insert_price_bar_if_missing(
            in_memory_db, ticker="AAPL", date=d,
            open_=100, high=101, low=99, close=100.5, volume=1000,
            source="capital.com")
    in_memory_db.commit()

    provider = mocker.MagicMock()
    provider._source_name = "capital.com"

    n = _fill_price_gaps("AAPL", provider, in_memory_db, date="2026-07-29")

    assert n == 0
    provider.get_ohlc_after.assert_not_called()


# ---------- fetch_missing_fundamentals() -- Phase 2b, gebaut, nicht verdrahtet
# (Sprint 3C / Analyse-Pipeline-Umbau, Task 7, R16) ----------

from src.data_collector import fetch_missing_fundamentals


def test_fetch_missing_fundamentals_fetches_and_persists_cache_misses(in_memory_db):
    """R13: aus der DB zurueckgelesen, nicht nur der Aufruf geprueft."""
    from src import db
    init_schema(in_memory_db)
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 30.0, "market_cap_b": 500.0, "sector": "Technology",
    }

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-19")

    ep.get_fundamentals.assert_called_once_with("AAPL")
    row = db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-19")
    assert row is not None
    assert row["pe_ratio"] == 30.0
    assert row["sector"] == "Technology"


def test_fetch_missing_fundamentals_skips_tickers_already_cached(in_memory_db):
    """Ein Cache-Hit braucht keinen Finnhub-Call -- sonst waere die Funktion
    selbst die Kostenquelle, die Task 7 aus Phase 1 herausloest."""
    from src import db
    init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-19")
    ep = MagicMock()

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-19")

    ep.get_fundamentals.assert_not_called()


def test_fetch_missing_fundamentals_continues_after_one_ticker_errors(in_memory_db, caplog):
    """R16: ein API-Fehler bei einem Ticker ueberspringt NUR diesen (WARNING),
    der Lauf laeuft fuer die uebrigen weiter."""
    import logging
    from src import db
    init_schema(in_memory_db)
    ep = MagicMock()
    ep.get_fundamentals.side_effect = [
        RuntimeError("Finnhub 500"),
        {"pe_ratio": 18.0, "sector": "Pharmaceuticals"},
    ]

    with caplog.at_level(logging.WARNING, logger="shares_future.data_collector"):
        fetch_missing_fundamentals(["BAD", "JNJ"], ep, in_memory_db, date="2026-05-19")

    assert "BAD" in caplog.text
    assert db.get_cached_fundamentals(in_memory_db, "BAD", today="2026-05-19") is None
    row = db.get_cached_fundamentals(in_memory_db, "JNJ", today="2026-05-19")
    assert row is not None
    assert row["pe_ratio"] == 18.0


def test_fetch_missing_fundamentals_skips_empty_provider_response(in_memory_db):
    """Ein leeres dict (Finnhub ohne API-Key/ohne Daten) darf keine leere
    Cache-Zeile anlegen -- der naechste Lauf soll es erneut versuchen."""
    from src import db
    init_schema(in_memory_db)
    ep = MagicMock()
    ep.get_fundamentals.return_value = {}

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert db.get_cached_fundamentals(in_memory_db, "AAPL", today="2026-05-19") is None


def test_fetch_missing_fundamentals_maps_sector(in_memory_db):
    """Frisch nachgeladene Fundamentals pflegen ticker_sectors mit, genau wie
    es _process_ticker frueher direkt nach einem Finnhub-Fetch getan hat."""
    from src import db
    init_schema(in_memory_db)
    ep = MagicMock()
    ep.get_fundamentals.return_value = {"sector": "Semiconductors"}

    fetch_missing_fundamentals(["NVDA"], ep, in_memory_db, date="2026-05-19")

    row = db.get_ticker_sector(in_memory_db, "NVDA")
    assert row is not None
    assert row["name"] == "Semiconductors"
    assert row["etf"] == "SOXX"


def test_fetch_missing_fundamentals_preserves_earnings_next_date_across_refresh(in_memory_db):
    """Regressionstest fuer einen im Review gefundenen Datenverlust-Bug:
    save_fundamentals_cache() ist ein INSERT OR REPLACE der GANZEN Zeile, und
    get_fundamentals() liefert nie ein earnings_next_date (das kommt vom
    Wochenjob, R15). Ohne Schutz wuerde ein bereits gesetztes Datum auf NULL
    zurueckfallen, sobald irgendein ANDERES Feld (hier: pe_ratio) seine
    7-Tage-TTL ueberschreitet und die Zeile neu geschrieben wird -- zwei
    unabhaengige Ablauf-Rhythmen teilen sich einen Voll-Zeilen-Schreibpfad.
    fetch_missing_fundamentals() muss das vorhandene Datum TTL-los nachlesen
    und in die neue Zeile uebernehmen."""
    from src import db
    init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL",
        {"pe_ratio": 20.0, "earnings_next_date": "2026-06-02"},
        fetched_date="2026-05-01",  # laengst ausserhalb der 7-Tage-TTL
    )
    ep = MagicMock()
    ep.get_fundamentals.return_value = {"pe_ratio": 25.0}  # kein earnings_next_date

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-21")

    row = in_memory_db.execute(
        "SELECT * FROM fundamentals_cache WHERE ticker='AAPL'").fetchone()
    assert row["pe_ratio"] == 25.0, "die frischen Fundamentals kommen trotzdem an"
    assert row["earnings_next_date"] == "2026-06-02", (
        "das alte Datum darf nicht verloren gehen, nur weil pe_ratio abgelaufen ist"
    )


def test_fetch_missing_fundamentals_leaves_earnings_next_date_null_when_never_set(in_memory_db):
    """Kein vorheriger Wert -> auch nach dem Refresh bleibt es NULL, kein
    Platzhalter wird erfunden."""
    from src import db
    init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL", {"pe_ratio": 20.0}, fetched_date="2026-05-01",
    )
    ep = MagicMock()
    ep.get_fundamentals.return_value = {"pe_ratio": 25.0}

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-21")

    row = in_memory_db.execute(
        "SELECT * FROM fundamentals_cache WHERE ticker='AAPL'").fetchone()
    assert row["pe_ratio"] == 25.0
    assert row["earnings_next_date"] is None


def test_fetch_missing_fundamentals_does_not_override_a_freshly_fetched_earnings_next_date(in_memory_db):
    """Liefert get_fundamentals() (in Zukunft, oder ein anderer Provider) doch
    einmal ein eigenes earnings_next_date mit, hat das Vorrang vor dem alten
    Cache-Wert -- die Nachlese darf frische Daten nie verdraengen."""
    from src import db
    init_schema(in_memory_db)
    db.save_fundamentals_cache(
        in_memory_db, "AAPL",
        {"pe_ratio": 20.0, "earnings_next_date": "2026-06-02"},
        fetched_date="2026-05-01",
    )
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 25.0, "earnings_next_date": "2026-09-15",
    }

    fetch_missing_fundamentals(["AAPL"], ep, in_memory_db, date="2026-05-21")

    row = in_memory_db.execute(
        "SELECT * FROM fundamentals_cache WHERE ticker='AAPL'").fetchone()
    assert row["earnings_next_date"] == "2026-09-15"


def test_fetch_missing_fundamentals_not_wired_into_process_ticker(in_memory_db):
    """R16: _process_ticker (Phase 1) ruft fetch_missing_fundamentals nicht auf
    -- Phase 1 bleibt Finnhub-frei. Das Nachladen sitzt in Phase 2b
    (run_phase_2b(), seit dem Abschluss-Review in main.run_pipeline verdrahtet),
    nicht hier."""
    init_schema(in_memory_db)
    df = _df_monotonic_up(250)
    _seed_price_history(in_memory_db, "AAPL", df)
    ep = _earnings_provider()

    out, _ = _process_ticker(
        ticker="AAPL", price_provider=_good_provider(df),
        earnings_provider=ep, conn=in_memory_db,
        date="2026-05-19", run_type="pre_market",
    )
    assert out["sector"] == "Unknown"
    ep.get_fundamentals.assert_not_called()


# ---------- run_phase_2b() -- Phase 2b (Abschluss-Review, Spec 4.7 / 18.1b+f) ----------

from src.data_collector import run_phase_2b
from src.db import save_fundamentals_cache


def test_phase_2b_mirrors_freshly_fetched_fundamentals_into_the_td(in_memory_db):
    """Der Kern des Befunds: fetch_missing_fundamentals() allein waermt nur den
    Cache fuer MORGEN. Die Werte muessen auch in das td-Dict zurueck, das HEUTE
    in den Phase-3-Prompt geht (Spec: 'market_cap_b erreicht Claude weiterhin
    ueber den Ticker-Snapshot aus 2b')."""
    init_schema(in_memory_db)
    td = {"ticker": "AAPL", "rsi_14": 55.0, "atr_pct": 2.5, "above_sma200": 3.0,
          "pe_ratio": None, "forward_pe": None, "market_cap_b": None,
          "debt_equity": None, "sector": "Unknown",
          "analyst_target_upside": None, "analyst_consensus": None,
          # Spec E3: _process_ticker() legt den Schluessel seit 2026-08-20 an --
          # das Literal hier bildet dessen Form nach, die Invariante (Phase 2b
          # FUELLT nur, legt nichts an) bleibt unveraendert scharf.
          "analyst_consensus_period": None,
          "earnings_in_days": None, "earnings_beat_pct": None,
          "data_quality": "medium"}
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "forward_pe": 26.0, "market_cap_b": 2800.0,
        "debt_equity": 1.4, "sector": "Semiconductors",
        "analyst_upside": 7.5, "consensus": "buy",
    }

    run_phase_2b([td], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert td["market_cap_b"] == 2800.0
    assert td["sector"] == "Semiconductors"
    assert td["pe_ratio"] == 28.4
    assert td["analyst_consensus"] == "buy"


def test_phase_2b_upgrades_data_quality_to_high(in_memory_db):
    """Spec 18.1f: die medium/high-Einstufung entsteht in Phase 2b, nachdem die
    Fundamentals da sind -- nicht in Phase 1."""
    init_schema(in_memory_db)
    td = {"ticker": "AAPL", "rsi_14": 55.0, "atr_pct": 2.5, "above_sma200": 3.0,
          "pe_ratio": None, "market_cap_b": None, "sector": "Unknown",
          "forward_pe": None, "debt_equity": None,
          "analyst_target_upside": None, "analyst_consensus": None,
          "earnings_in_days": None, "earnings_beat_pct": None,
          "data_quality": "medium"}
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "forward_pe": 26.0, "market_cap_b": 2800.0,
        "debt_equity": 1.4, "sector": "Semiconductors",
        "analyst_upside": 7.5, "consensus": "buy",
    }

    run_phase_2b([td], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert td["data_quality"] == "high"


def test_phase_2b_never_downgrades_to_low(in_memory_db):
    """Ein Ticker, der Phase 1 ueberlebt hat, darf in 2b nicht nachtraeglich auf
    'low' fallen -- der low-Skip gehoert laut Spec 18.1f ausschliesslich in
    Phase 1, und 2b laeuft erst nach dem Cutoff (Analyse teils bezahlt)."""
    init_schema(in_memory_db)
    td = {"ticker": "AAPL", "rsi_14": None, "atr_pct": None, "above_sma200": None,
          "pe_ratio": None, "market_cap_b": None, "sector": "Unknown",
          "forward_pe": None, "debt_equity": None,
          "analyst_target_upside": None, "analyst_consensus": None,
          "earnings_in_days": None, "earnings_beat_pct": None,
          "data_quality": "medium"}
    ep = MagicMock()
    ep.get_fundamentals.return_value = {}

    run_phase_2b([td], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert td["data_quality"] == "medium"


def test_phase_2b_only_touches_the_selected_candidates(in_memory_db):
    """2b ist kandidaten-only (Spec 4.7) -- ein nicht ausgewaehlter Ticker
    kostet keinen Finnhub-Call und behaelt seinen Phase-1-Stand."""
    init_schema(in_memory_db)
    picked = {"ticker": "AAPL", "rsi_14": 55.0, "atr_pct": 2.5, "sector": "Unknown",
              "pe_ratio": None, "market_cap_b": None, "above_sma200": 1.0,
              "forward_pe": None, "debt_equity": None,
              "analyst_target_upside": None, "analyst_consensus": None,
              "earnings_in_days": None, "earnings_beat_pct": None,
              "data_quality": "medium"}
    dropped = {**picked, "ticker": "MSFT"}
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "forward_pe": 26.0, "market_cap_b": 2800.0,
        "debt_equity": 1.4, "sector": "Semiconductors",
        "analyst_upside": 7.5, "consensus": "buy",
    }

    run_phase_2b([picked, dropped], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert picked["sector"] == "Semiconductors"
    assert dropped["sector"] == "Unknown"
    ep.get_fundamentals.assert_called_once_with("AAPL")


def test_phase_2b_computes_earnings_in_days_from_the_cached_date(in_memory_db):
    """earnings_in_days wird beim Lesen gerechnet (Spec 18.1d) -- auch auf dem
    2b-Pfad, nicht nur in Phase 1."""
    init_schema(in_memory_db)
    save_fundamentals_cache(
        in_memory_db, "AAPL",
        {"pe_ratio": 25.0, "forward_pe": 23.0, "market_cap_b": 200.0,
         "debt_equity": 1.0, "sector": "Technology", "analyst_upside": 5.0,
         "consensus": "buy", "earnings_next_date": "2026-05-29"},
        fetched_date="2026-05-19",
    )
    td = {"ticker": "AAPL", "rsi_14": 55.0, "atr_pct": 2.5, "above_sma200": 1.0,
          "pe_ratio": None, "market_cap_b": None, "sector": "Unknown",
          "forward_pe": None, "debt_equity": None,
          "analyst_target_upside": None, "analyst_consensus": None,
          "earnings_in_days": None, "earnings_beat_pct": None,
          "data_quality": "medium"}
    ep = MagicMock()

    run_phase_2b([td], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert td["earnings_in_days"] == 10
    ep.get_fundamentals.assert_not_called()   # Cache war warm


def test_phase_2b_adds_no_new_keys_to_the_td(in_memory_db):
    """Sidecar-Invariante: td geht in vier Claude-Prompts. 2b darf vorhandene
    Werte fuellen, aber niemals neue Schluessel einfuehren."""
    init_schema(in_memory_db)
    td = {"ticker": "AAPL", "rsi_14": 55.0, "atr_pct": 2.5, "above_sma200": 1.0,
          "pe_ratio": None, "market_cap_b": None, "sector": "Unknown",
          "forward_pe": None, "debt_equity": None,
          "analyst_target_upside": None, "analyst_consensus": None,
          # Spec E3: _process_ticker() legt den Schluessel seit 2026-08-20 an --
          # die Invariante (Phase 2b FUELLT nur, legt nichts an) bleibt scharf.
          "analyst_consensus_period": None,
          "earnings_in_days": None, "earnings_beat_pct": None,
          "data_quality": "medium"}
    before = set(td)
    ep = MagicMock()
    ep.get_fundamentals.return_value = {
        "pe_ratio": 28.4, "forward_pe": 26.0, "market_cap_b": 2800.0,
        "debt_equity": 1.4, "sector": "Semiconductors",
        "analyst_upside": 7.5, "consensus": "buy",
    }

    run_phase_2b([td], ["AAPL"], ep, in_memory_db, date="2026-05-19")

    assert set(td) == before
