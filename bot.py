import time
from datetime import datetime
import pytz

import config
from angel_client import get_angel, fetch_candles
from strategy import calculate_rsi, get_signal
from trader import execute_trade
from notifier import send_alert
from screener import get_candidates
from vix_monitor import fetch_vix, get_vix_mode, is_safe_to_buy, should_exit_all


IST = pytz.timezone("Asia/Kolkata")

MARKET_OPEN   = (9, 15)
MARKET_CLOSE  = (15, 25)
SCAN_INTERVAL = 300   # 5 minutes


def is_market_open() -> bool:
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return MARKET_OPEN <= t <= MARKET_CLOSE


# ── Smart stop loss ───────────────────────────────────────────────────────────

def check_stop_losses(nifty_change_pct: float):
    """
    Market-relative stop loss — runs every scan on all open positions.

    Exits a position only when ALL conditions are met:

      Condition 1 — Minimum hold time (30 min default)
        Protects against opening whipsaw — no exit in first 30 minutes

      Condition 2 — Market-relative underperformance
        stock_change < (nifty_change - STOP_LOSS_BUFFER)
        If Nifty is -2% and buffer is 1.5% → exit stocks worse than -3.5%
        If Nifty is flat (0%) → exit stocks worse than -1.5%
        Normal market-wide falls do NOT trigger this

      Condition 3 — Absolute floor (safety net)
        Always exit if loss exceeds STOP_LOSS_ABS_FLOOR (₹500)
        Catches extreme cases regardless of market
    """
    from trader import open_positions
    from screener import BROAD_UNIVERSE

    if not open_positions:
        return

    all_stocks = {s["symbol"]: s for s in BROAD_UNIVERSE}
    now        = datetime.now(IST)
    exited     = []

    for symbol, pos in list(open_positions.items()):
        stock = all_stocks.get(symbol)
        if not stock:
            continue

        try:
            buy_price = pos["price"]
            buy_qty   = pos["quantity"]

            # Parse buy time
            try:
                buy_time  = datetime.strptime(pos["time"], "%Y-%m-%d %H:%M:%S")
                hold_mins = (now - buy_time).total_seconds() / 60
            except Exception:
                hold_mins = 999   # unknown time = treat as old enough

            # Condition 1 — minimum hold
            if hold_mins < config.STOP_LOSS_MIN_HOLD_MINS:
                remaining = int(config.STOP_LOSS_MIN_HOLD_MINS - hold_mins)
                print(f"  [SL] {stock['name']:<22} | Hold protection: {remaining}min left")
                continue

            # Fetch current price
            closes        = fetch_candles(stock["token"], config.CANDLE_INTERVAL, 2)
            current_price = closes[-1]
            time.sleep(config.DELAY_BETWEEN_STOCKS)

            stock_change     = ((current_price - buy_price) / buy_price) * 100
            abs_loss         = round((current_price - buy_price) * buy_qty, 2)
            underperformance = stock_change - nifty_change_pct

            # Condition 2 — market-relative
            relative_sl_hit = underperformance < -config.STOP_LOSS_BUFFER

            # Condition 3 — absolute floor
            abs_floor_hit = abs_loss <= -config.STOP_LOSS_ABS_FLOOR

            if relative_sl_hit or abs_floor_hit:
                if relative_sl_hit:
                    reason = (f"RELATIVE SL: stock {stock_change:+.2f}% | "
                              f"Nifty {nifty_change_pct:+.2f}% | "
                              f"underperforms by {abs(underperformance):.2f}%")
                else:
                    reason = (f"ABSOLUTE SL: loss ₹{abs(abs_loss):.0f} "
                              f"exceeds floor ₹{config.STOP_LOSS_ABS_FLOOR}")

                print(f"\n  🛑 [SL] {stock['name']:<22} | {reason}")
                execute_trade(stock, "SELL", 0.0, current_price)
                exited.append(stock["name"])

                mode = "PAPER" if config.PAPER_TRADING else "LIVE"
                send_alert(
                    f"🛑 <b>[{mode}] STOP LOSS — {stock['name']}</b>\n"
                    f"Buy   : ₹{buy_price}\n"
                    f"Exit  : ₹{current_price}\n"
                    f"Loss  : ₹{abs(abs_loss):.0f}\n"
                    f"Reason: {reason}"
                )
            else:
                print(f"  [SL] {stock['name']:<22} | "
                      f"stock {stock_change:+.2f}% | Nifty {nifty_change_pct:+.2f}% | OK")

        except Exception as e:
            print(f"  [SL] Error checking {symbol}: {e}")

    if exited:
        print(f"\n  [SL] Exited {len(exited)}: {', '.join(exited)}")


