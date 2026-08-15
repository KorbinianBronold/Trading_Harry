"""Fundamentals + earnings-calendar provider via the Finnhub free tier. Does NOT
supply OHLC price data — that's CapitalComProvider's job; this provider only
implements the fundamentals/earnings half of the DataProvider interface."""
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import finnhub
import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.finnhub")

BERLIN = ZoneInfo("Europe/Berlin")

_client = (
    finnhub.Client(api_key=config.FINNHUB_API_KEY)
    if config.FINNHUB_API_KEY else None
)

# Sprint 3C / Analyse-Pipeline-Umbau, Plan 2, Task 11: Finnhub Free-Tier
# begrenzt auf 60 Calls/min. Ohne Drosselung wuerde der Wochenlauf (Task 12,
# bis zu ~500 Ticker x 2 Calls) das Limit sprengen.
_FINNHUB_RATE_LIMIT = 60
_FINNHUB_RATE_WINDOW_S = 60.0


class FinnhubProvider(DataProvider):
    LOOKBACK_DAYS = 90
    LOOKAHEAD_DAYS = 60

    def __init__(self):
        # Instanz-gebunden, nicht modulweit: der Wochenlauf haelt EINE
        # FinnhubProvider-Instanz ueber das ganze Universum (dieselbe
        # Invariante wie "ein Session-Object pro Run" bei Capital.com), und
        # Tests bekommen so automatisch ein frisches Fenster ohne
        # modulweiten Reset.
        self._call_times: list[float] = []

    def _respect_rate_limit(self) -> None:
        """Sliding-Window-Drosselung: pausiert, bevor ein Call das
        60-Sekunden-Fenster ueber _FINNHUB_RATE_LIMIT Eintraege hinaus
        fuellen wuerde."""
        now = time.time()
        cutoff = now - _FINNHUB_RATE_WINDOW_S
        while self._call_times and self._call_times[0] < cutoff:
            self._call_times.pop(0)
        if len(self._call_times) >= _FINNHUB_RATE_LIMIT:
            sleep_s = _FINNHUB_RATE_WINDOW_S - (now - self._call_times[0])
            if sleep_s > 0:
                log.info(f"Finnhub rate limit: sleeping {sleep_s:.1f}s")
                time.sleep(sleep_s)
        self._call_times.append(time.time())

    def get_price_history(self, ticker, days=90):
        """Not supported — Finnhub is earnings/fundamentals-only in this project."""
        raise NotImplementedError("FinnhubProvider only supplies earnings")

    def get_ohlc_after(self, ticker, start_date, end_date):
        """Not supported — use CapitalComProvider for OHLC data instead."""
        raise NotImplementedError("Finnhub provider is earnings-only; use CapitalComProvider for OHLC")

    def get_fundamentals(self, ticker: str) -> dict:
        """Fetches PE, market cap, sector, and analyst consensus for `ticker` from
        Finnhub. Returns an empty dict if no API key is configured or any call fails."""
        if _client is None:
            return {}
        try:
            # R: je ECHTEM Request drosseln, nicht je Methodenaufruf -- diese
            # eine Methode setzt drei Finnhub-Requests ab. Ein einzelnes
            # _respect_rate_limit() davor haette das Limit effektiv verdreifacht.
            self._respect_rate_limit()
            profile  = _client.company_profile2(symbol=ticker) or {}
            self._respect_rate_limit()
            resp     = _client.company_basic_financials(ticker, "all") or {}
            metrics  = resp.get("metric") or {}
            self._respect_rate_limit()
            recs     = _client.recommendation_trends(ticker) or []
        except Exception as e:
            log.warning(f"{ticker}: Finnhub fundamentals failed: {e}")
            return {}

        consensus = None
        if recs:
            r     = recs[0]
            total = (r.get("buy") or 0) + (r.get("hold") or 0) + (r.get("sell") or 0)
            if total > 0:
                ratio     = (r.get("buy") or 0) / total
                consensus = "buy" if ratio >= 0.6 else ("sell" if ratio <= 0.3 else "hold")

        mc_millions  = profile.get("marketCapitalization")
        market_cap_b = round(mc_millions / 1000, 2) if mc_millions else None

        de_raw  = metrics.get("totalDebt/totalEquityAnnual")
        debt_eq = round(de_raw / 100, 4) if de_raw is not None else None

        return {
            "pe_ratio":       metrics.get("peNormalizedAnnual"),
            "forward_pe":     metrics.get("forwardPE"),
            "market_cap_b":   market_cap_b,
            "debt_equity":    debt_eq,
            "sector":         profile.get("finnhubIndustry"),
            "analyst_upside": None,
            "consensus":      consensus,
        }

    def get_last_available_date(self, ticker):
        """Not applicable — Finnhub doesn't supply price history here. Always None."""
        return None

    def get_earnings_calendar(self, ticker: str) -> dict:
        """Returns the number of days until `ticker`'s next earnings report and the
        % EPS beat/miss of its last report, or Nones if unavailable/no API key."""
        if _client is None:
            return {"days_to_next": None, "last_beat_pct": None}
        self._respect_rate_limit()
        today = datetime.now(BERLIN).date()
        try:
            resp = _client.earnings_calendar(
                _from=(today - timedelta(days=self.LOOKBACK_DAYS)).isoformat(),
                to=(today + timedelta(days=self.LOOKAHEAD_DAYS)).isoformat(),
                symbol=ticker,
            )
        except Exception as e:
            log.warning(f"{ticker}: finnhub earnings call failed: {e}")
            return {"days_to_next": None, "last_beat_pct": None}

        items = (resp or {}).get("earningsCalendar", [])
        if not items:
            return {"days_to_next": None, "last_beat_pct": None}

        future = []
        last_beat = None
        for it in items:
            try:
                d = datetime.strptime(it["date"], "%Y-%m-%d").date()
            except (KeyError, ValueError):
                continue
            if d >= today:
                future.append((d, it))
            else:
                actual = it.get("epsActual")
                est = it.get("epsEstimate")
                if actual is not None and est and est != 0:
                    last_beat = round((actual - est) / est * 100, 2)

        days_to_next = None
        if future:
            future.sort(key=lambda x: x[0])
            days_to_next = (future[0][0] - today).days

        return {"days_to_next": days_to_next, "last_beat_pct": last_beat}
