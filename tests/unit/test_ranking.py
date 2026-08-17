from unittest.mock import MagicMock
import pytest

import config
from src import db
from src.ranking import rank_and_persist, score_total, _classify, _rank_key


def _analysis(ticker: str, direction: str = "long", momentum: float = 7.0,
              hold_days: int = 2, intraday: float = 1.5,
              total_score: float = 7.5, prob: int = 68,
              rr: float = 2.5, current: float = 100.0,
              asset_class: str = "stock") -> dict:
    """Minimal guardrail-passing analysis dict, with knobs."""
    tp = current + 5.0 if direction == "long" else current - 5.0
    sl = current - 2.0 if direction == "long" else current + 2.0
    return {
        "ticker": ticker, "asset_class": asset_class,
        "direction": direction, "confidence": "high",
        "current_price": current, "tp_price": tp, "sl_price": sl,
        "tp_pct": 5.0, "sl_pct": 2.0, "rr_ratio": rr,
        "total_score": total_score, "probability_pct": prob,
        "hold_days_recommended": hold_days,
        "intraday_range_pct": intraday,
        "summary": "ok", "earnings_warning": False,
        "sources_used": ["a.com", "b.com"],
        "signal_consistency_check": "ok",
        "scores": {
            "market_environment": {"value": 7.0, "evidence": ["x", "y"]},
            "company_quality":    {"value": 7.0, "evidence": ["x", "y"]},
            "valuation":           {"value": 6.0, "evidence": ["x", "y"]},
            "momentum":           {"value": momentum, "evidence": ["x", "y"]},
            "risk":               {"value": 6.0, "evidence": ["x", "y"]},
            "sector_trend":       {"value": 7.0, "evidence": ["x", "y"]},
            "catalyst":           {"value": 7.0, "evidence": ["x", "y"]},
            "policy_risk":        {"value": 6.0, "evidence": ["x", "y"]},
        },
    }


def _market_ctx() -> dict:
    # Kein "sector"-Key mehr: der Sektor kommt seit Task 8 aus ticker_sectors,
    # nicht aus dem marktweiten Kontext-Dict (dort war er ohnehin immer leer).
    return {"vix_level": 14.0, "market_regime": "risk_on"}


@pytest.fixture
def valid_analysis() -> dict:
    """Guardrail-taugliches Analyse-Dict fuer AAPL long — mehrere Ranking-Tests
    bauten dieses Dict bisher inline; seit Task 10 einmal als Fixture
    herausgezogen (Sprint 3B / Plan 2)."""
    return _analysis("AAPL", momentum=8.0)


def _seed_sector_for(conn, ticker="AAPL", sector="Technology Hardware"):
    """Ordnet `ticker` einem existierenden Sub-Sektor zu (aus init_schema's
    Seed) — Grundlage fuer die Momentum-Checks in den Task-10-Tests."""
    sid = conn.execute("SELECT id FROM sectors WHERE name=?", (sector,)).fetchone()["id"]
    conn.execute("INSERT OR REPLACE INTO ticker_sectors (ticker, sector_id) VALUES (?,?)",
                 (ticker, sid))
    conn.commit()
    return sid


def test_score_total_uses_dimension_weights(valid_analysis):
    t = score_total(valid_analysis)
    assert 6.0 < t < 8.5


def test_rank_and_persist_top_10_long_and_short(in_memory_db):
    db.init_schema(in_memory_db)
    stocks = (
        [_analysis(f"L{i}", direction="long", momentum=8.0, prob=70 - i)
         for i in range(15)]
        + [_analysis(f"S{i}", direction="short", momentum=3.0, prob=70 - i)
           for i in range(15)]
    )
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=stocks, commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert len(out["top_long"]) == 10
    assert len(out["top_short"]) == 10
    assert out["top_long"][0]["probability_pct"] >= out["top_long"][-1]["probability_pct"]
    rows = in_memory_db.execute(
        "SELECT direction, COUNT(*) AS n FROM predictions GROUP BY direction"
    ).fetchall()
    counts = {r["direction"]: r["n"] for r in rows}
    assert counts["long"] == 10
    assert counts["short"] == 10


