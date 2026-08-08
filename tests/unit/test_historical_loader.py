import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date, timedelta


def _multi_day_df(days: int = 756) -> pd.DataFrame:
    dates = pd.date_range(start="2023-01-02", periods=days, freq="B")
    return pd.DataFrame(
        {
            "Open":   [100.0] * days,
            "High":   [105.0] * days,
            "Low":    [ 99.0] * days,
            "Close":  [102.0] * days,
            "Volume": [1_000_000] * days,
        },
        index=dates,
    )


def test_load_ticker_history_inserts_rows(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = _multi_day_df(756)
        from setup.historical_loader import load_ticker_history
        inserted = load_ticker_history("AAPL", db_path=db_path)

    assert inserted > 0
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        "SELECT COUNT(*) FROM price_history WHERE ticker='AAPL'"
    ).fetchone()[0]
    conn.close()
    assert count == inserted


def test_load_ticker_history_skips_duplicates(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    df = _multi_day_df(30)
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = df
        from setup.historical_loader import load_ticker_history
        first  = load_ticker_history("MSFT", db_path=db_path)
        second = load_ticker_history("MSFT", db_path=db_path)

    assert first  == 30
    assert second == 0


def test_load_all_calls_load_ticker_history_per_ticker(mocker):
    mock_load = mocker.patch(
        "setup.historical_loader.load_ticker_history", return_value=100
    )
    from setup.historical_loader import load_all
    load_all(tickers=["AAPL", "MSFT", "NVDA"], db_path=":memory:")
    assert mock_load.call_count == 3


def test_load_ticker_history_returns_zero_on_empty_df(tmp_path):
    db_path = str(tmp_path / "test.db")
    import sqlite3
    from src import db
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    db.init_schema(conn)
    conn.close()

    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = None
        from setup.historical_loader import load_ticker_history
        result = load_ticker_history("UNKNOWN", db_path=db_path)

    assert result == 0


# ---------- Ticker-Status-CLI (Sprint 3B / Plan 1, Task 7) ----------

def _deactivate(conn, ticker: str, date: str = "2026-07-27"):
    import config
    from src import db
    for _ in range(config.TICKER_MAX_SKIPS + 1):
        db.log_skipped_ticker(conn, ticker=ticker, date=date,
                              run_type="pre_market", reason="x")


def test_reactivate_flag_resets_named_tickers(tmp_db_path, capsys):
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    _deactivate(conn, "DEAD")
    conn.close()

    from setup.historical_loader import main
    main(["--reactivate", "DEAD", "--db-path", str(tmp_db_path)])

    conn = db.connect(str(tmp_db_path))
    assert db.is_ticker_inactive(conn, "DEAD", today="2026-07-28") is False
    assert db.get_ticker_status(conn, "DEAD")["skip_count"] == 0
    conn.close()
    assert "DEAD" in capsys.readouterr().out


def test_reactivate_flag_handles_multiple_tickers(tmp_db_path, capsys):
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    _deactivate(conn, "DEAD")
    _deactivate(conn, "ALSODEAD")
    conn.close()

    from setup.historical_loader import main
    main(["--reactivate", "DEAD", "ALSODEAD", "--db-path", str(tmp_db_path)])

    conn = db.connect(str(tmp_db_path))
    assert db.list_inactive_tickers(conn) == []
    conn.close()


def test_reactivate_flag_reports_unknown_ticker(tmp_db_path, capsys):
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    conn.close()

    from setup.historical_loader import main
    main(["--reactivate", "NEVERSKIPPED", "--db-path", str(tmp_db_path)])
    out = capsys.readouterr().out
    assert "NEVERSKIPPED" in out
    assert "nichts zu tun" in out


def test_list_inactive_flag_prints_deactivated_tickers(tmp_db_path, capsys):
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    _deactivate(conn, "DEAD")
    conn.close()

    from setup.historical_loader import main
    main(["--list-inactive", "--db-path", str(tmp_db_path)])
    out = capsys.readouterr().out
    assert "DEAD" in out
    assert "2026-08-26" in out          # retry_after


def test_list_inactive_flag_says_so_when_empty(tmp_db_path, capsys):
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    conn.close()

    from setup.historical_loader import main
    main(["--list-inactive", "--db-path", str(tmp_db_path)])
    assert "Keine deaktivierten Ticker" in capsys.readouterr().out


def test_status_flags_do_not_load_any_history(tmp_db_path, capsys):
    """--reactivate/--list-inactive duerfen keine Capital.com-Calls ausloesen."""
    from src import db
    conn = db.connect(str(tmp_db_path))
    db.init_schema(conn)
    _deactivate(conn, "DEAD")
    conn.close()

    from setup.historical_loader import main
    with patch("setup.historical_loader.load_all") as mock_load:
        main(["--reactivate", "DEAD", "--db-path", str(tmp_db_path)])
        main(["--list-inactive", "--db-path", str(tmp_db_path)])
    mock_load.assert_not_called()


def test_a_mode_flag_is_required(capsys):
    """Ohne Modus-Flag bricht argparse ab, statt stillschweigend die MVP-Liste
    zu laden — sonst loest ein Tippfehler einen 500-Ticker-Pull aus."""
    from setup.historical_loader import main
    with pytest.raises(SystemExit):
        main([])


# ---------- --universe: Bootstrap einer leeren DB ----------

def test_universe_flag_loads_the_full_universe(tmp_db_path, mocker):
    """`--all` laedt nur die 20 Aktien. Fuer den CI-Bootstrap braucht es auch
    Rohstoffe, Krypto und die Sub-Sektor-ETFs — sonst laufen die Sektor- und
    Commodity-Phasen weiter gegen eine leere Historie."""
    from src.universe import full_universe
    load_all = mocker.patch("setup.historical_loader.load_all", return_value={})

    from setup.historical_loader import main
    main(["--universe", "--db-path", str(tmp_db_path)])

    load_all.assert_called_once()
    assert load_all.call_args.args[0] == full_universe()


def test_universe_flag_is_a_mode_flag(tmp_db_path):
    """--universe gehoert in dieselbe exklusive Gruppe wie --all: zwei Modi
    gleichzeitig sind ein Bedienfehler, kein zusammengesetzter Lauf."""
    from setup.historical_loader import main
    with pytest.raises(SystemExit):
        main(["--universe", "--all", "--db-path", str(tmp_db_path)])


# ---------- --report-coverage: sieht die DB gesund aus? ----------

def test_report_coverage_flags_tickers_below_the_minimum(tmp_db_path, capsys):
    """Der Kern des 04.08.-Befunds: 19 Bars sind eine unter MIN_BARS_RSI=20 und
    fuehren zu einem gruenen, leeren Lauf. Der Report muss so einen Ticker
    benennen, nicht nur eine Gesamtzahl."""
    from src import db
    from src.data_collector import MIN_BARS_RSI
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn)
    for i in range(MIN_BARS_RSI - 1):
        db.insert_price_bar_if_missing(
            conn, ticker="AAPL", date=f"2026-01-{i + 1:02d}",
            open_=1.0, high=2.0, low=0.5, close=1.5, volume=10, source="test")
    conn.commit(); conn.close()

    from setup.historical_loader import main
    main(["--report-coverage", "--db-path", str(tmp_db_path)])

    out = capsys.readouterr().out
    assert "AAPL" in out
    assert "19" in out


