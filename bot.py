import sys
import time
from datetime import datetime

import config
from angel_client import candle_cache_fresh, fetch_candles, get_angel
from logutil import log, setup_logging
import market_hours as mh
from notifier import send_alert
from risk import evaluate_stop_loss, hold_minutes
from screener import (
    DIRECTION_TO_STRATEGY,
    MIN_RSI_QUOTES,
    classify_rsi_tape,
    get_candidates,
    rank_buy_signals,
)
from strategy import calculate_rsi, get_signal
from trader import execute_trade, open_positions
from daily_report import format_alert, run_reports
from universe import apply_session_universe
from vix_monitor import (
    fetch_vix,
    get_vix_mode,
    is_safe_to_buy,
    should_exit_all,
    should_halt,
)


IST = mh.IST
MARKET_OPEN = config.MARKET_OPEN
MARKET_CLOSE = config.MARKET_CLOSE
SCAN_INTERVAL = config.SCAN_INTERVAL_SECONDS


def is_market_open() -> bool:
    return mh.is_market_open(
        market_open=config.MARKET_OPEN,
        market_close=config.MARKET_CLOSE,
    )


def is_square_off_window() -> bool:
    return mh.is_square_off_window(
        square_off=config.SQUARE_OFF_TIME,
        market_close=config.MARKET_CLOSE,
    )


def _universe_map() -> dict:
    return {s["symbol"]: s for s in config.BROAD_UNIVERSE}


def flatten_all(reason: str):
    """Sell every open slot (VIX, crisis, or end-of-day square-off)."""
    if not open_positions:
        log.info("[%s] No open positions to exit", reason)
        return

    log.warning("%s — exiting all %s positions", reason, len(open_positions))
    send_alert(
        f"🚨 <b>{reason}</b>\n"
        f"Action: Exiting ALL {len(open_positions)} positions"
    )

    stocks = _universe_map()
    for symbol, pos in list(open_positions.items()):
        stock = stocks.get(symbol)
        if not stock:
            log.error("Cannot exit %s — not in universe", symbol)
            continue
        try:
            closes = fetch_candles(stock["token"], config.CANDLE_INTERVAL, 2)
            current_price = closes[-1]
            buy_price = pos["price"] if isinstance(pos, dict) else pos
            buy_qty = pos["quantity"] if isinstance(pos, dict) else 1
            pnl = round((current_price - buy_price) * buy_qty, 2)
            execute_trade(stock, "SELL", 0.0, current_price)
            log.info("[EXIT %s] %-22s | ₹%s → ₹%s | ₹%s",
                     reason, stock["name"], buy_price, current_price, pnl)
            time.sleep(config.DELAY_BETWEEN_STOCKS)
        except Exception as e:
            log.error("[EXIT %s] Failed %s: %s", reason, symbol, e)


def check_stop_losses(nifty_change_pct: float):
    if not open_positions:
        return

    stocks = _universe_map()
    now = datetime.now(IST)
    exited = []

    for symbol, pos in list(open_positions.items()):
        stock = stocks.get(symbol)
        if not stock:
            continue
        try:
            buy_price = pos["price"]
            buy_qty = pos["quantity"]
            mins = hold_minutes(pos, now)

            closes = fetch_candles(stock["token"], config.CANDLE_INTERVAL, 2)
            current_price = closes[-1]
            time.sleep(config.DELAY_BETWEEN_STOCKS)

            hit, reason = evaluate_stop_loss(
                buy_price, buy_qty, current_price, nifty_change_pct, mins
            )
            stock_change = ((current_price - buy_price) / buy_price) * 100
            if not hit:
                if mins < config.STOP_LOSS_MIN_HOLD_MINS:
                    remaining = int(config.STOP_LOSS_MIN_HOLD_MINS - mins)
                    log.info("[SL] %-22s | Hold protection: %smin left",
                             stock["name"], remaining)
                else:
                    log.info("[SL] %-22s | stock %+.2f%% | Nifty %+.2f%% | OK",
                             stock["name"], stock_change, nifty_change_pct)
                continue

            log.warning("[SL] %-22s | %s", stock["name"], reason)
            execute_trade(stock, "SELL", 0.0, current_price)
            exited.append(stock["name"])
            abs_loss = round((current_price - buy_price) * buy_qty, 2)
            mode = "PAPER" if config.PAPER_TRADING else "LIVE"
            send_alert(
                f"🛑 <b>[{mode}] STOP LOSS — {stock['name']}</b>\n"
                f"Buy   : ₹{buy_price}\n"
                f"Exit  : ₹{current_price}\n"
                f"Loss  : ₹{abs(abs_loss):.0f}\n"
                f"Reason: {reason}"
            )
        except Exception as e:
            log.error("[SL] Error checking %s: %s", symbol, e)

    if exited:
        log.info("[SL] Exited %s: %s", len(exited), ", ".join(exited))


