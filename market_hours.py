"""NSE cash session clock (Asia/Kolkata). No broker imports."""

from datetime import datetime
import os

import pytz

IST = pytz.timezone("Asia/Kolkata")


def now_ist() -> datetime:
    return datetime.now(IST)


def parse_hhmm(value, default: tuple) -> tuple:
    if not value:
        return default
    parts = str(value).strip().split(":")
    return int(parts[0]), int(parts[1])


def session_end_hhmm(default: tuple) -> tuple:
    return parse_hhmm(os.getenv("SESSION_END"), default)


def is_weekday(now: datetime) -> bool:
    return now.weekday() < 5


def is_market_open(now: datetime | None = None,
                   market_open: tuple = (9, 15),
                   market_close: tuple = (15, 25)) -> bool:
    now = now or now_ist()
    if not is_weekday(now):
        return False
    t = (now.hour, now.minute)
    return market_open <= t <= market_close


def is_square_off_window(now: datetime | None = None,
                          square_off: tuple = (15, 15),
                          market_close: tuple = (15, 25)) -> bool:
    now = now or now_ist()
    if not is_weekday(now):
        return False
    t = (now.hour, now.minute)
    return square_off <= t <= market_close


def past_hhmm(now: datetime, hhmm: tuple) -> bool:
    return (now.hour, now.minute) >= hhmm


def session_mode_enabled() -> bool:
    return os.getenv("RUN_MARKET_SESSION", "").strip().lower() in ("1", "true", "yes")