def test_rank_drops_guardrail_failures(in_memory_db, valid_analysis):
    db.init_schema(in_memory_db)
    good = valid_analysis
    bad_hold = _analysis("BAD1", momentum=8.0, hold_days=6)
    bad_range = _analysis("BAD2", momentum=8.0, intraday=0.5)
    bad_momentum = _analysis("BAD3", direction="long", momentum=3.0)
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[good, bad_hold, bad_range, bad_momentum],
        commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    tickers = [p["ticker"] for p in out["top_long"]]
    assert tickers == ["AAPL"]


def test_rank_drops_direction_none(in_memory_db, valid_analysis):
    db.init_schema(in_memory_db)
    valid_analysis["direction"] = "none"
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert out["top_long"] == []
    assert out["top_short"] == []


def test_rank_keeps_all_commodities_crypto(in_memory_db):
    db.init_schema(in_memory_db)
    cc = [
        _analysis("GC=F", asset_class="commodity"),
        _analysis("SI=F", asset_class="commodity"),
        _analysis("BTC-USD", asset_class="crypto"),
    ]
    out = rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[], commodity_crypto_analyses=cc,
        market_context=_market_ctx(),
    )
    assert {a["ticker"] for a in out["commodities_crypto"]} == {"GC=F", "SI=F", "BTC-USD"}


def test_rank_persists_predictions_with_score_dimensions(in_memory_db, valid_analysis):
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-05-19", run_type="close",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    row = in_memory_db.execute(
        "SELECT score_momentum, score_company, hold_days_recommended, "
        "intraday_range_pct, learnable FROM predictions WHERE ticker='AAPL'"
    ).fetchone()
    assert row["score_momentum"] == 8.0
    assert row["hold_days_recommended"] == 2
    assert row["intraday_range_pct"] == 1.5
    assert row["learnable"] == 1


# ---------- guardrail_rejects + Sektor aus der DB (Sprint 3B / Plan 1, Task 8) ----------


def test_guardrail_reject_is_persisted(in_memory_db):
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("BAD", momentum=8.0, rr=1.0)],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
    )
    rows = db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "BAD"
    assert rows[0]["direction"] == "long"
    assert rows[0]["run_type"] == "pre_market"
    assert rows[0]["rule"] == "rr_ratio"
    assert rows[0]["enforced"] == 1
    assert "R/R" in rows[0]["detail"]


def test_rejected_analysis_is_not_persisted_as_prediction(in_memory_db):
    """Ein Reject wird protokolliert, aber niemals zur Prediction."""
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("BAD", momentum=8.0, rr=1.0)],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
    )
    n = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM predictions").fetchone()["n"]
    assert n == 0


def test_direction_none_is_not_logged_as_guardrail_reject(in_memory_db):
    """direction='none' ist eine bewusste Enthaltung, kein Regelverstoss."""
    db.init_schema(in_memory_db)
    a = _analysis("NEUTRAL", momentum=8.0)
    a["direction"] = "none"
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    assert db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27") == []


# ---------- D2: Enthaltungen sind sichtbar, aber keine Rejects ----------

def test_abstentions_are_counted_in_the_phase_4_summary(in_memory_db, caplog):
    """Am 2026-08-04 verschwanden 8 von 9 Kandidaten lautlos: sie hatten
    direction='none' und wurden ohne Logzeile uebersprungen. Im Log stand genau
    eine Drop-Begruendung (CL=F) und darunter "0 long, 0 short, 0 persisted" --
    die Luecke zwischen 9 Analysen und 1 Begruendung war nicht erklaerbar."""
    import logging
    db.init_schema(in_memory_db)
    abstain = _analysis("NEUTRAL", momentum=8.0)
    abstain["direction"] = "none"
    cc_abstain = _analysis("GC=F", asset_class="commodity", momentum=8.0)
    cc_abstain["direction"] = "none"

    with caplog.at_level(logging.INFO, logger="shares_future.ranking"):
        rank_and_persist(
            conn=in_memory_db, date="2026-07-27", run_type="pre_market",
            stock_analyses=[abstain], commodity_crypto_analyses=[cc_abstain],
            market_context=_market_ctx(),
        )

    assert "2" in caplog.text and "enthalten" in caplog.text.lower()


