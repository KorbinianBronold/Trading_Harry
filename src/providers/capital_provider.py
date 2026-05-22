"""Capital.com Demo REST API provider.

Authentication: POST /api/v1/session → CST + X-SECURITY-TOKEN headers.
Session is created lazily on first call and reused for the lifetime of the
provider instance (one instance per run).
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests

import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.capital")
BERLIN = ZoneInfo("Europe/Berlin")

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


class CapitalComProvider(DataProvider):
    _source_name = "capital.com"

    def __init__(self) -> None:
        self._cst: str | None = None
        self._security_token: str | None = None
        self._auth_failed: bool = False

    def _ensure_session(self) -> None:
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
        self._ensure_session()
        return {
            "X-CAP-API-KEY":    config.CAPITAL_COM_API_KEY,
            "CST":              self._cst,
            "X-SECURITY-TOKEN": self._security_token,
        }

    def _map(self, ticker: str) -> str:
        return TICKER_MAP.get(ticker, ticker)

    def _parse_prices(self, prices: list[dict]) -> pd.DataFrame | None:
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
        epic = self._map(ticker)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={"resolution": "DAY", "max": days},
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com price fetch failed: {e}")
            return None

    def get_ohlc_after(
        self, ticker: str, start_date: str, end_date: str,
    ) -> pd.DataFrame | None:
        epic = self._map(ticker)
        # Capital.com filters by snapshotTimeUTC. 'to=DATE T00:00:00' includes that
        # date's bar. 'to' must not exceed today's midnight — future dates → 400.
        # When start==end (same-day check), step 'from' back 1 day so the range
        # is non-empty and still captures today's bar.
        from datetime import date as _date, timedelta as _td
        start_dt = _date.fromisoformat(start_date)
        end_dt   = _date.fromisoformat(end_date)
        if start_dt >= end_dt:
            start_dt = end_dt - _td(days=1)
        try:
            resp = requests.get(
                f"{config.CAPITAL_COM_BASE_URL}/api/v1/prices/{epic}",
                headers=self._headers(),
                params={
                    "resolution": "DAY",
                    "max":        1000,
                    "from":       f"{start_dt.isoformat()}T00:00:00",
                    "to":         f"{end_dt.isoformat()}T00:00:00",
                },
                timeout=30,
            )
            resp.raise_for_status()
            return self._parse_prices(resp.json().get("prices", []))
        except Exception as e:
            log.warning(f"{ticker}: Capital.com OHLC fetch failed: {e}")
            return None

    def get_last_available_date(self, ticker: str) -> str | None:
        df = self.get_price_history(ticker, days=5)
        if df is None or df.empty:
            return None
        return df.index[-1].strftime("%Y-%m-%d")

    def get_premarket_price(self, ticker: str) -> float | None:
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
        return {}

    def get_earnings_calendar(self, ticker: str) -> dict:
        return {}
