"""Das deterministische technische Signal: Richtung plus zaehlbare Staerke.

Drei richtungsgebende Teilindikatoren stimmen ab (RSI mit Trend, MACD-Histogramm,
SMA-Trend); die Mehrheit bestimmt die Richtung. ADX moduliert die Staerke, ohne
die Richtung zu filtern.

Kein Claude-Call, kein Netz, keine Datenbank -- eine reine Funktion ueber das
Snapshot-Dict aus Phase 1. Damit ist das Signal reproduzierbar und
tabellengetrieben testbar.

Die drei Ablesungen sind bewusste Entscheidungen, keine Herleitungen -- welche
davon besser predictet, beantwortet Sprint 3D aus der Outcome-Historie:
  * RSI wird als MOMENTUM gelesen (ueber 50 und steigend = bullish), nicht als
    Mean-Reversion (ueberverkauft = Rebound). Gewaehlt, weil es zum bestehenden
    Guardrail momentum >= MOMENTUM_LONG_MIN passt.
  * MACD ueber das Vorzeichen des Histogramms, nicht ueber die Kreuzung. Eine
    Kreuzung feuert nur an zwei Bars und ist als Dauersignal wertlos.
  * Fehlt SMA200, stimmt der SMA-Teilindikator neutral -- nicht 'fehlend'.
"""
from dataclasses import dataclass

import config

_LONG, _SHORT, _NEUTRAL = "long", "short", "neutral"


@dataclass(frozen=True)
class TechnicalSignal:
    """Ergebnis der Signalrechnung fuer einen Ticker."""

    direction: str
    agreement: int
    adx_band: str
    strength: int


def _vote_rsi(td: dict) -> str:
    """RSI ueber/unter der Mittellinie, bestaetigt durch seinen Trend."""
    rsi, trend = td.get("rsi_14"), td.get("rsi_trend")
    if rsi is None:
        return _NEUTRAL
    if rsi > config.RSI_MIDLINE and trend == "rising":
        return _LONG
    if rsi < config.RSI_MIDLINE and trend == "falling":
        return _SHORT
    return _NEUTRAL


def _vote_macd(td: dict) -> str:
    """Vorzeichen des MACD-Histogramms (Linie minus Signallinie)."""
    line, signal = td.get("macd_line"), td.get("macd_signal_line")
    if line is None or signal is None:
        return _NEUTRAL
    if line > signal:
        return _LONG
    if line < signal:
        return _SHORT
    return _NEUTRAL


def _vote_sma(td: dict) -> str:
    """Kurs ueber SMA50 UND Kurs ueber SMA200 (beides als eigene Distanz in
    Prozent) -- kein Vergleich von SMA50 gegen SMA200, also kein Golden-/
    Death-Cross-Signal.

    Fehlt SMA200 -- unter 200 Bars Historie --, stimmt dieser Teilindikator
    neutral. Die Richtung entsteht dann aus den beiden anderen, und die
    niedrigere agreement-Zahl macht die duennere Grundlage sichtbar.
    """
    d50, d200 = td.get("above_sma50"), td.get("above_sma200")
    if d50 is None or d200 is None:
        return _NEUTRAL
    if d50 > 0 and d200 > 0:
        return _LONG
    if d50 < 0 and d200 < 0:
        return _SHORT
    return _NEUTRAL


def _adx_band(td: dict) -> str:
    """weak | normal | strong. Ein fehlender ADX gilt als normal -- er soll die
    Staerke weder deckeln noch anheben, wenn er unbekannt ist."""
    adx = td.get("adx_14")
    if adx is None:
        return "normal"
    if adx <= config.ADX_WEAK_BELOW:
        return "weak"
    if adx >= config.ADX_STRONG_ABOVE:
        return "strong"
    return "normal"


def compute(td: dict) -> TechnicalSignal:
    """Leitet Richtung und Staerke aus einem Phase-1-Snapshot ab."""
    votes = [_vote_rsi(td), _vote_macd(td), _vote_sma(td)]
    longs, shorts = votes.count(_LONG), votes.count(_SHORT)

    if longs >= 2:
        direction, agreement = _LONG, longs
    elif shorts >= 2:
        direction, agreement = _SHORT, shorts
    else:
        return TechnicalSignal(
            direction=_NEUTRAL, agreement=max(longs, shorts),
            adx_band=_adx_band(td), strength=0,
        )

    band = _adx_band(td)
    strength = agreement
    if band == "strong":
        strength = min(4, strength + 1)
    elif band == "weak":
        strength = 1

    return TechnicalSignal(
        direction=direction, agreement=agreement,
        adx_band=band, strength=strength,
    )
