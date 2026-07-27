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
    """Wählt aus den Suchtreffern den plausibelsten aus: exaktes Epic schlägt
    Epic-mit-Präfix, handelbar schlägt ausgesetzt. None, wenn nichts passt."""
    if not markets:
        return None

    def rank(m: dict) -> tuple:
        epic = (m.get("epic") or "").upper()
        sym = symbol.upper()
        exact = epic == sym
        prefix = epic.startswith(sym)
        tradeable = (m.get("marketStatus") or "").upper() == TRADEABLE
        # sort() ist aufsteigend -> negieren, damit "besser" nach vorn wandert
        return (not exact, not prefix, not tradeable, epic)

    return sorted(markets, key=rank)[0]


def resolve(provider, terms: list[str]) -> dict[str, list[dict]]:
    """Fragt für jedes Symbol die Capital.com-Marktsuche ab und gibt
    {symbol: [markt-dicts]} zurück."""
    out: dict[str, list[dict]] = {}
    for term in terms:
        out[term] = provider.search_markets(term)
    return out


def format_report(resolved: dict[str, list[dict]], sub_sectors: dict[str, str]) -> str:
    """Rendert den Auflösungs-Report inklusive kopierfertigem TICKER_MAP-Block für
    alle Symbole, deren Epic vom Symbol abweicht."""
    by_etf: dict[str, list[str]] = {}
    for sector, etf in sub_sectors.items():
        by_etf.setdefault(etf, []).append(sector)

    lines: list[str] = [
        "",
        "=" * 78,
        "Capital.com Epic-Aufloesung — Sub-Sektor-ETFs + VIX",
        "=" * 78,
    ]
    needs_mapping: dict[str, str] = {}
    missing: list[str] = []
    not_tradeable: list[str] = []

    for symbol, markets in resolved.items():
        sectors = ", ".join(sorted(by_etf.get(symbol, []))) or "VIX / Volatilitaet"
        best = pick_best(symbol, markets)
        if best is None:
            missing.append(symbol)
            lines.append(f"{symbol:<6} KEIN TREFFER".ljust(58) + f"[{sectors}]")
            continue

        epic = best.get("epic") or "?"
        status = (best.get("marketStatus") or "?").upper()
        itype = best.get("instrumentType") or "?"
        name = best.get("instrumentName") or "?"
        flag = "exakt" if epic.upper() == symbol.upper() else "ABWEICHEND"
        if status != TRADEABLE:
            not_tradeable.append(symbol)
        if epic.upper() != symbol.upper():
            needs_mapping[symbol] = epic

        lines.append(f"{symbol:<6} -> {epic:<18} [{flag:<10}] {status:<12} {itype}")
        lines.append(f"{'':<9} {name}")
        lines.append(f"{'':<9} Sub-Sektor: {sectors}")
        if len(markets) > 1:
            others = ", ".join(
                m.get("epic", "?") for m in markets[1:6] if m.get("epic") != epic
            )
            if others:
                lines.append(f"{'':<9} weitere Treffer: {others}")
        lines.append("")

    lines += ["-" * 78, "ZUSAMMENFASSUNG", "-" * 78]
    total = len(resolved)
    lines.append(f"geprueft:            {total}")
    lines.append(f"exakt aufgeloest:    {total - len(needs_mapping) - len(missing)}")
    lines.append(f"abweichendes Epic:   {len(needs_mapping)}"
                 + (f"  ({', '.join(needs_mapping)})" if needs_mapping else ""))
    lines.append(f"KEIN TREFFER:        {len(missing)}"
                 + (f"  ({', '.join(missing)})" if missing else ""))
    lines.append(f"nicht handelbar:     {len(not_tradeable)}"
                 + (f"  ({', '.join(not_tradeable)})" if not_tradeable else ""))

    lines += ["", "-" * 78, "In capital_provider.TICKER_MAP eintragen:", "-" * 78]
    if needs_mapping:
        for symbol, epic in needs_mapping.items():
            lines.append(f'    "{symbol}": "{epic}",')
    else:
        lines.append("    (nichts — alle Epics entsprechen dem Symbol)")

    if missing:
        lines += [
            "",
            "HINWEIS: Fuer Symbole ohne Treffer existiert bei Capital.com kein",
            "abrufbares Instrument. Der betroffene Sub-Sektor laeuft dann ohne",
            "ETF-Momentum-Check (weiches Verhalten, s. Entscheidung D6) — oder es",
            "wird ein Ersatz-ETF gewaehlt.",
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