def vix_exit_all(vix: float, vix_mode: str):
    """Force exits everything when VIX hits DEFENSE or CRISIS."""
    from trader import open_positions
    from screener import BROAD_UNIVERSE

    if not open_positions:
        print(f"  [VIX {vix_mode}] No open positions to exit")
        return

    print(f"\n  🚨 [VIX {vix_mode}] VIX={vix} — "
          f"exiting all {len(open_positions)} positions NOW")

    send_alert(
        f"🚨 <b>VIX CIRCUIT BREAKER — {vix_mode}</b>\n"
        f"VIX   : {vix}\n"
        f"Action: Exiting ALL {len(open_positions)} positions\n"
        f"Resume: when VIX drops below {config.VIX_CAUTION_MAX}"
    )

    all_stocks = {s["symbol"]: s for s in BROAD_UNIVERSE}

    for symbol, pos in list(open_positions.items()):
        stock = all_stocks.get(symbol)
        if not stock:
            continue
        try:
            closes        = fetch_candles(stock["token"], config.CANDLE_INTERVAL, 2)
            current_price = closes[-1]
            buy_price     = pos["price"] if isinstance(pos, dict) else pos
            buy_qty       = pos["quantity"] if isinstance(pos, dict) else 1
            pnl           = round((current_price - buy_price) * buy_qty, 2)
            pnl_str       = f"+₹{pnl}" if pnl >= 0 else f"-₹{abs(pnl)}"
            execute_trade(stock, "SELL", 0.0, current_price)
            print(f"  [VIX EXIT] {stock['name']:<22} | "
                  f"₹{buy_price} → ₹{current_price} | {pnl_str}")
            time.sleep(config.DELAY_BETWEEN_STOCKS)
        except Exception as e:
            print(f"  [VIX EXIT] Failed {symbol}: {e}")


def run_scan():
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*62}")
    print(f"  Scan at {now_str} IST")
    print(f"  Mode: {'⚠️  LIVE' if not config.PAPER_TRADING else 'PAPER TRADING'}")
    print(f"{'='*62}")

    # ── Step 1: VIX master circuit breaker ────────────────────────────────────
    vix_level             = fetch_vix()
    vix_mode, _, vix_desc = get_vix_mode(vix_level)
    vix_icon = {"NORMAL": "✅", "CAUTION": "⚠️", "DEFENSE": "🚨", "CRISIS": "🛑"}
    print(f"  {vix_icon.get(vix_mode,'?')} VIX: {vix_level} → {vix_mode} | {vix_desc}")

    # DEFENSE or CRISIS → exit everything and pause
    if should_exit_all(vix_level):
        vix_exit_all(vix_level, vix_mode)
        print(f"\n  Bot paused — resuming when VIX < {config.VIX_CAUTION_MAX}")
        return

    # ── Step 2: Screener + market direction ───────────────────────────────────
    try:
        stocks_to_scan, strategy_mode, gap_pct = get_candidates()
    except Exception as e:
        print(f"  [SCREENER] Failed ({e}) — falling back to config.STOCKS")
        stocks_to_scan = config.STOCKS
        strategy_mode  = "MEAN_REVERSION"
        gap_pct        = 0.0

    if not stocks_to_scan:
        print("  [SCREENER] Zero candidates — skipping scan.")
        send_alert("⚠️ Screener returned 0 candidates — check API!")
        return

    # Nifty intraday % change (from screener's gap calculation)
    nifty_change_pct = gap_pct

    # ── Step 3: Smart stop loss on all open positions ─────────────────────────
    print(f"\n  Checking stop losses (Nifty {nifty_change_pct:+.2f}% today)...")
    check_stop_losses(nifty_change_pct)

    # ── Step 4: Strategy mode ─────────────────────────────────────────────────
    is_flat_market = (strategy_mode == "FLAT")
    strategy_labels = {
        "STRONG_MOMENTUM": "STRONG MOMENTUM  RSI>60 + breakout → BUY",
        "MILD_MOMENTUM":   "MILD MOMENTUM    RSI>52 → BUY | RSI<44 → SELL",
        "FLAT":            "FLAT MARKET      RSI<35 → BUY | RSI>70 → SELL",
        "MEAN_REVERSION":  "MEAN REVERSION   RSI<25 → BUY | RSI>78 → SELL",
        "MOMENTUM":        "MOMENTUM         RSI>60 → BUY",
    }
    print(f"\n  Strategy : {strategy_labels.get(strategy_mode, strategy_mode)}")
    print(f"  Scanning : {len(stocks_to_scan)} candidates\n")

    # ── Step 5: RSI scan ──────────────────────────────────────────────────────
    signals = []
    for stock in stocks_to_scan:
        time.sleep(config.DELAY_BETWEEN_STOCKS)
        try:
            closes = fetch_candles(
                stock["token"],
                config.CANDLE_INTERVAL,
                config.CANDLES_NEEDED
            )
            if len(closes) < config.RSI_PERIOD + 1:
                continue

            rsi           = calculate_rsi(closes, config.RSI_PERIOD)
            current_price = closes[-1]

            signal = get_signal(
                rsi            = rsi,
                oversold       = config.RSI_OVERSOLD,
                overbought     = config.RSI_OVERBOUGHT,
                mode           = strategy_mode,
                closes         = closes,
                is_flat_market = is_flat_market,
            )
            signals.append((stock, signal, rsi, current_price))

        except Exception as e:
            print(f"  {stock['name']:<24} | ERROR: {e}")

    # ── Step 6: Market breadth filter ─────────────────────────────────────────
    buy_signals  = [s for s in signals if s[1] == "BUY"]
    sell_signals = [s for s in signals if s[1] == "SELL"]

    if strategy_mode == "MEAN_REVERSION" and \
       len(buy_signals) > config.MAX_BUY_SIGNALS_PER_SCAN:
        print(f"\n  MARKET FILTER: {len(buy_signals)} BUYs "
              f"(limit {config.MAX_BUY_SIGNALS_PER_SCAN}) — skipping all BUYs.")
        buy_signals = []

    # ── Step 7: VIX CAUTION — allow SELLs, block new BUYs ───────────────────
    if vix_mode == "CAUTION":
        if buy_signals:
            print(f"\n  ⚠️  VIX CAUTION ({vix_level}) — "
                  f"blocking {len(buy_signals)} BUY(s), processing SELLs only")
        buy_signals = []

    # ── Step 8: Print results ─────────────────────────────────────────────────
    for stock, signal, rsi, price in signals:
        marker = " ◀ TRADE" if signal != "HOLD" else ""
        print(f"  {stock['name']:<24} | ₹{price:<10} | RSI {rsi:>6.2f} → {signal}{marker}")

    # ── Step 9: Execute trades ────────────────────────────────────────────────
    executed = 0
    for stock, signal, rsi, price in buy_signals + sell_signals:
        trade = execute_trade(stock, signal, rsi, price)
        if trade:
            executed += 1
            mode = "PAPER" if config.PAPER_TRADING else "LIVE"
            send_alert(
                f"<b>[{mode}] {signal} — {strategy_mode}</b>\n"
                f"Stock : {stock['name']}\n"
                f"Price : ₹{price}\n"
                f"RSI   : {rsi}\n"
                f"P&L   : {trade.get('pnl', 'N/A')}"
            )

    if executed:
        print(f"\n  Executed {executed} trade(s) this scan")

    # ── Step 10: Summary ──────────────────────────────────────────────────────
    from trader import open_positions
    if open_positions:
        print(f"\n  Open ({len(open_positions)}/{config.MAX_OPEN_POSITIONS}): "
              f"{', '.join(k.replace('-EQ','') for k in open_positions.keys())}")
    else:
        print(f"\n  Open positions: 0 — all flat")


