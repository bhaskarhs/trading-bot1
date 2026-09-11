from datetime import datetime

import pytz

import config
from daily_report import analyze_day
from ledger import fifo_round_trips
from persist import load_json, save_json
from risk import evaluate_stop_loss, hold_minutes
from universe import TOKEN_FIXES, merge_universe
from vix_monitor import get_vix_mode, should_halt, should_exit_all


def test_universe_has_unique_tokens():
    tokens = [s["token"] for s in config.BROAD_UNIVERSE]
    symbols = [s["symbol"] for s in config.BROAD_UNIVERSE]
    assert len(tokens) == len(set(tokens))
    assert len(symbols) == len(set(symbols))
    by_symbol = {s["symbol"]: s["token"] for s in config.BROAD_UNIVERSE}
    assert by_symbol["PATANJALI-EQ"] == TOKEN_FIXES["PATANJALI-EQ"]
    assert by_symbol["DMART-EQ"] == TOKEN_FIXES["DMART-EQ"]
    assert by_symbol["UPL-EQ"] != by_symbol["DMART-EQ"]
    assert by_symbol["POWERGRID-EQ"] != by_symbol["PATANJALI-EQ"]


def test_merge_drops_duplicate_token():
    a = [{"name": "A", "symbol": "AAA-EQ", "token": "1"}]
    b = [{"name": "B", "symbol": "BBB-EQ", "token": "1"}]
    merged = merge_universe(a, b)
    assert [s["symbol"] for s in merged] == ["AAA-EQ"]


def test_hold_minutes_naive_ist_does_not_crash():
    ist = pytz.timezone("Asia/Kolkata")
    now = ist.localize(datetime(2026, 4, 8, 13, 30, 0))
    pos = {"time": "2026-04-08 12:58:18"}
    mins = hold_minutes(pos, now)
    assert 30 < mins < 40


def test_absolute_pct_stop_ignores_hold_window():
    hit, reason = evaluate_stop_loss(
        buy_price=100,
        quantity=10,
        current_price=98.0,
        nifty_change_pct=0.0,
        hold_mins=5,
    )
    assert hit is True
    assert "ABS PCT" in reason


def test_relative_stop_waits_for_hold():
    hit, _ = evaluate_stop_loss(
        buy_price=100,
        quantity=1,
        current_price=99.0,
        nifty_change_pct=0.0,
        hold_mins=5,
    )
    assert hit is False
    hit, reason = evaluate_stop_loss(
        buy_price=100,
        quantity=1,
        current_price=99.4,
        nifty_change_pct=1.0,
        hold_mins=40,
    )
    assert hit is True
    assert "RELATIVE" in reason


def test_fifo_matches_overnight_holds():
    trades = [
        {"timestamp": "2026-04-24 09:18:03", "action": "BUY", "symbol": "INFY-EQ",
         "stock": "Infosys", "price": 100, "quantity": 2},
        {"timestamp": "2026-04-29 09:15:28", "action": "SELL", "symbol": "INFY-EQ",
         "stock": "Infosys", "price": 90, "quantity": 2},
    ]
    closed, unmatched = fifo_round_trips(trades)
    assert unmatched == []
    assert closed[0]["pnl"] == -20.0
    result = analyze_day("2026-04-24", trades)
    assert result["realised_pnl"] == 0
    assert result["open_positions"] == 1
    result = analyze_day("2026-04-29", trades)
    assert result["realised_pnl"] == -20.0
    assert result["open_positions"] == 0


def test_atomic_json_roundtrip(tmp_path):
    path = tmp_path / "ledger.json"
    save_json(str(path), {"a": 1})
    assert load_json(str(path), {}) == {"a": 1}


def test_vix_crisis_halts():
    mode, _, _ = get_vix_mode(26)
    assert mode == "CRISIS"
    assert should_halt(26) is True
    assert should_exit_all(22) is True
    assert should_halt(22) is False
    assert should_halt(14) is False


def test_vix_good_day_is_at_or_below_14():
    assert get_vix_mode(12)[0] == "NORMAL"
    assert get_vix_mode(13)[0] == "NORMAL"
    assert get_vix_mode(14)[0] == "NORMAL"
    assert get_vix_mode(14.01)[0] == "CAUTION"
    assert get_vix_mode(15)[0] == "CAUTION"
    assert get_vix_mode(19.9)[0] == "CAUTION"
    assert get_vix_mode(20)[0] == "DEFENSE"



def test_missing_credentials_message():
    from angel_client import _require_credentials
    old = (config.ANGEL_API_KEY, config.ANGEL_TOTP_SECRET)
    config.ANGEL_API_KEY = None
    config.ANGEL_TOTP_SECRET = None
    try:
        try:
            _require_credentials()
            assert False, "should have raised"
        except RuntimeError as e:
            assert "Missing Angel credentials" in str(e)
    finally:
        config.ANGEL_API_KEY, config.ANGEL_TOTP_SECRET = old
