"""Tests fuer .github/workflows/bootstrap-db.yml.

Hintergrund: die CI-Datenbank (Release-Asset `db-latest`) wurde nie mit echter
Historie bestueckt — sie sammelte nur die Bars ein, die die Laeufe selbst
schrieben. Am 2026-08-04 standen dort 19 Bars je Aktie, eine unter
MIN_BARS_RSI=20. Ergebnis: drei technisch gruene Laeufe, die 18 von 20 Tickern
uebersprangen und keine einzige Prediction erzeugten.

Dieser Workflow ist der einmalige Bootstrap dagegen. Er laeuft ausschliesslich
von Hand — ein versehentlich scharf geschalteter Cron wuerde 46 Ticker x 1000
Bars gegen Capital.com ziehen, ohne dass jemand hinsieht.
"""
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[2]
            / ".github" / "workflows" / "bootstrap-db.yml").read_text()
ANALYZE = (Path(__file__).resolve().parents[2]
           / ".github" / "workflows" / "analyze.yml").read_text()


def test_bootstrap_is_manual_only():
    """Kein `schedule:`. Der Bootstrap ist eine bewusste Einzelaktion; als Cron
    wuerde er die Historie taeglich sinnlos neu ziehen."""
    assert "workflow_dispatch:" in WORKFLOW
    assert "schedule:" not in WORKFLOW


def test_bootstrap_loads_the_full_universe():
    """`--all` deckt nur die 20 Aktien ab. Rohstoffe, Krypto und die
    Sub-Sektor-ETFs brauchen genauso Historie, sonst bleibt die Luecke halb
    geschlossen — und `final_close` schreibt sie ohnehin alle fort."""
    assert "--universe" in WORKFLOW
    assert "historical_loader" in WORKFLOW


def test_bootstrap_shares_the_analyze_concurrency_group():
    """Beide Workflows schreiben dasselbe Release-Asset. Ohne gemeinsame Gruppe
    koennte ein Bootstrap mitten in einen Pipelinelauf laufen und dessen
    hochgeladene DB ueberschreiben — der Lauf waere spurlos weg."""
    import re
    group_bootstrap = re.search(r"group: ([^\n]+)", WORKFLOW).group(1).strip()
    group_analyze = re.search(r"group: ([^\n]+)", ANALYZE).group(1).strip()
    assert group_bootstrap == group_analyze
    assert "cancel-in-progress: false" in WORKFLOW


def test_bootstrap_uploads_with_clobber():
    """Ohne --clobber schlaegt der Upload fehl, weil das Asset schon existiert —
    der Bootstrap waere dann umsonst gelaufen."""
    assert "--clobber" in WORKFLOW


def test_bootstrap_downloads_the_existing_db_first():
    """Die CI-Linie bleibt erhalten: skipped_tickers, cost_tracking und
    bestehende Predictions duerfen der Bestueckung nicht zum Opfer fallen.
    Der Loader ergaenzt Bars (INSERT OR IGNORE), er ersetzt keine Datenbank."""
    assert "gh release download db-latest" in WORKFLOW


def test_bootstrap_reports_coverage_afterwards():
    """Ein Bootstrap, dessen Ergebnis niemand sieht, ist so blind wie die Laeufe,
    die er reparieren soll. Der Workflow gibt die Bar-Abdeckung aus."""
    assert "--report-coverage" in WORKFLOW