def test_abstentions_stay_out_of_guardrail_rejects(in_memory_db, caplog):
    """Sichtbar heisst nicht "als Regelverstoss gezaehlt": eine Enthaltung ist
    ein legitimes Analyseergebnis. Wuerde sie in guardrail_rejects landen,
    verzerrte sie die Weekly-Auswertung, welche Regel wie oft greift."""
    import logging
    db.init_schema(in_memory_db)
    a = _analysis("NEUTRAL", momentum=8.0)
    a["direction"] = "none"

    with caplog.at_level(logging.INFO, logger="shares_future.ranking"):
        rank_and_persist(
            conn=in_memory_db, date="2026-07-27", run_type="pre_market",
            stock_analyses=[a], commodity_crypto_analyses=[],
            market_context=_market_ctx(),
        )

    assert db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27") == []
    assert "enthalten" in caplog.text.lower()


def test_commodity_crypto_rejects_are_persisted_too(in_memory_db):
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[],
        commodity_crypto_analyses=[
            _analysis("GC=F", asset_class="commodity", intraday=0.2),
        ],
        market_context=_market_ctx(),
    )
    rows = db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27")
    assert [r["ticker"] for r in rows] == ["GC=F"]
    assert rows[0]["rule"] == "intraday_range"


def test_guardrail_reject_rule_names_are_grouped_per_violation(in_memory_db):
    """Die Weekly-Mail aggregiert nach `rule` — jede Verletzung braucht daher
    einen stabilen, kurzen Namen statt der rohen Fehlermeldung."""
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[
            _analysis("R", momentum=8.0, rr=1.0),
            _analysis("H", momentum=8.0, hold_days=9),
            _analysis("I", momentum=8.0, intraday=0.3),
            _analysis("M", direction="long", momentum=2.0),
        ],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
    )
    rows = db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27")
    by_ticker = {r["ticker"]: r["rule"] for r in rows}
    assert by_ticker == {
        "R": "rr_ratio",
        "H": "hold_days",
        "I": "intraday_range",
        "M": "momentum_consistency",
    }


def test_guardrail_reject_rule_name_for_missing_field(in_memory_db):
    db.init_schema(in_memory_db)
    a = _analysis("NOSUM", momentum=8.0)
    a["summary"] = None
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[a], commodity_crypto_analyses=[],
        market_context=_market_ctx(),
    )
    rows = db.load_guardrail_rejects_since(in_memory_db, since="2026-07-27")
    assert rows[0]["rule"] == "required_field"


def test_prediction_row_takes_sector_from_ticker_sectors(in_memory_db):
    db.init_schema(in_memory_db)
    sid = db.resolve_sector_id(in_memory_db, "Semiconductors")
    db.upsert_ticker_sector(in_memory_db, "NVDA", sid)

    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("NVDA", momentum=8.0)],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
    )
    row = in_memory_db.execute(
        "SELECT sector, vix_at_prediction, market_regime "
        "FROM predictions WHERE ticker='NVDA'"
    ).fetchone()
    assert row["sector"] == "Semiconductors"
    assert row["vix_at_prediction"] == 14.0
    assert row["market_regime"] == "risk_on"


def test_prediction_row_sector_is_none_when_unmapped(in_memory_db):
    db.init_schema(in_memory_db)
    rank_and_persist(
        conn=in_memory_db, date="2026-07-27", run_type="pre_market",
        stock_analyses=[_analysis("UNMAPPED", momentum=8.0)],
        commodity_crypto_analyses=[], market_context=_market_ctx(),
    )
    row = in_memory_db.execute(
        "SELECT sector FROM predictions WHERE ticker='UNMAPPED'"
    ).fetchone()
    assert row["sector"] is None


# ---------- B.3-Checks weich ausgefuehrt (Sprint 3B / Plan 2, Task 10) ----------


def test_ranking_writes_sector_momentum_onto_the_prediction(in_memory_db, valid_analysis):
    """3D kann die Korrelation nur ueber predictions rechnen — verworfene Signale
    haben nie ein Outcome."""
    db.init_schema(in_memory_db)
    sid = _seed_sector_for(in_memory_db)
    from src.ranking import rank_and_persist
    rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={}, sector_momentum={sid: {"etf_momentum": 1.2,
                                                  "db_momentum": 0.8,
                                                  "ticker_count": 4}},
    )
    row = in_memory_db.execute(
        "SELECT sector_etf_momentum, sector_db_momentum FROM predictions").fetchone()
    assert row["sector_etf_momentum"] == 1.2
    assert row["sector_db_momentum"] == 0.8


