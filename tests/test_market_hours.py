from datetime import datetime

import pytz

from market_hours import (
    is_market_open,
    is_square_off_window,
    parse_hhmm,
    past_hhmm,
    session_end_hhmm,
    session_mode_enabled,
)


IST = pytz.timezone("Asia/Kolkata")


def _at(h, m):
    return IST.localize(datetime(2026, 9, 10, h, m, 0))  # Thursday


def test_open_only_in_cash_hours():
    assert is_market_open(_at(9, 15)) is True
    assert is_market_open(_at(15, 25)) is True
    assert is_market_open(_at(9, 14)) is False
    assert is_market_open(_at(15, 26)) is False
    sat = IST.localize(datetime(2026, 9, 12, 10, 0, 0))
    assert is_market_open(sat) is False


def test_square_off_window():
    assert is_square_off_window(_at(15, 15)) is True
    assert is_square_off_window(_at(15, 10)) is False


def test_session_end_env(monkeypatch):
    monkeypatch.delenv("SESSION_END", raising=False)
    assert session_end_hhmm((15, 30)) == (15, 30)
    monkeypatch.setenv("SESSION_END", "12:15")
    assert session_end_hhmm((15, 30)) == (12, 15)
    assert parse_hhmm("9:15", (0, 0)) == (9, 15)


def test_morning_slice_is_over_at_1215(monkeypatch):
    monkeypatch.setenv("SESSION_END", "12:15")
    assert past_hhmm(_at(12, 15), session_end_hhmm((15, 30))) is True
    assert past_hhmm(_at(12, 14), session_end_hhmm((15, 30))) is False


def test_session_mode_flag(monkeypatch):
    monkeypatch.delenv("RUN_MARKET_SESSION", raising=False)
    assert session_mode_enabled() is False
    monkeypatch.setenv("RUN_MARKET_SESSION", "1")
    assert session_mode_enabled() is True
