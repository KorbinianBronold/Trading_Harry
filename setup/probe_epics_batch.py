"""Read-only-Sonde: akzeptiert Capital.coms /markets-Endpunkt eine Liste von Epics?

Beantwortet die offene Frage aus der Spec (2026-08-11-analyse-pipeline-umbau-design,
Abschnitt 4.3.1). Bei ~500 Tickern entscheidet sie zwischen einem Sammelabruf
(~10 Calls) und 500 Einzel-Calls -- und damit darueber, ob die Laufzeit-Vorgabe
von 5-10 Minuten ohne Parallelisierung erreichbar ist.

Die Sonde SCHREIBT NICHTS: weder in die Datenbank noch bei Capital.com. Nur GETs.

Aufruf:
    python setup/probe_epics_batch.py --run-live

Ohne --run-live passiert NICHTS -- die Sonde bricht sofort ab, bevor sie auch
nur eine Zeile Netzwerkcode erreicht. Gleiches Prinzip wie --run-live bei den
pytest-Live-Tests (tests/conftest.py): ein Skript, das echte Fremdsysteme
anspricht, darf nicht durch einen blossen Aufruf ohne Flag loslaufen.

Exit-Codes:
    0  Sammelabruf funktioniert          -> Plan 2 nutzt Chunks
    1  Sammelabruf nicht verfuegbar      -> Plan 2 nutzt Einzel-Calls ohne Pause
    2  Teilantwort oder Laengengrenze    -> Ergebnis von Hand lesen
    3  --run-live fehlt                  -> Sonde nicht ausgefuehrt
"""
import argparse
import sys
from pathlib import Path

# Beim Direktaufruf (python setup/probe_epics_batch.py) liegt nur setup/ auf dem
# sys.path -- ohne diesen Bootstrap scheitert `import config` mit ModuleNotFoundError.
# Gleiche Ursache wie Bug B-07 bei historical_loader.py.
if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

import config
from src.providers.capital_provider import CapitalComProvider

# Bewusst MVP-Ticker mit bekannt gutem Epic-Mapping: ein Fehlschlag liegt dann
# eindeutig am Listen-Parameter und nicht an einem unbekannten Symbol.
SMALL_PROBE = ["AAPL", "MSFT", "NVDA"]


