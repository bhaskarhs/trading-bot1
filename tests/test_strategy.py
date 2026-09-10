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


def test_strong_momentum_needs_near_high():
    closes = [100 + i for i in range(12)]
    assert is_near_recent_high(closes) is True
    assert get_signal(65, 25, 78, "STRONG_MOMENTUM", closes=closes) == "BUY"
    far_from_high = [100] * 10 + [90]
    assert get_signal(65, 25, 78, "STRONG_MOMENTUM", closes=far_from_high) == "HOLD"
