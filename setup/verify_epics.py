"""Verify-Tool: löst die Capital.com-Epics für alle Sub-Sektor-ETFs und den VIX auf.

Kein Pipeline-Code — wird ausschliesslich manuell aufgerufen und nie automatisch aus
main.py. Zweck: bevor der Sektor-ETF-Momentum-Check (Sprint 3B, Spec B.3) gebaut wird,
muss feststehen, unter welchem Epic Capital.com die Instrumente tatsächlich führt und
ob sie auf dem Demo-Konto überhaupt handelbar sind.

Ausgabe: eine Zeile je Symbol mit Status (exakt / ABWEICHEND / KEIN TREFFER) plus ein
kopierfertiger TICKER_MAP-Block für alle Symbole, deren Epic vom Symbol abweicht.

Aufruf (beide Varianten funktionieren):
    python -m setup.verify_epics
    python setup/verify_epics.py
"""
import argparse
import logging
import sys
from pathlib import Path

# Direktaufruf ("python setup/verify_epics.py") legt nur setup/ auf sys.path — ohne
# diesen Bootstrap schlägt "import config" fehl.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.providers.capital_provider import CapitalComProvider  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
log = logging.getLogger("shares_future.verify_epics")

TRADEABLE = "TRADEABLE"


def search_terms() -> list[str]:
    """Liefert alle zu prüfenden Symbole: jedes Sub-Sektor-ETF plus den VIX.
    Doppelte ETF-Symbole (mehrere Sub-Sektoren teilen sich einen ETF) werden
    zusammengefasst."""
    etfs = sorted(set(config.SUB_SECTOR_ETFS.values()))
    return etfs + [config.VIX_TICKER]


def pick_best(symbol: str, markets: list[dict]) -> dict | None:
    """Gibt den Treffer zurück, dessen Epic EXAKT dem Symbol entspricht — sonst None.

    Bewusst kein Fuzzy-Fallback: Capital.coms Marktsuche ist eine Volltextsuche und
    liefert zu jedem Kürzel irgendetwas. Ein "plausibelster Treffer" führte im Lauf
    vom 2026-07-27 dazu, dass KBE (Bank-ETF) auf KBH (KB Home, Hausbauer) und XLB
    (Materials) auf ACI (Albertsons) abgebildet wurden. Für einen Momentum-Guardrail
    ist ein falsches Instrument schlimmer als gar keins — deshalb: exakt oder nichts."""
    sym = symbol.strip().upper()
    for m in markets:
        if (m.get("epic") or "").strip().upper() == sym:
            return m
    return None


FUND_WORDS = ("ETF", "FUND", "INDEX", "TRUST", "SPDR", "ISHARES", "SELECT SECTOR")


def looks_like_fund(market: dict) -> bool:
    """True, wenn der Instrumentenname nach Fonds/Index klingt.

    Ein exakter Epic-Treffer allein genügt nicht: Capital.com führt das Epic 'PPH'
    für die PPHE Hotel Group, nicht für den gleichnamigen Pharma-ETF. Ohne diese
    Prüfung wäre ein Hotelbetreiber als Pharma-Sektor-Proxy durchgerutscht."""
    name = (market.get("instrumentName") or "").upper()
    return any(w in name for w in FUND_WORDS)


def etf_candidates(markets: list[dict], limit: int = 8) -> list[dict]:
    """Filtert aus den Suchtreffern die heraus, die dem Namen nach ein Fonds sind
    — Kandidaten für einen Ersatz-Ticker, wenn das gesuchte Symbol fehlt."""
    return [m for m in markets if looks_like_fund(m)][:limit]


def resolve(provider, terms: list[str]) -> dict[str, list[dict]]:
    """Fragt für jedes Symbol die Capital.com-Marktsuche ab und gibt
    {symbol: [markt-dicts]} zurück."""
    out: dict[str, list[dict]] = {}
    for term in terms:
        out[term] = provider.search_markets(term)
    return out


