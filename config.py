"""Central configuration: env vars, ticker universes, scoring weights, and all
trading/guardrail constants (CFD margin, hold-day limits, cost caps). No functions —
pure module-level constants loaded once at import time."""
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

# Sub-Sektor -> Sektor-ETF-Symbol. Bewusst feiner als die 11 GICS-Sektoren: ein
# Halbleiter-Setup soll gegen SOXX geprüft werden, nicht gegen den breiten XLK,
# in dem Software und Hardware das Signal verwässern. Quelle für die
# sectors-Tabelle und für den Sektor-ETF-Momentum-Check (Sprint 3B / B.3).
#
# JEDES Symbol hier ist am 2026-07-27 per setup/verify_epics.py gegen die
# Capital.com Demo-API verifiziert: exakter Epic-Treffer, TRADEABLE, und der
# Instrumentenname wurde von Hand gegengelesen. Neue Einträge NIE ungeprüft
# hinzufügen — Capital.coms Volltextsuche liefert zu jedem Kürzel irgendetwas,
# und das Epic "PPH" gehört dort z.B. der PPHE Hotel Group, nicht dem
# gleichnamigen Pharma-ETF.
#
# Nicht abbildbar, weil Capital.com keinen passenden ETF führt (Stand 2026-07-27):
#   - Communication: weder XLC noch VOX, FCOM, IXP, XTL oder IYZ vorhanden.
#     GOOGL/META laufen daher ohne Sektor-Guardrail (weiches Verhalten, D6).
#   - Chemie / Verpackung / Papier: XLB, VAW und IYM fehlen. Nur der engere
#     Bergbau-Teil ist über XME abgedeckt, deshalb heisst der Sub-Sektor
#     "Metals & Mining" statt "Materials" — er misst genau das und nicht mehr.
#   - Pharma- und MedTech-spezifische ETFs (XPH, IHI, IHE, XHE, PJP, IHF)
#     fehlen alle. Beide Sub-Sektoren bleiben getrennt (das Learning Modul in
#     3D soll sie unterscheiden können), zeigen aber auf denselben breiten XLV.
SUB_SECTOR_ETFS: dict[str, str] = {
    "Semiconductors":               "SOXX",   # iShares Semiconductor ETF
    "Software":                     "VGT",    # Vanguard Information Technology ETF
    "Technology Hardware":          "XLK",    # Technology Select Sector SPDR
    "Biotech":                      "XBI",    # SPDR S&P Biotech
    "MedTech":                      "XLV",    # Health Care Select Sector SPDR
    "Pharma":                       "XLV",    # Health Care Select Sector SPDR
    "Healthcare Rest":              "XLV",    # Health Care Select Sector SPDR
    "Oil & Gas":                    "XOP",    # SPDR S&P Oil & Gas Expl. & Prod.
    "Clean Energy":                 "ICLN",   # iShares Global Clean Energy
    "Banks":                        "KBWB",   # Invesco KBW Bank ETF
    "Financials Rest":              "XLF",    # Financial Select Sector SPDR
    "Retail":                       "XRT",    # SPDR S&P Retail
    "Auto":                         "CARZ",   # First Trust NASDAQ Global Auto
    "Aerospace & Defense":          "ITA",    # iShares U.S. Aerospace & Defense
    "Transport":                    "XTN",    # SPDR S&P Transportation
    "Industrials Rest":             "XLI",    # Industrial Select Sector SPDR
    "Metals & Mining":              "XME",    # SPDR S&P Metals & Mining
    "Real Estate":                  "XLRE",   # Real Estate Select Sector SPDR
    "Utilities":                    "XLU",    # Utilities Select Sector SPDR
    "Consumer Staples":             "XLP",    # Consumer Staples Select Sector SPDR
    "Consumer Discretionary Rest":  "XLY",    # Consumer Discr. Select Sector SPDR
}

# Internes Ticker-Symbol für den Volatilitätsindex (CBOE VIX).
VIX_TICKER = "VIX"