def test_report_coverage_makes_no_api_calls(tmp_db_path, mocker):
    """Reine DB-Operation wie --list-inactive. Ein Report, der Capital.com
    anfasst, waere in einem Fehlerfall genau das Falsche."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()
    cap = mocker.patch("setup.historical_loader.CapitalComProvider")
    load_all = mocker.patch("setup.historical_loader.load_all")

    from setup.historical_loader import main
    main(["--report-coverage", "--db-path", str(tmp_db_path)])

    cap.assert_not_called()
    load_all.assert_not_called()


def test_report_coverage_reports_missing_tickers(tmp_db_path, capsys):
    """Ein Ticker ganz ohne Bars ist der schlimmere Fall — er wird nie
    nachgeladen, weil _fill_price_gaps bei leerer Historie bewusst nichts tut."""
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    from setup.historical_loader import main
    main(["--report-coverage", "--db-path", str(tmp_db_path)])

    out = capsys.readouterr().out
    assert "AAPL" in out and "0" in out


# ---------- Direktaufruf (Sprint 3B / Plan 1, Schnitt 1) ----------

def test_script_runs_when_invoked_directly():
    """CLAUDE.md dokumentiert `python setup/historical_loader.py --all`.

    Beim Direktaufruf legt Python nur setup/ auf sys.path, nicht das Projekt-Root —
    ohne Bootstrap scheitert `import config` mit ModuleNotFoundError. Dieser Test
    ruft das Skript als echten Subprozess auf, weil sich der Fehler in-process
    nicht reproduzieren laesst (pytest hat das Root laengst im Pfad).
    """
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(root / "setup" / "historical_loader.py"), "--help"],
        capture_output=True, text=True, cwd=str(root), timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "--full-sp500" in proc.stdout


def test_script_runs_as_module():
    """Die -m-Variante muss weiterhin funktionieren."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "setup.historical_loader", "--help"],
        capture_output=True, text=True, cwd=str(root), timeout=60,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"


