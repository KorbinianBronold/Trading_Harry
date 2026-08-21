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
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
EMAIL_TO = os.getenv("EMAIL_TO")
EMAIL_FROM = os.getenv("EMAIL_FROM")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
PAID_API_KEY = os.getenv("PAID_API_KEY")
PAID_API_TYPE = os.getenv("PAID_API_TYPE", "polygon")

CLAUDE_MODEL_SONNET = "claude-sonnet-5"
CLAUDE_MODEL_HAIKU = "claude-haiku-4-5"
CLAUDE_MODEL_OPUS = "claude-opus-5"

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

# Mindestzahl Ticker in einem Sub-Sektor, damit das DB-basierte Momentum-Signal
# (Sprint 3B / D9) berechnet wird. Darunter ist der Durchschnitt statistisch
# wertlos und sector_momentum.db_momentum bleibt NULL.
SECTOR_DB_MOMENTUM_MIN_TICKERS = 3

# Sprint 3B / Plan 2 (B.3): ab wie vielen Signalen im selben Sub-Sektor die Mail
# vor Klumpenrisiko warnt. Reine Warnung, blockiert nie.
SECTOR_CLUSTER_WARN_AT = 3

# Sprint 3B / Plan 2 (B.3): VIX-Schwellen. Ueber HIGH_CONFIDENCE_ONLY gehen nur
# noch Signale mit confidence='high' durch, ueber NO_NEW_LONGS gar keine Longs mehr.
VIX_HIGH_CONFIDENCE_ONLY = 25.0
VIX_NO_NEW_LONGS = 35.0

# Sprint 3B / Plan 2 (B.3): ab welcher Kursluecke zwischen dem 15:00-Kurs und dem
# 16:10-Kurs die Mail warnt. Reine Warnung — ob das Signal durchfaellt, entscheidet
# die neu berechnete R/R-Ratio.
OPENING_GAP_WARN_PCT = 1.5

# D9 (B.3.1): solange False, blockiert der Sektor-Guardrail nie — er schreibt nur
# guardrail_rejects-Zeilen mit enforced=0. Erst auf True stellen, wenn die
# Sub-Sektor-Mapping-Abdeckung in der Weekly-Mail stabil hoch ist.
SECTOR_GUARDRAIL_STRICT = False

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
# Sprint 3C / Analyse-Pipeline-Umbau, Plan 2 (Trichter), Task 10: 80 -> 50 und
# ab sofort gelesen (broad_scan.cutoff_candidates()). War bis dahin tot.
# BATCH_SIZE_QUICK entfernt -- ebenfalls tot, quick_filter_batch() lief immer
# als ein Call ueber alle Ticker, nie in 30er-Batches.
MAX_DEEP_ANALYSIS = 50