def run_scan():
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    log.info("=" * 62)
    log.info("Scan at %s IST", now_str)
    log.info("Mode: %s", "LIVE" if not config.PAPER_TRADING else "PAPER TRADING")

    vix_level = fetch_vix()
    vix_mode, _, vix_desc = get_vix_mode(vix_level)
    log.info("VIX: %s → %s | %s", vix_level, vix_mode, vix_desc)

    if should_halt(vix_level):
        flatten_all(f"VIX CRISIS {vix_level}")
        log.warning("Bot HALTED — no scans until VIX < %s", config.VIX_CAUTION_MAX)
        send_alert(
            f"🛑 <b>VIX CRISIS — bot halted</b>\n"
            f"VIX: {vix_level}\n"
            f"Resume when VIX < {config.VIX_CAUTION_MAX}"
        )
        return "halt"

    if should_exit_all(vix_level):
        flatten_all(f"VIX {vix_mode} {vix_level}")
        log.warning("Paused new trades — resuming when VIX < %s",
                    config.VIX_CAUTION_MAX)
        return "pause"

    try:
        packed = get_candidates()
        stocks_to_scan, strategy_mode, nifty_pct = packed[0], packed[1], packed[2]
        allow_new_buys = packed[3] if len(packed) > 3 else True
    except Exception as e:
        log.error("[SCREENER] Failed (%s) — RSI full universe anyway", e)
        stocks_to_scan = [
            {"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
            for s in config.BROAD_UNIVERSE
        ]
        strategy_mode = "RSI_TAPE"
        nifty_pct = 0.0
        allow_new_buys = True

    log.info("Checking stop losses (Nifty %+.2f%% today)...", nifty_pct)
    check_stop_losses(nifty_pct)

    if not stocks_to_scan:
        log.warning("[SCREENER] Zero candidates — exits-only this scan.")
        if not allow_new_buys:
            send_alert("⚠️ Screener has no trustworthy tape — blocked new buys")
        return None

    strategy_labels = {
        "STRONG_MOMENTUM": "STRONG MOMENTUM  RSI>60 + breakout → BUY",
        "MILD_MOMENTUM":   "MILD MOMENTUM    RSI>52 → BUY | RSI<44 → SELL",
        "FLAT":            "FLAT MARKET      RSI<35 → BUY | RSI>70 → SELL",
        "MEAN_REVERSION":  "MEAN REVERSION   RSI<25 → BUY | RSI>78 → SELL",
        "MOMENTUM":        "MOMENTUM         RSI>60 → BUY",
        "RSI_TAPE":        "RSI TAPE         scan all names, then pick mode from RSI",
    }
    log.info("Strategy : %s", strategy_labels.get(strategy_mode, strategy_mode))
    log.info("RSI scan : %s stocks (full universe, not A-50)", len(stocks_to_scan))

    quotes = []
    candle_errors = 0
    for stock in stocks_to_scan:
        if not candle_cache_fresh(
            stock["token"], config.CANDLE_INTERVAL, config.CANDLES_NEEDED
        ):
            time.sleep(config.DELAY_BETWEEN_STOCKS)
        try:
            closes = fetch_candles(
                stock["token"],
                config.CANDLE_INTERVAL,
                config.CANDLES_NEEDED,
            )
            if len(closes) < config.RSI_PERIOD + 1:
                continue
            rsi = calculate_rsi(closes, config.RSI_PERIOD)
            quotes.append((stock, rsi, closes[-1], closes))
        except Exception as e:
            candle_errors += 1
            if candle_errors <= 8:
                log.error("%-24s | ERROR: %s", stock["name"], e)
            elif candle_errors == 9:
                log.error("Suppressing further candle errors this scan")

    if strategy_mode == "RSI_TAPE":
        inferred = classify_rsi_tape([q[1] for q in quotes])
        log.info("RSI tape (%s prints) → %s", len(quotes), inferred)
        if inferred == "UNKNOWN":
            allow_new_buys = False
            strategy_mode = "FLAT"
        else:
            strategy_mode = DIRECTION_TO_STRATEGY[inferred]
        log.info("Strategy : %s", strategy_labels.get(strategy_mode, strategy_mode))

    if len(quotes) < MIN_RSI_QUOTES:
        log.warning("Only %s RSI prints (need %s) — blocking new buys",
                    len(quotes), MIN_RSI_QUOTES)
        allow_new_buys = False

    signals = []
    for stock, rsi, price, closes in quotes:
        signal = get_signal(
            rsi=rsi,
            oversold=config.RSI_OVERSOLD,
            overbought=config.RSI_OVERBOUGHT,
            mode=strategy_mode,
            closes=closes,
            is_flat_market=(strategy_mode == "FLAT"),
        )
        signals.append((stock, signal, rsi, price))

    buy_signals = [s for s in signals if s[1] == "BUY"]
    sell_signals = [s for s in signals if s[1] == "SELL"]
    hold_n = len(signals) - len(buy_signals) - len(sell_signals)
    log.info("RSI filter: %s names | BUY %s | SELL %s | HOLD %s",
             len(signals), len(buy_signals), len(sell_signals), hold_n)
    for stock, signal, rsi, price in buy_signals + sell_signals:
        log.info("%-24s | ₹%-10s | RSI %6.2f → %s ◀ TRADE",
                 stock["name"], price, rsi, signal)

    if not allow_new_buys and buy_signals:
        log.warning("DATA FILTER: blocking %s BUY(s)", len(buy_signals))
        buy_signals = []

    if not is_safe_to_buy(vix_level):
        if buy_signals:
            log.info("VIX %s (%s) — blocking %s BUY(s), processing SELLs only",
                     vix_mode, vix_level, len(buy_signals))
        buy_signals = []

    free_slots = max(0, config.MAX_OPEN_POSITIONS - len(open_positions))
    entry_cap = min(config.MAX_BUY_SIGNALS_PER_SCAN, free_slots)
    ranked_buys = rank_buy_signals(buy_signals, strategy_mode, entry_cap)
    if len(buy_signals) > len(ranked_buys):
        log.info("Ranked %s RSI BUYs → %s entries: %s",
                 len(buy_signals), len(ranked_buys),
                 ", ".join(s[0]["name"] for s in ranked_buys) or "(none)")
    buy_signals = ranked_buys

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
        log.info("Executed %s trade(s) this scan", executed)

    if open_positions:
        log.info("Open (%s/%s): %s",
                 len(open_positions), config.MAX_OPEN_POSITIONS,
                 ", ".join(k.replace("-EQ", "") for k in open_positions.keys()))
    else:
        log.info("Open positions: 0 — all flat")
    return None


def _wait_out_halt():
    while is_market_open() and not _slice_over():
        vix = fetch_vix(force=True)
        if not should_halt(vix):
            log.info("VIX %s — leaving halt", vix)
            return
        log.info("[HALT] VIX %s — sleeping 60s", vix)
        time.sleep(60)


def _slice_over(now=None) -> bool:
    now = now or mh.now_ist()
    end = mh.session_end_hhmm(config.MARKET_CLOSE)
    return (not is_market_open()) or mh.past_hhmm(now, end)


def _should_flatten_this_slice() -> bool:
    """Morning GHA slice (SESSION_END before 15:15) must keep positions for the afternoon job."""
    end = mh.session_end_hhmm(config.MARKET_CLOSE)
    return end >= config.SQUARE_OFF_TIME


_eod_report_day = None


def trading_day_ist(now=None) -> str:
    now = now or mh.now_ist()
    return now.strftime("%Y-%m-%d")


def run_eod_daily_report(now=None):
    """Once per calendar day: write reports/YYYY-MM-DD + daily_log.json after the cash session."""
    global _eod_report_day
    day = trading_day_ist(now)
    if _eod_report_day == day:
        return None
    try:
        results = run_reports(only_date=day, quiet=True)
        result = results[0] if results else None
        if result is None:
            log.warning("Daily report produced no row for %s", day)
            return None
        _eod_report_day = day
        log.info(
            "Daily report %s | trades=%s matched=%s pnl=%s win=%s%% open=%s | reports/%s.json + daily_log.json",
            day,
            result["total_trades"],
            result["matched_trades"],
            result["realised_pnl"],
            result["win_rate"],
            result["open_positions"],
            day,
        )
        send_alert(format_alert(result))
        return result
    except Exception as e:
        log.error("Daily report failed: %s", e)
        return None


def wait_for_session_start():
    now = mh.now_ist()
    if not mh.is_weekday(now):
        log.info("Weekend — nothing to run")
        sys.exit(0)
    if mh.past_hhmm(now, config.MARKET_CLOSE) and not is_market_open():
        log.info("NSE already closed today (%s IST) — session exit",
                 now.strftime("%H:%M"))
        if _should_flatten_this_slice():
            run_eod_daily_report(now)
        sys.exit(0)
    while not is_market_open():
        now = mh.now_ist()
        if _slice_over(now):
            log.info("Past session end before open — exit")
            sys.exit(0)
        log.info("[%s] Waiting for 09:15 IST...", now.strftime("%H:%M"))
        time.sleep(20)


def _sleep_until_next_scan():
    end = mh.session_end_hhmm(config.MARKET_CLOSE)
    now = mh.now_ist()
    target = now.replace(hour=end[0], minute=end[1], second=0, microsecond=0)
    remaining = (target - now).total_seconds()
    delay = SCAN_INTERVAL
    if remaining > 0:
        delay = min(SCAN_INTERVAL, remaining)
    log.info("Next scan in %s seconds...", int(delay))
    time.sleep(max(5, delay))


def main():
    setup_logging()
    log.info("=" * 62)
    log.info("NSE Trading Bot — RSI + VIX Circuit Breaker + Smart SL")
    log.info("Capital  : ₹%s | Per trade: ₹%s | Max positions: %s",
             f"{config.TOTAL_CAPITAL:,}", f"{config.CAPITAL_PER_TRADE:,}",
             config.MAX_OPEN_POSITIONS)
    log.info("Mode     : %s",
             "LIVE TRADING" if not config.PAPER_TRADING else "PAPER TRADING")
    log.info("Stop loss: -%s%% vs Nifty | abs -%s%% | hold≥%smin | floor ₹%s",
             config.STOP_LOSS_BUFFER, config.STOP_LOSS_PCT,
             config.STOP_LOSS_MIN_HOLD_MINS, config.STOP_LOSS_ABS_FLOOR)
    log.info("VIX guard: caution>%s | exit>%s | halt>%s",
             config.VIX_NORMAL_MAX, config.VIX_CAUTION_MAX, config.VIX_DEFENSE_MAX)
    log.info("Square-off from %s IST",
             f"{config.SQUARE_OFF_TIME[0]:02d}:{config.SQUARE_OFF_TIME[1]:02d}")
    if mh.session_mode_enabled():
        end = mh.session_end_hhmm(config.MARKET_CLOSE)
        log.info("GitHub/session slice until %02d:%02d IST then exit",
                 end[0], end[1])

    if mh.session_mode_enabled():
        wait_for_session_start()

    apply_session_universe()

    get_angel()

    vix = fetch_vix()
    _, _, vix_desc = get_vix_mode(vix)
    log.info("Startup VIX check: %s", vix_desc)

    send_alert(
        f"🤖 <b>Bot started</b>\n"
        f"Mode : {'PAPER' if config.PAPER_TRADING else '⚠️ LIVE'}\n"
        f"VIX  : {vix}\n"
        f"SL   : -{config.STOP_LOSS_BUFFER}% vs Nifty | "
        f"-{config.STOP_LOSS_PCT}% abs | floor ₹{config.STOP_LOSS_ABS_FLOOR}"
    )

    while True:
        now = mh.now_ist()

        if mh.session_mode_enabled() and _slice_over(now):
            if _should_flatten_this_slice():
                flatten_all("EOD SQUARE-OFF")
                run_eod_daily_report(now)
            log.info("Session slice complete — process exit")
            return

        if not is_market_open():
            log.info("[%s] Market closed — waiting for 9:15 AM IST (Mon-Fri)...",
                     now.strftime("%H:%M"))
            time.sleep(60)
            continue

        if is_square_off_window():
            flatten_all("EOD SQUARE-OFF")
            log.info("Square-off window — not opening new trades")
            run_eod_daily_report(now)
            if mh.session_mode_enabled():
                return
            time.sleep(60)
            continue

        result = run_scan()
        if result == "halt":
            _wait_out_halt()
            continue
        if mh.session_mode_enabled():
            _sleep_until_next_scan()
        else:
            log.info("Next scan in %s minutes...", SCAN_INTERVAL // 60)
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
