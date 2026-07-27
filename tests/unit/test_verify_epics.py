"""Unit-Tests für setup/verify_epics.py — reine Offline-Tests gegen einen
gemockten Provider, es geht nie ein echter Capital.com-Request raus."""
from unittest.mock import MagicMock

import config
from setup.verify_epics import (
    format_report, main, pick_best, resolve, search_terms,
)


def _market(epic: str, status: str = "TRADEABLE", itype: str = "SHARES") -> dict:
    return {
        "epic": epic,
        "instrumentName": f"{epic} Fund",
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


# ---------- pick_best ----------

def test_pick_best_returns_none_without_markets():
    assert pick_best("XLK", []) is None


def test_pick_best_prefers_exact_epic_over_prefix():
    markets = [_market("XLKQ"), _market("XLK")]
    assert pick_best("XLK", markets)["epic"] == "XLK"


def test_pick_best_prefers_tradeable_when_no_exact_match():
    markets = [_market("XLK_A", status="SUSPENDED"), _market("XLK_B")]
    assert pick_best("XLK", markets)["epic"] == "XLK_B"


def test_pick_best_falls_back_to_first_plausible_hit():
    markets = [_market("SOMETHINGELSE")]
    assert pick_best("XLK", markets)["epic"] == "SOMETHINGELSE"


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
    "Utilities": "XLU",
}


def test_format_report_marks_exact_deviating_and_missing():
    resolved = {
        "XLK":  [_market("XLK")],
        "SOXX": [_market("SOXX_US")],
        "XLU":  [],
    }
    report = format_report(resolved, _SUB_SECTORS)
    assert "exakt" in report
    assert "ABWEICHEND" in report
    assert "KEIN TREFFER" in report
    assert "SOXX_US" in report


def test_format_report_emits_ticker_map_line_only_for_deviating_epic():
    resolved = {"XLK": [_market("XLK")], "SOXX": [_market("SOXX_US")]}
    report = format_report(resolved, _SUB_SECTORS)
    mapping_block = report.split("TICKER_MAP eintragen:")[-1]
    assert '"SOXX": "SOXX_US",' in mapping_block
    assert '"XLK"' not in mapping_block


def test_format_report_says_nothing_to_map_when_all_exact():
    resolved = {"XLK": [_market("XLK")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "alle Epics entsprechen dem Symbol" in report


def test_format_report_names_the_sub_sector_behind_each_etf():
    resolved = {"SOXX": [_market("SOXX")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "Semiconductors" in report


def test_format_report_flags_non_tradeable_markets():
    resolved = {"XLK": [_market("XLK", status="SUSPENDED")]}
    report = format_report(resolved, _SUB_SECTORS)
    assert "nicht handelbar:     1" in report


# ---------- main ----------

def test_main_returns_1_without_api_key(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", None)
    assert main([]) == 1
    assert "CAPITAL_COM_API_KEY" in capsys.readouterr().out


def test_main_prints_report_for_explicit_symbols(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", "dummy")
    provider = MagicMock()
    provider.search_markets.return_value = [_market("XLK")]
    monkeypatch.setattr(
        "setup.verify_epics.CapitalComProvider", lambda: provider,
    )
    assert main(["--symbols", "XLK"]) == 0
    out = capsys.readouterr().out
    assert "XLK" in out
    assert provider.search_markets.call_count == 1


def test_main_returns_1_when_session_fails(monkeypatch, capsys):
    monkeypatch.setattr(config, "CAPITAL_COM_API_KEY", "dummy")
    provider = MagicMock()
    provider.search_markets.side_effect = RuntimeError("auth failed")
    monkeypatch.setattr(
        "setup.verify_epics.CapitalComProvider", lambda: provider,
    )
    assert main(["--symbols", "XLK"]) == 1
    assert "Capital.com-Session fehlgeschlagen" in capsys.readouterr().out
