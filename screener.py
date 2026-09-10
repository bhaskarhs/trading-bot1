"""
screener.py — Market direction detection + candidate filtering

Market modes detected:
  STRONG_UP   → Nifty gap or intraday > +2.0%  → scan top gainers
  MILD_UP     → Nifty up +0.5% to +2.0%        → scan gainers > 1%
  FLAT        → Nifty ±0.5%                     → scan both directions > 1%
  DOWN        → Nifty down < -0.5%              → scan top fallers

Fallback: if LTP API fails or finds 0 candidates → scan all stocks in universe
"""

import time

from angel_client import get_angel
import config
from logutil import log

MIN_MOVE_PCT   = config.SCREENER_MIN_MOVE_PCT
MAX_CANDIDATES = 50
BATCH_SIZE     = 25
NIFTY_TOKEN    = "99926000"
BROAD_UNIVERSE = config.BROAD_UNIVERSE


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
    """Returns (mode, nifty_pct, gap_pct)."""
    angel = get_angel()
    try:
        res = angel.getMarketData(
            mode="LTP",
            exchangeTokens={"NSE_INDEX": [NIFTY_TOKEN]}
        )
        if not res or not res.get("status"):
            return "FLAT", 0.0, 0.0

        items = res.get("data", {}).get("fetched", [])
        if not items:
            return "FLAT", 0.0, 0.0

        ltp = float(items[0].get("ltp", 0))
        open_price = float(items[0].get("open", 0))
        prev_close = float(items[0].get("previous_close", open_price))

        if open_price <= 0:
            return "FLAT", 0.0, 0.0

        pct = round(((ltp - open_price) / open_price) * 100, 2)
        gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2) \
            if prev_close > 0 else 0.0

        if gap_pct > 2.0 or pct > 2.0:
            return "STRONG_UP", pct, gap_pct
        elif gap_pct < -1.5:
            return "DOWN", pct, gap_pct

        if pct > 0.5:
            return "MILD_UP", pct, gap_pct
        elif pct < -0.5:
            return "DOWN", pct, gap_pct
        return "FLAT", pct, gap_pct

    except Exception as e:
        log.warning("[SCREENER] Nifty direction error: %s", e)
        return "FLAT", 0.0, 0.0


def get_candidates(verbose: bool = True) -> tuple:
    """
    Returns (candidates_list, strategy_mode, nifty_intraday_pct)

    nifty_intraday_pct is used for market-relative stop loss (not overnight gap).
    """
    direction, nifty_pct, _gap_pct = get_market_direction()

    mode_map = {
        "STRONG_UP": "STRONG_MOMENTUM",
        "MILD_UP":   "MILD_MOMENTUM",
        "FLAT":      "FLAT",
        "DOWN":      "MEAN_REVERSION",
    }
    strategy_mode = mode_map[direction]

    labels = {
        "STRONG_UP": f"STRONG BULLISH  Nifty +{nifty_pct}% → top gainers (RSI>60)",
        "MILD_UP":   f"MILD BULLISH    Nifty +{nifty_pct}% → gainers ≥1% (RSI>52)",
        "FLAT":      f"FLAT            Nifty {nifty_pct:+.2f}% → movers ≥1% (RSI<35/70)",
        "DOWN":      f"BEARISH         Nifty {nifty_pct}% → top fallers (RSI<25)",
    }

    if verbose:
        log.info("[SCREENER] Market: %s", labels[direction])
        log.info("[SCREENER] Universe: %s stocks", len(BROAD_UNIVERSE))

    unique = list(BROAD_UNIVERSE)
    token_map = {s["token"]: s for s in unique}
    all_ltp = {}

    for i in range(0, len(token_map), BATCH_SIZE):
        batch = list(token_map.keys())[i:i + BATCH_SIZE]
        ltp_data = _fetch_ltp_batch(batch)
        all_ltp.update(ltp_data)
        time.sleep(1.0)

    from trader import open_positions
    candidates = []

    for token, stock in token_map.items():
        data = all_ltp.get(token)
        if not data:
            continue
        ltp = data["ltp"]
        open_price = data["open"]
        if open_price <= 0 or ltp <= 0:
            continue

        pct = ((ltp - open_price) / open_price) * 100
        is_held = stock["symbol"] in open_positions

        if is_held:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
            continue

        if direction in ("STRONG_UP", "MILD_UP") and pct >= MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
        elif direction == "DOWN" and pct <= -MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
        elif direction == "FLAT" and abs(pct) >= MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})

    candidates.sort(
        key=lambda x: x["pct_change"],
        reverse=(direction in ("STRONG_UP", "MILD_UP")),
    )
    candidates = candidates[:MAX_CANDIDATES]

    if verbose:
        log.info("[SCREENER] %s candidates:", len(candidates))
        for c in candidates[:8]:
            arrow = "↑" if c["pct_change"] > 0 else "↓"
            log.info("  %-24s %s%5.2f%%  ₹%s",
                     c["name"], arrow, abs(c["pct_change"]), c["ltp"])
        if len(candidates) > 8:
            log.info("  ... and %s more", len(candidates) - 8)

    if not candidates:
        log.info("[SCREENER] No candidates found — falling back to full universe scan")
        candidates = unique[:MAX_CANDIDATES]

    clean = [{"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
             for s in candidates]
    return clean, strategy_mode, nifty_pct
