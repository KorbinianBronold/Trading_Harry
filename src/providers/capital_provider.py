"""Capital.com Demo REST API provider.

Authentication: POST /api/v1/session → CST + X-SECURITY-TOKEN headers.
Session is created lazily on first call and reused for the lifetime of the
provider instance (one instance per run).
"""
import logging
from datetime import date as _date, datetime as _datetime, timedelta, timezone

import pandas as pd
import requests

import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.capital")

# Capital.com beantwortet /prices mit max>1000 per HTTP 400. Empirisch am
# 2026-07-27 ermittelt: max=1000 liefert 1000 Bars, max=1001 einen 400er.
MAX_BARS_PER_REQUEST = 1000


def _not_in_future(ts: str) -> str:
    """Klemmt einen 'to'-Zeitstempel auf 'jetzt' (UTC).

    Capital.com beantwortet ein 'to' in der Zukunft mit HTTP 400 -- gemessen am
    2026-08-06 genuegen fuenf Minuten. Das Verhalten steht NICHT in der API-Doku
    (CapitalcomPublicAPI.pdf S. 73 nennt nur das Format). Ausgeloest wird es
    davon, dass das Laufdatum aus Europe/Berlin stammt, die API aber laut Doku
    auf snapshotTimeUTC filtert: zwischen 00:00 und 02:00 Berlin laeuft das
    Berliner Datum dem UTC-Datum voraus."""
    now = _datetime.now(timezone.utc).replace(tzinfo=None)
    parsed = _datetime.fromisoformat(ts)
    return min(parsed, now).strftime("%Y-%m-%dT%H:%M:%S")


TICKER_MAP: dict[str, str] = {
    "GC=F":    "GOLD",
    "SI=F":    "SILVER",
    "CL=F":    "OIL_CRUDE",   # Capital.com epic (not CRUDE_OIL)
    "BTC-USD": "BTCUSD",
    "ETH-USD": "ETHUSD",
    "SOL-USD": "SOLUSD",
    "XRP-USD": "XRPUSD",
    "BRK-B":   "BRKB",        # Capital.com epic for Berkshire B
}

# Rueckrichtung fuer Phase 1c (B.4): get_open_positions() liefert Epics, wir
# rechnen intern in Tickern. Beim Import einmal gebaut statt bei jedem Aufruf.
_EPIC_TO_TICKER: dict[str, str] = {v: k for k, v in TICKER_MAP.items()}


def epic_to_ticker(epic: str) -> str | None:
    """Uebersetzt ein Capital.com-Epic zurueck in unser internes Ticker-Symbol.

    Gibt None zurueck, wenn das Epic zu keinem Ticker unserer Universen gehoert —
    typisch fuer von Hand eroeffnete Fremdpositionen. Fuer sie existieren keine
    Indikator-Daten, sie werden vom Aufrufer geloggt und uebersprungen."""
    if epic in _EPIC_TO_TICKER:
        return _EPIC_TO_TICKER[epic]
    known = set(config.SP500_FULL_TICKERS if config.USE_FULL_SP500
                else config.SP500_MVP_TICKERS)
    return epic if epic in known else None


