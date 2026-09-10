from datetime import datetime

import pytz

import config

IST = pytz.timezone("Asia/Kolkata")


def hold_minutes(pos: dict, now: datetime | None = None) -> float:
    """Minutes since buy. Naive ledger times are treated as IST."""
    now = now or datetime.now(IST)
    raw = (pos or {}).get("time")
    if not raw:
        return 999.0
    try:
        buy = datetime.strptime(str(raw), "%Y-%m-%d %H:%M:%S")
        if now.tzinfo is not None and buy.tzinfo is None:
            buy = IST.localize(buy)
        elif now.tzinfo is None and buy.tzinfo is not None:
            now = now.replace(tzinfo=None)
        return (now - buy).total_seconds() / 60.0
    except Exception:
        return 999.0


def evaluate_stop_loss(
    buy_price: float,
    quantity: int,
    current_price: float,
    nifty_change_pct: float,
    hold_mins: float,
) -> tuple:
    """
    Returns (hit: bool, reason: str | None).

    Absolute % and rupee floors fire even inside the hold window.
    Market-relative stop still waits for STOP_LOSS_MIN_HOLD_MINS.
    """
    if buy_price <= 0:
        return False, None

    stock_change = ((current_price - buy_price) / buy_price) * 100
    abs_pnl = round((current_price - buy_price) * quantity, 2)
    underperformance = stock_change - nifty_change_pct

    abs_pct_hit = stock_change <= -config.STOP_LOSS_PCT
    abs_floor_hit = abs_pnl <= -config.STOP_LOSS_ABS_FLOOR
    relative_sl_hit = underperformance < -config.STOP_LOSS_BUFFER

    if abs_pct_hit:
        return True, (
            f"ABS PCT SL: stock {stock_change:+.2f}% "
            f"exceeds -{config.STOP_LOSS_PCT}%"
        )
    if abs_floor_hit:
        return True, (
            f"ABSOLUTE SL: loss ₹{abs(abs_pnl):.0f} "
            f"exceeds floor ₹{config.STOP_LOSS_ABS_FLOOR}"
        )
    if hold_mins < config.STOP_LOSS_MIN_HOLD_MINS:
        return False, None
    if relative_sl_hit:
        return True, (
            f"RELATIVE SL: stock {stock_change:+.2f}% | "
            f"Nifty {nifty_change_pct:+.2f}% | "
            f"underperforms by {abs(underperformance):.2f}%"
        )
    return False, None
