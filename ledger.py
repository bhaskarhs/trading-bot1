from collections import defaultdict


def fifo_round_trips(trades: list) -> tuple:
    """
    Match BUY → SELL across the full history (not per calendar day).

    Returns (closed, unmatched_buys).
    Closed rows include pnl using the SELL quantity when present.
    """
    buy_queue = defaultdict(list)
    closed = []

    for t in sorted(trades, key=lambda x: x.get("timestamp") or ""):
        action = t.get("action")
        symbol = t.get("symbol") or t.get("stock")
        if not symbol:
            continue
        if action == "BUY":
            buy_queue[symbol].append(t)
        elif action == "SELL" and buy_queue[symbol]:
            buy_trade = buy_queue[symbol].pop(0)
            qty = t.get("quantity", buy_trade.get("quantity", 1))
            pnl = round((t["price"] - buy_trade["price"]) * qty, 2)
            closed.append({
                "stock": t.get("stock") or buy_trade.get("stock") or symbol,
                "symbol": t.get("symbol") or buy_trade.get("symbol") or symbol,
                "buy_price": buy_trade["price"],
                "sell_price": t["price"],
                "qty": qty,
                "buy_time": buy_trade.get("timestamp", ""),
                "sell_time": t.get("timestamp", ""),
                "rsi_buy": buy_trade.get("rsi"),
                "rsi_sell": t.get("rsi"),
                "pnl": pnl,
                "result": "PROFIT" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN",
            })

    unmatched = []
    for queue in buy_queue.values():
        unmatched.extend(queue)
    return closed, unmatched
