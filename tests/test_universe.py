from pathlib import Path

from universe import (
    join_index_to_scrip,
    load_bundled_nifty500_symbols,
    parse_nifty500_csv,
    resolve_nifty500_symbols,
)


SAMPLE = """Company Name,Industry,Symbol,Series,ISIN Code
360 ONE WAM Ltd.,Financial Services,360ONE,EQ,INE466L01038
HDFC Bank Ltd.,Financial Services,HDFCBANK,EQ,INE040A01034
Foo Bond,Other,FOOBOND,GB,INE000000000
"""


def test_parse_nifty500_skips_non_eq():
    symbols = parse_nifty500_csv(SAMPLE)
    assert symbols == ["360ONE", "HDFCBANK"]


def test_join_index_adds_eq_and_drops_missing():
    scrip = {
        "HDFCBANK-EQ": {"name": "HDFC Bank", "symbol": "HDFCBANK-EQ", "token": "1333"},
        "INFY-EQ": {"name": "Infosys", "symbol": "INFY-EQ", "token": "1594"},
    }
    built = join_index_to_scrip(["HDFCBANK", "MISSING"], scrip)
    assert [s["symbol"] for s in built] == ["HDFCBANK-EQ"]
    assert built[0]["token"] == "1333"


def test_bundled_nifty500_snapshot_is_wide():
    symbols = load_bundled_nifty500_symbols()
    assert len(symbols) >= 450
    assert "HDFCBANK" in symbols
    assert "RELIANCE" in symbols
    assert all(not s.endswith("-EQ") for s in symbols)


def test_resolve_falls_back_to_snapshot(monkeypatch):
    import universe as u

    def boom(timeout=30):
        raise RuntimeError("blocked")

    monkeypatch.setattr(u, "fetch_nifty500_symbols", boom)
    monkeypatch.setattr(u, "NIFTY500_SNAPSHOT", Path("data/nifty500_symbols.txt"))
    symbols = resolve_nifty500_symbols()
    assert len(symbols) >= 450
    assert "INFY" in symbols
