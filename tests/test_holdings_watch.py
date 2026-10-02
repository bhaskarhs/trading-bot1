"""After a fill, skip the Nifty 500 radar and only track held names."""

from unittest.mock import MagicMock

import bot
import config
from bot import (
    holdings_watch_list,
    hunting_new_names,
    next_scan_interval_seconds,
    run_scan,
)


INFY = {"name": "Infosys", "symbol": "INFY-EQ", "token": "1594"}
TCS = {"name": "TCS", "symbol": "TCS-EQ", "token": "11536"}


def test_hunting_only_when_flat(monkeypatch):
    monkeypatch.setattr(bot, "open_positions", {})
    assert hunting_new_names() is True
    monkeypatch.setattr(
        bot,
        "open_positions",
        {"INFY-EQ": {"price": 1500, "quantity": 13}},
    )
    assert hunting_new_names() is False


def test_holdings_watch_list_is_held_names_only(monkeypatch):
    monkeypatch.setattr(
        bot,
        "_universe_map",
        lambda: {"INFY-EQ": INFY, "TCS-EQ": TCS},
    )
    monkeypatch.setattr(
        bot,
        "open_positions",
        {"INFY-EQ": {"price": 1500, "quantity": 13}},
    )
    assert holdings_watch_list() == [INFY]


def test_next_scan_is_faster_while_holding(monkeypatch):
    monkeypatch.setattr(bot, "open_positions", {})
    assert next_scan_interval_seconds() == config.SCAN_INTERVAL_SECONDS
    monkeypatch.setattr(
        bot,
        "open_positions",
        {"INFY-EQ": {"price": 1500, "quantity": 13}},
    )
    assert next_scan_interval_seconds() == config.HOLDINGS_SCAN_INTERVAL_SECONDS
    assert next_scan_interval_seconds() < config.SCAN_INTERVAL_SECONDS


def _quiet_scan_deps(monkeypatch):
    monkeypatch.setattr(bot, "fetch_vix", lambda: 12.0)
    monkeypatch.setattr(bot, "get_vix_mode", lambda _v: ("NORMAL", "ok", "ok"))
    monkeypatch.setattr(bot, "should_halt", lambda _v: False)
    monkeypatch.setattr(bot, "should_exit_all", lambda _v: False)
    monkeypatch.setattr(bot, "is_safe_to_buy", lambda _v: True)
    monkeypatch.setattr(
        bot,
        "get_market_direction",
        lambda: ("FLAT", 0.1, 0.0, True),
    )
    monkeypatch.setattr(bot, "check_stop_losses", lambda _n: None)
    monkeypatch.setattr(bot, "send_alert", MagicMock())
    monkeypatch.setattr(bot, "execute_trade", MagicMock(return_value=None))
    monkeypatch.setattr(bot, "candle_cache_fresh", lambda *a, **k: True)
    monkeypatch.setattr(bot.mh, "is_past_last_entry", lambda **k: False)
    monkeypatch.setattr(bot, "is_square_off_window", lambda: False)
    closes = [100 + i * 0.1 for i in range(25)]
    monkeypatch.setattr(bot, "fetch_candles", lambda *a, **k: closes)


def test_run_scan_skips_universe_when_holding(monkeypatch):
    _quiet_scan_deps(monkeypatch)
    called = {"n": 0}

    def _should_not_run(**kwargs):
        called["n"] += 1
        raise AssertionError("get_candidates must not run while holding")

    monkeypatch.setattr(bot, "get_candidates", _should_not_run)
    monkeypatch.setattr(
        bot,
        "open_positions",
        {"INFY-EQ": {"price": 1500, "quantity": 13}},
    )
    monkeypatch.setattr(bot, "_universe_map", lambda: {"INFY-EQ": INFY})
    tokens = []

    def _candles(token, interval, n):
        tokens.append(token)
        return [1500 + i * 0.2 for i in range(25)]

    monkeypatch.setattr(bot, "fetch_candles", _candles)
    run_scan()
    assert called["n"] == 0
    assert tokens == ["1594"]


def test_run_scan_hunts_universe_when_flat(monkeypatch):
    _quiet_scan_deps(monkeypatch)
    monkeypatch.setattr(bot, "open_positions", {})
    seen = {"n": 0}

    def _candidates(held=None):
        seen["n"] += 1
        return [INFY, TCS], "FLAT", 0.1, True

    monkeypatch.setattr(bot, "get_candidates", _candidates)
    run_scan()
    assert seen["n"] == 1