# Sprint 3C / Analyse-Pipeline-Umbau, Plan 3a (Batch-Tiefenanalyse), Spec 20.3:
# Ziel-Batchgroesse der Phase-3-Tiefenanalyse. Ganze Sub-Sektoren werden bis zu
# diesem Wert gepackt (deep_analysis.build_batches()).
#
# 8 ist ein begruendeter STARTWERT, kein final getunter Wert -- Spec 19.2 wollte
# ihn erst nach dem Testlauf festschreiben. Herleitung: bei den 20 MVP-Aktien
# ergibt 8 genau 3 Batches (8/8/4) statt 20 Einzelcalls.
#
# ⚠️ Die max_tokens-Rechnung hier war urspruenglich mit TOKENS_PER_TICKER_DEEP=900
# gemacht (~9.200 bei n=8) und ist seit der C.10-Kalibrierung veraltet: mit dem
# jetzigen Wert (2500, s. deep_analysis.py) liefert max_tokens_for_batch(8)
# tatsaechlich 20.200 -- ueber der hier frueher genannten "~16.000er Zone", aber
# unkritisch, weil der Call ohnehin gestreamt laeuft (Spec 4.8/20.4). Verifiziert
# gegen die echte API (PROJECT_STATUS C.11): 0 Kappungen bei 47-54 % Auslastung.
# Ob 8 die beste Batchgroesse ist, bleibt weiterhin ungemessen -- nur EIN Wert
# lief im Verifikationslauf.
#
# ⚠️ Der C.11-Befund "0 Kappungen" oben gilt nur fuer claude-sonnet-4-6 (kein
# Denken ohne explizites thinking-Feld). Seit der 2026-08-20-Migration auf
# claude-sonnet-5 (adaptives Denken standardmaessig an, teilt sich die
# max_tokens-Decke mit dem Antworttext) kappten BEIDE Batches (n=8, n=4) beim
# ersten Versuch in einem Live-Messlauf -- C.9 reproduziert. TOKENS_PER_TICKER_DEEP
# deshalb auf 6000 angehoben (deep_analysis.py); im Verifikationslauf danach
# liefen beide Batches (n=8, n=3) im ersten Versuch sauber durch.
#
# ⚠️ Wer diese Zahlen erneut anfasst: unter adaptivem Denken beweist EIN sauberer
# Lauf nichts. In derselben Messreihe kappte Phase 0 (trend_analyzer) nur im
# zweiten von drei Laeufen und Phase 3b (commodities_crypto) nur im dritten --
# jeweils bei identischem Code und identischer Decke. Deshalb faengt seit dieser
# Migration jeder Claude-Aufrufer eine Kappung explizit ab (Batch-Pfade ueber
# BatchTruncatedError, die Einzelcalls ueber utils.call_claude_retry_on_truncation);
# die angehobenen Decken sind nur die Optimierung, die das Netz selten ausloest.
BATCH_SIZE_DEEP = 8

# Sprint 3C / Analyse-Pipeline-Umbau, Plan 2 (Trichter), Spec 4.7: ein Ticker
# qualifiziert technisch, sobald eine Richtung entsteht (Mehrheit ab zwei
# Teilindikatoren) UND der Trend nicht als schwach eingestuft ist (der
# Weak-ADX-Deckel drueckt die Staerke sonst auf 1). Vorlaeufig -- endgueltig
# nach dem Testlauf gegen echte Verteilungen (Spec 19.3).
TECH_MIN_FOR_DEEP = 2

# Sprint 3C / Analyse-Pipeline-Umbau, Plan 3b (Spec 5.3): ein Earnings-Termin
# in <= EARNINGS_WARNING_DAYS ist die einzige fundamentale Tatsache mit
# unmittelbarer Intraday-Wirkung -- er kann den Kurs springen lassen und
# entwertet damit das analytisch hergeleitete TP/SL. Fuer Rohstoffe/Krypto ist
# earnings_in_days immer None (Spec 4.7), der Check dort trivial erfuellt.
EARNINGS_WARNING_DAYS = 2

# Spec 5.5: Deckel fuer Divergenz-Kandidaten je Richtung, sortiert nach
# rank_score. UNBESTAETIGTER STARTWERT, kein Messergebnis -- der
# Verifikationslauf vom 2026-08-17 enthielt null Divergenzfaelle, der Deckel
# hat also noch nie gebunden (Spec 20.5). Dieselbe Klasse Zahl wie
# BATCH_SIZE_DEEP vor seiner eigenen Kalibrierung.
DIVERGENCE_TOP_N = 5

# Ticker-Deaktivierung (Sprint 3B / B.7, Entscheidung D3): ein Ticker, der
# wiederholt keine brauchbaren Daten liefert, wird nach TICKER_MAX_SKIPS Skips
# deaktiviert und erst nach TICKER_RETRY_AFTER_DAYS Tagen automatisch erneut
# versucht. Sofortiges Zuruecksetzen von Hand:
#   python setup/historical_loader.py --reactivate TICKER
TICKER_MAX_SKIPS = 20
TICKER_RETRY_AFTER_DAYS = 30

