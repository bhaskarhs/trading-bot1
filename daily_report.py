"""
daily_report.py

Run this at the end of each trading day:
    python daily_report.py

Generates two files in a 'reports/' folder:
    reports/YYYY-MM-DD.json     ← structured data for comparison
    reports/YYYY-MM-DD.txt      ← readable summary you can read/share
"""

import json
import os
from datetime import datetime
from collections import defaultdict

PAPER_LOG_FILE = "paper_trades.json"
REPORTS_DIR    = "reports"
DAILY_LOG_FILE = os.path.join(REPORTS_DIR, "daily_log.json")


def load_trades():
    if not os.path.exists(PAPER_LOG_FILE):
        print("No paper_trades.json found.")
        return []
    with open(PAPER_LOG_FILE) as f:
        return json.load(f)


def group_by_day(trades):
    """Groups all trades by date."""
    days = defaultdict(list)
    for t in trades:
        date = t["timestamp"][:10]
        days[date].append(t)
    return days


def analyze_day(date, trades):
    """
    Analyses one day's trades.
    Matches each BUY to the next SELL of same stock to compute real P&L.
    """
    buys  = [t for t in trades if t["action"] == "BUY"]
    sells = [t for t in trades if t["action"] == "SELL"]

    # Match BUY → SELL per stock (first-in first-out)
    buy_queue  = defaultdict(list)
    matched    = []
    unmatched_buys = []

    for t in sorted(trades, key=lambda x: x["timestamp"]):
        if t["action"] == "BUY":
            buy_queue[t["stock"]].append(t)
        elif t["action"] == "SELL" and buy_queue[t["stock"]]:
            buy_trade = buy_queue[t["stock"]].pop(0)
            pnl = round((t["price"] - buy_trade["price"]) * t["quantity"], 2)
            matched.append({
                "stock":      t["stock"],
                "buy_price":  buy_trade["price"],
                "sell_price": t["price"],
                "buy_time":   buy_trade["timestamp"][11:],
                "sell_time":  t["timestamp"][11:],
                "rsi_buy":    buy_trade["rsi"],
                "rsi_sell":   t["rsi"],
                "pnl":        pnl,
                "result":     "PROFIT" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN",
            })

    # Remaining unmatched buys = open positions
    for stock, queue in buy_queue.items():
        for t in queue:
            unmatched_buys.append(t)

    # Stats
    total_pnl      = round(sum(m["pnl"] for m in matched), 2)
    profitable     = [m for m in matched if m["pnl"] > 0]
    losing         = [m for m in matched if m["pnl"] < 0]
    win_rate       = round(len(profitable) / len(matched) * 100, 1) if matched else 0
    avg_profit     = round(sum(m["pnl"] for m in profitable) / len(profitable), 2) if profitable else 0
    avg_loss       = round(sum(m["pnl"] for m in losing) / len(losing), 2) if losing else 0
    best_trade     = max(matched, key=lambda x: x["pnl"]) if matched else None
    worst_trade    = min(matched, key=lambda x: x["pnl"]) if matched else None
    open_exposure  = round(sum(t["value"] for t in unmatched_buys), 2)

    # Most active stocks
    stock_counts = defaultdict(int)
    for t in trades:
        stock_counts[t["stock"]] += 1
    most_active = sorted(stock_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "date":           date,
        "total_trades":   len(trades),
        "total_buys":     len(buys),
        "total_sells":    len(sells),
        "matched_trades": len(matched),
        "open_positions": len(unmatched_buys),
        "open_exposure":  open_exposure,
        "realised_pnl":   total_pnl,
        "win_rate":       win_rate,
        "profitable":     len(profitable),
        "losing":         len(losing),
        "avg_profit":     avg_profit,
        "avg_loss":       avg_loss,
        "best_trade":     best_trade,
        "worst_trade":    worst_trade,
        "most_active":    most_active,
        "matched":        matched,
        "open_positions_detail": unmatched_buys,
    }


