"""
daily_report.py

Run this at the end of each trading day:
    python daily_report.py

The bot also calls run_reports() once trading time is over.

Generates a day-by-day track in reports/:
    reports/YYYY-MM-DD.json     ← structured data for that session
    reports/YYYY-MM-DD.txt      ← readable summary
    reports/daily_log.json      ← one row per day (grows over time)
"""

import os
from collections import defaultdict

from persist import load_json, save_json
from ledger import fifo_round_trips

PAPER_LOG_FILE = "paper_trades.json"
REPORTS_DIR    = "reports"


def daily_log_path(reports_dir=REPORTS_DIR):
    return os.path.join(reports_dir, "daily_log.json")


def load_trades():
    if not os.path.exists(PAPER_LOG_FILE):
        print("No paper_trades.json found.")
        return []
    return load_json(PAPER_LOG_FILE, [])


def analyze_day(date, all_trades):
    """
    FIFO-match across all history up to this date.
    Realised P&L is attributed to the SELL date (overnight holds count).
    """
    day_trades = [t for t in all_trades if t["timestamp"][:10] == date]
    through = [t for t in all_trades if t["timestamp"][:10] <= date]
    closed_all, unmatched_buys = fifo_round_trips(through)
    matched = []
    for c in closed_all:
        if c["sell_time"][:10] != date:
            continue
        matched.append({
            **c,
            "buy_time": c["buy_time"][11:] if len(c["buy_time"]) > 10 else c["buy_time"],
            "sell_time": c["sell_time"][11:] if len(c["sell_time"]) > 10 else c["sell_time"],
        })

    buys = [t for t in day_trades if t["action"] == "BUY"]
    sells = [t for t in day_trades if t["action"] == "SELL"]

    total_pnl      = round(sum(m["pnl"] for m in matched), 2)
    profitable     = [m for m in matched if m["pnl"] > 0]
    losing         = [m for m in matched if m["pnl"] < 0]
    win_rate       = round(len(profitable) / len(matched) * 100, 1) if matched else 0
    avg_profit     = round(sum(m["pnl"] for m in profitable) / len(profitable), 2) if profitable else 0
    avg_loss       = round(sum(m["pnl"] for m in losing) / len(losing), 2) if losing else 0
    best_trade     = max(matched, key=lambda x: x["pnl"]) if matched else None
    worst_trade    = min(matched, key=lambda x: x["pnl"]) if matched else None
    open_exposure  = round(sum(t.get("value", 0) for t in unmatched_buys), 2)

    stock_counts = defaultdict(int)
    for t in day_trades:
        stock_counts[t["stock"]] += 1
    most_active = sorted(stock_counts.items(), key=lambda x: -x[1])[:5]

    return {
        "date":           date,
        "total_trades":   len(day_trades),
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


def save_day_json(result, reports_dir=REPORTS_DIR):
    """Saves the day's structured result to reports/YYYY-MM-DD.json"""
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"{result['date']}.json")
    save_json(path, result)
    return path


def save_day_txt(result, reports_dir=REPORTS_DIR):
    """Saves a readable text summary to reports/YYYY-MM-DD.txt"""
    os.makedirs(reports_dir, exist_ok=True)
    path = os.path.join(reports_dir, f"{result['date']}.txt")

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


def log_entry(result):
    """Lightweight row stored in daily_log.json (one per calendar day)."""
    return {
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


def update_daily_log(result, reports_dir=REPORTS_DIR):
    """
    Appends/updates daily_log.json with this day's summary.
    Re-running the same date replaces that row — the file is the day-by-day track.
    """
    path = daily_log_path(reports_dir)
    os.makedirs(reports_dir, exist_ok=True)
    log = load_json(path, [])
    if not isinstance(log, list):
        log = []

    entry = log_entry(result)
    existing = next((i for i, e in enumerate(log) if e.get("date") == result["date"]), None)
    if existing is not None:
        log[existing] = entry
    else:
        log.append(entry)

    log.sort(key=lambda x: x["date"])
    save_json(path, log)
    return log


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


def format_alert(result):
    """Short Telegram / log line for the day's track."""
    pnl = result["realised_pnl"]
    pnl_s = f"+₹{pnl}" if pnl >= 0 else f"-₹{abs(pnl)}"
    return (
        f"📊 <b>Daily report — {result['date']}</b>\n"
        f"Trades : {result['total_trades']} "
        f"({result['total_buys']} BUY / {result['total_sells']} SELL)\n"
        f"Closed : {result['matched_trades']} | "
        f"Win {result['win_rate']}% "
        f"({result['profitable']}/{result['losing']})\n"
        f"PnL    : {pnl_s}\n"
        f"Open   : {result['open_positions']} "
        f"(₹{result['open_exposure']:,.0f})"
    )


def write_day(result, reports_dir=REPORTS_DIR):
    json_path = save_day_json(result, reports_dir)
    txt_path = save_day_txt(result, reports_dir)
    log = update_daily_log(result, reports_dir)
    return json_path, txt_path, log


def run_reports(only_date=None, reports_dir=REPORTS_DIR, trades=None, quiet=False):
    """
    Write per-day files and refresh daily_log.json.

    only_date: if set, write that calendar day even when it has zero fills
               (so EOD always leaves a track). Otherwise rebuild every date
               present in the ledger.
    """
    trades = load_trades() if trades is None else trades
    if trades is None:
        trades = []

    dates = sorted({t["timestamp"][:10] for t in trades if t.get("timestamp")})
    if only_date:
        dates = [only_date]
    elif not dates:
        if not quiet:
            print("No paper_trades.json found.")
        return []

    if not quiet:
        print(f"\nFound {len(trades)} trades across {len(dates)} day(s)\n")

    results = []
    for date in dates:
        day_n = sum(1 for t in trades if t.get("timestamp", "")[:10] == date)
        if not quiet:
            print(f"Processing {date} ({day_n} trades)...")
        result = analyze_day(date, trades)
        json_path, txt_path, log = write_day(result, reports_dir)
        results.append(result)

        if not quiet:
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

    log = load_json(daily_log_path(reports_dir), [])
    if not quiet:
        print_comparison(log)
        print(f"\nAll reports saved to '{reports_dir}/' folder")
    return results


def main():
    run_reports()


if __name__ == "__main__":
    main()
