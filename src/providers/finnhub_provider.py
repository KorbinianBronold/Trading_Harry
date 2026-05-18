import logging
from datetime import datetime, timedelta
import finnhub
import config
from src.providers.base import DataProvider

log = logging.getLogger("shares_future.finnhub")

_client = (
    finnhub.Client(api_key=config.FINNHUB_API_KEY)
    if config.FINNHUB_API_KEY else None
)


class FinnhubProvider(DataProvider):
    LOOKBACK_DAYS = 90
    LOOKAHEAD_DAYS = 60

    def get_price_history(self, ticker, days=90):
        raise NotImplementedError("FinnhubProvider only supplies earnings")

    def get_fundamentals(self, ticker):
        return {}

    def get_last_available_date(self, ticker):
        return None

    def get_earnings_calendar(self, ticker: str) -> dict:
        if _client is None:
            return {"days_to_next": None, "last_beat_pct": None}
        today = datetime.now().date()
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
