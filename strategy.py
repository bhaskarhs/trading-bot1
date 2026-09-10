"""
strategy.py — 4-mode strategy system

  STRONG_MOMENTUM  (Nifty gap/surge > +2%):
    BUY  RSI > 60 AND near recent high
    SELL RSI < 50

  MILD_MOMENTUM    (Nifty up +0.5% to +2%):  ← NEW — fixes missing gradual recovery trades
    BUY  RSI > 52  (no near_high requirement)
    SELL RSI < 44

  FLAT             (Nifty ±0.5%):
    BUY  RSI < 35
    SELL RSI > 70

  MEAN_REVERSION   (Nifty down < -0.5%):
    BUY  RSI < 25
    SELL RSI > 78
"""

import pandas as pd


def calculate_rsi(closes: list, period: int = 14) -> float:
    """Calculates RSI from a list of closing prices. Returns 0-100."""
    if len(closes) < period + 1:
        raise ValueError(f"Need at least {period + 1} prices, got {len(closes)}")

    series   = pd.Series(closes)
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss
    rsi      = 100 - (100 / (1 + rs))
    return round(float(rsi.iloc[-1]), 2)


def is_near_recent_high(closes: list, lookback: int = 10, threshold: float = 0.97) -> bool:
    """
    Returns True if current price is within 3% of its recent high.
    Used only by STRONG_MOMENTUM strategy.
    """
    if len(closes) < lookback:
        return False
    recent_high = max(closes[-lookback:])
    current     = closes[-1]
    return current >= recent_high * threshold


def get_signal(rsi: float,
               oversold: float,
               overbought: float,
               mode: str = "MEAN_REVERSION",
               closes: list = None,
               is_flat_market: bool = False) -> str:
    """
    Unified signal function — picks thresholds based on mode.

    mode options:
      STRONG_MOMENTUM  → RSI > 60 + near high → BUY | RSI < 50 → SELL
      MILD_MOMENTUM    → RSI > 52 → BUY | RSI < 44 → SELL
      FLAT             → RSI < 35 → BUY | RSI > 70 → SELL
      MEAN_REVERSION   → RSI < 25 → BUY | RSI > 78 → SELL
    """

    if mode == "STRONG_MOMENTUM":
        near_high = is_near_recent_high(closes) if closes else False
        if rsi > 60 and near_high:
            return "BUY"
        elif rsi < 50:
            return "SELL"
        return "HOLD"

    elif mode == "MILD_MOMENTUM":
        # No near_high check — just RSI momentum
        if rsi > 52:
            return "BUY"
        elif rsi < 44:
            return "SELL"
        return "HOLD"

    elif mode == "FLAT":
        if rsi < 35:
            return "BUY"
        elif rsi > 70:
            return "SELL"
        return "HOLD"

    else:  # MEAN_REVERSION (default)
        if rsi < oversold:
            return "BUY"
        elif rsi > overbought:
            return "SELL"
        return "HOLD"