def save_day_json(result):
    """Saves the day's structured result to reports/YYYY-MM-DD.json"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{result['date']}.json")
    with open(path, "w") as f:
        json.dump(result, f, indent=2)
    return path


def save_day_txt(result):
    """Saves a readable text summary to reports/YYYY-MM-DD.txt"""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    path = os.path.join(REPORTS_DIR, f"{result['date']}.txt")

    lines = []
    lines.append("=" * 60)
    lines.append(f"  DAILY TRADING REPORT — {result['date']}")
    lines.append("=" * 60)
    lines.append("")

    # Overview
    pnl_str = f"+₹{result['realised_pnl']}" if result['realised_pnl'] >= 0 else f"-₹{abs(result['realised_pnl'])}"
    lines.append("OVERVIEW")
    lines.append(f"  Total trades     : {result['total_trades']} "
                 f"({result['total_buys']} BUY / {result['total_sells']} SELL)")
    lines.append(f"  Matched trades   : {result['matched_trades']} completed round-trips")
    lines.append(f"  Open positions   : {result['open_positions']} "
                 f"(₹{result['open_exposure']:,.2f} exposure)")
    lines.append(f"  Realised P&L     : {pnl_str}")
    lines.append(f"  Win rate         : {result['win_rate']}% "
                 f"({result['profitable']} wins / {result['losing']} losses)")
    lines.append(f"  Avg profit trade : ₹{result['avg_profit']}")
    lines.append(f"  Avg loss trade   : ₹{result['avg_loss']}")
    lines.append("")

    # Best / Worst
    if result["best_trade"]:
        b = result["best_trade"]
        lines.append("BEST TRADE")
        lines.append(f"  {b['stock']} | BUY ₹{b['buy_price']} → SELL ₹{b['sell_price']} "
                     f"| P&L: +₹{b['pnl']}")
        lines.append("")

    if result["worst_trade"]:
        w = result["worst_trade"]
        lines.append("WORST TRADE")
        lines.append(f"  {w['stock']} | BUY ₹{w['buy_price']} → SELL ₹{w['sell_price']} "
                     f"| P&L: -₹{abs(w['pnl'])}")
        lines.append("")

    # All matched trades
    if result["matched"]:
        lines.append("COMPLETED TRADES")
        lines.append(f"  {'Stock':<22} {'Buy':>8} {'Sell':>8} {'P&L':>8}  Result")
        lines.append(f"  {'-'*55}")
        for m in result["matched"]:
            pnl_s = f"+₹{m['pnl']}" if m['pnl'] >= 0 else f"-₹{abs(m['pnl'])}"
            lines.append(f"  {m['stock']:<22} ₹{m['buy_price']:>7} ₹{m['sell_price']:>7} "
                         f"{pnl_s:>8}  {m['result']}")
        lines.append("")

    # Open positions
    if result["open_positions_detail"]:
        lines.append("OPEN POSITIONS (not yet sold)")
        lines.append(f"  {'Stock':<22} {'Buy Price':>10}  Buy Time")
        lines.append(f"  {'-'*45}")
        for t in result["open_positions_detail"]:
            lines.append(f"  {t['stock']:<22} ₹{t['price']:>9}  {t['timestamp'][11:]}")
        lines.append("")

    # Most active
    lines.append("MOST ACTIVE STOCKS")
    for stock, count in result["most_active"]:
        lines.append(f"  {stock:<22} {count} signals")
    lines.append("")
    lines.append("=" * 60)

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def update_daily_log(result):
    """
    Appends/updates the daily_log.json with today's summary.
    This file grows day by day — perfect for weekly/monthly comparison.
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)

    log = []
    if os.path.exists(DAILY_LOG_FILE):
        with open(DAILY_LOG_FILE) as f:
            log = json.load(f)

    # Summary entry for the log (lightweight — no full trade details)
    entry = {
        "date":           result["date"],
        "total_trades":   result["total_trades"],
        "matched_trades": result["matched_trades"],
        "open_positions": result["open_positions"],
        "realised_pnl":   result["realised_pnl"],
        "win_rate":       result["win_rate"],
        "profitable":     result["profitable"],
        "losing":         result["losing"],
        "open_exposure":  result["open_exposure"],
    }

    # Replace if date already exists, otherwise append
    existing = next((i for i, e in enumerate(log) if e["date"] == result["date"]), None)
    if existing is not None:
        log[existing] = entry
    else:
        log.append(entry)

    log.sort(key=lambda x: x["date"])

    with open(DAILY_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def print_comparison(log):
    """Prints a multi-day comparison table."""
    if len(log) < 2:
        return
    print("\nMULTI-DAY COMPARISON")
    print(f"  {'Date':<12} {'Trades':>7} {'Matched':>8} {'P&L':>10} {'Win%':>6} {'Open':>6}")
    print(f"  {'-'*55}")
    total_pnl = 0
    for e in log:
        pnl_s = f"+₹{e['realised_pnl']}" if e['realised_pnl'] >= 0 else f"-₹{abs(e['realised_pnl'])}"
        total_pnl += e['realised_pnl']
        print(f"  {e['date']:<12} {e['total_trades']:>7} {e['matched_trades']:>8} "
              f"{pnl_s:>10} {e['win_rate']:>5}% {e['open_positions']:>6}")
    print(f"  {'-'*55}")
    total_s = f"+₹{round(total_pnl,2)}" if total_pnl >= 0 else f"-₹{abs(round(total_pnl,2))}"
    print(f"  {'TOTAL':<12} {'':>7} {'':>8} {total_s:>10}")


def main():
    trades = load_trades()
    if not trades:
        return

    days = group_by_day(trades)
    print(f"\nFound {len(trades)} trades across {len(days)} day(s)\n")

    for date, day_trades in sorted(days.items()):
        print(f"Processing {date} ({len(day_trades)} trades)...")
        result   = analyze_day(date, day_trades)
        json_path = save_day_json(result)
        txt_path  = save_day_txt(result)
        update_daily_log(result)

        # Print summary to terminal
        pnl_s = f"+₹{result['realised_pnl']}" if result['realised_pnl'] >= 0 \
                else f"-₹{abs(result['realised_pnl'])}"
        print(f"  Realised P&L     : {pnl_s}")
        print(f"  Win rate         : {result['win_rate']}% "
              f"({result['profitable']} wins / {result['losing']} losses)")
        print(f"  Open positions   : {result['open_positions']} "
              f"(₹{result['open_exposure']:,.2f} exposure)")
        print(f"  Saved → {json_path}")
        print(f"  Saved → {txt_path}")
        print()

    # Show multi-day comparison if we have history
    if os.path.exists(DAILY_LOG_FILE):
        with open(DAILY_LOG_FILE) as f:
            log = json.load(f)
        print_comparison(log)

    print(f"\nAll reports saved to '{REPORTS_DIR}/' folder")


if __name__ == "__main__":
    main()
