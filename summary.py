import json
import os
from collections import defaultdict

PAPER_LOG_FILE = "paper_trades.json"
POSITIONS_FILE = "open_positions.json"


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def show_summary():
    trades = load_json(PAPER_LOG_FILE)
    if not trades:
        print("No paper trades found yet. Run bot.py first.")
        return

    open_pos = load_json(POSITIONS_FILE) or {}

    # ── Match BUY → SELL per stock (FIFO) ────────────────────────────────────
    buy_queue  = defaultdict(list)
    closed     = []

    for t in sorted(trades, key=lambda x: x["timestamp"]):
        if t["action"] == "BUY":
            buy_queue[t["symbol"]].append(t)
        elif t["action"] == "SELL" and buy_queue[t["symbol"]]:
            buy_trade = buy_queue[t["symbol"]].pop(0)
            qty       = t.get("quantity", 1)
            pnl       = round((t["price"] - buy_trade["price"]) * qty, 2)
            closed.append({
                "stock":      t["stock"],
                "buy_price":  buy_trade["price"],
                "sell_price": t["price"],
                "qty":        qty,
                "buy_time":   buy_trade["timestamp"],
                "sell_time":  t["timestamp"],
                "pnl":        pnl,
            })

    # ── Open positions: from open_positions.json ──────────────────────────────
    open_trades = []
    for symbol, pos in open_pos.items():
        if isinstance(pos, dict):
            open_trades.append({
                "stock":     pos.get("stock", symbol.replace("-EQ", "")),
                "symbol":    symbol,
                "buy_price": pos.get("price", 0),
                "qty":       pos.get("quantity", 1),
                "value":     pos.get("value", 0),
                "time":      pos.get("time", "—"),
            })

    # ── Print ─────────────────────────────────────────────────────────────────
    print("\n" + "="*65)
    print(f"  Paper Trading Summary")
    print("="*65)

    # Closed trades
    print(f"\n  CLOSED TRADES ({len(closed)})")
    if closed:
        print(f"  {'Stock':<22} {'Buy':>10} {'Sell':>10} {'Qty':>4} {'P&L':>10}  Result")
        print(f"  {'-'*62}")
        total_pnl = 0
        for c in closed:
            pnl_str = f"+₹{c['pnl']}" if c["pnl"] >= 0 else f"-₹{abs(c['pnl'])}"
            result  = "PROFIT" if c["pnl"] > 0 else "LOSS" if c["pnl"] < 0 else "FLAT"
            print(f"  {c['stock']:<22} ₹{c['buy_price']:>9} ₹{c['sell_price']:>9} "
                  f"{c['qty']:>4} {pnl_str:>10}  {result}")
            total_pnl += c["pnl"]

        wins   = [c for c in closed if c["pnl"] > 0]
        losses = [c for c in closed if c["pnl"] < 0]
        pnl_str = f"+₹{total_pnl:.2f}" if total_pnl >= 0 else f"-₹{abs(total_pnl):.2f}"

        print(f"  {'-'*62}")
        print(f"  Realised P&L  : {pnl_str}")
        print(f"  Win rate      : {len(wins)}/{len(closed)} "
              f"({len(wins)/len(closed)*100:.0f}%)" if closed else "")
        if wins:
            print(f"  Avg profit    : +₹{sum(c['pnl'] for c in wins)/len(wins):.2f}")
        if losses:
            print(f"  Avg loss      : -₹{abs(sum(c['pnl'] for c in losses)/len(losses)):.2f}")
    else:
        print("  No closed trades yet.")

    # Open positions
    print(f"\n  OPEN POSITIONS ({len(open_trades)}) — holding, not yet sold")
    if open_trades:
        print(f"  {'Stock':<22} {'Buy Price':>10} {'Qty':>4}  {'Value':>12}  Since")
        print(f"  {'-'*62}")
        total_exposure = 0
        for o in open_trades:
            print(f"  {o['stock']:<22} ₹{o['buy_price']:>9} {o['qty']:>4}  "
                  f"₹{o['value']:>11,.2f}  {o['time'][11:16]}")
            total_exposure += o["value"]
        print(f"  {'-'*62}")
        print(f"  Total exposure: ₹{total_exposure:,.2f}")
    else:
        print("  No open positions — all flat.")

    print("="*65)


if __name__ == "__main__":
    show_summary()
