"""Einmal-Probe: Phase 1 gegen die echten Provider laufen lassen und auswerten,
welche finnhubIndustry-Rohwerte sich auf Sub-Sektoren aufloesen lassen.

Kein Pipeline-Code, kein Claude, keine Mail. Schreibt in eine temporaere DB,
damit data/tracking.db unberuehrt bleibt. Wegwerfbar — nach der Auswertung loeschen.
"""
import logging
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.data_collector import collect
from src.providers.capital_provider import CapitalComProvider
from src.providers.finnhub_provider import FinnhubProvider

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# WARN-Meldungen aus db.resolve_sector_id einsammeln
unresolved: list[str] = []


class _Collector(logging.Handler):
    def emit(self, record):
        msg = record.getMessage()
        if "unknown sector value from provider" in msg:
            unresolved.append(msg.split("provider: ")[-1].strip())


logging.getLogger("shares_future.db").addHandler(_Collector())

# Kopie der echten DB, damit die geladene Historie da ist, das Original aber
# unberuehrt bleibt.
import shutil
tmp = Path(tempfile.mkdtemp()) / "probe.db"
shutil.copy("data/tracking.db", tmp)
conn = db.connect(str(tmp))
db.init_schema(conn)

tickers = config.SP500_MVP_TICKERS
print(f"\nPhase 1 fuer {len(tickers)} MVP-Ticker gegen Capital.com + Finnhub ...\n")

tds, skipped = collect(
    tickers=tickers,
    price_provider=CapitalComProvider(),
    earnings_provider=FinnhubProvider(),
    conn=conn,
    date="2026-07-27",
    run_type="probe",
)

print("\n" + "=" * 78)
print("ERGEBNIS: Finnhub-Rohsektor -> Sub-Sektor")
print("=" * 78)

by_sub = defaultdict(list)
rows = []
for td in tds:
    t = td["ticker"]
    raw = td.get("sector")
    mapped = db.get_ticker_sector(conn, t)
    name = mapped["name"] if mapped else None
    etf = mapped["etf"] if mapped else None
    rows.append((t, raw, name, etf))
    by_sub[name].append(t)

print(f"{'Ticker':<8} {'finnhubIndustry':<28} {'Sub-Sektor':<28} ETF")
print("-" * 78)
for t, raw, name, etf in sorted(rows, key=lambda r: (r[2] is None, r[2] or "", r[0])):
    print(f"{t:<8} {str(raw):<28} {str(name):<28} {etf or '-'}")

print("\n" + "-" * 78)
print("NICHT AUFGELOESTE finnhubIndustry-WERTE (WARN-Logs)")
print("-" * 78)
if unresolved:
    for v in sorted(set(unresolved)):
        betroffen = [t for t, raw, name, _ in rows if name is None and repr(raw) == v]
        print(f"  {v:<32} -> {', '.join(betroffen) or '(kein Ticker in dieser Liste)'}")
else:
    print("  keine — alle Rohwerte liessen sich aufloesen")

print("\n" + "-" * 78)
print("SUB-SEKTOR-BELEGUNG (>=3 Ticker => db_momentum berechenbar)")
print("-" * 78)
for name, ts in sorted(by_sub.items(), key=lambda x: (x[0] is None, -len(x[1]))):
    if name is None:
        continue
    _min = getattr(config, "SECTOR_DB_MOMENTUM_MIN_TICKERS", 3)  # kommt erst in Task 9a
    flag = "  <-- db_momentum moeglich" if len(ts) >= _min else ""
    print(f"  {name:<30} {len(ts)}  ({', '.join(ts)}){flag}")

n_unmapped = sum(1 for r in rows if r[2] is None)
print(f"\nZusammenfassung: {len(tds)} Ticker verarbeitet, {skipped} uebersprungen, "
      f"{n_unmapped} ohne Sub-Sektor.")
conn.close()
