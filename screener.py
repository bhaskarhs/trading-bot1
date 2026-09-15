"""
screener.py — Market direction + full-universe RSI list

1. Classify the tape (Nifty quote, else LTP breadth, else RSI tape later).
2. Hand the **entire** Nifty 500 to bot.py for RSI (not the first 50 A-names,
   not only names that already moved 1%).
3. After RSI, rank the matches and take the best few slots.

LTP is optional annotation (% change) for ranking. Missing LTP no longer
shrinks the RSI list.
"""

import time
from statistics import median

from angel_client import get_angel
import config
from logutil import log

MIN_MOVE_PCT   = config.SCREENER_MIN_MOVE_PCT
MAX_CANDIDATES = 50  # kept for mover-ranking helpers / tests; RSI list is the full universe
BATCH_SIZE     = 25
NIFTY_TOKEN    = "99926000"
BROAD_UNIVERSE = config.BROAD_UNIVERSE
MIN_LTP_QUOTES = 80
MIN_BREADTH_QUOTES = 50
MIN_RSI_QUOTES = 80

DIRECTION_TO_STRATEGY = {
    "STRONG_UP": "STRONG_MOMENTUM",
    "MILD_UP":   "MILD_MOMENTUM",
    "FLAT":      "FLAT",
    "DOWN":      "MEAN_REVERSION",
    "UNKNOWN":   "RSI_TAPE",
}


def classify_nifty(pct: float, gap_pct: float) -> str:
    if gap_pct > 2.0 or pct > 2.0:
        return "STRONG_UP"
    if gap_pct < -1.5:
        return "DOWN"
    if pct > 0.5:
        return "MILD_UP"
    if pct < -0.5:
        return "DOWN"
    return "FLAT"


def classify_breadth(pcts: list) -> str:
    """
    Infer tape direction from stock % changes when the Nifty quote failed.
    Uses names that actually moved (≥ MIN_MOVE_PCT) so a quiet majority
    does not hide a sector (e.g. IT) bid.
    """
    movers = [p for p in pcts if abs(p) >= MIN_MOVE_PCT]
    if len(movers) < 10:
        if len(pcts) < MIN_BREADTH_QUOTES:
            return "UNKNOWN"
        return "FLAT"
    up_share = sum(1 for p in movers if p > 0) / len(movers)
    avg = sum(movers) / len(movers)
    if up_share >= 0.65:
        return "STRONG_UP" if avg >= 2.0 else "MILD_UP"
    if up_share <= 0.35:
        return "DOWN"
    return "FLAT"


def classify_rsi_tape(rsis: list) -> str:
    """
    When Nifty and LTP both fail, the RSI distribution of the full universe
    is the tape. A cluster of RSI>60 (IT bid) is MILD/STRONG, not FLAT dips.
    """
    if len(rsis) < 50:
        return "UNKNOWN"
    hot = sum(1 for r in rsis if r > 60)
    cold = sum(1 for r in rsis if r < 35)
    mid = median(rsis)
    if hot >= 30 and hot > cold:
        return "STRONG_UP" if mid >= 62 else "MILD_UP"
    if cold >= 30 and cold > hot:
        return "DOWN" if mid <= 30 else "FLAT"
    if mid >= 55:
        return "MILD_UP"
    if mid <= 42:
        return "DOWN"
    return "FLAT"


