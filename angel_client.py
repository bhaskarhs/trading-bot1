import time
from datetime import datetime, timedelta

import pyotp
import pytz
import requests
from SmartApi import SmartConnect

import config
from logutil import log

requests.adapters.DEFAULT_RETRIES = 3

_angel = None
_refresh_token = None
_session_ts = 0.0
_candle_cache = {}


def _require_credentials():
    missing = [
        name for name, val in (
            ("ANGEL_API_KEY", config.ANGEL_API_KEY),
            ("ANGEL_CLIENT_ID", config.ANGEL_CLIENT_ID),
            ("ANGEL_MPIN", config.ANGEL_MPIN),
            ("ANGEL_TOTP_SECRET", config.ANGEL_TOTP_SECRET),
        ) if not val
    ]
    if missing:
        raise RuntimeError(
            "Missing Angel credentials: " + ", ".join(missing)
            + ". Copy .env.example to .env or use python demo.py"
        )


def _login():
    global _angel, _refresh_token, _session_ts
    _require_credentials()
    totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
    angel = SmartConnect(api_key=config.ANGEL_API_KEY)
    data = angel.generateSession(config.ANGEL_CLIENT_ID, config.ANGEL_MPIN, totp)
    if not data or not data.get("status"):
        message = (data or {}).get("message", "unknown error")
        raise Exception(f"Angel One login failed: {message}")
    payload = data.get("data") or {}
    _refresh_token = payload.get("refreshToken")
    _angel = angel
    _session_ts = time.time()
    log.info("Angel One login successful")
    return _angel


def get_angel(force: bool = False):
    """Cached session; refreshes JWT on a timer or after auth errors."""
    global _angel, _session_ts
    now = time.time()
    ttl = getattr(config, "SESSION_REFRESH_SECONDS", 6 * 3600)
    if _angel is not None and not force and (now - _session_ts) < ttl:
        return _angel

    if _angel is not None and _refresh_token and not force:
        try:
            data = _angel.generateToken(_refresh_token)
            if data and data.get("status"):
                _session_ts = now
                log.info("Angel One session refreshed")
                return _angel
        except Exception as e:
            log.warning("Session refresh failed (%s) — logging in again", e)

    return _login()


def confirm_order(order_id: str, timeout: int = 8) -> tuple:
    """Poll order book. Returns (accepted, status)."""
    if not order_id:
        return False, "NO_ORDER_ID"
    angel = get_angel()
    deadline = time.time() + timeout
    last = "UNKNOWN"
    while time.time() < deadline:
        try:
            book = angel.orderBook()
            rows = (book or {}).get("data") or []
            for row in rows:
                oid = str(row.get("orderid") or row.get("orderId") or "")
                if oid != str(order_id):
                    continue
                last = str(row.get("status") or row.get("orderstatus") or "")
                upper = last.upper()
                if "REJECT" in upper or "CANCEL" in upper:
                    return False, last
                if "COMPLETE" in upper or upper in ("FILLED", "EXECUTED"):
                    return True, last
        except Exception as e:
            log.warning("orderBook poll failed: %s", e)
            get_angel(force=True)
        time.sleep(1)
    log.warning("Order %s not confirmed in time (last=%s)", order_id, last)
    return True, last


def fetch_candles(symbol_token: str, interval: str, count: int, retries: int = 4) -> list:
    """
    Fetches recent OHLCV candles for a given stock.
    Requests data from 2 days ago to ensure enough candles for RSI calculation.
    Returns a list of closing prices (most recent last).
    """
    cache_key = (str(symbol_token), interval, count)
    ttl = getattr(config, "CANDLE_CACHE_SECONDS", 90)
    hit = _candle_cache.get(cache_key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]

    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    from_time = now - timedelta(days=2)

    params = {
        "exchange":    "NSE",
        "symboltoken": str(symbol_token),
        "interval":    interval,
        "fromdate":    from_time.strftime("%Y-%m-%d %H:%M"),
        "todate":      now.strftime("%Y-%m-%d %H:%M"),
    }

    last_error = None
    for attempt in range(1, retries + 1):
        angel = get_angel(force=(attempt > 2))
        try:
            res = angel.getCandleData(params)
        except Exception as e:
            last_error = e
            log.warning("Candle request error (%s) attempt %s", e, attempt)
            time.sleep(attempt * 2)
            continue

        if res and res.get("status"):
            candles = res.get("data") or []
            if not candles:
                raise Exception("No candle data returned")
            closes = [float(c[4]) for c in candles]
            closes = closes[-count:] if len(closes) >= count else closes
            _candle_cache[cache_key] = (time.time(), closes)
            return closes

        errorcode = (res or {}).get("errorcode")
        message = (res or {}).get("message", "unknown")
        if errorcode in ("AB1019", "AB1021"):
            wait = attempt * 3
            log.info("Rate limited (%s). Waiting %ss (%s/%s)",
                     errorcode, wait, attempt, retries)
            time.sleep(wait)
            continue
        if errorcode in ("AG8001", "AB8050") or "token" in str(message).lower():
            get_angel(force=True)
            continue
        raise Exception(f"Failed to fetch candles: {message}")

    raise Exception(f"Failed after {retries} retries: {last_error}")