def test_soft_check_writes_reject_row_but_keeps_the_signal(in_memory_db, valid_analysis):
    """E4: pre_market erhebt und warnt, blockiert aber nicht."""
    db.init_schema(in_memory_db)
    sid = _seed_sector_for(in_memory_db)
    from src.ranking import rank_and_persist
    out = rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={"vix_level": 40.0},
        sector_momentum={sid: {"etf_momentum": -1.2, "db_momentum": None,
                               "ticker_count": 1}},
        enforce_checks=False,
    )
    assert len(out["top_long"]) == 1, "weicher Check darf nicht blockieren"
    rejects = in_memory_db.execute(
        "SELECT rule, enforced FROM guardrail_rejects").fetchall()
    rules = {r["rule"] for r in rejects}
    assert "vix_no_new_longs" in rules
    assert "sector_momentum_partial" in rules
    assert all(r["enforced"] == 0 for r in rejects)


def test_no_reject_row_when_no_check_fires(in_memory_db, valid_analysis):
    """B.3.1: kein Signal vorhanden -> kein Check, KEIN Log-Eintrag."""
    db.init_schema(in_memory_db)
    from src.ranking import rank_and_persist
    rank_and_persist(
        conn=in_memory_db, date="2026-07-30", run_type="pre_market",
        stock_analyses=[valid_analysis], commodity_crypto_analyses=[],
        market_context={}, sector_momentum={},
    )
    n = in_memory_db.execute(
        "SELECT COUNT(*) AS n FROM guardrail_rejects").fetchone()["n"]
    assert n == 0


@pytest.mark.parametrize("message, expected", [
    ("Required field missing: summary",                        "required_field"),
    ("Too few sources: 1 < 2",                                 "sources"),
    ("Dimension momentum: too few evidence items (1 < 2)",     "evidence"),
    ("R/R 1.2 below hard minimum 1.5",                         "rr_ratio"),
    ("Signal consistency: long momentum 3.0 < 6.0",            "momentum_consistency"),
    ("Haltedauer > 5 Tage - nicht CFD-geeignet",               "hold_days"),
    ("Intraday-Range < 1.0% - nicht CFD-geeignet",             "intraday_range"),
    ("Confidence 'high' incompatible with data_quality 'low'", "confidence_data_quality"),
    ("Long TP 99 not above entry 100",                         "tp_sl_direction"),
    ("Short SL 99 not above entry 100",                        "tp_sl_direction"),
    ("Etwas voellig Neues",                                    "other"),
])
def test_rule_name_maps_every_guardrail_message(message, expected):
    """Jede Meldung aus GuardrailsChecker.check_analysis() muss auf einen
    stabilen Regelnamen fallen — 'other' ist der Auffangfall, nicht der Normalfall."""
    from src.ranking import _rule_name
    assert _rule_name(message) == expected


# ---------- D3: ein Lauf ohne Predictions warnt von sich aus ----------

def test_zero_persisted_predictions_raises_a_warning(in_memory_db, caplog):
    """Unabhaengig von der Ursache: "nichts persistiert" darf nie unbemerkt in
    einem gruenen Job verschwinden. Am 2026-08-04 endeten drei Laeufe genau so
    -- technisch erfolgreich, inhaltlich leer, ohne ein einziges WARNING."""
    import logging
    db.init_schema(in_memory_db)
    a = _analysis("NEUTRAL", momentum=8.0)
    a["direction"] = "none"

    with caplog.at_level(logging.WARNING, logger="shares_future.ranking"):
        rank_and_persist(
            conn=in_memory_db, date="2026-07-27", run_type="pre_market",
            stock_analyses=[a], commodity_crypto_analyses=[],
            market_context=_market_ctx(),
        )

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings, "Ein Lauf ohne Predictions muss warnen"
    assert "keine" in caplog.text.lower() or "0" in caplog.text