class CapitalComProvider(DataProvider):
    _source_name = "capital.com"

    def __init__(self) -> None:
        """Initializes an unauthenticated instance; the session is created lazily
        on the first API call."""
        self._cst: str | None = None
        self._security_token: str | None = None
        self._auth_failed: bool = False

    def _ensure_session(self) -> None:
        """Authenticates once (POST /session) and caches the CST/security-token
        headers; skips re-authenticating if a prior attempt already failed."""
        if self._auth_failed:
            raise RuntimeError("Capital.com session auth previously failed — skipping")
        if self._cst:
            return
        try:
            identifier = config.CAPITAL_COM_IDENTIFIER or config.CAPITAL_COM_API_KEY
            resp = requests.post(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/session",
                json={
                    "identifier":        identifier,
                    "password":          config.CAPITAL_COM_PASSWORD,
                    "encryptedPassword": False,
                },
                headers={"X-CAP-API-KEY": config.CAPITAL_COM_API_KEY},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            self._auth_failed = True
            log.error(f"Capital.com session auth failed (will not retry): {e}")
            raise
        self._cst            = resp.headers.get("CST")
        self._security_token = resp.headers.get("X-SECURITY-TOKEN")

    def _headers(self) -> dict:
        """Returns the auth headers required on every Capital.com API call,
        triggering session creation first if needed."""
        self._ensure_session()
        return {
            "X-CAP-API-KEY":    config.CAPITAL_COM_API_KEY,
            "CST":              self._cst,
            "X-SECURITY-TOKEN": self._security_token,
        }

    def _map(self, ticker: str) -> str:
        """Translates an internal ticker symbol to its Capital.com epic, or
        returns it unchanged if no mapping exists."""
        return TICKER_MAP.get(ticker, ticker)

    def _parse_prices(self, prices: list[dict]) -> pd.DataFrame | None:
        """Converts Capital.com's raw price list into a bid-price OHLCV
        DataFrame indexed by date, or None if the input is empty."""
        if not prices:
            return None
        rows = []
        for p in prices:
            snap = p.get("snapshotTime", "")
            date_str = snap.replace("/", "-")[:10]
            rows.append({
                "Date":   date_str,
                "Open":   float(p["openPrice"]["bid"]),
                "High":   float(p["highPrice"]["bid"]),
                "Low":    float(p["lowPrice"]["bid"]),
                "Close":  float(p["closePrice"]["bid"]),
                "Volume": int(p.get("lastTradedVolume") or 0),
            })
        df = pd.DataFrame(rows)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        return df if not df.empty else None

    def get_price_history(self, ticker: str, days: int = 90) -> pd.DataFrame | None:
        """Fetches the last `days` daily bars for `ticker`; returns None on any
        request/parse failure instead of raising.

        `days` is clamped to MAX_BARS_PER_REQUEST — Capital.com rejects anything
        above with HTTP 400, and a silent 400 per ticker is far worse than a
        slightly shorter history."""
        epic = self._map(ticker)
        capped = min(days, MAX_BARS_PER_REQUEST)
        if capped < days:
            log.info(
                f"{ticker}: {days} Bars angefragt, auf {capped} gedeckelt "
                f"(Capital.com-Limit)"
            )
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={"resolution": "DAY", "max": capped},
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com price fetch failed: {e}")
            return None

    def search_markets(self, search_term: str) -> list[dict]:
        """Searches Capital.com's instrument catalogue for `search_term` and returns
        the raw market dicts (epic, instrumentName, instrumentType, marketStatus);
        empty list on any failure. Read-only — used by setup/verify_epics.py."""
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets",
                headers=self._headers(),
                params={"searchTerm": search_term},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("markets", [])
        except Exception as e:
            log.warning(f"Capital.com market search for '{search_term}' failed: {e}")
            return []

    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        """Fetches daily bars for `ticker` between start_date and end_date
        (inclusive); returns None on any request/parse failure."""
        epic = self._map(ticker)
        # Capital.com filters by snapshotTimeUTC. 'to=DATE T00:00:00' includes that
        # date's bar. 'to' must not exceed today's midnight — future dates → 400.
        # When start==end (same-day check), step 'from' back 1 day so the range
        # is non-empty and still captures today's bar.
        start_dt = _date.fromisoformat(start_date)
        end_dt   = _date.fromisoformat(end_date)
        if start_dt >= end_dt:
            start_dt = end_dt - timedelta(days=1)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={
                    "resolution": "DAY",
                    "max":        1000,
                    "from":       f"{start_dt.isoformat()}T00:00:00",
                    "to":         _not_in_future(f"{end_dt.isoformat()}T00:00:00"),
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com OHLC fetch failed: {e}")
            return None

    def get_last_available_date(self, ticker: str) -> str | None:
        """Returns the most recent date Capital.com has a bar for `ticker`, or
        None if no data is available."""
        df = self.get_price_history(ticker, days=5)
        if df is None or df.empty:
            return None
        return df.index[-1].strftime("%Y-%m-%d")

    def get_premarket_price(self, ticker: str) -> float | None:
        """Returns the current bid price for `ticker` from the live market
        snapshot, or None on failure."""
        epic = self._map(ticker)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/markets/{epic}",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            bid = resp.json().get("snapshot", {}).get("bid")
            return float(bid) if bid is not None else None
        except Exception as e:
            log.warning(f"{ticker}: Capital.com premarket fetch failed: {e}")
            return None

    def get_open_positions(self) -> list[dict]:
        """Returns all currently open demo-account positions as a list of dicts
        (ticker, direction, entry/current price, TP/SL, P&L); empty list on failure."""
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/positions",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            out = []
            for p in resp.json().get("positions", []):
                pos = p.get("position", {})
                mkt = p.get("market", {})
                out.append({
                    "ticker":        mkt.get("epic"),
                    "direction":     "long" if pos.get("direction") == "BUY" else "short",
                    "entry_price":   pos.get("level"),
                    "current_price": mkt.get("bid"),
                    "tp_price":      pos.get("limitLevel"),
                    "sl_price":      pos.get("stopLevel"),
                    "profit_loss":   pos.get("profit"),
                    "status":        "open",
                })
            return out
        except Exception as e:
            log.warning(f"Capital.com open positions fetch failed: {e}")
            return []

    def get_closed_positions(self, date: str) -> list[dict]:
        """Returns positions that were closed on `date`, filtered from the account
        activity log; empty list on failure or if none closed."""
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/history/activity",
                headers=self._headers(),
                params={
                    "from":     f"{date}T00:00:00",
                    "to":       f"{date}T23:59:59",
                    "detailed": "true",
                },
                timeout=30,
            )
            resp.raise_for_status()
            out = []
            for act in resp.json().get("activities", []):
                if act.get("type") != "POSITION":
                    continue
                det = act.get("details", {})
                actions = det.get("actions") or []
                if not any(a.get("actionType") == "POSITION_CLOSED" for a in actions):
                    continue
                out.append({
                    "ticker":      act.get("epic"),
                    "direction":   "long" if det.get("direction") == "BUY" else "short",
                    "exit_price":  det.get("level"),
                    "profit_loss": det.get("profit"),
                    "status":      "closed",
                })
            return out
        except Exception as e:
            log.warning(f"Capital.com closed positions fetch failed: {e}")
            return []

    def get_fundamentals(self, ticker: str) -> dict:
        """Not supported by Capital.com — always returns {}; FinnhubProvider
        supplies fundamentals instead."""
        return {}

    def get_earnings_calendar(self, ticker: str) -> dict:
        """Not supported by Capital.com — always returns {}; FinnhubProvider
        supplies the earnings calendar instead."""
        return {}