def format_report(resolved: dict[str, list[dict]], sub_sectors: dict[str, str]) -> str:
    """Rendert den Auflösungs-Report: bestätigte Epics, fehlende Symbole samt
    Fonds-Kandidaten als Ersatz, und eine Zusammenfassung."""
    by_etf: dict[str, list[str]] = {}
    for sector, etf in sub_sectors.items():
        by_etf.setdefault(etf, []).append(sector)

    lines: list[str] = [
        "",
        "=" * 78,
        "Capital.com Epic-Aufloesung — Sub-Sektor-ETFs + VIX",
        "(nur EXAKTE Epic-Treffer gelten; Fuzzy-Treffer sind bei dieser",
        " Volltextsuche wertlos, s. pick_best-Docstring)",
        "=" * 78,
    ]
    confirmed: list[str] = []
    missing: list[str] = []
    not_tradeable: list[str] = []
    suspicious: list[str] = []

    for symbol, markets in resolved.items():
        sectors = ", ".join(sorted(by_etf.get(symbol, []))) or "VIX / Volatilitaet"
        best = pick_best(symbol, markets)

        if best is None:
            missing.append(symbol)
            lines.append(f"{symbol:<6} KEIN TREFFER  —  Sub-Sektor: {sectors}")
            cands = etf_candidates(markets)
            if cands:
                lines.append(f"{'':<9} Fonds-Kandidaten bei Capital.com:")
                for c in cands:
                    lines.append(
                        f"{'':<11} {c.get('epic', '?'):<12} "
                        f"{(c.get('marketStatus') or '?').upper():<11} "
                        f"{c.get('instrumentName', '?')}"
                    )
            else:
                lines.append(f"{'':<9} (kein Fonds unter den Suchtreffern)")
            lines.append("")
            continue

        status = (best.get("marketStatus") or "?").upper()
        if status != TRADEABLE:
            not_tradeable.append(symbol)

        if looks_like_fund(best):
            confirmed.append(symbol)
            verdict = "OK          "
        else:
            suspicious.append(symbol)
            verdict = "NAME PRUEFEN"

        lines.append(
            f"{symbol:<6} {verdict}  {status:<12} "
            f"{best.get('instrumentType') or '?'}"
        )
        lines.append(f"{'':<9} {best.get('instrumentName') or '?'}")
        lines.append(f"{'':<9} Sub-Sektor: {sectors}")
        if symbol in suspicious:
            lines.append(
                f"{'':<9} !! Epic passt, Name klingt aber nicht nach Fonds — "
                f"vermutlich ein fremdes Instrument."
            )
        lines.append("")

    lines += ["-" * 78, "ZUSAMMENFASSUNG", "-" * 78]
    lines.append(f"geprueft:            {len(resolved)}")
    lines.append(f"bestaetigt:          {len(confirmed)}")
    lines.append(f"NAME PRUEFEN:        {len(suspicious)}"
                 + (f"  ({', '.join(suspicious)})" if suspicious else ""))
    lines.append(f"KEIN TREFFER:        {len(missing)}"
                 + (f"  ({', '.join(missing)})" if missing else ""))
    lines.append(f"nicht handelbar:     {len(not_tradeable)}"
                 + (f"  ({', '.join(not_tradeable)})" if not_tradeable else ""))

    if missing:
        lines += [
            "",
            "-" * 78,
            "HINWEIS zu den fehlenden Symbolen",
            "-" * 78,
            "Capital.com fuehrt diese Instrumente nicht. Zwei Wege:",
            "  1. Ersatz-ETF aus den Kandidaten oben waehlen und in",
            "     config.SUB_SECTOR_ETFS eintragen.",
            "  2. Sub-Sektor auf einen breiteren, bestaetigten ETF zusammenlegen.",
            "Ein TICKER_MAP-Eintrag hilft hier NICHT — das Instrument fehlt",
            "vollstaendig, es heisst nicht bloss anders.",
        ]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Löst alle Sub-Sektor-ETF- und VIX-Epics auf und schreibt den Report nach
    stdout. Gibt 0 zurück, oder 1 wenn die Capital.com-Session nicht zustande kam."""
    parser = argparse.ArgumentParser(
        description="Verify Capital.com epics for sub-sector ETFs and the VIX",
    )
    parser.add_argument(
        "--symbols", nargs="+", metavar="SYM",
        help="Nur diese Symbole pruefen statt aller Sub-Sektor-ETFs",
    )
    ns = parser.parse_args(argv)

    if not config.CAPITAL_COM_API_KEY:
        print("FEHLER: CAPITAL_COM_API_KEY ist nicht gesetzt (.env pruefen).")
        return 1

    terms = ns.symbols or search_terms()
    provider = CapitalComProvider()
    try:
        resolved = resolve(provider, terms)
    except Exception as e:
        print(f"FEHLER: Capital.com-Session fehlgeschlagen: {e}")
        return 1

    print(format_report(resolved, config.SUB_SECTOR_ETFS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
