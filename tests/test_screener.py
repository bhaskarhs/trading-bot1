from screener import (
    annotate_universe,
    classify_breadth,
    classify_nifty,
    classify_rsi_tape,
    rank_buy_signals,
    select_mover_candidates,
)
from trader import calculate_quantity
import config


def _row(symbol, pct, name=None, token="1"):
    return {
        "name": name or symbol,
        "symbol": symbol,
        "token": token,
        "pct_change": pct,
        "ltp": 100 + pct,
    }


def test_classify_nifty_bands():
    assert classify_nifty(0.2, 0.0) == "FLAT"
    assert classify_nifty(0.8, 0.0) == "MILD_UP"
    assert classify_nifty(2.1, 0.0) == "STRONG_UP"
    assert classify_nifty(0.0, 2.5) == "STRONG_UP"
    assert classify_nifty(-0.8, 0.0) == "DOWN"
    assert classify_nifty(0.2, -1.6) == "DOWN"


def test_breadth_detects_it_bid_when_nifty_quote_missing():
    # Quiet names + a cluster of IT-sized gainers should look like a bid,
    # not FLAT, so we would BUY RSI>52 instead of RSI<35 dip names.
    pcts = [-0.2] * 40 + [1.8, 2.1, 1.5, 1.2, 1.1, 1.4, 1.9, 2.0, 1.3, 1.6]
    assert classify_breadth(pcts) == "MILD_UP"


def test_breadth_unknown_when_tape_is_empty():
    assert classify_breadth([]) == "UNKNOWN"
    assert classify_breadth([0.1, -0.1, 0.0]) == "UNKNOWN"


def test_flat_ranks_by_abs_move_so_gainers_are_not_dropped():
    rows = [
        _row("ACC-EQ", -1.2, "Acc"),
        _row("INFY-EQ", 2.4, "Infosys"),
        _row("TCS-EQ", 1.9, "TCS"),
        _row("3MINDIA-EQ", -0.4, "3Mindia"),  # below 1% — not a mover
    ]
    picked = select_mover_candidates("FLAT", rows, held=set(), limit=2)
    assert [r["symbol"] for r in picked] == ["INFY-EQ", "TCS-EQ"]


def test_mild_up_keeps_gainers_not_losers():
    rows = [
        _row("ACC-EQ", -1.5, "Acc"),
        _row("INFY-EQ", 1.8, "Infosys"),
    ]
    picked = select_mover_candidates("MILD_UP", rows, held=set(), limit=10)
    assert [r["symbol"] for r in picked] == ["INFY-EQ"]


def test_holdings_stay_on_list_even_if_not_top_movers():
    rows = [
        _row("ACC-EQ", 0.1, "Acc"),
        _row("INFY-EQ", 3.0, "Infosys"),
    ]
    picked = select_mover_candidates("MILD_UP", rows, held={"ACC-EQ"}, limit=1)
    symbols = [r["symbol"] for r in picked]
    assert "ACC-EQ" in symbols
    assert "INFY-EQ" in symbols


def test_quantity_skips_names_above_slot():
    assert calculate_quantity(config.CAPITAL_PER_TRADE + 1) == 0
    assert calculate_quantity(1000) == int(config.CAPITAL_PER_TRADE / 1000)


def test_annotate_universe_keeps_every_name_including_it():
    unique = [
        {"name": "Acc", "symbol": "ACC-EQ", "token": "1"},
        {"name": "Infosys", "symbol": "INFY-EQ", "token": "2"},
        {"name": "TCS", "symbol": "TCS-EQ", "token": "3"},
    ]
    rows = [_row("INFY-EQ", 2.4, "Infosys")]
    out = annotate_universe(unique, rows)
    assert [s["symbol"] for s in out] == ["ACC-EQ", "INFY-EQ", "TCS-EQ"]
    assert out[1]["pct_change"] == 2.4
    assert "pct_change" not in out[0]


def test_rank_buys_picks_best_rsi_not_list_order():
    acc = ({"name": "Acc", "symbol": "ACC-EQ", "pct_change": -0.2}, "BUY", 33.0, 1225)
    infy = ({"name": "Infosys", "symbol": "INFY-EQ", "pct_change": -1.8}, "BUY", 12.0, 1500)
    tcs = ({"name": "TCS", "symbol": "TCS-EQ", "pct_change": 1.5}, "BUY", 22.0, 3600)
    # Acc is first in the A-list but not the most oversold
    ranked = rank_buy_signals([acc, infy, tcs], "FLAT", limit=2)
    assert [s[0]["symbol"] for s in ranked] == ["INFY-EQ", "TCS-EQ"]

    hot_infy = ({"name": "Infosys", "symbol": "INFY-EQ", "pct_change": 2.4}, "BUY", 68.0, 1500)
    mild_acc = ({"name": "Acc", "symbol": "ACC-EQ", "pct_change": 1.1}, "BUY", 53.0, 1225)
    ranked = rank_buy_signals([mild_acc, hot_infy], "MILD_MOMENTUM", limit=1)
    assert ranked[0][0]["symbol"] == "INFY-EQ"


def test_rsi_tape_hot_cluster_is_momentum_not_flat_dips():
    rsis = [50] * 40 + [65] * 35
    assert classify_rsi_tape(rsis) == "MILD_UP"
    assert classify_rsi_tape([50] * 10) == "UNKNOWN"
