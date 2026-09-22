"""
screener.py — Market direction + LTP radar + RSI shortlist

1. Classify the tape (Nifty quote, else LTP breadth).
2. LTP the full Nifty 500 (radar).
3. RSI only the top movers in the right direction, plus holdings.
4. If quote/LTP is empty: rebuild day % from 15-min candles on the bundled
   Nifty 100 book (how 16 Sep still filled). Fail closed only if candles fail too.

LTP % is the entry rank on a bid. RSI is a band, not “pick max RSI”.
"""

import time
from statistics import median

from angel_client import (
    get_market_quote,
    quote_index,
    session_quote_from_candles,
)
import config
from logutil import log

MIN_MOVE_PCT   = config.SCREENER_MIN_MOVE_PCT
MAX_CANDIDATES = getattr(config, "RSI_CANDIDATE_LIMIT", 50)
BATCH_SIZE     = 25
NIFTY_TOKEN    = "99926000"
BROAD_UNIVERSE = config.BROAD_UNIVERSE
MIN_LTP_QUOTES = 80
MIN_BREADTH_QUOTES = 50
# Shortlist quality floor (not 80 — that blocked every 50-name RSI book)
MIN_RSI_QUOTES = 8

DIRECTION_TO_STRATEGY = {
    "STRONG_UP": "STRONG_MOMENTUM",
    "MILD_UP":   "MILD_MOMENTUM",
    "FLAT":      "FLAT",
    "DOWN":      "MEAN_REVERSION",
    "UNKNOWN":   "FLAT",
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
    Momentum → largest day's % first (the tape), RSI already gated to the band.
    """
    def sort_key(item):
        stock, rsi = item[0], item[2]
        pct = stock.get("pct_change")
        move = 0.0 if pct is None else float(pct)
        if mode in ("FLAT", "MEAN_REVERSION"):
            return (rsi, -abs(move))
        return (-move, rsi)

    return sorted(buys, key=sort_key)[: max(0, limit)]


def rsi_book_for_scan(direction: str, rows: list, held: set,
                      limit: int = MAX_CANDIDATES) -> tuple:
    """
    Radar = `rows` (LTP). RSI list = movers + holdings, or holdings only.

    Returns (stocks_for_rsi, allow_new_buys, strategy_mode).
    UNKNOWN / empty tape → fail closed (no new buys, no 498-name RSI).
    """
    held = held or set()
    strategy_mode = DIRECTION_TO_STRATEGY.get(direction, "FLAT")
    if direction == "UNKNOWN" or not rows:
        held_rows = [r for r in rows if r.get("symbol") in held]
        return held_rows, False, "FLAT"

    stocks = select_mover_candidates(direction, rows, held, limit=limit)
    fresh = [s for s in stocks if s["symbol"] not in held]
    return stocks, len(fresh) > 0, strategy_mode


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


def _parse_fetched(res: dict) -> dict:
    result = {}
    for item in (res or {}).get("data", {}).get("fetched", []):
        token = str(item.get("symbolToken") or item.get("symboltoken") or "")
        try:
            ltp = float(item.get("ltp", 0))
            open_px = float(item.get("open", 0))
        except (TypeError, ValueError):
            continue
        if token and ltp > 0:
            result[token] = {"ltp": ltp, "open": open_px}
    return result


def _fetch_ltp_batch(tokens: list, retries: int = 3) -> dict:
    for attempt in range(1, retries + 1):
        res = get_market_quote("LTP", {"NSE": [str(t) for t in tokens]})
        if res:
            parsed = _parse_fetched(res)
            if parsed:
                return parsed
        if attempt < retries:
            time.sleep(attempt)
            continue
    log.warning("[SCREENER] Quote batch empty for %s tokens", len(tokens))
    return {}


def get_market_direction() -> tuple:
    """Returns (mode, nifty_pct, gap_pct, nifty_ok)."""
    hit = quote_index(NIFTY_TOKEN)
    if not hit or hit.get("open", 0) <= 0:
        log.warning("[SCREENER] Nifty quote unavailable — LTP breadth or candle radar")
        return "UNKNOWN", 0.0, 0.0, False
    ltp = hit["ltp"]
    open_price = hit["open"]
    raw = hit.get("raw") or {}
    prev_close = float(raw.get("previous_close") or open_price)
    pct = hit.get("pct_change")
    if pct is None:
        pct = round(((ltp - open_price) / open_price) * 100, 2)
    gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2) \
        if prev_close > 0 else 0.0
    return classify_nifty(pct, gap_pct), pct, gap_pct, True


def _candle_radar_rows(stocks: list, delay: float = 0.2) -> list:
    """Day % from 15-min bars when market/v1/quote returns an empty body."""
    rows = []
    for stock in stocks:
        quote = session_quote_from_candles(stock["token"])
        if not quote:
            time.sleep(delay)
            continue
        rows.append({
            **stock,
            "pct_change": quote["pct_change"],
            "ltp": quote["ltp"],
        })
        time.sleep(delay)
    return rows


def get_candidates(verbose: bool = True, held: set | None = None) -> tuple:
    """
    Returns (stocks_for_rsi, strategy_mode, nifty_intraday_pct, allow_new_buys)

    LTP radar is the full universe. RSI list is movers + holdings only.
    allow_new_buys is False when the tape is unknown or there are no fresh movers.
    """
    held = held or set()
    direction, nifty_pct, _gap_pct, nifty_ok = get_market_direction()

    unique = list(BROAD_UNIVERSE)
    token_map = {s["token"]: s for s in unique}
    all_ltp = {}

    empty_batches = 0
    for i in range(0, len(token_map), BATCH_SIZE):
        batch = list(token_map.keys())[i:i + BATCH_SIZE]
        ltp_data = _fetch_ltp_batch(batch)
        if not ltp_data:
            empty_batches += 1
            if empty_batches >= 2 and not all_ltp:
                log.warning("[SCREENER] First LTP batches empty — skip remaining quote radar")
                break
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

    radar_source = "ltp"
    ltp_ok = len(rows) >= MIN_LTP_QUOTES
    if not ltp_ok:
        candle_universe = list(getattr(config, "STOCKS", unique))
        log.warning(
            "[SCREENER] LTP radar empty (%s rows) — candle radar on %s bundled names",
            len(rows), len(candle_universe),
        )
        rows = _candle_radar_rows(candle_universe)
        pcts = [r["pct_change"] for r in rows]
        min_ok = min(MIN_BREADTH_QUOTES, max(10, len(candle_universe) // 4))
        ltp_ok = len(rows) >= min_ok
        radar_source = "candles"

    if not nifty_ok:
        if ltp_ok:
            direction = classify_breadth(pcts)
            if pcts:
                nifty_pct = round(median(pcts), 2)
            log.info("[SCREENER] Nifty quote missing — %s breadth says %s (median %+.2f%%, %s quotes)",
                     radar_source, direction, nifty_pct, len(rows))
        else:
            direction = "UNKNOWN"
            log.warning("[SCREENER] Nifty/LTP/candles thin (%s quotes) — fail closed, no new buys",
                        len(rows))

    stocks, allow_new_buys, strategy_mode = rsi_book_for_scan(
        direction, rows, held, limit=MAX_CANDIDATES
    )

    labels = {
        "STRONG_UP": f"STRONG BULLISH  Nifty +{nifty_pct}% → RSI {len(stocks)} movers then BUY RSI 52–70/60–70",
        "MILD_UP":   f"MILD BULLISH    Nifty +{nifty_pct}% → RSI {len(stocks)} movers then BUY RSI 52–{int(config.RSI_MOMENTUM_BUY_MAX)}",
        "FLAT":      f"FLAT            Nifty {nifty_pct:+.2f}% → RSI {len(stocks)} movers then BUY RSI<35",
        "DOWN":      f"BEARISH         Nifty {nifty_pct}% → RSI {len(stocks)} movers then BUY RSI<25",
        "UNKNOWN":   f"DATA GAP        fail closed ({len(stocks)} holdings for exits only)",
    }

    if verbose:
        log.info("[SCREENER] Market: %s", labels.get(direction, direction))
        log.info("[SCREENER] RSI shortlist: %s | radar rows: %s (%s) | nifty_ok: %s | new_buys: %s",
                 len(stocks), len(rows), radar_source, nifty_ok, allow_new_buys)
        movers = sorted(rows, key=lambda x: abs(x["pct_change"]), reverse=True)[:8]
        if movers:
            log.info("[SCREENER] Biggest LTP moves (radar; RSI only the shortlist):")
            for c in movers:
                arrow = "↑" if c["pct_change"] > 0 else "↓"
                log.info("  %-24s %s%5.2f%%  ₹%s",
                         c["name"], arrow, abs(c["pct_change"]), c["ltp"])

    return stocks, strategy_mode, nifty_pct, allow_new_buys