# Sprint 3D / Trainingsdaten-Fundament (Spec E1): gemeinsame Aufbewahrungsfrist
# fuer die vier Tabellen, aus denen das Lernmodul spaeter Merkmale zieht.
#
# ⚠️ Bis 2026-08-20 standen hier VIER verschiedene Literale direkt im SQL von
# cleanup_old_data() -- und news_summaries stand als einzige auf 30 Tagen, weil
# sie als Logtabelle angelegt wurde, BEVOR C.16 sie zur Trainingsdatenquelle
# machte. Man behielt das Label (outcomes, dauerhaft) und verlor nach einem
# Monat die Begruendung. Eine benannte Konstante macht die Frist zu einer
# bewussten Entscheidung statt zu einem uebersehenen Literal.
#
# Zwei Jahre, weil Saisonalitaet und Regimewechsel mehr als einen Jahreszyklus
# brauchen -- sonst lernt 3D ein einzelnes Marktjahr auswendig.
#
# ⚠️ GROESSE (die Datenbank reist bei jedem Lauf durch ein GitHub Release):
# bei 20 Tickern ~27 news_summaries- und ~20 cutoff_log-Zeilen taeglich, also
# grob 35.000 Zeilen in zwei Jahren -- wenige MB. Bei 500 Tickern waeren es
# ~557 news_summaries-Zeilen MIT VOLLTEXT und ~500 cutoff_log-Zeilen taeglich,
# zusammen mehrere hundert MB. Diese Frist gehoert deshalb bei einer
# Universumsvergroesserung erneut auf den Tisch (s. PROJECT_STATUS C.20).
LEARNING_RETENTION_DAYS = 730

RR_RATIO_DEFAULT = 2.0
# Spec G1/G2 (2026-08-21): ab welchem Bruchteil der typischen Tagesschwankung
# ein Stop als "ausserhalb des Rauschens" gilt. Anlass: alle sieben vorliegenden
# Outcomes waren sl_hit, SECHS davon an Tag 1, und der Stop lag bei 0,39-0,78
# einer Tagesspanne -- keiner darueber.
#
# ⚠️ UNBESTAETIGTER STARTWERT, und der Check dazu ist bewusst WEICH. Mit dieser
# Schwelle haette ein harter Check alle 14 damals vorliegenden Signale verworfen.
# Wer ihn scharf stellt, OHNE vorher die Verteilung in guardrail_rejects
# anzusehen, schaltet die Pipeline ab. Nach ~30 Outcomes ist die Zahl messbar.
STOP_MIN_INTRADAY_RANGE_FRAC = 0.8

# Spec G4: ab welchem Anteil des Morgen-Risikobudgets ein Setup um 16:10 als
# aufgebraucht gilt. HART durchgesetzt -- anders als oben ist hier nicht die
# Schwelle die offene Frage: bei drei Vierteln verbrauchtem Budget ist die
# Praemisse des Morgens widerlegt, bevor die Position eroeffnet wurde.
STOP_BUDGET_SPENT_MAX = 0.75

RR_RATIO_MIN_HARD = 1.5
MOMENTUM_LONG_MIN = 6.0
MOMENTUM_SHORT_MAX = 4.0

# Analyse-Pipeline-Umbau: Schwellen des deterministischen Technik-Signals.
# ADX misst Trendstaerke, nicht Richtung: unter 20 gilt der Markt als trendlos
# und die Signalstaerke wird gedeckelt, ueber 25 als klar trendend und die
# Staerke steigt. Bewusst Verstaerkungsfaktor, KEIN Filter -- ein Signal in
# einem trendlosen Markt landet weit unten, wird aber nicht verworfen.
ADX_WEAK_BELOW = 20.0
ADX_STRONG_ABOVE = 25.0
RSI_MIDLINE = 50.0

CFD_MARGIN_EUR = 500
CFD_LEVERAGE = 5

# Spec F7: 4,00 -> 6,00 mit der Universumsvergroesserung auf 142 Ticker
# (hochgerechnet ~4,92 EUR je Lauf). ⚠️ Der Deckel ist die letzte Sicherung
# gegen einen Kostenunfall -- angehoben, weil die GRUNDLAST steigt, nicht weil
# er stoert. Der Puffer von ~1,08 EUR deckt die Streuung, die adaptives Denken
# erzeugt (C.18).
MAX_COST_PER_RUN_EUR = 6.00
COST_WARN_THRESHOLD_EUR = 4.50
CLAUDE_PARALLEL_CALLS = 5

CAPITAL_COM_BATCH_PAUSE = 12

