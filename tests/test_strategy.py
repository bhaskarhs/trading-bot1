from strategy import calculate_rsi, get_signal, is_near_recent_high


def falling_closes():
    return [100 - i for i in range(20)]


def rising_closes():
    return [80 + i for i in range(20)]


def test_rsi_oversold_on_selloff():
    rsi = calculate_rsi(falling_closes(), 14)
    assert rsi < 25


def test_rsi_overbought_on_rally():
    rsi = calculate_rsi(rising_closes(), 14)
    assert rsi > 70


def test_mean_reversion_buy_sell():
    assert get_signal(20, 25, 78, "MEAN_REVERSION") == "BUY"
    assert get_signal(80, 25, 78, "MEAN_REVERSION") == "SELL"
    assert get_signal(50, 25, 78, "MEAN_REVERSION") == "HOLD"


def test_mild_momentum():
    assert get_signal(55, 25, 78, "MILD_MOMENTUM") == "BUY"
    assert get_signal(40, 25, 78, "MILD_MOMENTUM") == "SELL"
    assert get_signal(86.1, 25, 78, "MILD_MOMENTUM") == "HOLD"
    assert get_signal(70.0, 25, 78, "MILD_MOMENTUM") == "BUY"
    assert get_signal(70.01, 25, 78, "MILD_MOMENTUM") == "HOLD"


def test_flat_matches_mild_momentum_not_knives():
    assert get_signal(55, 25, 78, "FLAT") == "BUY"
    assert get_signal(12.5, 25, 78, "FLAT") != "BUY"
    assert get_signal(19.7, 25, 78, "FLAT") != "BUY"
    assert get_signal(40, 25, 78, "FLAT") == "SELL"


def test_quality_rejects_falling_knife():
    from strategy import passes_long_quality
    stock = {"name": "Atherenerg", "symbol": "ATHERENERG-EQ", "pct_change": -1.2}
    falling = [100, 99, 98, 97]
    ok, reason = passes_long_quality(stock, falling, "FLAT", nifty_pct=0.3)
    assert ok is False
    assert "still down" in reason


def test_quality_accepts_green_bounce_on_flat():
    from strategy import passes_long_quality
    stock = {"name": "Infosys", "symbol": "INFY-EQ", "pct_change": 1.8}
    bounce = [100, 101, 100.5, 102]
    ok, _ = passes_long_quality(stock, bounce, "FLAT", nifty_pct=0.3, min_day_pct=1.0)
    assert ok is True


def test_quality_mean_reversion_drops_laggards():
    from strategy import passes_long_quality
    stock = {"name": "Suzlon", "symbol": "SUZLON-EQ", "pct_change": -3.5}
    bounce = [50, 49, 48, 48.2]
    ok, reason = passes_long_quality(
        stock, bounce, "MEAN_REVERSION", nifty_pct=-0.8, max_lag_vs_nifty=1.5
    )
    assert ok is False
    assert "lags Nifty" in reason
