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


# ---------- check_earnings (Task 4, Spec 5.3) ----------

def test_check_earnings_none_when_no_earnings_date():
    """Rohstoffe/Krypto: earnings_in_days ist immer None (Spec 4.7) -- trivial erfuellt."""
    from src.signal_checks import check_earnings
    assert check_earnings("long", None, enforce=True) is None


def test_check_earnings_none_when_far_out():
    from src.signal_checks import check_earnings
    assert check_earnings("long", 5, enforce=True) is None


def test_check_earnings_fires_at_the_threshold():
    from src.signal_checks import check_earnings
    result = check_earnings("long", 2, enforce=True)
    assert result is not None
    assert result.rule == "earnings_imminent"
    assert result.enforced is True


def test_check_earnings_fires_when_imminent():
    from src.signal_checks import check_earnings
    result = check_earnings("short", 0, enforce=True)
    assert result is not None
    assert result.enforced is True


def test_check_earnings_respects_enforce_false():
    from src.signal_checks import check_earnings
    result = check_earnings("long", 1, enforce=False)
    assert result is not None
    assert result.enforced is False


def test_check_earnings_just_outside_threshold_does_not_fire():
    from src.signal_checks import check_earnings
    assert check_earnings("long", 3, enforce=True) is None


# ---------- Stop-Distanz (Spec G1-G5, 2026-08-21) --------------------------
# Anlass: alle 7 Outcomes waren sl_hit, 6 davon an TAG 1. Gemessen an
# intraday_range_pct liegt der Stop bei 0,39-0,78 einer typischen
# Tagesschwankung -- das Rauschen erreicht ihn, bevor die These sich bewaehrt.

from src.signal_checks import check_stop_distance, check_stop_budget_spent


def test_stop_inside_the_noise_band_is_flagged_but_never_enforced():
    """Spec G2: WEICH. Ein harter Check haette alle 14 Bestands-Signale
    verworfen -- das waere eine Abschaltung, keine Kalibrierung."""
    c = check_stop_distance(sl_pct=0.96, intraday_range_pct=2.12)

    assert c is not None
    assert c.enforced is False, "der Check darf NIE blockieren (G2)"
    assert "0.45" in c.detail or "0,45" in c.detail


def test_stop_outside_the_noise_band_is_silent():
    c = check_stop_distance(sl_pct=2.50, intraday_range_pct=2.12)
    assert c is None


def test_stop_distance_is_silent_without_an_intraday_range():
    assert check_stop_distance(sl_pct=1.0, intraday_range_pct=None) is None
    assert check_stop_distance(sl_pct=None, intraday_range_pct=2.0) is None


def test_stop_distance_uses_the_absolute_value():
    """sl_pct kommt in den Daten auch negativ vor (GC=F: -0.61)."""
    c = check_stop_distance(sl_pct=-0.61, intraday_range_pct=1.58)
    assert c is not None and c.enforced is False


# --- Teil B: Restabstand zum Stop, HART ---

def test_spent_stop_budget_is_rejected_long():
    """Der echte NVDA-Fall, der den Befund ausgeloest hat: um 16:10 stand der
    Kurs 0,11 % vor dem Stop und wurde mit 'R/R 26,2' freigegeben."""
    c = check_stop_budget_spent(
        entry_price=221.06, sl_price=218.94, current_price=219.19, enforce=True)

    assert c is not None
    assert c.enforced is True
    assert c.rule == "stop_too_close"


def test_spent_stop_budget_is_rejected_short():
    """Spec G5: richtungsneutral -- ein Vorzeichenfehler traefe nur eine Seite."""
    # Short: Stop LIEGT UEBER dem Entry. Budget 4.0, verbraucht 3.2 (80 %).
    c = check_stop_budget_spent(
        entry_price=100.0, sl_price=104.0, current_price=103.2, enforce=True)

    assert c is not None and c.enforced is True


def test_fresh_setup_passes_in_both_directions():
    assert check_stop_budget_spent(
        entry_price=100.0, sl_price=98.0, current_price=99.8, enforce=True) is None
    assert check_stop_budget_spent(
        entry_price=100.0, sl_price=102.0, current_price=100.2, enforce=True) is None


def test_stop_budget_boundary_is_not_rejected():
    """Genau auf der Schwelle (75 %) noch durchlassen -- erst darueber greifen."""
    # Budget 4.0, verbraucht 3.0 = exakt 0.75
    assert check_stop_budget_spent(
        entry_price=100.0, sl_price=96.0, current_price=97.0, enforce=True) is None


def test_stop_budget_is_silent_without_prices():
    assert check_stop_budget_spent(
        entry_price=None, sl_price=98.0, current_price=99.0, enforce=True) is None
    assert check_stop_budget_spent(
        entry_price=100.0, sl_price=100.0, current_price=99.0, enforce=True) is None
