"""Replay 15–16 Sep paper fills against the two-speed / fail-closed rules."""

from datetime import datetime

import pytz

from market_hours import is_past_last_entry
from strategy import get_signal

IST = pytz.timezone("Asia/Kolkata")

# Actual paper BUYs from paper_trades.json (16 Sep afternoon GHA run).
SEP16_MILD_BUYS = [
    ("Ntpcgreen", 86.1, "2026-09-16 15:02:18"),
    ("Tatacomm", 83.44, "2026-09-16 15:02:18"),
    ("Hdbfs", 77.86, "2026-09-16 15:02:18"),
    ("Abdl", 77.79, "2026-09-16 15:02:18"),
    ("Radico", 76.7, "2026-09-16 15:02:18"),
]

SEP15_DIP_BUYS = [
    ("3Mindia", 5.06, "2026-09-15 14:40:24"),
    ("Acc", 26.64, "2026-09-15 14:40:24"),
    ("Aubank", 14.76, "2026-09-15 14:40:24"),
    ("Awl", 15.57, "2026-09-15 14:40:24"),
    ("Acutaas", 34.45, "2026-09-15 14:40:24"),
]


def _at(stamp: str):
    return IST.localize(datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S"))


def test_sep16_overbought_momentum_would_not_buy():
    for name, rsi, _stamp in SEP16_MILD_BUYS:
        assert get_signal(rsi, 25, 78, "MILD_MOMENTUM") == "HOLD", name


def test_sep16_fill_time_is_past_last_entry():
    for _name, _rsi, stamp in SEP16_MILD_BUYS:
        assert is_past_last_entry(_at(stamp), last_entry=(14, 30)) is True


def test_sep16_data_gap_fail_closed_skips_the_498_name_rsi():
    from screener import rsi_book_for_scan
    stocks, allow, mode = rsi_book_for_scan("UNKNOWN", rows=[], held=set())
    assert allow is False
    assert stocks == []
    assert mode == "FLAT"


def test_sep15_dip_rsi_still_valid_in_flat_but_clock_was_late():
    for name, rsi, stamp in SEP15_DIP_BUYS:
        assert get_signal(rsi, 25, 78, "FLAT") == "BUY", name
        assert is_past_last_entry(_at(stamp), last_entry=(14, 30)) is True