def annotate_universe(unique: list, rows: list) -> list:
    """Full Nifty 500 (or bundled list) with optional LTP % for ranking."""
    by_sym = {r["symbol"]: r for r in rows}
    out = []
    for s in unique:
        item = {"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
        extra = by_sym.get(s["symbol"])
        if extra:
            item["pct_change"] = extra.get("pct_change")
            item["ltp"] = extra.get("ltp")
        out.append(item)
    return out


def rank_buy_signals(buys: list, mode: str, limit: int) -> list:
    """
    buys: (stock, signal, rsi, price)
    FLAT / mean-reversion → most oversold first.
    Momentum → strongest RSI first.
    Day-move is a tie-break so IT gainers beat a random A-name with the same RSI.
    """
    def sort_key(item):
        stock, rsi = item[0], item[2]
        pct = stock.get("pct_change")
        move = 0.0 if pct is None else float(pct)
        if mode in ("FLAT", "MEAN_REVERSION"):
            return (rsi, -abs(move))
        return (-rsi, -move)

    return sorted(buys, key=sort_key)[: max(0, limit)]


def select_mover_candidates(direction: str, rows: list, held: set,
                            min_move: float = MIN_MOVE_PCT,
                            limit: int = MAX_CANDIDATES) -> list:
    """
    rows: dicts with name/symbol/token/pct_change/ltp
    FLAT ranks by |pct| so gainers (IT on a bid) are not truncated behind
    the weakest names. Bull days rank gainers; down days rank fallers.
    """
    picked = []
    for row in rows:
        if row["symbol"] in held:
            picked.append(row)
            continue
        pct = row["pct_change"]
        if direction in ("STRONG_UP", "MILD_UP") and pct >= min_move:
            picked.append(row)
        elif direction == "DOWN" and pct <= -min_move:
            picked.append(row)
        elif direction == "FLAT" and abs(pct) >= min_move:
            picked.append(row)

    if direction in ("STRONG_UP", "MILD_UP"):
        picked.sort(key=lambda x: x["pct_change"], reverse=True)
    elif direction == "DOWN":
        picked.sort(key=lambda x: x["pct_change"])
    else:
        picked.sort(key=lambda x: abs(x["pct_change"]), reverse=True)

    held_rows = [r for r in picked if r["symbol"] in held]
    fresh = [r for r in picked if r["symbol"] not in held][:limit]
    # Always keep holdings on the RSI list (stops / exits), then top movers.
    merged = held_rows + [r for r in fresh if r["symbol"] not in held]
    return merged[: limit + len(held_rows)]


def _fetch_ltp_batch(tokens: list, retries: int = 3) -> dict:
    angel = get_angel()
    for attempt in range(1, retries + 1):
        try:
            res = angel.getMarketData(
                mode="LTP",
                exchangeTokens={"NSE": [str(t) for t in tokens]}
            )
            if not res or not res.get("status"):
                return {}
            result = {}
            for item in res.get("data", {}).get("fetched", []):
                token = str(item.get("symbolToken", ""))
                result[token] = {
                    "ltp":  float(item.get("ltp",  0)),
                    "open": float(item.get("open", 0)),
                }
            return result
        except Exception as e:
            err = str(e)
            if "timed out" in err.lower() or "timeout" in err.lower():
                wait = attempt * 3
                log.info("[SCREENER] Timeout on batch, waiting %ss (%s/%s)",
                         wait, attempt, retries)
                time.sleep(wait)
                continue
            log.warning("[SCREENER] Batch error: %s", e)
            return {}
    log.warning("[SCREENER] Batch failed after %s retries — skipping batch", retries)
    return {}


def get_market_direction() -> tuple:
    """Returns (mode, nifty_pct, gap_pct, nifty_ok)."""
    angel = get_angel()
    last_err = None
    for attempt in range(1, 4):
        try:
            res = angel.getMarketData(
                mode="LTP",
                exchangeTokens={"NSE_INDEX": [NIFTY_TOKEN]}
            )
            if not res or not res.get("status"):
                last_err = "empty Nifty payload"
                time.sleep(attempt)
                continue

            items = res.get("data", {}).get("fetched", [])
            if not items:
                last_err = "no Nifty row"
                time.sleep(attempt)
                continue

            ltp = float(items[0].get("ltp", 0))
            open_price = float(items[0].get("open", 0))
            prev_close = float(items[0].get("previous_close", open_price))

            if open_price <= 0:
                return "UNKNOWN", 0.0, 0.0, False

            pct = round(((ltp - open_price) / open_price) * 100, 2)
            gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2) \
                if prev_close > 0 else 0.0
            return classify_nifty(pct, gap_pct), pct, gap_pct, True
        except Exception as e:
            last_err = e
            log.warning("[SCREENER] Nifty direction error (%s/3): %s", attempt, e)
            time.sleep(attempt)
    log.warning("[SCREENER] Nifty quote unavailable (%s) — LTP breadth or full RSI tape",
                last_err)
    return "UNKNOWN", 0.0, 0.0, False


