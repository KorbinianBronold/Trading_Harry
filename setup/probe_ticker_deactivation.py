"""Realtest der Ticker-Deaktivierung (Sprint 3B / B.7) gegen die echte Capital.com-API.

Laesst FAKEXXXX 21-mal durch Phase 1 laufen, protokolliert skip_count und das
inactive-Flag und prueft danach, dass wirklich KEIN API-Call mehr rausgeht.
Wegwerfbar, laeuft gegen eine Kopie der DB — data/tracking.db bleibt unberuehrt.
"""
import logging
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from src import db
from src.data_collector import collect
from src.providers.capital_provider import CapitalComProvider
from src.providers.finnhub_provider import FinnhubProvider

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

FAKE = "FAKEXXXX"

tmp = Path(tempfile.mkdtemp()) / "probe.db"
shutil.copy("data/tracking.db", tmp)
conn = db.connect(str(tmp))
db.init_schema(conn)


class CountingProvider(CapitalComProvider):
    """Zaehlt jeden echten Preis-Call mit, damit sich 'keine API-Calls mehr'
    nachweisen laesst statt nur behaupten."""
    calls = 0

    def get_price_history(self, ticker, days=90):
        type(self).calls += 1
        return super().get_price_history(ticker, days=days)

    def get_ohlc_after(self, ticker, start_date, end_date):
        type(self).calls += 1
        return super().get_ohlc_after(ticker, start_date, end_date)


provider = CountingProvider()
earnings = FinnhubProvider()

print(f"\n{'Lauf':<6}{'Datum':<13}{'skip_count':<12}{'inactive':<10}"
      f"{'retry_after':<13}{'API-Calls'}")
print("-" * 70)

for i in range(config.TICKER_MAX_SKIPS + 1):
    date = f"2026-07-{i + 1:02d}"
    before = CountingProvider.calls
    collect(
        tickers=[FAKE], price_provider=provider, earnings_provider=earnings,
        conn=conn, date=date, run_type="probe",
    )
    st = db.get_ticker_status(conn, FAKE)
    print(f"{i + 1:<6}{date:<13}{st['skip_count']:<12}{st['inactive']:<10}"
          f"{str(st['retry_after']):<13}{CountingProvider.calls - before}")

st = db.get_ticker_status(conn, FAKE)
print("\n" + "=" * 70)
print(f"Nach {st['skip_count']} Skips: inactive={st['inactive']}, "
      f"retry_after={st['retry_after']}")
print("=" * 70)

# --- Nachweis 1: gesperrt => keine API-Calls mehr ---
before = CountingProvider.calls
collect(tickers=[FAKE], price_provider=provider, earnings_provider=earnings,
        conn=conn, date="2026-07-25", run_type="probe")
gesperrt = CountingProvider.calls - before
print(f"\nLauf am 2026-07-25 (vor retry_after): {gesperrt} API-Calls "
      f"-> {'OK, gesperrt' if gesperrt == 0 else 'FEHLER, Ticker wurde abgerufen'}")

# --- Nachweis 2: ab retry_after wird wieder versucht ---
before = CountingProvider.calls
collect(tickers=[FAKE], price_provider=provider, earnings_provider=earnings,
        conn=conn, date=st["retry_after"], run_type="probe")
retry = CountingProvider.calls - before
st2 = db.get_ticker_status(conn, FAKE)
print(f"Lauf am {st['retry_after']} (= retry_after):   {retry} API-Calls "
      f"-> {'OK, erneut versucht' if retry > 0 else 'FEHLER, kein Retry'}")
print(f"   Fehlschlag verlaengert die Sperre: retry_after jetzt {st2['retry_after']}")

# --- Nachweis 3: manuelles Reaktivieren ---
changed = db.reactivate_ticker(conn, FAKE)
st3 = db.get_ticker_status(conn, FAKE)
print(f"\n--reactivate: geaendert={changed}, skip_count={st3['skip_count']}, "
      f"inactive={st3['inactive']}, retry_after={st3['retry_after']}")

print(f"\nAPI-Calls insgesamt: {CountingProvider.calls}")
conn.close()
