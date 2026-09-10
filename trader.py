from datetime import datetime

import pytz

from angel_client import confirm_order, get_angel
import config
from logutil import log
from persist import load_json, save_json

PAPER_LOG_FILE = "paper_trades.json"
POSITIONS_FILE = "open_positions.json"
IST = pytz.timezone("Asia/Kolkata")


def _load_positions() -> dict:
    data = load_json(POSITIONS_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_positions(positions: dict):
    save_json(POSITIONS_FILE, positions)


open_positions = _load_positions()
if open_positions:
    log.info("Resumed %s open position(s) from previous session.", len(open_positions))


def is_holding(stock: dict) -> bool:
    return stock["symbol"] in open_positions


def _load_paper_trades():
    data = load_json(PAPER_LOG_FILE, [])
    return data if isinstance(data, list) else []


def _save_paper_trades(trades):
    save_json(PAPER_LOG_FILE, trades)


def calculate_quantity(price: float) -> int:
    if price <= 0:
        return 1
    qty = int(config.CAPITAL_PER_TRADE / price)
    return max(1, qty)


def _extract_order_id(response) -> str | None:
    if isinstance(response, str) and response:
        return response
    if not isinstance(response, dict):
        return None
    data = response.get("data")
    if isinstance(data, dict):
        return data.get("orderid") or data.get("orderId")
    if isinstance(data, str):
        return data
    return response.get("orderid")


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
        log.info("[SKIP] Already holding %s", stock["name"])
        return None

    if signal == "SELL" and not is_holding(stock):
        log.info("[SKIP] Not holding %s — nothing to sell", stock["name"])
        return None

    if signal == "BUY" and len(open_positions) >= config.MAX_OPEN_POSITIONS:
        log.info("[SKIP] Max %s positions reached — skipping %s",
                 config.MAX_OPEN_POSITIONS, stock["name"])
        return None

    if signal == "SELL" and stock["symbol"] in open_positions:
        pos = open_positions[stock["symbol"]]
        quantity = pos["quantity"]
        buy_price = pos["price"]
        pnl = round((current_price - buy_price) * quantity, 2)
    else:
        quantity = calculate_quantity(current_price)
        pnl = None

    trade_value = round(quantity * current_price, 2)
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")

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
                "stock":    stock["name"],
            }
            _save_positions(open_positions)
            log.info("[PAPER] BUY  %-22s | ₹%s × %s = ₹%.0f | RSI: %s | Slots: %s/%s",
                     stock["name"], current_price, quantity, trade_value, rsi,
                     len(open_positions), config.MAX_OPEN_POSITIONS)
        else:
            del open_positions[stock["symbol"]]
            _save_positions(open_positions)
            pnl_str = f"+₹{pnl}" if pnl >= 0 else f"-₹{abs(pnl)}"
            log.info("[PAPER] SELL %-22s | ₹%s × %s | RSI: %s | P&L: %s | Slots: %s/%s",
                     stock["name"], current_price, quantity, rsi, pnl_str,
                     len(open_positions), config.MAX_OPEN_POSITIONS)
        return trade

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
        angel = get_angel()
        response = angel.placeOrder(order_params)
        order_id = _extract_order_id(response)
        accepted, status = confirm_order(order_id)
        if not accepted:
            log.error("[LIVE] Order rejected for %s: %s (%s)",
                      stock["name"], order_id, status)
            return None

        if signal == "BUY":
            open_positions[stock["symbol"]] = {
                "price":    current_price,
                "quantity": quantity,
                "value":    trade_value,
                "time":     timestamp,
                "stock":    stock["name"],
                "order_id": order_id,
            }
        else:
            open_positions.pop(stock["symbol"], None)
        _save_positions(open_positions)

        log.info("[LIVE] %s %s | ₹%s × %s | Order: %s | %s",
                 signal, stock["name"], current_price, quantity, order_id, status)
        return {"order_id": order_id, "pnl": pnl, **order_params}
    except Exception as e:
        log.error("[LIVE] Order FAILED for %s: %s", stock["name"], e)
        return None