# Normalisierung: Finnhub liefert im Feld `finnhubIndustry` ein gemischtes
# Vokabular — teils Sektor-Ebene ("Consumer Cyclical"), teils Industrie-Ebene
# ("Semiconductors"), teils Yahoo-Bezeichnungen. Dieses Dict bildet alle bekannten
# Varianten auf die Sub-Sektor-Namen aus SUB_SECTOR_ETFS ab.
# Nicht auflösbare Werte werden in src/db.py mit WARN geloggt (sector_id bleibt
# NULL), damit die Liste bewusst per Commit wächst statt still zu versagen.
# Der Lookup ist case- und whitespace-insensitiv (s. db._SECTOR_ALIAS_LOOKUP).
#
# Welche Werte bewusst NICHT gemappt sind und warum, steht am Ende des Dicts.
# Grundregel: lieber ungemappt als falsch gemappt — ein Momentum-Check gegen ein
# fremdes Instrument erzeugt aktiv falsche Signale, ein fehlender Check nur keine.
SECTOR_ALIASES: dict[str, str] = {
    # --- Sub-Sektor-Namen auf sich selbst (Direkttreffer) ---
    "Semiconductors":              "Semiconductors",
    "Software":                    "Software",
    "Technology Hardware":         "Technology Hardware",
    "Biotech":                     "Biotech",
    "MedTech":                     "MedTech",
    "Pharma":                      "Pharma",
    "Healthcare Rest":             "Healthcare Rest",
    "Oil & Gas":                   "Oil & Gas",
    "Clean Energy":                "Clean Energy",
    "Banks":                       "Banks",
    "Financials Rest":             "Financials Rest",
    "Retail":                      "Retail",
    "Auto":                        "Auto",
    "Aerospace & Defense":         "Aerospace & Defense",
    "Transport":                   "Transport",
    "Industrials Rest":            "Industrials Rest",
    "Metals & Mining":             "Metals & Mining",
    "Real Estate":                 "Real Estate",
    "Utilities":                   "Utilities",
    "Consumer Staples":            "Consumer Staples",
    "Consumer Discretionary Rest": "Consumer Discretionary Rest",
    # --- Technologie ---
    "Semiconductors & Semiconductor Equipment":   "Semiconductors",
    "IT Services":                                "Software",
    "Internet":                                   "Software",
    "Information Technology Services":            "Software",
    "Technology":                                 "Technology Hardware",
    "Information Technology":                     "Technology Hardware",
    "Electronic Equipment":                       "Technology Hardware",
    "Computers & Peripherals":                    "Technology Hardware",
    "Communications Equipment":                   "Technology Hardware",
    "Technology Hardware, Storage & Peripherals": "Technology Hardware",
    # --- Gesundheit (alle drei Sub-Sektoren zeigen auf XLV, s.o.) ---
    "Biotechnology":                    "Biotech",
    "Medical Devices":                  "MedTech",
    "Health Care Equipment & Supplies": "MedTech",
    "Life Sciences Tools & Services":   "MedTech",
    "Pharmaceuticals":                  "Pharma",
    "Drug Manufacturers":               "Pharma",
    "Health Care":                      "Healthcare Rest",
    "Healthcare":                       "Healthcare Rest",
    "Health Care Providers & Services": "Healthcare Rest",
    "Managed Health Care":              "Healthcare Rest",
    # --- Energie ---
    "Energy":                      "Oil & Gas",
    "Oil, Gas & Consumable Fuels": "Oil & Gas",
    "Energy Equipment & Services": "Oil & Gas",
    "Renewable Energy":            "Clean Energy",
    "Alternative Energy":          "Clean Energy",
    "Solar":                       "Clean Energy",
    # --- Finanzen: nur reine Banken auf KBWB, alles Uebrige auf den breiten XLF ---
    "Banking":                        "Banks",
    "Thrifts & Mortgage Finance":     "Banks",
    "Insurance":                      "Financials Rest",
    "Financial Services":             "Financials Rest",
    "Financial":                      "Financials Rest",
    "Diversified Financial Services": "Financials Rest",
    "Capital Markets":                "Financials Rest",
    "Financials":                     "Financials Rest",
    # --- Konsum zyklisch ---
    "Multiline Retail":                   "Retail",
    "Specialty Retail":                   "Retail",
    "Internet & Direct Marketing Retail": "Retail",
    "Distributors":                       "Retail",
    "Automobiles":                        "Auto",
    "Auto Components":                    "Auto",
    "Automobiles & Components":           "Auto",
    "Consumer Discretionary":             "Consumer Discretionary Rest",
    "Consumer Cyclical":                  "Consumer Discretionary Rest",
    "Hotels, Restaurants & Leisure":      "Consumer Discretionary Rest",
    "Textiles, Apparel & Luxury Goods":   "Consumer Discretionary Rest",
    "Leisure Products":                   "Consumer Discretionary Rest",
    "Diversified Consumer Services":      "Consumer Discretionary Rest",
    "Household Durables":                 "Consumer Discretionary Rest",
    "Homebuilding":                       "Consumer Discretionary Rest",
    # --- Konsum defensiv ---
    "Consumer Defensive":       "Consumer Staples",
    "Consumer products":        "Consumer Staples",
    "Food Products":            "Consumer Staples",
    "Beverages":                "Consumer Staples",
    "Tobacco":                  "Consumer Staples",
    "Household Products":       "Consumer Staples",
    "Personal Products":        "Consumer Staples",
    "Food & Staples Retailing": "Consumer Staples",
    # --- Industrie ---
    "Airlines":                         "Transport",
    "Road & Rail":                      "Transport",
    "Logistics & Transportation":       "Transport",
    "Transportation":                   "Transport",
    "Air Freight & Logistics":          "Transport",
    "Marine":                           "Transport",
    "Transportation Infrastructure":    "Transport",
    "Industrials":                      "Industrials Rest",
    "Machinery":                        "Industrials Rest",
    "Industrial Conglomerates":         "Industrials Rest",
    "Electrical Equipment":             "Industrials Rest",
    "Building":                         "Industrials Rest",
    "Building Products":                "Industrials Rest",
    "Construction":                     "Industrials Rest",
    "Commercial Services & Supplies":   "Industrials Rest",
    "Professional Services":            "Industrials Rest",
    "Business Services":                "Industrials Rest",
    "Trading Companies & Distributors": "Industrials Rest",
    # --- Rohstoffe: NUR Bergbau/Metalle. Chemie, Verpackung und Papier bleiben
    #     bewusst ungemappt — XME misst sie nicht (s. Kommentar oben). ---
    "Metals & Mining": "Metals & Mining",
    "Basic Materials": "Metals & Mining",
    # --- Immobilien ---
    "REITs":                                        "Real Estate",
    "Equity Real Estate Investment Trusts (REITs)": "Real Estate",
    "Real Estate Management & Development":         "Real Estate",
    # --- Versorger ---
    "Electric Utilities": "Utilities",
    "Gas Utilities":      "Utilities",
    "Water Utilities":    "Utilities",
    "Multi-Utilities":    "Utilities",
    # --- BEWUSST NICHT GEMAPPT (kein passender ETF bei Capital.com) ---
    # Communication Services, Media, Entertainment, Interactive Media & Services,
    # Telecommunication(+ Services), Diversified/Wireless Telecommunication Services
    #   -> kein Communication-ETF verfuegbar; GOOGL/META laufen ohne Guardrail.
    # Chemicals, Packaging, Containers & Packaging, Paper & Forest(+ Products),
    # Construction Materials, Constr. Mat., Materials
    #   -> nur Bergbau ist ueber XME abgedeckt, Chemie laeuft voellig anders.
}

SP500_MIN_MARKET_CAP_B = 5
SP500_MIN_ATR_PCT = 2.0
MAX_HOLD_DAYS = 5
HOLD_TARGET = "intraday"
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

CAPITAL_COM_BATCH_PAUSE = 12

CAPITAL_COM_API_KEY    = os.getenv("CAPITAL_COM_API_KEY")
CAPITAL_COM_IDENTIFIER = os.getenv("CAPITAL_COM_IDENTIFIER")  # account email/login
CAPITAL_COM_PASSWORD   = os.getenv("CAPITAL_COM_PASSWORD")
CAPITAL_COM_BASE_URL   = "https://demo-api-capital.backend-capital.com"

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

USE_FULL_SP500 = os.getenv("USE_FULL_SP500", "false").lower() == "true"

# Full S&P 500 ticker list. Replace with complete 500-symbol list before enabling USE_FULL_SP500.
SP500_FULL_TICKERS: list[str] = SP500_MVP_TICKERS  # stub — replace with full list