def main():
    print("\n" + "="*62)
    print("  NSE Trading Bot — RSI + VIX Circuit Breaker + Smart SL")
    print(f"  Capital  : ₹{config.TOTAL_CAPITAL:,} | "
          f"Per trade: ₹{config.CAPITAL_PER_TRADE:,} | "
          f"Max positions: {config.MAX_OPEN_POSITIONS}")
    print(f"  Mode     : {'⚠️  LIVE TRADING' if not config.PAPER_TRADING else 'PAPER TRADING'}")
    print(f"  Stop loss: -{config.STOP_LOSS_BUFFER}% vs Nifty | "
          f"hold≥{config.STOP_LOSS_MIN_HOLD_MINS}min | "
          f"floor ₹{config.STOP_LOSS_ABS_FLOOR}")
    print(f"  VIX guard: caution>{config.VIX_NORMAL_MAX} | "
          f"exit>{config.VIX_CAUTION_MAX} | "
          f"halt>{config.VIX_DEFENSE_MAX}")
    print("="*62)

    get_angel()

    vix = fetch_vix()
    _, _, vix_desc = get_vix_mode(vix)
    print(f"\n  Startup VIX check: {vix_desc}")

    send_alert(
        f"🤖 <b>Bot started</b>\n"
        f"Mode : {'PAPER' if config.PAPER_TRADING else '⚠️ LIVE'}\n"
        f"VIX  : {vix}\n"
        f"SL   : -{config.STOP_LOSS_BUFFER}% vs Nifty | "
        f"floor ₹{config.STOP_LOSS_ABS_FLOOR}"
    )

    last_scan_day = None

    while True:
        now   = datetime.now(IST)
        today = now.date()

        if last_scan_day != today:
            last_scan_day = today

        if is_market_open():
            run_scan()
            print(f"\n  Next scan in {SCAN_INTERVAL // 60} minutes...")
            time.sleep(SCAN_INTERVAL)
        else:
            print(f"  [{now.strftime('%H:%M')}] Market closed — "
                  f"waiting for 9:15 AM IST (Mon-Fri)...")
            time.sleep(60)


if __name__ == "__main__":
    main()
