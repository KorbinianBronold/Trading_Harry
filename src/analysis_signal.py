"""Analysis-Strength-Signal (Spec 5.2): das zweite der zwei Ranking-Signale.

Zaehlt, wie viele der acht Score-Dimensionen belegte, richtungsuebereinstimmende
Evidenz tragen -- das Gegenstueck zum deterministischen Technik-Signal aus
technical_signal.py. Reine Funktion ueber das Analyse-Dict aus Phase 3, kein
Netz, keine Datenbank.

⚠️ ZWEI POLARITAETEN, nicht eine -- und das ist der Kern dieses Moduls:

  * `momentum` ist ABSOLUT abgelesen: eine Kursbewegung, hoch = bullisch,
    tief = baerisch. Ein guter Short hat hier einen NIEDRIGEN Wert.
  * die anderen SIEBEN sind TRADE-RELATIV. Die aktiven v2-Prompts legen das
    woertlich fest (prompts/deep_analysis_v2.txt, prompts/commodities_crypto_v2.txt,
    Abschnitt zur Polaritaet): "HIGHER IS ALWAYS BETTER FOR THE PROPOSED TRADE,
    in the direction you chose. There is no dimension where a high number is a
    warning." -- ausbuchstabiert an `valuation`: 10 heisst "guenstig fuer einen
    Long" UND "ueberdehnt fuer einen Short". Ein guter Short hat hier also
    HOHE Werte.

Fuer `long` fallen beide Konventionen zusammen, fuer `short` sind sie
gegenlaeufig. Wer die absolute Momentum-Schwelle auf alle acht Dimensionen
anwendet, dreht jeden Short um: ein gut belegter Short (momentum 2.0, die
uebrigen sieben auf 9.0) zaehlte 1, ein Short, gegen den alle acht Dimensionen
sprechen (alle auf 2.0), zaehlte 8. Genau das war der C1-Befund aus dem
Plan-3b-Abschluss-Review.

Warum `momentum` die Ausnahme BLEIBT und nicht mitgedreht wird: an seiner
absoluten Lesart haengen zwei bestehende harte Regeln -- die Guardrails
(src/guardrails.py:84-93 verlangen `momentum <= MOMENTUM_SHORT_MAX` fuer jeden
Short) und dieselbe Regel noch einmal woertlich in den v2-Prompts selbst. Der
Satz "EVERY one of the eight" im Polaritaets-Absatz der Prompts widerspricht
dem; das ist eine bekannte, bewusst stehengelassene Inkonsistenz in der
Prompt-Ebene (Regel 10: Prompts werden nie ueberschrieben). Der Code loest sie
auf der Seite auf, an der die Guardrails haengen.

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


def _counts_for_trade(dim: str, value: float, direction: str) -> bool:
    """Liegt `value` auf der Seite, die FUER diesen Trade spricht?

    Die Fallunterscheidung ist die im Modul-Docstring hergeleitete: `momentum`
    absolut (long: hoch, short: tief), die uebrigen sieben trade-relativ (immer
    hoch, unabhaengig von der Richtung -- so schreiben es die aktiven v2-Prompts
    fest). Beide Zweige nutzen dieselben, bereits existierenden Schwellen aus
    config.py -- Spec 5.2 verbietet ausdruecklich neue Konstanten dafuer."""
    if dim == "momentum":
        if direction == "long":
            return value >= config.MOMENTUM_LONG_MIN
        return value <= config.MOMENTUM_SHORT_MAX
    return value >= config.MOMENTUM_LONG_MIN


def analysis_strength(analysis: dict) -> int:
    """Spec 5.2: zaehlt Dimensionen mit evidence_quality != 'thin', >= 2 Belegen
    und einem Wert, der FUER den vorgeschlagenen Trade spricht.

    ⚠️ 'Fuer den Trade' heisst nicht in beiden Konventionen dasselbe -- siehe
    Modul-Docstring: `momentum` wird gegen die richtungsabhaengigen Schwellen
    geprueft (long >= MOMENTUM_LONG_MIN, short <= MOMENTUM_SHORT_MAX), die
    anderen sieben Dimensionen unabhaengig von der Richtung gegen
    MOMENTUM_LONG_MIN, weil die v2-Prompts sie bereits trade-relativ erheben.
    Ohne diese Trennung zaehlt die Funktion bei jedem Short das Gegenteil.

    direction='none' oder eine unbekannte Richtung liefert 0: ein Ranking ohne
    Richtung ist sinnlos."""
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
        if _counts_for_trade(dim, value, direction):
            n += 1
    return n
