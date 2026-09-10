import time
import pyotp
from SmartApi import SmartConnect
import config
import requests
from datetime import datetime, timedelta
import pytz

requests.adapters.DEFAULT_RETRIES = 3

_angel = None

def get_angel():
    """Returns an authenticated Angel One session (creates one if needed)."""
    global _angel
    if _angel is not None:
        return _angel

    totp  = pyotp.TOTP(config.ANGEL_TOTP_SECRET).now()
    angel = SmartConnect(api_key=config.ANGEL_API_KEY)
    data  = angel.generateSession(config.ANGEL_CLIENT_ID, config.ANGEL_MPIN, totp)

    if not data["status"]:
        raise Exception(f"Angel One login failed: {data['message']}")

    print("Angel One login successful!")
    _angel = angel
    return _angel


def fetch_candles(symbol_token: str, interval: str, count: int, retries: int = 3) -> list:
    """
    Fetches recent OHLCV candles for a given stock.
    Requests data from 2 days ago to ensure enough candles for RSI calculation.
    Returns a list of closing prices (most recent last).
    """
    ist = pytz.timezone("Asia/Kolkata")
    now = datetime.now(ist)
    # Go back 2 days to collect enough candles (especially early in trading day)
    from_time = now - timedelta(days=2)

    params = {
        "exchange":    "NSE",
        "symboltoken": symbol_token,
        "interval":    interval,
        "fromdate":    from_time.strftime("%Y-%m-%d %H:%M"),
        "todate":      now.strftime("%Y-%m-%d %H:%M"),
    }

    angel = get_angel()

    for attempt in range(1, retries + 1):
        res = angel.getCandleData(params)

        if res["status"]:
            candles = res["data"]
            if not candles:
                raise Exception("No candle data returned")
            closes = [float(c[4]) for c in candles]
            # Return last 'count' candles (or fewer if not enough)
            return closes[-count:] if len(closes) >= count else closes

        # Rate limited – wait and retry
        # AB1019 = historical data rate limit
        # AB1021 = concurrent request limit (too many requests at once)
        if res.get("errorcode") in ("AB1019", "AB1021"):
            wait = attempt * 3   # 3s, 6s, 9s — slightly longer for AB1021
            print(f"    Rate limited ({res.get('errorcode')}). "
                  f"Waiting {wait}s (attempt {attempt}/{retries})...")
            time.sleep(wait)
            continue

        # Any other error – raise immediately
        raise Exception(f"Failed to fetch candles: {res['message']}")

    raise Exception(f"Failed after {retries} retries due to rate limiting")