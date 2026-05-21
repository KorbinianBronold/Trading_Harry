import logging
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


class FinnhubProvider(DataProvider):
    LOOKBACK_DAYS = 90
    LOOKAHEAD_DAYS = 60

    def get_price_history(self, ticker, days=90):
        raise NotImplementedError("FinnhubProvider only supplies earnings")

    def get_ohlc_after(self, ticker, start_date, end_date):
        raise NotImplementedError("Finnhub provider is earnings-only; use yfinance for OHLC")

    def get_fundamentals(self, ticker: str) -> dict:
        if _client is None:
            return {}
        try:
            profile  = _client.company_profile2(symbol=ticker) or {}
            resp     = _client.company_basic_financials(ticker, "all") or {}
            metrics  = resp.get("metric") or {}
            recs     = _client.recommendation_trends(ticker) or []
            _client.price_target(ticker)  # fetched; not used yet
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
        return None

    def get_earnings_calendar(self, ticker: str) -> dict:
        if _client is None:
            return {"days_to_next": None, "last_beat_pct": None}
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
