"""Unit-Tests für setup/verify_epics.py — reine Offline-Tests gegen einen
gemockten Provider, es geht nie ein echter Capital.com-Request raus."""
from unittest.mock import MagicMock

import config
from setup.verify_epics import (
    etf_candidates, format_report, looks_like_fund, main, pick_best,
    resolve, search_terms,
)


def _market(epic: str, name: str | None = None,
            status: str = "TRADEABLE", itype: str = "SHARES") -> dict:
    return {
        "epic": epic,
        "instrumentName": name if name is not None else f"{epic} ETF",
        "instrumentType": itype,
        "marketStatus": status,
    }


# ---------- search_terms ----------

def test_search_terms_covers_every_sub_sector_etf_plus_vix():
    terms = search_terms()
    assert set(config.SUB_SECTOR_ETFS.values()).issubset(set(terms))
    assert config.VIX_TICKER in terms


def test_search_terms_deduplicates_shared_etfs():
    """Teilen sich mehrere Sub-Sektoren einen ETF, wird er nur einmal geprüft."""
    terms = search_terms()
    assert len(terms) == len(set(terms))


# ---------- pick_best: nur exakte Treffer ----------

def test_pick_best_returns_none_without_markets():
    assert pick_best("XLK", []) is None


def test_pick_best_returns_exact_epic_match():
    markets = [_market("XLKQ"), _market("XLK")]
    assert pick_best("XLK", markets)["epic"] == "XLK"


def test_pick_best_is_case_and_whitespace_insensitive():
    assert pick_best(" xlk ", [_market("XLK")])["epic"] == "XLK"


def test_pick_best_returns_none_without_exact_match():
    """Kein Fuzzy-Fallback: ein Präfix-Treffer ist KEIN Treffer."""
    assert pick_best("XLK", [_market("XLKQ"), _market("ALKT")]) is None


def test_pick_best_never_returns_an_unrelated_instrument():
    """Regression zum Lauf vom 2026-07-27: die Volltextsuche lieferte für KBE
    (Bank-ETF) unter anderem KBH (KB Home, Hausbauer). Ein Momentum-Guardrail
    gegen das falsche Instrument ist schlimmer als gar keiner."""
    markets = [
        _market("KBH", "KB Home"),
        _market("KBWB", "Invesco KBW Bank ETF"),
        _market("UBER", "Uber Technologies"),
    ]
    assert pick_best("KBE", markets) is None


def test_pick_best_returns_match_even_when_not_tradeable():
    """Handelbarkeit ist eine Warnung im Report, kein Ausschlusskriterium für
    die Identifikation des Instruments."""
    hit = pick_best("KIE", [_market("KIE", status="CLOSED")])
    assert hit is not None and hit["marketStatus"] == "CLOSED"


# ---------- etf_candidates ----------

def test_etf_candidates_keeps_only_fund_like_names():
    markets = [
        _market("KBH", "KB Home"),
        _market("KBWB", "Invesco KBW Bank ETF"),
        _market("XLF", "Financial Select Sector SPDR Fund"),
        _market("UBER", "Uber Technologies"),
    ]
    epics = [c["epic"] for c in etf_candidates(markets)]
    assert epics == ["KBWB", "XLF"]


def test_etf_candidates_respects_limit():
    markets = [_market(f"E{i}", f"Fund {i}") for i in range(20)]
    assert len(etf_candidates(markets, limit=3)) == 3


def test_etf_candidates_empty_when_nothing_fund_like():
    assert etf_candidates([_market("KBH", "KB Home")]) == []


# ---------- resolve ----------

def test_resolve_queries_every_symbol():
    provider = MagicMock()
    provider.search_markets.return_value = [_market("XLK")]
    out = resolve(provider, ["XLK", "XLE"])
    assert set(out.keys()) == {"XLK", "XLE"}
    assert provider.search_markets.call_count == 2


# ---------- format_report ----------

_SUB_SECTORS = {
    "Technology Hardware": "XLK",
    "Semiconductors": "SOXX",
    "Banks": "KBE",
}


def test_format_report_marks_confirmed_and_missing():
    resolved = {
        "XLK": [_market("XLK", "Technology Select Sector SPDR Fund")],
        "KBE": [_market("KBH", "KB Home")],
    }
    report = format_report(resolved, _SUB_SECTORS)
    assert "XLK    OK" in report
    assert "KBE    KEIN TREFFER" in report


