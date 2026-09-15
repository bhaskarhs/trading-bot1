"""
screener.py — Market direction detection + candidate filtering

Market modes detected:
  STRONG_UP   → Nifty gap or intraday > +2.0%  → scan top gainers
  MILD_UP     → Nifty up +0.5% to +2.0%        → scan gainers > 1%
  FLAT        → Nifty ±0.5%                     → scan biggest |movers| > 1%
  DOWN        → Nifty down < -0.5%              → scan top fallers
  UNKNOWN     → Nifty quote missing and LTP too thin → no new buys

Never fall back to "first N names in the universe". That path bought
alphabetical A-names (3Mindia, Acc, …) and never RSI-scanned IT (INFY/TCS
sit hundreds of rows down the Nifty 500 list).
"""

import time
from statistics import median

from angel_client import get_angel
import config
from logutil import log

MIN_MOVE_PCT   = config.SCREENER_MIN_MOVE_PCT
MAX_CANDIDATES = 50
BATCH_SIZE     = 25
NIFTY_TOKEN    = "99926000"
BROAD_UNIVERSE = config.BROAD_UNIVERSE
# Need a real tape, not 0–1 surviving batches, before we open new trades.
MIN_LTP_QUOTES = 80
MIN_BREADTH_QUOTES = 50


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
    log.warning("[SCREENER] Nifty quote unavailable (%s) — will use LTP breadth or skip buys",
                last_err)
    return "UNKNOWN", 0.0, 0.0, False


def get_candidates(verbose: bool = True) -> tuple:
    """
    Returns (candidates_list, strategy_mode, nifty_intraday_pct, allow_new_buys)

    nifty_intraday_pct is used for market-relative stop loss (not overnight gap).
    allow_new_buys is False when we do not have a trustworthy tape.
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

    from trader import open_positions
    held = set(open_positions.keys()) if open_positions else set()

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
            log.warning("[SCREENER] Nifty quote missing and only %s LTP rows — no new buys",
                        len(rows))

    mode_map = {
        "STRONG_UP": "STRONG_MOMENTUM",
        "MILD_UP":   "MILD_MOMENTUM",
        "FLAT":      "FLAT",
        "DOWN":      "MEAN_REVERSION",
        "UNKNOWN":   "FLAT",
    }
    strategy_mode = mode_map[direction]
    allow_new_buys = direction != "UNKNOWN" and ltp_ok

    labels = {
        "STRONG_UP": f"STRONG BULLISH  Nifty +{nifty_pct}% → top gainers (RSI>60)",
        "MILD_UP":   f"MILD BULLISH    Nifty +{nifty_pct}% → gainers ≥1% (RSI>52)",
        "FLAT":      f"FLAT            Nifty {nifty_pct:+.2f}% → |movers| ≥1% (RSI<35/70)",
        "DOWN":      f"BEARISH         Nifty {nifty_pct}% → top fallers (RSI<25)",
        "UNKNOWN":   "DATA GAP — holdings only, no new buys",
    }

    if verbose:
        log.info("[SCREENER] Market: %s", labels[direction])
        log.info("[SCREENER] Universe: %s stocks | LTP rows: %s | new buys: %s",
                 len(BROAD_UNIVERSE), len(rows), allow_new_buys)

    if not allow_new_buys:
        held_rows = [r for r in rows if r["symbol"] in held]
        if not held_rows:
            held_rows = [s for s in unique if s["symbol"] in held]
        candidates = held_rows
        if verbose:
            log.info("[SCREENER] %s holding(s) kept for exits; skipping new entries",
                     len(candidates))
        clean = [{"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
                 for s in candidates]
        return clean, strategy_mode, nifty_pct, False

    candidates = select_mover_candidates(direction, rows, held)

    if verbose:
        log.info("[SCREENER] %s candidates:", len(candidates))
        for c in candidates[:8]:
            arrow = "↑" if c["pct_change"] > 0 else "↓"
            log.info("  %-24s %s%5.2f%%  ₹%s",
                     c["name"], arrow, abs(c["pct_change"]), c["ltp"])
        if len(candidates) > 8:
            log.info("  ... and %s more", len(candidates) - 8)

    if not candidates:
        log.info("[SCREENER] No ≥%s%% movers — not substituting the universe head",
                 MIN_MOVE_PCT)

    clean = [{"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
             for s in candidates]
    return clean, strategy_mode, nifty_pct, True
