import json
import os
from datetime import datetime
from angel_client import get_angel
import config

PAPER_LOG_FILE = "paper_trades.json"
POSITIONS_FILE = "open_positions.json"


# ─── Persistent position tracker ──────────────────────────────────────────────
def _load_positions() -> dict:
    if os.path.exists(POSITIONS_FILE):
        with open(POSITIONS_FILE) as f:
            return json.load(f)
    return {}


def _save_positions(positions: dict):
    with open(POSITIONS_FILE, "w") as f:
        json.dump(positions, f, indent=2)


open_positions = _load_positions()
if open_positions:
    print(f"  Resumed {len(open_positions)} open position(s) from previous session.")


def is_holding(stock: dict) -> bool:
    return stock["symbol"] in open_positions


def _load_paper_trades():
    if os.path.exists(PAPER_LOG_FILE):
        with open(PAPER_LOG_FILE) as f:
            return json.load(f)
    return []


def _save_paper_trades(trades):
    with open(PAPER_LOG_FILE, "w") as f:
        json.dump(trades, f, indent=2)


def calculate_quantity(price: float) -> int:
    """
    Calculates how many shares to buy based on capital per trade.
    Example: ₹20,000 / ₹7,400 Apollo = 2 shares
    Rounds DOWN so we never exceed capital limit.
    Minimum 1 share.
    """
    if price <= 0:
        return 1
    qty = int(config.CAPITAL_PER_TRADE / price)
    return max(1, qty)


def execute_trade(stock: dict, signal: str, rsi: float, current_price: float):
    """
    Executes BUY or SELL with:
    - Dynamic quantity based on CAPITAL_PER_TRADE
    - Max MAX_OPEN_POSITIONS at a time
    - Persistent position tracking across restarts
    """
    if signal == "HOLD":
        return

    if signal == "BUY" and is_holding(stock):
        print(f"  [SKIP] Already holding {stock['name']}")
        return None

    if signal == "SELL" and not is_holding(stock):
        print(f"  [SKIP] Not holding {stock['name']} — nothing to sell")
        return None

    if signal == "BUY" and len(open_positions) >= config.MAX_OPEN_POSITIONS:
        print(f"  [SKIP] Max {config.MAX_OPEN_POSITIONS} positions reached "
              f"— skipping {stock['name']}")
        return None

    # For SELL: always use the original buy quantity (fixes NTPC mismatch bug)
    if signal == "SELL" and stock["symbol"] in open_positions:
        pos         = open_positions[stock["symbol"]]
        quantity    = pos["quantity"]   # use stored buy qty, not recalculated
        buy_price   = pos["price"]
        pnl         = round((current_price - buy_price) * quantity, 2)
    else:
        quantity    = calculate_quantity(current_price)
        pnl         = None

    trade_value = round(quantity * current_price, 2)
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if config.PAPER_TRADING:
        trade = {
            "timestamp": timestamp,
            "mode":      "PAPER",
            "stock":     stock["name"],
            "symbol":    stock["symbol"],
            "action":    signal,
            "quantity":  quantity,
            "price":     current_price,
            "value":     trade_value,
            "rsi":       rsi,
            "pnl":       pnl,
        }
        trades = _load_paper_trades()
        trades.append(trade)
        _save_paper_trades(trades)

        if signal == "BUY":
            open_positions[stock["symbol"]] = {
                "price":    current_price,
                "quantity": quantity,
                "value":    trade_value,
                "time":     timestamp,
            }
            _save_positions(open_positions)
            print(f"  [PAPER] BUY  {stock['name']:<22} | "
                  f"₹{current_price} × {quantity} = ₹{trade_value:,.0f} | "
                  f"RSI: {rsi} | "
                  f"Slots: {len(open_positions)}/{config.MAX_OPEN_POSITIONS}")
        else:
            del open_positions[stock["symbol"]]
            _save_positions(open_positions)
            pnl_str = f"+₹{pnl}" if pnl >= 0 else f"-₹{abs(pnl)}"
            print(f"  [PAPER] SELL {stock['name']:<22} | "
                  f"₹{current_price} × {quantity} | "
                  f"RSI: {rsi} | P&L: {pnl_str} | "
                  f"Slots: {len(open_positions)}/{config.MAX_OPEN_POSITIONS}")
        return trade

    else:
        order_params = {
            "variety":         "NORMAL",
            "tradingsymbol":   stock["symbol"],
            "symboltoken":     stock["token"],
            "transactiontype": signal,
            "exchange":        "NSE",
            "ordertype":       "MARKET",
            "producttype":     "INTRADAY",
            "duration":        "DAY",
            "quantity":        str(quantity),
            "price":           "0",
        }
        try:
            angel    = get_angel()
            response = angel.placeOrder(order_params)
            order_id = response["data"]["orderid"]

            if signal == "BUY":
                open_positions[stock["symbol"]] = {
                    "price":    current_price,
                    "quantity": quantity,
                    "value":    trade_value,
                    "time":     timestamp,
                }
            else:
                open_positions.pop(stock["symbol"], None)
            _save_positions(open_positions)

            print(f"  [LIVE] {signal} {stock['name']} | "
                  f"₹{current_price} × {quantity} | Order: {order_id}")
            return {"order_id": order_id, **order_params}
        except Exception as e:
            print(f"  [LIVE] Order FAILED for {stock['name']}: {e}")
            return None