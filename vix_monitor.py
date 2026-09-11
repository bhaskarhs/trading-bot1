"""
vix_monitor.py

Fetches India VIX every scan and returns the market safety mode.

VIX Levels (configurable in config.py):
  <= 14  NORMAL   — good / quiet day; new trades allowed
  15-20  CAUTION  — no new BUYs, only manage existing positions
  20-25  DEFENSE  — exit all positions, go to cash
  > 25   CRISIS   — halt bot completely

  A good day for this cash RSI bot is India VIX about 11–14 (ideal ~12–13).
  Fetch failures use VIX_FETCH_FALLBACK (13), still NORMAL.

VIX spikes during:
  - Geopolitical shocks (Iran-Israel, Russia-Ukraine)
  - Domestic uncertainty (elections, budget surprises)
  - Global crashes (Fed rate shocks, banking crises)
"""

from logutil import log
from angel_client import get_angel
import config
import time as t

VIX_TOKEN     = "99919003"   # Angel One India VIX token
CACHE_SECONDS = 240          # reuse cached value for 4 minutes

_cached_vix  = None
_cache_ts    = None


def fetch_vix(force: bool = False) -> float:
    """
    Fetches current India VIX.
    Returns cached value if fetched within last 4 minutes.
    Falls back to last known value, else VIX_FETCH_FALLBACK (calm, still NORMAL).
    """
    global _cached_vix, _cache_ts

    if (not force) and _cached_vix and _cache_ts and (t.time() - _cache_ts) < CACHE_SECONDS:
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
                vix        = round(float(items[0].get("ltp", config.VIX_FETCH_FALLBACK)), 2)
                _cached_vix = vix
                _cache_ts   = t.time()
                return vix
    except Exception as e:
        log.warning("[VIX] Fetch error: %s", e)

    fallback = _cached_vix if _cached_vix is not None else config.VIX_FETCH_FALLBACK
    log.warning("[VIX] Using fallback %s (do not treat as a real print)", fallback)
    return fallback


def get_vix_mode(vix: float = None) -> tuple:
    """
    Returns (mode, vix_value, description)

    Modes:
      NORMAL  → VIX <= VIX_NORMAL_MAX  → trade freely
      CAUTION → VIX < VIX_CAUTION_MAX  → hold, no new entries
      DEFENSE → VIX < VIX_DEFENSE_MAX  → exit everything
      CRISIS  → VIX >= VIX_DEFENSE_MAX → halt bot
    """
    if vix is None:
        vix = fetch_vix()

    if vix <= config.VIX_NORMAL_MAX:
        mode = "NORMAL"
        desc = f"VIX {vix} — good/quiet day, trading active"
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


def should_halt(vix: float = None) -> bool:
    """CRISIS: do not scan again until VIX drops below VIX_CAUTION_MAX."""
    mode, _, _ = get_vix_mode(vix)
    return mode == "CRISIS"


def should_exit_all(vix: float = None) -> bool:
    """Returns True when VIX hits DEFENSE or CRISIS — exit everything."""
    mode, _, _ = get_vix_mode(vix)
    return mode in ("DEFENSE", "CRISIS")
