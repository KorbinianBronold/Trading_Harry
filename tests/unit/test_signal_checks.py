"""Tests fuer src/signal_checks.py — die rechnerischen B.3-Checks.

Bewusst ohne jedes Mocking: das Modul spricht weder mit Claude noch mit dem Netz.
Faellt hier etwas um, liegt es an der Logik und nicht an einer Fremd-API."""
import pytest

from src import db


def _seed_sector(conn, ticker="AAPL", sector="Technology Hardware", etf="XLK"):
    """Legt einen Sub-Sektor an und ordnet ihm den Ticker zu."""
    db.init_schema(conn)
    sid = conn.execute("SELECT id FROM sectors WHERE name=?", (sector,)).fetchone()["id"]
    conn.execute("INSERT OR REPLACE INTO ticker_sectors (ticker, sector_id) VALUES (?, ?)",
                 (ticker, sid))
    conn.commit()
    return sid


def _bar(conn, ticker, date, close):
    conn.execute(
        "INSERT OR REPLACE INTO price_history (ticker, date, close) VALUES (?, ?, ?)",
        (ticker, date, close))
    conn.commit()


def test_daily_change_pct_uses_the_two_most_recent_bars(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_ignores_bars_after_the_date(in_memory_db):
    """Sonst misst der 16:10-Lauf gegen einen Kurs, den es noch nicht gab."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    _bar(in_memory_db, "AAPL", "2026-07-31", 200.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_daily_change_pct_is_none_with_a_single_bar(in_memory_db):
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-30", 102.0)
    from src.signal_checks import daily_change_pct
    assert daily_change_pct(in_memory_db, "AAPL", "2026-07-30") is None


def test_relative_strength_is_ticker_minus_sector_etf(in_memory_db):
    """+3% Ticker gegen +1% ETF ergibt +2 Punkte relative Staerke."""
    _seed_sector(in_memory_db)
    _bar(in_memory_db, "AAPL", "2026-07-29", 100.0)
    _bar(in_memory_db, "AAPL", "2026-07-30", 103.0)
    _bar(in_memory_db, "XLK", "2026-07-29", 100.0)
    _bar(in_memory_db, "XLK", "2026-07-30", 101.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(
        in_memory_db, "AAPL", "2026-07-30") == pytest.approx(2.0)


def test_relative_strength_is_none_without_sector_mapping(in_memory_db):
    """Grundregel: lieber kein Wert als ein Wert gegen ein fremdes Instrument."""
    db.init_schema(in_memory_db)
    _bar(in_memory_db, "GOOGL", "2026-07-29", 100.0)
    _bar(in_memory_db, "GOOGL", "2026-07-30", 103.0)
    from src.signal_checks import compute_relative_strength
    assert compute_relative_strength(in_memory_db, "GOOGL", "2026-07-30") is None


def test_cluster_check_is_silent_below_the_threshold():
    from src.signal_checks import check_cluster
    assert check_cluster("Semiconductors", 2) is None


def test_cluster_check_warns_at_the_threshold():
    from src.signal_checks import check_cluster
    r = check_cluster("Semiconductors", 3)
    assert r is not None
    assert r.rule == "sector_cluster"
    assert r.enforced is False, "Klumpenrisiko ist immer nur eine Warnung"
    assert "Semiconductors" in r.detail


# ---------- VIX (B.3, hartes Filterkriterium) ----------

def test_vix_below_thresholds_is_silent():
    from src.signal_checks import check_vix
    assert check_vix("long", "medium", 18.0, enforce=True) is None


def test_vix_above_35_blocks_new_longs():
    from src.signal_checks import check_vix
    r = check_vix("long", "high", 40.0, enforce=True)
    assert r is not None and r.rule == "vix_no_new_longs" and r.enforced is True


def test_vix_above_35_leaves_shorts_alone():
    """Die Regel lautet 'keine neuen LONG-Signale' — Shorts sind nicht gemeint."""
    from src.signal_checks import check_vix
    assert check_vix("short", "high", 40.0, enforce=True) is None


def test_vix_between_25_and_35_blocks_only_low_confidence():
    from src.signal_checks import check_vix
    assert check_vix("long", "high", 28.0, enforce=True) is None
    r = check_vix("long", "medium", 28.0, enforce=True)
    assert r is not None and r.rule == "vix_high_confidence_only"


def test_vix_confidence_filter_stays_cumulative_above_35():
    """Regression: der Filter darf mit steigender Volatilitaet nur strenger werden,
    nie lockerer. Ein Short mit confidence='medium' war bei VIX 28 blockiert —
    bei VIX 40 muss das Confidence-Band weiterhin greifen, nicht plötzlich
    verschwinden, nur weil die Long-Schwelle zusaetzlich ueberschritten ist."""
    from src.signal_checks import check_vix
    r = check_vix("short", "medium", 40.0, enforce=True)
    assert r is not None and r.rule == "vix_high_confidence_only"


def test_vix_is_silent_when_the_level_is_unknown():
    """Phase 0b darf ausfallen — dann filtert der VIX-Check eben nicht."""
    from src.signal_checks import check_vix
    assert check_vix("long", "medium", None, enforce=True) is None


# ---------- E4: derselbe Check, zwei Runs ----------

def test_same_check_blocks_only_when_enforce_is_true():
    """Entscheidung E4 in einem Test: pre_market erhebt und warnt,
    trade_proposals setzt durch."""
    from src.signal_checks import check_vix
    weich = check_vix("long", "medium", 40.0, enforce=False)
    hart = check_vix("long", "medium", 40.0, enforce=True)
    assert weich is not None and hart is not None
    assert weich.rule == hart.rule, "gleicher Befund"
    assert weich.enforced is False and hart.enforced is True


# ---------- D9: Sektor-Momentum (B.3.1) ----------

def test_d9_silent_when_both_signals_support_the_direction():
    from src.signal_checks import check_sector_momentum
    assert check_sector_momentum("long", 1.2, 0.8, enforce=True) is None


def test_d9_silent_when_no_signal_exists():
    """B.3.1 woertlich: 'keines vorhanden -> kein Check, KEIN Log-Eintrag'."""
    from src.signal_checks import check_sector_momentum
    assert check_sector_momentum("long", None, None, enforce=True) is None


def test_d9_hard_only_when_both_agree_and_strict_is_on(monkeypatch):
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, -0.9, enforce=True)
    assert r is not None and r.rule == "sector_momentum" and r.enforced is True


def test_d9_stays_soft_while_strict_is_off(monkeypatch):
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", False)
    r = check_sector_momentum("long", -1.5, -0.9, enforce=True)
    assert r is not None and r.enforced is False


def test_d9_conflicting_signals_stay_soft_even_with_strict(monkeypatch):
    """Widerspruechliche Signale duerfen NIE hart blocken — auch nicht mit STRICT."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, +0.9, enforce=True)
    assert r is not None and r.rule == "sector_momentum_conflict"
    assert r.enforced is False


def test_d9_single_signal_stays_soft_even_with_strict(monkeypatch):
    """Der MVP-Normalfall: 19 von 21 Sub-Sektoren haben nur das ETF-Signal."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    r = check_sector_momentum("long", -1.5, None, enforce=True)
    assert r is not None and r.rule == "sector_momentum_partial"
    assert r.enforced is False


def test_d9_compares_direction_not_magnitude(monkeypatch):
    """Live-Befund 2026-07-28: Retail lag bei +2,89% ETF gegen +1,17% DB.
    Faktor ~2,5 bei gleichem Vorzeichen ist KEIN Widerspruch."""
    import config
    from src.signal_checks import check_sector_momentum
    monkeypatch.setattr(config, "SECTOR_GUARDRAIL_STRICT", True)
    assert check_sector_momentum("long", 2.89, 1.17, enforce=True) is None


def test_blocks_is_true_only_for_enforced_results():
    from src.signal_checks import CheckResult, blocks
    assert blocks([CheckResult("a", "x", enforced=False)]) is False
    assert blocks([CheckResult("a", "x", enforced=False),
                   CheckResult("b", "y", enforced=True)]) is True
    assert blocks([]) is False


# ---------- recompute_rr_ratio (Task 13): TP/SL bleiben absolut ----------

def test_recompute_rr_ratio_long():
    from src.signal_checks import recompute_rr_ratio
    # Einstieg 100, TP 106, SL 98 -> Chance 6, Risiko 2 -> 3.0
    assert recompute_rr_ratio(100.0, 106.0, 98.0, "long") == pytest.approx(3.0)


def test_recompute_rr_ratio_short():
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(100.0, 94.0, 102.0, "short") == pytest.approx(3.0)


def test_recompute_rr_ratio_shrinks_when_the_entry_drifted():
    """Nach dem Opening naeher am TP: dasselbe Ziel, schlechteres Verhaeltnis."""
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(104.0, 106.0, 98.0, "long") == pytest.approx(1/3)


def test_recompute_rr_ratio_is_none_past_the_stop():
    """Kurs schon durch den SL — kein sinnvolles Verhaeltnis mehr."""
    from src.signal_checks import recompute_rr_ratio
    assert recompute_rr_ratio(97.0, 106.0, 98.0, "long") is None


# ---------- check_opening_gap (Task 15, B.3): Luecke seit dem Morgen-Einstieg ----------

def test_opening_gap_is_silent_below_the_threshold():
    from src.signal_checks import check_opening_gap
    assert check_opening_gap(100.0, 101.0) is None


def test_opening_gap_warns_on_a_large_move_up():
    from src.signal_checks import check_opening_gap
    r = check_opening_gap(100.0, 103.0)
    assert r is not None and r.rule == "opening_gap"
    assert r.enforced is False, "ein Gap ist eine Information, kein Urteil"
    assert "+3.0" in r.detail


def test_opening_gap_warns_on_a_large_move_down():
    from src.signal_checks import check_opening_gap
    r = check_opening_gap(100.0, 97.0)
    assert r is not None and "-3.0" in r.detail


def test_opening_gap_is_silent_without_data():
    from src.signal_checks import check_opening_gap
    assert check_opening_gap(None, 103.0) is None
    assert check_opening_gap(100.0, None) is None
    assert check_opening_gap(0.0, 103.0) is None
