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


def is_past_last_entry(now: datetime | None = None,
                       last_entry: tuple = (14, 30)) -> bool:
    """True once new cash entries are too close to the 15:15 flatten."""
    now = now or now_ist()
    if not is_weekday(now):
        return True
    return past_hhmm(now, last_entry)


def past_hhmm(now: datetime, hhmm: tuple) -> bool:
    return (now.hour, now.minute) >= hhmm


def session_mode_enabled() -> bool:
    return os.getenv("RUN_MARKET_SESSION", "").strip().lower() in ("1", "true", "yes")


def gha_session_phases(now: datetime | None = None,
                       morning_end: tuple = (12, 15),
                       market_close: tuple = (15, 25)) -> tuple:
    """
    Which GitHub jobs should run for a trigger at `now` IST.

    A late Actions start (after 12:15) must skip the morning slice so the
    afternoon job still runs — `needs: morning` would otherwise skip it.
    """
    now = now or now_ist()
    if not is_weekday(now):
        return False, False
    t = (now.hour, now.minute)
    if t > market_close:
        return False, False
    run_morning = t < morning_end
    run_afternoon = True
    return run_morning, run_afternoon