# ---------- B-09: eine Session pro Lauf, nicht je Ticker ----------


def test_load_all_authenticates_once_for_all_tickers(tmp_path):
    """Capital.com limitiert den /session-Endpoint. Ein Provider je Ticker
    laeuft ab ~20 Tickern in HTTP 429 und verletzt ausserdem die Invariante
    'Ein Session-Object pro Run' (PROJECT_STATUS Abschnitt 4)."""
    import pandas as pd
    db_path = str(tmp_path / "t.db")
    df = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
         "Volume": [10]},
        index=pd.to_datetime(["2026-07-27"]),
    )
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = df
        from setup.historical_loader import load_all
        load_all(tickers=["AAPL", "MSFT", "NVDA", "AMZN"], db_path=db_path)

    assert MockCap.call_count == 1, (
        f"{MockCap.call_count} Provider fuer 4 Ticker — jeder baut eine eigene "
        f"Session auf und laeuft in das Rate-Limit"
    )


def test_load_all_still_fetches_every_ticker(tmp_path):
    """Die geteilte Session darf keinen Ticker verschlucken."""
    import pandas as pd
    db_path = str(tmp_path / "t.db")
    df = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
         "Volume": [10]},
        index=pd.to_datetime(["2026-07-27"]),
    )
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        MockCap.return_value.get_price_history.return_value = df
        from setup.historical_loader import load_all
        out = load_all(tickers=["AAPL", "MSFT", "NVDA"], db_path=db_path)

    fetched = [c.args[0] for c in
               MockCap.return_value.get_price_history.call_args_list]
    assert fetched == ["AAPL", "MSFT", "NVDA"]
    assert set(out) == {"AAPL", "MSFT", "NVDA"}


def test_load_ticker_history_reuses_a_passed_provider(tmp_path):
    """Wird ein Provider uebergeben, darf kein neuer gebaut werden."""
    import pandas as pd
    db_path = str(tmp_path / "t.db")
    provider = MagicMock()
    provider.get_price_history.return_value = pd.DataFrame(
        {"Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0],
         "Volume": [10]},
        index=pd.to_datetime(["2026-07-27"]),
    )
    with patch("setup.historical_loader.CapitalComProvider") as MockCap:
        from setup.historical_loader import load_ticker_history
        n = load_ticker_history("AAPL", db_path=db_path, provider=provider)

    assert n == 1
    MockCap.assert_not_called()
    provider.get_price_history.assert_called_once()


# ---------- Der laufende Tag ist nicht final ----------

def test_loader_never_writes_todays_provisional_bar(tmp_db_path, mocker):
    """price_history enthaelt ausschliesslich FINALE Tagesbars -- der Loader ist
    als manueller Backfill der zweite Schreiber und muss sich daran halten.

    Aufgefallen am 2026-08-08 (Samstag): `--universe` schrieb den vier
    Krypto-Tickern eine Bar von genau diesem Tag. Krypto handelt durchgehend,
    die UTC-Tagesbar schliesst erst um 00:00 UTC -- der Wert war also eine
    Teilbar. Genau die Vermischung von provisorisch und final war der
    Frozen-Bar-Bug, dessen Beseitigung der Preismodell-Umbau ist."""
    import pandas as pd
    from datetime import date as date_cls
    from src import db
    conn = db.connect(str(tmp_db_path)); db.init_schema(conn); conn.close()

    today = date_cls.today().isoformat()
    yesterday = (date_cls.today() - timedelta(days=1)).isoformat()
    prov = MagicMock()
    prov.get_price_history.return_value = pd.DataFrame(
        {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
         "Close": [1.0, 2.0], "Volume": [1, 2]},
        index=pd.to_datetime([yesterday, today]),
    )

    from setup.historical_loader import load_ticker_history
    load_ticker_history("BTC-USD", db_path=str(tmp_db_path), provider=prov)

    conn = db.connect(str(tmp_db_path))
    dates = [r["date"] for r in conn.execute(
        "SELECT date FROM price_history WHERE ticker='BTC-USD'").fetchall()]
    conn.close()
    assert today not in dates, "Der laufende Tag ist noch nicht final"
    assert yesterday in dates
