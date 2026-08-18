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

import pytest

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


# ---------- Sprint 3B / Plan 2, Task 2: Ziel-Cron-Struktur (B.1) ----------

REMOVED_RUN_TYPES = ("midday", "evaluate", "position_check")


@pytest.mark.parametrize("removed", REMOVED_RUN_TYPES)
def test_workflow_has_no_removed_run_types(removed):
    """B.1: kein Cron, keine workflow_dispatch-Option, kein case-Zweig darf
    einen entfernten Run-Type noch nennen — sonst laeuft der Job in Exit 2."""
    assert removed not in WORKFLOW


def test_only_the_us_summer_slot_is_scheduled():
    """Stand 2026-08-18: der Workflow faehrt bewusst NUR die Sommerzeit, der
    EST-Slot ist nicht geplant (TODO im schedule-Block von analyze.yml).

    Der Lauf soll 40 min NACH der US-Eroeffnung liegen, also um 10:10
    America/New_York — 14:10 UTC unter EDT, 15:10 UTC unter EST. Ohne den
    EST-Slot laeuft trade_proposals im Winter gar nicht: der Zeitzonen-Filter
    im Schritt "Determine run_type" wirft den EDT-Slot dann weg (s.
    test_the_wrong_trade_proposals_slot_is_skipped). Das ist die bewusst
    gewaehlte Variante — der Lauf faellt aus, statt um 09:10 ET zu laufen,
    also 20 Minuten VOR der Eroeffnung. Genau so lief er frueher von Anfang
    November bis Mitte Maerz: der Opening-Gap-Check verglich zwei
    Pre-Open-Kurse und feuerte nie, die Re-Validierung arbeitete auf Kursen
    von vor dem Opening. Die Praemisse des Laufs fiel damit lautlos weg.

    ⚠️ Geprueft wird gegen die tatsaechlich geplanten cron-Zeilen, nicht per
    Substring gegen die ganze Datei: '10 15 * * 1-5' kommt im Kommentartext
    weiterhin vor, und ein Substring-Test waere allein dadurch gruen
    geblieben — er haette die Entfernung des Slots gar nicht bemerkt.

    Wird die Winterzeit nachgezogen, gehoert dieser Test mit umgestellt: dann
    muessen BEIDE Slots geplant sein, jeder mit eigenem case-Zweig."""
    crons = set(re.findall(r"- cron: '([^']+)'", WORKFLOW))
    assert "10 14 * * 1-5" in crons, "Slot fuer die US-Sommerzeit (EDT) fehlt"
    assert "10 15 * * 1-5" not in crons, (
        "Der EST-Slot ist derzeit bewusst NICHT geplant. Wenn er absichtlich "
        "wieder dazukommt, diesen Test und das TODO im schedule-Block "
        "mitziehen — und den case-Zweig nicht vergessen")
    assert 'T="trade_proposals"' in WORKFLOW


def test_the_wrong_trade_proposals_slot_is_skipped():
    """Cron ist UTC-fix, also feuern BEIDE Slots das ganze Jahr. Ohne Filter
    liefe der 16:10-Lauf zweimal taeglich — und einer davon zur falschen Zeit."""
    step = _step("Determine run_type")
    assert "America/New_York" in step, (
        "Der Slot-Filter muss an der US-Zeitzone haengen, nicht an Europe/Berlin: "
        "EU und USA schalten die Sommerzeit an verschiedenen Wochenenden um")
    assert '"-0400:14"' in step and '"-0500:15"' in step
    assert "if: steps.rt.outputs.type != ''" in _step("Run analysis"), (
        "Der uebersprungene Slot darf die Analyse nicht starten")


def test_every_cron_has_a_matching_case_branch():
    """Ein Cron ohne case-Zweig fiele still auf den close-Default zurueck."""
    crons = set(re.findall(r"- cron: '([^']+)'", WORKFLOW))
    cases = set(re.findall(r'"([0-9*/, -]+)"\)\s+T=', WORKFLOW))
    assert crons == cases, f"Cron/case-Mismatch: {crons ^ cases}"


def test_every_case_branch_and_dispatch_option_is_a_real_run_type():
    """Der Job stirbt sonst mit argparse Exit 2, und zwar erst zur Laufzeit.

    Genau dieser Bruch ist der Grund, warum analyze.yml und main.py:RUN_TYPES
    laut Spec 6.5 zusammen wechseln muessen. Da die Pipeline seit dem Umbau nie
    gelaufen ist, ist diese statische Pruefung das einzige Signal, das es gibt."""
    from main import RUN_TYPES
    opts = re.search(r"options: \[([^\]]+)\]", WORKFLOW).group(1)
    assert {o.strip() for o in opts.split(",")} == set(RUN_TYPES)
    for t in set(re.findall(r'T="([a-z_]+)"', WORKFLOW)):
        assert t in RUN_TYPES, f"case-Zweig '{t}' ist kein bekannter Run-Type"


def test_final_close_runs_daily_not_only_on_weekdays():
    """Der Samstagslauf holt Freitags Schlusskurs: openingHours schliesst
    freitags um 21:00 UTC, die Bar wird also erst nach Mitternacht final."""
    assert "'15 0 * * *'" in WORKFLOW
    assert 'T="final_close"' in WORKFLOW


def test_workflow_has_a_concurrency_lock():
    """Zwei Laeufe auf derselben DB gewinnen den Release-Upload nach
    Zufallsprinzip -- wer zuletzt hochlaedt, gewinnt."""
    assert "concurrency:" in WORKFLOW
    assert "cancel-in-progress: false" in WORKFLOW, (
        "Ein laufender Job schreibt bereits phasenweise in die DB -- ihn "
        "abzuschneiden waere schlimmer als zu warten")
