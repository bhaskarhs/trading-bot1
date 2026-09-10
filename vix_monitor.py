"""
vix_monitor.py

Fetches India VIX every scan and returns the market safety mode.

VIX Levels (configurable in config.py):
  < 15   NORMAL   — all strategies active, trade freely
  15-20  CAUTION  — no new BUYs, only manage existing positions
  20-25  DEFENSE  — exit all positions, go to cash
  > 25   CRISIS   — halt bot completely

VIX spikes during:
  - Geopolitical shocks (Iran-Israel, Russia-Ukraine)
  - Domestic uncertainty (elections, budget surprises)
  - Global crashes (Fed rate shocks, banking crises)
"""

import time as t
from angel_client import get_angel
import config

VIX_TOKEN     = "99919003"   # Angel One India VIX token
CACHE_SECONDS = 240          # reuse cached value for 4 minutes

_cached_vix  = None
_cache_ts    = None


def fetch_vix() -> float:
    """
    Fetches current India VIX.
    Returns cached value if fetched within last 4 minutes.
    Falls back to last known value (or 15.0) on error.
    """
    global _cached_vix, _cache_ts

    if _cached_vix and _cache_ts and (t.time() - _cache_ts) < CACHE_SECONDS:
        return _cached_vix

    angel = get_angel()
    try:
        res = angel.getMarketData(
            mode="LTP",
            exchangeTokens={"NSE_INDEX": [VIX_TOKEN]}
        )
        if res and res.get("status"):
            items = res.get("data", {}).get("fetched", [])
            if items:
                vix        = round(float(items[0].get("ltp", 15.0)), 2)
                _cached_vix = vix
                _cache_ts   = t.time()
                return vix
    except Exception as e:
        print(f"  [VIX] Fetch error: {e}")

    return _cached_vix or 15.0


def get_vix_mode(vix: float = None) -> tuple:
    """
    Returns (mode, vix_value, description)

    Modes:
      NORMAL  → VIX < VIX_NORMAL_MAX   → trade freely
      CAUTION → VIX < VIX_CAUTION_MAX  → hold, no new entries
      DEFENSE → VIX < VIX_DEFENSE_MAX  → exit everything
      CRISIS  → VIX >= VIX_DEFENSE_MAX → halt bot
    """
    if vix is None:
        vix = fetch_vix()

    if vix < config.VIX_NORMAL_MAX:
        mode = "NORMAL"
        desc = f"VIX {vix} — normal market, trading active"
    elif vix < config.VIX_CAUTION_MAX:
        mode = "CAUTION"
        desc = f"VIX {vix} — elevated! No new BUYs, holding existing"
    elif vix < config.VIX_DEFENSE_MAX:
        mode = "DEFENSE"
        desc = f"VIX {vix} — HIGH VOLATILITY! Exiting all positions"
    else:
        mode = "CRISIS"
        desc = f"VIX {vix} — EXTREME! Bot halted for safety"

    return mode, vix, desc


def is_safe_to_buy(vix: float = None) -> bool:
    """Returns True only when VIX is in NORMAL mode."""
    mode, _, _ = get_vix_mode(vix)
    return mode == "NORMAL"


def should_exit_all(vix: float = None) -> bool:
    """Returns True when VIX hits DEFENSE or CRISIS — exit everything."""
    mode, _, _ = get_vix_mode(vix)
    return mode in ("DEFENSE", "CRISIS")