CAPITAL_COM_API_KEY    = os.getenv("CAPITAL_COM_API_KEY")
CAPITAL_COM_IDENTIFIER = os.getenv("CAPITAL_COM_IDENTIFIER")  # account email/login
CAPITAL_COM_PASSWORD   = os.getenv("CAPITAL_COM_PASSWORD")
CAPITAL_COM_BASE_URL   = "https://demo-api-capital.backend-capital.com"

# ⚠️ Diese Variable wird an GENAU EINER Stelle ausgewertet:
# src/universe.py:stock_universe(). Bis 2026-08-21 stand der Ausdruck
# "SP500_FULL_TICKERS if USE_FULL_SP500 else ..." fuenffach im Code (main.py 2x,
# db.py, universe.py, capital_provider.py) -- dieselbe Streuung, die bei
# LEARNING_RETENTION_DAYS eine von vier Tabellen auf einer abweichenden Frist
# stehen liess. Ein Test (test_universe.py) haelt die Einzelquelle fest.
USE_FULL_SP500 = os.getenv("USE_FULL_SP500", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Produktivuniversum: 150 Ticker, sektor-balanciert (2026-08-21).
#
# Ausgewaehlt aus den 451 verifizierten SP500_FULL_TICKERS nach vier Regeln:
#   1. Die 20 SP500_MVP_TICKERS sind gesetzt (laengste Historie).
#   2. Jeder Sub-Sektor bekommt mindestens SECTOR_DB_MOMENTUM_MIN_TICKERS (3).
#      Die Zahl ist nicht gegriffen: darunter liefert compute_sector_db_momentum()
#      strukturell NULL, der Sub-Sektor traegt also gar kein Signal bei.
#   3. Die restlichen Plaetze proportional zur Sektorgroesse im S&P 500.
#   4. Innerhalb eines Sub-Sektors entscheidet das durchschnittliche
#      Dollar-Volumen der letzten 60 Bars -- bei HOLD_TARGET="intraday" mit
#      CFD-Hebel 5 bestimmt Liquiditaet den Spread und die Ausfuehrungsqualitaet.
#
# Verteilung ueber die Sub-Sektoren:
#   Financials Rest 15, Industrials Rest 15, Technology Hardware 11
#   Healthcare Rest 10, Consumer Staples 9, Real Estate 9
#   Utilities 9, Consumer Discretionary Rest 8, Oil & Gas 8
#   Retail 8, Semiconductors 7, Banks 6
#   Transport 6, Aerospace & Defense 5, Biotech 5
#   Pharma 5, Auto 4, MedTech 4
#   Metals & Mining 4
#
# ⚠️ GOOGL und META tragen bei Finnhub `Media` und bleiben damit ungemappt --
# fuer Communication fuehrt Capital.com keinen ETF (s. SUB_SECTOR_ETFS). Sie
# laufen bewusst ohne Sektor-Guardrail (D6), sind als MVP-Ticker aber gesetzt.
#
# ⚠️ "Clean Energy" (ICLN) bleibt leer: Finnhub fuehrt FSLR als `Semiconductors`,
# und kein anderer S&P-500-Wert faellt dort hinein. Der Sub-Sektor ist mit
# diesem Universum strukturell unbesetzbar -- kein Auswahlfehler.
#
# ⚠️ Wer diese Liste aendert, braucht VORHER den Backfill:
# setup/historical_loader.py --universe. Ein Ticker ohne Historie wird als
# 'insufficient bars' uebersprungen und deaktiviert sich nach TICKER_MAX_SKIPS.
# ---------------------------------------------------------------------------
SP500_PROD_TICKERS: list[str] = SP500_MVP_TICKERS + [
    "ABNB", "ABT", "ADBE", "ADP", "AEE", "AEP", "ALL", "AMAT", "AMD",
    "AMGN", "AMT", "APH", "APP", "APTV", "AXP", "AZO", "BA", "BKNG",
    "BLK", "BMY", "BNY", "C", "CASY", "CAT", "CEG", "CL", "CMI", "COF",
    "COHR", "COIN", "COP", "COR", "COST", "CVX", "D", "DAL", "DASH", "DE",
    "DELL", "DHI", "DHR", "DLR", "DUK", "ELV", "EME", "EOG", "EQIX",
    "ESS", "ETN", "F", "FANG", "FCX", "FDX", "GE", "GILD", "GLW", "GM",
    "GS", "GWW", "HCA", "HLT", "HOOD", "HUM", "IBM", "IDXX", "INTC",
    "ISRG", "KMB", "KO", "LMT", "MAR", "MCD", "MCK", "MCO", "MLM", "MNST",
    "MPC", "MRK", "MRVL", "MS", "MSCI", "MTB", "MTD", "MU", "NEE", "NEM",
    "NOC", "NSC", "NUE", "NVR", "O", "ORCL", "PANW", "PEP", "PH", "PLD",
    "PLTR", "PM", "PNC", "PSA", "PSX", "PWR", "RCL", "REGN", "SBUX", "SO",
    "SPG", "SPGI", "STLD", "STX", "SYK", "TDG", "TJX", "TMO", "UBER",
    "ULTA", "UNP", "UPS", "URI", "USB", "VLO", "VRT", "VRTX", "VST",
    "WAT", "WDC", "WEC", "WELL", "WFC", "ZTS",
]

# Vollstaendiges Aktien-Universum (Spec F4/F5; 2026-08-21 von 142 auf 451).
# Quelle: die S&P-500-Konstituentenliste als CSV
# (github.com/datasets/s-and-p-500-companies), 503 Symbole, Punktnotation auf
# unsere Konvention normalisiert (BRK.B -> BRK-B).
#
# ⚠️ JEDES Symbol ist per DIREKTEM Epic-Abruf gegen Capital.com verifiziert
# (/markets?epics=), ausdruecklich NICHT ueber die Volltextsuche -- die liefert
# laut SUB_SECTOR_ETFS-Kommentar zu jedem Kuerzel irgendetwas.
# 450 von 503 loesten auf (89 %), 53 nicht; sie fehlen bewusst. Ein Ticker ohne
# Kurse wuerde als 'insufficient bars' uebersprungen, zaehlte Richtung
# TICKER_MAX_SKIPS und deaktivierte sich selbst.
# Nicht auffindbar: ACGL AIZ AMCR APO ARES ATO AXON BALL BF-B BG BLDR BRO CPAY
# CRH CRL CTVA DD EG EMR EVRG FDXF FERG FICO FISV FITB FIX FLEX GEV HONA HUBB
# HWM IEX J KVUE LHX LYB NTRS PCG PSKY Q RVTY SNDK SOLV STE TEL TKO TT TYL VLTO
# WBD WRB WST XYZ
# Einzige Handkorrektur: FI ergaenzt -- die CSV fuehrt Fiserv noch als FISV,
# Capital.com kennt nur das neue Symbol.
#
# ⚠️ Die Liste alleine vergroessert nichts: es braucht USE_FULL_SP500=true UND
# vorher den Backfill (historical_loader.py). Der Gap-Mechanismus in
# data_collector._fill_price_gaps() legt KEINE Historie an -- er fuellt nur
# Loecher in vorhandener; sein eigener Docstring sagt das.
SP500_FULL_TICKERS: list[str] = SP500_MVP_TICKERS + [
    "A", "ABNB", "ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE",
    "AEP", "AES", "AFL", "AIG", "AJG", "AKAM", "ALB", "ALGN", "ALL", "ALLE",
    "AMAT", "AMD", "AME", "AMGN", "AMP", "AMT", "ANET", "AON", "AOS", "APA",
    "APD", "APH", "APP", "APTV", "ARE", "AVY", "AWK", "AXP", "AZO", "BA",
    "BAC", "BAX", "BBY", "BDX", "BEN", "BIIB", "BKNG", "BKR", "BLK", "BMY",
    "BNY", "BR", "BSX", "BX", "BXP", "C", "CAH", "CARR", "CASY", "CAT",
    "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW", "CEG", "CF", "CFG",
    "CHD", "CHRW", "CHTR", "CI", "CIEN", "CINF", "CL", "CLX", "CMCSA",
    "CME", "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COHR", "COIN", "COO",
    "COP", "COR", "COST", "CPRT", "CPT", "CRM", "CRWD", "CSCO", "CSGP",
    "CSX", "CTAS", "CTSH", "CVNA", "CVS", "CVX", "D", "DAL", "DASH", "DDOG",
    "DE", "DECK", "DELL", "DG", "DGX", "DHI", "DHR", "DIS", "DLR", "DLTR",
    "DOC", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN", "DXCM",
    "EBAY", "ECHO", "ECL", "ED", "EFX", "EIX", "EL", "ELV", "EME", "EOG",
    "EQIX", "EQT", "ERIE", "ES", "ESS", "ETN", "ETR", "EW", "EXC", "EXE",
    "EXPD", "EXPE", "EXR", "F", "FANG", "FAST", "FCX", "FDS", "FDX", "FE",
    "FFIV", "FI", "FIS", "FOX", "FOXA", "FRT", "FSLR", "FTNT", "FTV", "GD",
    "GDDY", "GE", "GEHC", "GEN", "GILD", "GIS", "GL", "GLW", "GM", "GNRC",
    "GOOG", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL", "HAS", "HBAN", "HCA",
    "HIG", "HII", "HLT", "HON", "HOOD", "HPE", "HPQ", "HRL", "HSIC", "HST",
    "HSY", "HUM", "IBKR", "IBM", "ICE", "IDXX", "IFF", "INCY", "INTC",
    "INTU", "INVH", "IP", "IQV", "IR", "IRM", "ISRG", "IT", "ITW", "IVZ",
    "JBHT", "JBL", "JCI", "JKHY", "KDP", "KEY", "KEYS", "KHC", "KIM", "KKR",
    "KLAC", "KMB", "KMI", "KO", "KR", "L", "LDOS", "LEN", "LH", "LII",
    "LIN", "LITE", "LMT", "LNT", "LOW", "LRCX", "LULU", "LUV", "LVS", "LYV",
    "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO", "MDLZ", "MDT", "MET",
    "MGM", "MKC", "MLM", "MMM", "MNST", "MO", "MOS", "MPC", "MPWR", "MRK",
    "MRNA", "MRSH", "MRVL", "MS", "MSCI", "MSI", "MTB", "MTD", "MU", "NCLH",
    "NDAQ", "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC", "NOW", "NRG",
    "NSC", "NTAP", "NUE", "NVR", "NWS", "NWSA", "NXPI", "O", "ODFL", "OKE",
    "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY", "PANW", "PAYX", "PCAR",
    "PEG", "PEP", "PFE", "PFG", "PGR", "PH", "PHM", "PKG", "PLD", "PLTR",
    "PM", "PNC", "PNR", "PNW", "PODD", "PPG", "PPL", "PRU", "PSA", "PSX",
    "PTC", "PWR", "PYPL", "QCOM", "RCL", "RDDT", "REG", "REGN", "RF", "RJF",
    "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX", "SBAC", "SBUX",
    "SCHW", "SHW", "SJM", "SLB", "SMCI", "SNA", "SNPS", "SO", "SPG", "SPGI",
    "SRE", "STLD", "STT", "STX", "STZ", "SW", "SWK", "SWKS", "SYF", "SYK",
    "SYY", "T", "TAP", "TDG", "TDY", "TECH", "TER", "TFC", "TGT", "TJX",
    "TMO", "TMUS", "TPL", "TPR", "TRGP", "TRMB", "TROW", "TRV", "TSCO",
    "TSN", "TTD", "TTWO", "TXN", "TXT", "UAL", "UBER", "UDR", "UHS", "ULTA",
    "UNP", "UPS", "URI", "USB", "VEEV", "VICI", "VLO", "VMC", "VMRK",
    "VRSK", "VRSN", "VRT", "VRTX", "VST", "VTR", "VTRS", "VZ", "WAB", "WAT",
    "WDAY", "WDC", "WEC", "WELL", "WFC", "WM", "WMB", "WSM", "WTW", "WY",
    "WYNN", "XEL", "XYL", "YUM", "ZBH", "ZBRA", "ZTS",
]
