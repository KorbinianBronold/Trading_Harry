"""Gemeinsame Hilfen fuer die Live-Tests.

Die Ergebniszeile jedes Live-Tests soll ohne Log-Wuehlerei sichtbar sein: im
Terminal per print, unter GitHub Actions zusaetzlich in der Job-Zusammenfassung."""
import logging
import os

import pytest

log = logging.getLogger("shares_future.live")


@pytest.fixture
def report():
    """Gibt eine Funktion zurueck, die eine Ergebniszeile ins Log, nach stdout
    und (unter Actions) in GITHUB_STEP_SUMMARY schreibt."""
    def _report(line: str) -> None:
        log.info(line)
        print(line)
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    return _report


@pytest.fixture
def key_source() -> str:
    """Woher die Zugangsdaten in diesem Lauf stammen — die lokale .env und das
    GitHub-Secret sind unabhaengige Werte und koennen einzeln ablaufen."""
    return "GitHub Secret" if os.environ.get("GITHUB_ACTIONS") else ".env (lokal)"
