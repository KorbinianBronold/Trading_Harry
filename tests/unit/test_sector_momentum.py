"""Tests fuer src/sector_momentum.py — die Erhebung beider Momentum-Signale
je Sub-Sektor (Sprint 3B / Plan 1, Task 9a, Entscheidung D9). Komplett offline:
der Capital.com-Provider ist durchgehend gemockt."""
from unittest.mock import MagicMock

import pandas as pd

from src import db


def _etf_frame(*closes: float, dates: tuple[str, ...] | None = None) -> pd.DataFrame:
    """Minimaler OHLCV-Frame wie ihn CapitalComProvider.get_price_history()
    liefert — ein Bar je uebergebenem Schlusskurs."""
    dates = dates or ("2026-07-24", "2026-07-27")
    return pd.DataFrame(
        {"Open": list(closes), "High": list(closes),
         "Low": list(closes), "Close": list(closes),
         "Volume": [0] * len(closes)},
        index=pd.to_datetime(list(dates)),
    )


def _bar(conn, ticker: str, date: str, close: float) -> None:
    db.insert_price_bar_if_missing(
        conn, ticker=ticker, date=date, open_=close, high=close,
        low=close, close=close, volume=1000, source="capital.com",
    )


def _provider(frame) -> MagicMock:
    p = MagicMock()
    p._source_name = "capital.com"
    p.get_price_history.return_value = frame
    return p


def test_collect_writes_one_row_per_sub_sector(in_memory_db):
    import config
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    out = collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 101.0)),
    )
    assert len(out) == len(config.SUB_SECTOR_ETFS)
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert len(stored) == len(config.SUB_SECTOR_ETFS)


def test_collect_computes_etf_momentum_from_fetched_bars(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 102.0)),
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["etf_momentum"], 4) == 2.0


def test_collect_never_writes_price_history(in_memory_db):
    """sector_momentum fasst price_history nicht an — final_close ist der
    alleinige Schreiber (Preismodell-Umbau 2026-08-06).

    Die Umkehrung des frueheren test_collect_persists_etf_bars_into_price_history.
    Dieses Modul war der dritte, leicht uebersehene Schreiber: es legte die Bars
    der Sektor-ETFs per INSERT OR IGNORE ab, und zwar die Teilbar des laufenden
    Tages. Da compute_relative_strength den Ticker GEGEN seinen Sub-Sektor-ETF
    vergleicht und beide Seiten aus price_history liest, war die ETF-Seite
    genauso eingefroren wie die Ticker-Seite. Die ETF-Bars holt seit Task 5 der
    final_close-Lauf, und zwar final."""
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 102.0)),
    )
    n = in_memory_db.execute(
        "SELECT COUNT(*) AS c FROM price_history").fetchone()["c"]
    assert n == 0, "sector_momentum darf price_history nicht schreiben"


def test_collect_ignores_etf_bars_after_the_run_date(in_memory_db):
    """Ein Frame, der ueber `date` hinausreicht, darf weder gespeichert werden
    noch das Momentum verfaelschen — sonst misst der ETF einen anderen Tag als
    das DB-Signal."""
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    frame = _etf_frame(100.0, 102.0, 200.0,
                       dates=("2026-07-24", "2026-07-27", "2026-07-28"))

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(frame),
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["etf_momentum"], 4) == 2.0
    dates = [r["date"] for r in in_memory_db.execute(
        "SELECT date FROM price_history WHERE ticker='SOXX'").fetchall()]
    assert "2026-07-28" not in dates


def test_collect_leaves_etf_momentum_none_when_fetch_returns_nothing(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(None),
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert stored[sid]["etf_momentum"] is None


def test_collect_leaves_etf_momentum_none_when_fetch_raises(in_memory_db):
    """Ein einzelner ETF-Ausfall darf den ganzen Lauf nicht abbrechen."""
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = _provider(None)
    provider.get_price_history.side_effect = RuntimeError("Capital.com 500")

    out = collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    assert all(e["etf_momentum"] is None for e in out.values())


def test_collect_leaves_etf_momentum_none_with_only_one_bar(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, dates=("2026-07-27",))),
    )
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert stored[sid]["etf_momentum"] is None


def test_collect_fetches_each_etf_only_once(in_memory_db):
    """MedTech, Pharma und Healthcare Rest teilen sich XLV — ein Call genuegt."""
    import config
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    provider = _provider(_etf_frame(100.0, 101.0))

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=provider,
    )
    assert provider.get_price_history.call_count == len(
        set(config.SUB_SECTOR_ETFS.values()))


def test_shared_etf_yields_identical_etf_momentum_for_its_sub_sectors(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 103.0)),
    )
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    xlv_ids = [db.resolve_sector_id(in_memory_db, n)
               for n in ("MedTech", "Pharma", "Healthcare Rest")]
    assert {round(stored[i]["etf_momentum"], 4) for i in xlv_ids} == {3.0}


def test_collect_fills_db_momentum_when_enough_tickers(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    sid = db.resolve_sector_id(in_memory_db, "Pharmaceuticals")
    for t, today in (("JNJ", 102.0), ("LLY", 104.0), ("ABBV", 106.0)):
        db.upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", today)
    in_memory_db.commit()

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 101.0)),
    )
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["db_momentum"], 4) == 4.0
    assert stored[sid]["ticker_count"] == 3


def test_collect_leaves_db_momentum_none_below_minimum(in_memory_db):
    from src.sector_momentum import collect_sector_momentum
    db.init_schema(in_memory_db)
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    for t in ("NVDA", "AVGO"):
        db.upsert_ticker_sector(in_memory_db, t, sid)
        _bar(in_memory_db, t, "2026-07-24", 100.0)
        _bar(in_memory_db, t, "2026-07-27", 105.0)
    in_memory_db.commit()

    collect_sector_momentum(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        price_provider=_provider(_etf_frame(100.0, 101.0)),
    )
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert stored[sid]["db_momentum"] is None
    assert stored[sid]["ticker_count"] == 2


def test_collect_is_idempotent_within_a_run(in_memory_db):
    """Zweiter Aufruf desselben Runs ueberschreibt, statt zu duplizieren."""
    from src.sector_momentum import collect_sector_momentum
    import config
    db.init_schema(in_memory_db)

    for frame in (_etf_frame(100.0, 101.0), _etf_frame(100.0, 105.0)):
        collect_sector_momentum(
            conn=in_memory_db, date="2026-07-27", run_type="pre_market",
            price_provider=_provider(frame),
        )
    n = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM sector_momentum").fetchone()["n"]
    assert n == len(config.SUB_SECTOR_ETFS)
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    stored = db.load_sector_momentum(in_memory_db, "2026-07-27", "pre_market")
    assert round(stored[sid]["etf_momentum"], 4) == 5.0