def test_no_warning_when_predictions_were_persisted(in_memory_db, caplog):
    """Die Warnung muss den Normalfall in Ruhe lassen, sonst stumpft sie ab."""
    import logging
    db.init_schema(in_memory_db)

    with caplog.at_level(logging.WARNING, logger="shares_future.ranking"):
        result = rank_and_persist(
            conn=in_memory_db, date="2026-07-27", run_type="pre_market",
            stock_analyses=[_analysis("AAPL", momentum=8.0)],
            commodity_crypto_analyses=[],
            market_context=_market_ctx(),
        )

    assert result["top_long"] or result["top_short"], "Testaufbau: es muss etwas durchkommen"
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


# ---------- _classify() / _rank_key() (Sprint 3B / Plan 3b, Task 7) ----------


def _stock_analysis(direction="long"):
    return {"ticker": "AAPL", "direction": direction, "scores": {
        dim: {"value": 7.0 if direction == "long" else 3.0,
              "evidence": ["a", "b"], "evidence_quality": "ok"}
        for dim in ["market_environment", "company_quality", "valuation",
                    "momentum", "risk", "sector_trend", "catalyst", "policy_risk"]
    }}


def test_classify_core_when_tech_matches():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "long", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "core"
    assert strength == 8
    assert rank_score == 24


def test_classify_divergence_when_tech_neutral():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "neutral", "tech_strength": 0}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "divergence"
    assert rank_score is None  # tech_strength=0 -> NULL, nie 0 (Spec 20.5 #3)


def test_classify_conflict_when_tech_opposes():
    a = _stock_analysis("long")
    ctx = {"tech_direction": "short", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "conflict"


def test_classify_missing_sidecar_entry_treated_as_divergence():
    """Kein Sidecar-Eintrag (leeres ctx) -- konservativ wie neutral, nicht
    blockierend wie ein Konflikt."""
    a = _stock_analysis("long")
    klasse, strength, rank_score = _classify(a, {}, cc=False)
    assert klasse == "divergence"


def test_classify_commodity_never_conflicts():
    """Spec 20.5 #2: Rohstoffe/Krypto werden nie disqualifiziert, auch nicht
    bei gegenlaeufigem Technik-Signal."""
    a = _stock_analysis("long")
    a["ticker"] = "GC=F"
    ctx = {"tech_direction": "short", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=True)
    assert klasse == "core"
    assert rank_score == 24  # trotzdem gebildet, fuer die Sortierung


def test_classify_zero_analysis_strength_yields_null_not_zero():
    """Spec 5.4: rank_score ist NULL, nie 0 -- auch wenn NICHT das
    Technik-Signal, sondern analysis_strength der Nullfaktor ist. Erreichbar
    ueber eine Analyse, die die Guardrails besteht (momentum-WERT stimmt), aber
    keine Dimension zaehlbar belegt (alle thin)."""
    a = _stock_analysis("long")
    for dim in a["scores"]:
        a["scores"][dim]["evidence_quality"] = "thin"
    ctx = {"tech_direction": "long", "tech_strength": 3}
    klasse, strength, rank_score = _classify(a, ctx, cc=False)
    assert klasse == "core"
    assert strength == 0
    assert rank_score is None, "0 hiesse 'schlechtester Kandidat', nicht 'nicht rankbar'"


def test_classify_commodity_without_tech_signal_gets_null_rank_score():
    a = _stock_analysis("long")
    a["ticker"] = "SI=F"
    klasse, strength, rank_score = _classify(a, {}, cc=True)
    assert klasse == "core"
    assert rank_score is None


def test_rank_key_sorts_by_rank_score_descending():
    high = _rank_key(strength=6, rank_score=18, ticker="NVDA")
    low = _rank_key(strength=4, rank_score=12, ticker="BRK-B")
    assert high < low  # tuple-Vergleich: kleinerer Schluessel = weiter vorn


def test_rank_key_falls_back_to_strength_when_rank_score_is_none():
    """Zwei Divergenz-Kandidaten (rank_score immer None) sortieren nach
    analysis_strength, nicht per Zufall gleich (Spec 5.4-Fussnote)."""
    stronger = _rank_key(strength=6, rank_score=None, ticker="AAPL")
    weaker = _rank_key(strength=2, rank_score=None, ticker="ZZZZ")
    assert stronger < weaker


def test_rank_key_ticker_breaks_ties_deterministically():
    a = _rank_key(strength=4, rank_score=12, ticker="AAA")
    b = _rank_key(strength=4, rank_score=12, ticker="ZZZ")
    assert a < b
