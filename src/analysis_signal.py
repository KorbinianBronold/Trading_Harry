"""Analysis-Strength-Signal (Spec 5.2): das zweite der zwei Ranking-Signale.

Zaehlt, wie viele der acht Score-Dimensionen belegte, richtungsuebereinstimmende
Evidenz tragen -- das Gegenstueck zum deterministischen Technik-Signal aus
technical_signal.py. Reine Funktion ueber das Analyse-Dict aus Phase 3, kein
Netz, keine Datenbank.

Heisst bewusst NICHT news_strength: der Name ist seit Plan 2 als Scan-Wert aus
Phase 2 (0-3) vergeben (broad_scan.py, cutoff_log). Zwei Skalen unter einem
Namen wuerden eine Spalte erzeugen, deren Bedeutung von der Tabelle abhaengt --
und die 3D-Frage 'sagt der billige Scan die teure Analyse vorher?' unformulierbar
machen (Spec 20.5 #1)."""
import config

DIMENSIONS = (
    "market_environment", "company_quality", "valuation", "momentum",
    "risk", "sector_trend", "catalyst", "policy_risk",
)


def analysis_strength(analysis: dict) -> int:
    """Spec 5.2: zaehlt Dimensionen mit evidence_quality != 'thin', >= 2 Belegen
    und einem Wert auf der Trade-Richtung-Seite der bestehenden Momentum-
    Schwellen (config.MOMENTUM_LONG_MIN / MOMENTUM_SHORT_MAX -- keine neuen
    Konstanten). direction='none' oder eine unbekannte Richtung liefert 0: ein
    Ranking ohne Richtung ist sinnlos."""
    direction = analysis.get("direction")
    if direction not in ("long", "short"):
        return 0
    scores = analysis.get("scores", {})
    n = 0
    for dim in DIMENSIONS:
        sd = scores.get(dim)
        if not sd:
            continue
        if sd.get("evidence_quality") == "thin":
            continue
        if len(sd.get("evidence") or []) < 2:
            continue
        value = sd.get("value")
        if value is None:
            continue
        if direction == "long" and value >= config.MOMENTUM_LONG_MIN:
            n += 1
        elif direction == "short" and value <= config.MOMENTUM_SHORT_MAX:
            n += 1
    return n
