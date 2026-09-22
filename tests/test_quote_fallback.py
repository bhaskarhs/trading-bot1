"""Quote empty-body handling and the 16 Sep candle-radar fallback."""

from angel_client import (
    get_market_quote,
    is_empty_body_error,
    quote_index,
    session_quote_from_candles,
)
import config
import screener


EMPTY = "Couldn't parse the JSON response received from the server: b''"


def test_empty_body_error_detects_smartapi_message():
    assert is_empty_body_error(Exception(EMPTY))
    assert is_empty_body_error(Exception("other")) is False


def test_get_market_quote_swallows_empty_body(monkeypatch):
    class DeadQuote:
        def getMarketData(self, mode, exchangeTokens):
            raise Exception(EMPTY)

    monkeypatch.setattr("angel_client.get_angel", lambda force=False: DeadQuote())
    assert get_market_quote("LTP", {"NSE": ["1594"]}) is None


def test_quote_index_falls_back_to_order_ltp(monkeypatch):
    monkeypatch.setattr("angel_client.get_market_quote", lambda *a, **k: None)
    monkeypatch.setattr(
        "angel_client.ltp_one",
        lambda *a, **k: {"ltp": 25000.0, "open": 24800.0, "pct_change": 0.81},
    )
    monkeypatch.setattr("angel_client.session_quote_from_candles", lambda *a, **k: None)
    hit = quote_index("99926000")
    assert hit["ltp"] == 25000.0


def test_quote_index_falls_back_to_candles(monkeypatch):
    monkeypatch.setattr("angel_client.get_market_quote", lambda *a, **k: None)
    monkeypatch.setattr("angel_client.ltp_one", lambda *a, **k: None)
    monkeypatch.setattr(
        "angel_client.session_quote_from_candles",
        lambda token, interval=None: {"ltp": 13.2, "open": 13.0, "pct_change": 1.54},
    )
    hit = quote_index("99919003")
    assert hit["ltp"] == 13.2


def test_session_quote_prefers_todays_bars(monkeypatch):
    rows = [
        ["2026-09-21T15:00:00+05:30", 90, 91, 89, 90, 1],
        ["2026-09-22T09:15:00+05:30", 100, 102, 99, 101, 1],
        ["2026-09-22T09:30:00+05:30", 101, 104, 100, 103, 1],
    ]
    monkeypatch.setattr("angel_client._request_candles", lambda *a, **k: rows)

    class _DT:
        @staticmethod
        def now(tz=None):
            import datetime as dt
            import pytz
            return pytz.timezone("Asia/Kolkata").localize(dt.datetime(2026, 9, 22, 13, 0))

    monkeypatch.setattr("angel_client.datetime", _DT)
    hit = session_quote_from_candles("1594")
    assert hit["open"] == 100
    assert hit["ltp"] == 103
    assert hit["pct_change"] == 3.0


def test_get_candidates_uses_candle_radar_when_ltp_empty(monkeypatch):
    bundled = [
        {"name": f"S{i}", "symbol": f"S{i}-EQ", "token": str(i)}
        for i in range(16)
    ]
    monkeypatch.setattr(screener, "get_market_direction",
                        lambda: ("UNKNOWN", 0.0, 0.0, False))
    monkeypatch.setattr(screener, "_fetch_ltp_batch", lambda tokens, retries=3: {})
    monkeypatch.setattr(screener.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(screener, "BROAD_UNIVERSE", bundled[:2])
    monkeypatch.setattr(config, "STOCKS", bundled)
    monkeypatch.setattr(
        screener,
        "_candle_radar_rows",
        lambda stocks, delay=0.2: [
            {**s, "pct_change": 1.8, "ltp": 110.0} for s in stocks
        ],
    )
    stocks, mode, nifty_pct, allow = screener.get_candidates(verbose=False, held=set())
    assert allow is True
    assert mode == "MILD_MOMENTUM"
    assert nifty_pct == 1.8
    assert len(stocks) == 16
