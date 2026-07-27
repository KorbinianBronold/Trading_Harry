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