def get_candidates(verbose: bool = True) -> tuple:
    """
    Returns (stocks_for_rsi, strategy_mode, nifty_intraday_pct, allow_new_buys)

    stocks_for_rsi is the **full universe** every time. bot.py RSI-filters it.
    allow_new_buys is False only when we have no names to RSI at all.
    """
    direction, nifty_pct, _gap_pct, nifty_ok = get_market_direction()

    unique = list(BROAD_UNIVERSE)
    token_map = {s["token"]: s for s in unique}
    all_ltp = {}

    for i in range(0, len(token_map), BATCH_SIZE):
        batch = list(token_map.keys())[i:i + BATCH_SIZE]
        ltp_data = _fetch_ltp_batch(batch)
        all_ltp.update(ltp_data)
        time.sleep(1.0)

    rows = []
    pcts = []
    for token, stock in token_map.items():
        data = all_ltp.get(token)
        if not data:
            continue
        ltp = data["ltp"]
        open_price = data["open"]
        if open_price <= 0 or ltp <= 0:
            continue
        pct = round(((ltp - open_price) / open_price) * 100, 2)
        pcts.append(pct)
        rows.append({**stock, "pct_change": pct, "ltp": ltp})

    ltp_ok = len(rows) >= MIN_LTP_QUOTES
    if not nifty_ok:
        if ltp_ok:
            direction = classify_breadth(pcts)
            if pcts:
                nifty_pct = round(median(pcts), 2)
            log.info("[SCREENER] Nifty quote missing — breadth says %s (median %+.2f%%, %s quotes)",
                     direction, nifty_pct, len(rows))
        else:
            direction = "UNKNOWN"
            log.warning("[SCREENER] Nifty/LTP thin (%s quotes) — RSI the full universe anyway",
                        len(rows))

    strategy_mode = DIRECTION_TO_STRATEGY[direction]
    stocks = annotate_universe(unique, rows)
    allow_new_buys = len(stocks) > 0

    labels = {
        "STRONG_UP": f"STRONG BULLISH  Nifty +{nifty_pct}% → RSI all {len(stocks)} then BUY RSI>60",
        "MILD_UP":   f"MILD BULLISH    Nifty +{nifty_pct}% → RSI all {len(stocks)} then BUY RSI>52",
        "FLAT":      f"FLAT            Nifty {nifty_pct:+.2f}% → RSI all {len(stocks)} then BUY RSI<35",
        "DOWN":      f"BEARISH         Nifty {nifty_pct}% → RSI all {len(stocks)} then BUY RSI<25",
        "UNKNOWN":   f"DATA GAP        RSI all {len(stocks)}, infer mode from RSI tape",
    }

    if verbose:
        log.info("[SCREENER] Market: %s", labels[direction])
        log.info("[SCREENER] RSI universe: %s | LTP rows: %s | nifty_ok: %s",
                 len(stocks), len(rows), nifty_ok)
        movers = sorted(rows, key=lambda x: abs(x["pct_change"]), reverse=True)[:8]
        if movers:
            log.info("[SCREENER] Biggest LTP moves (ranking only, not the RSI gate):")
            for c in movers:
                arrow = "↑" if c["pct_change"] > 0 else "↓"
                log.info("  %-24s %s%5.2f%%  ₹%s",
                         c["name"], arrow, abs(c["pct_change"]), c["ltp"])

    return stocks, strategy_mode, nifty_pct, allow_new_buys
