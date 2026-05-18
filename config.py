import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "tracking.db"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
PAID_API_KEY = os.getenv("PAID_API_KEY")
PAID_API_TYPE = os.getenv("PAID_API_TYPE", "polygon")

CLAUDE_MODEL_SONNET = "claude-sonnet-4-6"
CLAUDE_MODEL_HAIKU = "claude-haiku-4-5"
CLAUDE_MODEL_OPUS = "claude-opus-4-7"

SIMULATION_ONLY = True

SP500_MVP_TICKERS = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "LLY",
    "ABBV", "AVGO",
]
COMMODITY_TICKERS = {"Gold": "GC=F", "Silber": "SI=F", "Öl": "CL=F"}
CRYPTO_TICKERS = {
    "Bitcoin": "BTC-USD", "Ethereum": "ETH-USD",
    "Solana": "SOL-USD", "XRP": "XRP-USD",
}

SP500_MIN_MARKET_CAP_B = 5
SP500_MIN_ATR_PCT = 0.8
MAX_DEEP_ANALYSIS = 80
BATCH_SIZE_QUICK = 30

RR_RATIO_DEFAULT = 2.0
RR_RATIO_MIN_HARD = 1.5
MOMENTUM_LONG_MIN = 6.0
MOMENTUM_SHORT_MAX = 4.0

CFD_MARGIN_EUR = 500
CFD_LEVERAGE = 5

MAX_COST_PER_RUN_EUR = 4.00
COST_WARN_THRESHOLD_EUR = 3.00
CLAUDE_PARALLEL_CALLS = 5

YFINANCE_PAUSE_SEC = 0.8
YFINANCE_BATCH_PAUSE = 12

DIMENSION_WEIGHTS = {
    "market_environment": 0.10,
    "company_quality":    0.18,
    "valuation":          0.12,
    "momentum":           0.22,
    "risk":               0.10,
    "sector_trend":       0.10,
    "catalyst":           0.10,
    "policy_risk":        0.08,
}
