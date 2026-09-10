"""
demo.py — run the strategy locally without Angel One credentials.

Prints a full scan-style log using synthetic 15-minute candles so you can see
how RSI + the four market modes produce BUY / SELL / HOLD.
"""

from strategy import calculate_rsi, get_signal
import config


def make_closes(kind: str) -> list:
    """Build 25 synthetic closes that produce a known RSI regime."""
    base = 1000.0
    if kind == "oversold":
        return [base - i * 4 for i in range(25)]
    if kind == "overbought":
        return [base + i * 4 for i in range(25)]
    if kind == "breakout":
        closes = [base + i * 0.5 for i in range(15)]
        closes += [base + 8 + i * 3 for i in range(10)]
        return closes
    # chop / mid RSI
    return [base + ((-1) ** i) * 2 for i in range(25)]


def run_demo():
    print("\n" + "=" * 62)
    print("  NSE Trading Bot — DEMO SCAN (no broker login)")
    print(f"  Capital  : ₹{config.TOTAL_CAPITAL:,} | "
          f"Per trade: ₹{config.CAPITAL_PER_TRADE:,} | "
          f"Max positions: {config.MAX_OPEN_POSITIONS}")
    print(f"  Mode     : PAPER TRADING (synthetic candles)")
    print(f"  Stop loss: -{config.STOP_LOSS_BUFFER}% vs Nifty | "
          f"hold≥{config.STOP_LOSS_MIN_HOLD_MINS}min | "
          f"floor ₹{config.STOP_LOSS_ABS_FLOOR}")
    print("=" * 62)

    samples = [
        ("Coal India", "oversold"),
        ("TCS", "overbought"),
        ("Reliance", "breakout"),
        ("HDFC Bank", "chop"),
    ]
    modes = ["MEAN_REVERSION", "FLAT", "MILD_MOMENTUM", "STRONG_MOMENTUM"]

    for mode in modes:
        print(f"\n  Strategy : {mode}")
        print(f"  Scanning : {len(samples)} synthetic candidates\n")
        for name, kind in samples:
            closes = make_closes(kind)
            rsi = calculate_rsi(closes, config.RSI_PERIOD)
            price = closes[-1]
            signal = get_signal(
                rsi=rsi,
                oversold=config.RSI_OVERSOLD,
                overbought=config.RSI_OVERBOUGHT,
                mode=mode,
                closes=closes,
                is_flat_market=(mode == "FLAT"),
            )
            marker = " ◀ TRADE" if signal != "HOLD" else ""
            print(f"  {name:<24} | ₹{price:<10} | RSI {rsi:>6.2f} → {signal}{marker}")

    print("\n  Open positions: 0 — demo does not persist trades")
    print("  Next scan would wait 5 minutes in live bot.py\n")


if __name__ == "__main__":
    run_demo()