def _extract_markets(payload: dict) -> list[dict]:
    """Holt die Instrumentenliste aus der Antwort.

    Capital.com nennt sie je nach Abfrageform `marketDetails` (Epic-Liste) oder
    `markets` (Volltextsuche) -- beide werden akzeptiert, damit die Sonde nicht
    an einer Namensfrage scheitert.
    """
    for key in ("marketDetails", "markets"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _bid_of(market: dict) -> float | None:
    """Liest den Bid-Kurs aus einem Markt-Dict, egal wie tief er verschachtelt ist."""
    snapshot = market.get("snapshot") or {}
    return snapshot.get("bid")


def _offer_of(market: dict) -> float | None:
    """Liest den Offer-(Ask-)Kurs, falls vorhanden.

    Beantwortet die offene Frage aus Spec 4.3.1: liefert der Sammelabruf den
    Spread kostenlos mit, oder braucht 'spread-bereinigtes R/R' (Spec § 17)
    einen zusaetzlichen Call?"""
    snapshot = market.get("snapshot") or {}
    return snapshot.get("offer")


def _epic_of(market: dict) -> str | None:
    """Liest den Epic aus einem Markt-Dict."""
    instrument = market.get("instrument") or {}
    return instrument.get("epic") or market.get("epic")


def _try_batch(provider: CapitalComProvider, epics: list[str]) -> tuple[int, int]:
    """Fragt `epics` als kommaseparierte Liste ab.

    Gibt (HTTP-Status, Zahl der zurueckgelieferten Instrumente) zurueck.
    """
    resp = requests.get(
        f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets",
        headers=provider._headers(),
        params={"epics": ",".join(epics)},
        timeout=30,
    )
    if not resp.ok:
        return resp.status_code, 0
    return resp.status_code, len(_extract_markets(resp.json()))


def main() -> int:
    """Prueft Einzelabruf, kleinen Sammelabruf und -- falls der klappt -- die
    Laengengrenze anhand des vollen MVP-Universums."""
    provider = CapitalComProvider()

    epics = [provider._map(t) for t in SMALL_PROBE]
    unmapped = [t for t, e in zip(SMALL_PROBE, epics) if t == e]
    print(f"Epics: {dict(zip(SMALL_PROBE, epics))}")
    if unmapped:
        print(f"  Hinweis: ohne Mapping in TICKER_MAP: {unmapped}")

    # --- Referenz: der heute genutzte Einzelabruf --------------------------
    single = requests.get(
        f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets/{epics[0]}",
        headers=provider._headers(),
        timeout=30,
    )
    print(f"\n[A] Einzelabruf /markets/{epics[0]}: HTTP {single.status_code}")
    if single.ok:
        print(f"    bid = {single.json().get('snapshot', {}).get('bid')}")
    else:
        print(f"    Body: {single.text[:300]}")
        print("\nABBRUCH: schon der Einzelabruf scheitert. Zugangsdaten pruefen.")
        return 2

    # --- Kandidat: kommaseparierte Liste ----------------------------------
    joined = ",".join(epics)
    resp = requests.get(
        f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets",
        headers=provider._headers(),
        params={"epics": joined},
        timeout=30,
    )
    print(f"\n[B] Sammelabruf /markets?epics={joined}: HTTP {resp.status_code}")
    if not resp.ok:
        print(f"    Body: {resp.text[:400]}")
        print("\nERGEBNIS: Sammelabruf NICHT verfuegbar.")
        print("  -> Plan 2 nutzt Einzel-Calls OHNE feste Pause (unter 600/min),")
        print("     mit der 429-Notbremse aus Spec 4.3.3.")
        return 1

    payload = resp.json()
    markets = _extract_markets(payload)
    print(f"    Antwort-Schluessel: {list(payload.keys())}")
    print(f"    Instrumente: {len(markets)} (angefragt: {len(epics)})")
    for m in markets:
        print(f"      {_epic_of(m)}: bid={_bid_of(m)} offer={_offer_of(m)}")

    # --- offene Frage aus Spec 4.3.1: liefert der Sammelabruf ein offer-Feld? --
    has_offer = bool(markets) and all(_offer_of(m) is not None for m in markets)
    print(f"\n[B'] offer-Feld im Sammelabruf (Spec 4.3.1, letzter Absatz): "
          f"{'JA, in allen Snapshots vorhanden' if has_offer else 'NEIN -- fehlt in mindestens einem Snapshot'}")

    if len(markets) != len(epics):
        print("\nERGEBNIS: Teilantwort -- Ursache von Hand klaeren, bevor Plan 2")
        print("  darauf aufbaut.")
        return 2

    # --- Folgefrage: wie lang darf die Liste sein? ------------------------
    # Ohne diese Antwort muesste Plan 2 die Chunk-Groesse raten.
    print("\n[C] Laengengrenze, gemessen am MVP-Universum:")
    all_epics = [provider._map(t) for t in config.SP500_MVP_TICKERS]
    largest_ok = len(epics)
    for size in (10, 20):
        if size > len(all_epics):
            break
        status, count = _try_batch(provider, all_epics[:size])
        verdict = "ok" if count == size else f"nur {count} zurueck"
        print(f"    {size:>3} Epics: HTTP {status}, {verdict}")
        if status == 200 and count == size:
            largest_ok = size
        else:
            break

    print(f"\nERGEBNIS: Sammelabruf FUNKTIONIERT, bestaetigt bis {largest_ok} Epics.")
    print("  -> Plan 2 nutzt Chunks. Chunk-Groesse konservativ auf den")
    print(f"     bestaetigten Wert ({largest_ok}) setzen, nicht darueber raten.")
    return 0


def _parse_args() -> argparse.Namespace:
    """Parst --run-live. Das ist das einzige Argument -- ohne Flag macht die
    Sonde keinen einzigen Netzwerk-Call (Sicherheitsnetz, s. Modul-Docstring)."""
    parser = argparse.ArgumentParser(
        description="Read-only-Sonde: akzeptiert Capital.coms /markets-Endpunkt "
                     "eine Liste von Epics?",
    )
    parser.add_argument(
        "--run-live", action="store_true",
        help="Fuehrt die Sonde wirklich gegen die Capital.com-Demo-API aus "
             "(nur lesende GETs). Ohne dieses Flag passiert nichts.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if not args.run_live:
        print("Sonde macht per Default keine echten API-Calls.")
        print("Ausfuehren mit: python setup/probe_epics_batch.py --run-live")
        raise SystemExit(3)
    raise SystemExit(main())
