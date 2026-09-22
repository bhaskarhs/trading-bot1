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


def _bar_stamp(interval: str) -> str:
    """Align candle cache to the current bar so a 15-min RSI scan is reused."""
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    if interval == "FIFTEEN_MINUTE":
        bucket = (now.minute // 15) * 15
        return f"{now:%Y-%m-%d}-{now.hour:02d}{bucket:02d}"
    if interval == "FIVE_MINUTE":
        bucket = (now.minute // 5) * 5
        return f"{now:%Y-%m-%d}-{now.hour:02d}{bucket:02d}"
    return now.strftime("%Y-%m-%d-%H%M")


def _candle_cache_key(symbol_token: str, interval: str, count: int) -> tuple:
    return (str(symbol_token), interval, int(count), _bar_stamp(interval))


def candle_cache_fresh(symbol_token: str, interval: str, count: int) -> bool:
    """True if we already have this bar's closes — skip the inter-stock delay."""
    hit = _candle_cache.get(_candle_cache_key(symbol_token, interval, count))
    if not hit:
        return False
    ttl = getattr(config, "CANDLE_CACHE_SECONDS", 900)
    return (time.time() - hit[0]) < ttl


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


def _stamp_network_headers(angel):
    """
    smartapi-python hardcodes X-ClientPublicIP to 106.193.147.98 in a finally
    block. Quote (/market/v1/quote) often returns an empty body from GitHub
    US runners when that header does not match the source IP. Auth still works.
    """
    ip = None
    try:
        ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
    except Exception as e:
        log.warning("Public IP lookup failed (%s) — leaving SDK default", e)
    if ip:
        angel.clientPublicIp = ip
        angel.clientPublicIP = ip
        log.info("Angel X-ClientPublicIP set to runner %s", ip)
    try:
        import socket
        local = socket.gethostbyname(socket.gethostname())
        if local and not local.startswith("127."):
            angel.clientLocalIp = local
            angel.clientLocalIP = local
    except Exception:
        pass
    orig = angel.requestHeaders

    def _headers():
        headers = orig()
        headers.setdefault("User-Agent", "smartapi-python/1.4.1")
        return headers

    angel.requestHeaders = _headers


def is_empty_body_error(exc: BaseException) -> bool:
    text = str(exc)
    return "Couldn't parse the JSON response" in text or "b''" in text


def _login():
    global _angel, _refresh_token, _session_ts
    _require_credentials()
    totp = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
    angel = SmartConnect(api_key=config.ANGEL_API_KEY)
    _stamp_network_headers(angel)
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
    cache_key = _candle_cache_key(symbol_token, interval, count)
    ttl = getattr(config, "CANDLE_CACHE_SECONDS", 900)
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


def _request_candles(symbol_token: str, interval: str, retries: int = 4) -> list:
    """Raw Angel candle rows: [timestamp, open, high, low, close, volume]."""
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
            return res.get("data") or []
        errorcode = (res or {}).get("errorcode")
        message = (res or {}).get("message", "unknown")
        if errorcode in ("AB1019", "AB1021"):
            time.sleep(attempt * 3)
            continue
        if errorcode in ("AG8001", "AB8050") or "token" in str(message).lower():
            get_angel(force=True)
            continue
        raise Exception(f"Failed to fetch candles: {message}")
    raise Exception(f"Failed after {retries} retries: {last_error}")


def session_quote_from_candles(symbol_token: str, interval: str | None = None) -> dict | None:
    """
    Day open / last close from 15-min candles. Used when getMarketData returns
    an empty body (GitHub runners) so the screener still has a radar.
    """
    interval = interval or config.CANDLE_INTERVAL
    try:
        rows = _request_candles(symbol_token, interval)
    except Exception as e:
        log.warning("Candle radar failed for %s: %s", symbol_token, e)
        return None
    if not rows:
        return None
    ist = pytz.timezone("Asia/Kolkata")
    today = datetime.now(ist).strftime("%Y-%m-%d")
    todays = [r for r in rows if str(r[0]).startswith(today)]
    use = todays or rows[-20:]
    try:
        open_px = float(use[0][1])
        ltp = float(use[-1][4])
    except (TypeError, ValueError, IndexError):
        return None
    if open_px <= 0 or ltp <= 0:
        return None
    pct = round(((ltp - open_px) / open_px) * 100, 2)
    return {"ltp": ltp, "open": open_px, "pct_change": pct}


def get_market_quote(mode: str, exchange_tokens: dict):
    """getMarketData, swallowing the empty-body WAF response as None."""
    angel = get_angel()
    try:
        res = angel.getMarketData(mode=mode, exchangeTokens=exchange_tokens)
        if res and res.get("status"):
            return res
        log.warning("[QUOTE] getMarketData status=%s", (res or {}).get("status"))
        return None
    except Exception as e:
        if is_empty_body_error(e):
            log.warning("[QUOTE] empty body from market/v1/quote")
            return None
        log.warning("[QUOTE] getMarketData error: %s", e)
        return None


def ltp_one(exchange: str, tradingsymbol: str, token: str) -> dict | None:
    """Order-book LTP endpoint — different path from market/v1/quote."""
    angel = get_angel()
    try:
        res = angel.ltpData(exchange, tradingsymbol, str(token))
    except Exception as e:
        log.warning("[LTP] ltpData %s %s failed: %s", exchange, tradingsymbol, e)
        return None
    if not res or not res.get("status"):
        return None
    data = res.get("data") or {}
    try:
        ltp = float(data.get("ltp") or 0)
        open_px = float(data.get("open") or 0)
    except (TypeError, ValueError):
        return None
    if ltp <= 0:
        return None
    if open_px <= 0:
        open_px = float(data.get("close") or ltp)
    pct = round(((ltp - open_px) / open_px) * 100, 2) if open_px else 0.0
    return {"ltp": ltp, "open": open_px, "pct_change": pct, "raw": data}


INDEX_LTP_SPECS = {
    "99926000": (("NSE_INDEX", "Nifty 50"), ("NSE", "Nifty 50")),
    "99919003": (("NSE_INDEX", "INDIA VIX"), ("NSE", "INDIA VIX")),
}


def quote_index(token: str, mode: str = "LTP") -> dict | None:
    """Nifty / VIX: market quote, then order LTP, then candles."""
    token = str(token)
    exchange_key = "NSE_INDEX"
    res = get_market_quote(mode, {exchange_key: [token]})
    if res:
        items = (res.get("data") or {}).get("fetched") or []
        if items:
            item = items[0]
            try:
                ltp = float(item.get("ltp") or 0)
                open_px = float(item.get("open") or 0)
            except (TypeError, ValueError):
                ltp, open_px = 0.0, 0.0
            if ltp > 0:
                if open_px <= 0:
                    open_px = float(item.get("previous_close") or ltp)
                pct = round(((ltp - open_px) / open_px) * 100, 2) if open_px else 0.0
                return {"ltp": ltp, "open": open_px, "pct_change": pct, "raw": item}
    for exchange, symbol in INDEX_LTP_SPECS.get(token, ()):
        hit = ltp_one(exchange, symbol, token)
        if hit:
            log.info("[QUOTE] %s via ltpData %s", token, symbol)
            return hit
    hit = session_quote_from_candles(token)
    if hit:
        log.info("[QUOTE] %s via candles", token)
    return hit
