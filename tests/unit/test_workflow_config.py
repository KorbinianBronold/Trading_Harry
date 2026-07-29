"""Tests fuer .github/workflows/analyze.yml.

Hintergrund (B-10): der Upload der tracking.db nach Release `db-latest` hing an
`if: success()`. Da ein fehlgeschlagener Mailversand den Analyse-Schritt mit
Exit 1 beendet, wurde die DB dann nicht hochgeladen — die komplette Arbeit eines
Laufs (Trends, Marktkontext, Predictions, Sektor-Mapping, Kosten) ging verloren,
obwohl sie bereits committet war.

Die DB-Persistenz ueber GitHub Releases ist eine dokumentierte Architektur-
Entscheidung (PROJECT_STATUS Abschnitt 4); sie darf nicht an der Zustellung
einer E-Mail haengen."""
import re
from pathlib import Path

WORKFLOW = (Path(__file__).resolve().parents[2]
            / ".github" / "workflows" / "analyze.yml").read_text()


def _step(name_fragment: str) -> str:
    """Gibt den YAML-Block eines Steps ab '- name: ...' bis zum naechsten Step."""
    pattern = rf"- name: [^\n]*{re.escape(name_fragment)}[^\n]*\n(?:(?!\n      - name:).)*"
    m = re.search(pattern, WORKFLOW, re.DOTALL)
    assert m, f"Step mit '{name_fragment}' nicht in analyze.yml gefunden"
    return m.group(0)


def test_db_upload_runs_even_when_the_analysis_step_fails():
    """B-10: sonst kostet ein Mailausfall den gesamten Lauf."""
    step = _step("Upload tracking.db")
    assert "if: always()" in step, (
        "Der DB-Upload haengt nicht an always() — bei Exit 1 im Analyse-Schritt "
        "geht der komplette Lauf verloren"
    )
    assert "if: success()" not in step


def test_db_upload_still_uses_clobber():
    """Ohne --clobber schlaegt der Upload beim zweiten Lauf des Tages fehl."""
    assert "--clobber" in _step("Upload tracking.db")


def test_weekly_snapshot_stays_on_success():
    """Der Wochen-Snapshot ist ein Archiv-Stand und soll bewusst NUR bei einem
    sauberen Lauf entstehen — anders als der laufende db-latest-Upload."""
    step = _step("Weekly DB snapshot")
    assert "success()" in step


def test_analysis_step_is_not_silenced():
    """Der Analyse-Schritt darf keinen continue-on-error bekommen: ein echter
    Fehler muss den Job weiterhin rot faerben."""
    step = _step("Run analysis")
    assert "continue-on-error" not in step