# ---------- looks_like_fund: der PPH-Fall ----------

def test_looks_like_fund_accepts_etfs_and_indices():
    for name in ("iShares Semiconductor ETF", "Technology Select Sector SPDR Fund",
                 "Volatility Index", "KKR Real Estate Finance Trust Inc"):
        assert looks_like_fund(_market("X", name)) is True


def test_looks_like_fund_rejects_operating_companies():
    for name in ("PPHE Hotel Group Ltd", "KB Home", "Alcon Inc."):
        assert looks_like_fund(_market("X", name)) is False


def test_format_report_flags_exact_epic_with_non_fund_name():
    """Regression: Capital.com fuehrt das Epic 'PPH' fuer die PPHE Hotel Group,
    nicht fuer den gleichnamigen Pharma-ETF. Exakter Treffer, falsches Papier."""
    report = format_report({"PPH": [_market("PPH", "PPHE Hotel Group Ltd")]},
                           {"Pharma": "PPH"})
    assert "NAME PRUEFEN" in report
    assert "nicht nach Fonds" in report
    assert "bestaetigt:          0" in report
    assert "NAME PRUEFEN:        1  (PPH)" in report


def test_format_report_never_suggests_a_ticker_map_entry_for_missing_symbols():
    """Ein fehlendes Instrument ist kein Umbenennungs-Problem — TICKER_MAP hilft nicht."""
    resolved = {"KBE": [_market("KBH", "KB Home")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "KBH" not in report          # der Fehltreffer taucht gar nicht erst auf
    assert "TICKER_MAP-Eintrag hilft hier NICHT" in report


def test_format_report_lists_fund_candidates_for_missing_symbols():
    resolved = {"KBE": [_market("KBH", "KB Home"),
                        _market("KBWB", "Invesco KBW Bank ETF")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "Fonds-Kandidaten" in report
    assert "KBWB" in report
    assert "Invesco KBW Bank ETF" in report


def test_format_report_says_when_no_candidate_exists():
    resolved = {"KBE": [_market("KBH", "KB Home")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "kein Fonds unter den Suchtreffern" in report


def test_format_report_counts_summary_correctly():
    resolved = {
        "XLK":  [_market("XLK")],
        "SOXX": [_market("SOXX")],
        "KBE":  [_market("KBH", "KB Home")],
    }
    report = format_report(resolved, _SUB_SECTORS)
    assert "geprueft:            3" in report
    assert "bestaetigt:          2" in report
    assert "KEIN TREFFER:        1  (KBE)" in report


def test_format_report_names_the_sub_sector_behind_each_etf():
    report = format_report({"SOXX": [_market("SOXX")]}, _SUB_SECTORS)
    assert "Semiconductors" in report


def test_format_report_flags_non_tradeable_markets():
    report = format_report({"XLK": [_market("XLK", status="SUSPENDED")]}, _SUB_SECTORS)
    assert "nicht handelbar:     1" in report


def test_format_report_omits_hint_block_when_nothing_missing():
    report = format_report({"XLK": [_market("XLK")]}, _SUB_SECTORS)
    assert "HINWEIS zu den fehlenden Symbolen" not in report


# ---------- main ----------

def test_main_returns_1_without_api_key(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", None)
    assert main([]) == 1
    assert "CAPITAL_COM_API_KEY" in capsys.readouterr().out


def test_main_prints_report_for_explicit_symbols(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", "dummy")
    provider = MagicMock()
    provider.search_markets.return_value = [_market("XLK")]
    monkeypatch.setattr("setup.verify_epics.CapitalComProvider", lambda: provider)
    assert main(["--symbols", "XLK"]) == 0
    assert "XLK" in capsys.readouterr().out
    assert provider.search_markets.call_count == 1


def test_main_returns_1_when_session_fails(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", "dummy")
    provider = MagicMock()
    provider.search_markets.side_effect = RuntimeError("auth failed")
    monkeypatch.setattr("setup.verify_epics.CapitalComProvider", lambda: provider)
    assert main(["--symbols", "XLK"]) == 1
    assert "Capital.com-Session fehlgeschlagen" in capsys.readouterr().out
