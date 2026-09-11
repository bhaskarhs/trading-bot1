"""
Single stock universe + Angel scrip-master token repair.

Default session list is Nifty 500 (liquid cash names), not all ~2000 NSE
symbols. LTP-screen that list; RSI still runs only on the top movers.

Known bad tokens in the original lists (NSE cash EQ):
  PATANJALI-EQ was Power Grid 14977
  DMART-EQ was UPL 11287
  DIXON-EQ was actually DMART 19913
  JIOFIN-EQ / IRFC-EQ / BSE-EQ / RVNL-EQ used BSE-style codes
"""

import copy
from pathlib import Path

import requests

from logutil import log

TOKEN_FIXES = {
    "PATANJALI-EQ": "17029",
    "DMART-EQ": "19913",
    "UPL-EQ": "11287",
    "WHIRLPOOL-EQ": "18011",
    "JIOFIN-EQ": "18143",
    "PGHH-EQ": "2535",
    "BSE-EQ": "19585",
    "DIXON-EQ": "21690",
    "RVNL-EQ": "9552",
    "IRFC-EQ": "2029",
    "AUBANK-EQ": "21238",
    "LTF-EQ": "24948",
    "MAXHEALTH-EQ": "22377",
    "BAJAJHLDNG-EQ": "305",
    "BIOCON-EQ": "11373",
    "COLPAL-EQ": "15141",
    "HAVELLS-EQ": "9819",
    "IDBI-EQ": "1476",
    "MUTHOOTFIN-EQ": "23650",
    "PNB-EQ": "10666",
    "POLYCAB-EQ": "9590",
    "SBICARD-EQ": "17971",
    "TVSMOTOR-EQ": "8479",
    "VBL-EQ": "18921",
    "VOLTAS-EQ": "3718",
    "MANAPPURAM-EQ": "19061",
    "MCX-EQ": "31181",
    "OFSS-EQ": "10738",
    "PHOENIXLTD-EQ": "14552",
    "PIIND-EQ": "24184",
    "TORNTPOWER-EQ": "13786",
    "UNIONBANK-EQ": "10753",
}

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/"
    "OpenAPI_File/files/OpenAPIScripMaster.json"
)
NIFTY500_CSV_URLS = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "https://archives.nseindia.com/content/indices/ind_nifty500list.csv",
)
NSE_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; nse-rsi-bot/1.0)",
    "Accept": "text/csv,*/*",
    "Referer": "https://www.nseindia.com/",
}
NIFTY500_SNAPSHOT = Path(__file__).resolve().parent / "data" / "nifty500_symbols.txt"

MIDCAPS = [
    {"name": "AU Small Finance", "symbol": "AUBANK-EQ", "token": "21238"},
    {"name": "Bank of Baroda", "symbol": "BANKBARODA-EQ", "token": "4668"},
    {"name": "BSE Ltd", "symbol": "BSE-EQ", "token": "19585"},
    {"name": "Coforge", "symbol": "COFORGE-EQ", "token": "11543"},
    {"name": "Dixon Tech", "symbol": "DIXON-EQ", "token": "21690"},
    {"name": "Federal Bank", "symbol": "FEDERALBNK-EQ", "token": "1023"},
    {"name": "HPCL", "symbol": "HINDPETRO-EQ", "token": "1406"},
    {"name": "IRCTC", "symbol": "IRCTC-EQ", "token": "13611"},
    {"name": "IRFC", "symbol": "IRFC-EQ", "token": "2029"},
    {"name": "Jubilant Food", "symbol": "JUBLFOOD-EQ", "token": "18096"},
    {"name": "L&T Finance", "symbol": "LTF-EQ", "token": "24948"},
    {"name": "Manappuram Fin", "symbol": "MANAPPURAM-EQ", "token": "10720"},
    {"name": "Max Healthcare", "symbol": "MAXHEALTH-EQ", "token": "22377"},
    {"name": "MCX India", "symbol": "MCX-EQ", "token": "11850"},
    {"name": "MRF", "symbol": "MRF-EQ", "token": "2277"},
    {"name": "NMDC", "symbol": "NMDC-EQ", "token": "15332"},
    {"name": "Oracle Fin Services", "symbol": "OFSS-EQ", "token": "2725"},
    {"name": "Page Industries", "symbol": "PAGEIND-EQ", "token": "14413"},
    {"name": "Petronet LNG", "symbol": "PETRONET-EQ", "token": "11351"},
    {"name": "Phoenix Mills", "symbol": "PHOENIXLTD-EQ", "token": "17524"},
    {"name": "PI Industries", "symbol": "PIIND-EQ", "token": "13813"},
    {"name": "Rail Vikas Nigam", "symbol": "RVNL-EQ", "token": "9552"},
    {"name": "Torrent Pharma", "symbol": "TORNTPHARM-EQ", "token": "3518"},
    {"name": "Torrent Power", "symbol": "TORNTPOWER-EQ", "token": "3545"},
    {"name": "Union Bank", "symbol": "UNIONBANK-EQ", "token": "2752"},
]


def apply_token_fixes(stocks: list) -> list:
    out = []
    for raw in stocks:
        s = dict(raw)
        s["token"] = str(TOKEN_FIXES.get(s["symbol"], s["token"]))
        out.append(s)
    return out


def merge_universe(*groups) -> list:
    """Keep first symbol, skip later rows that reuse a token."""
    seen_symbol, seen_token, out = set(), set(), []
    for group in groups:
        for raw in apply_token_fixes(group):
            symbol, token = raw["symbol"], str(raw["token"])
            if symbol in seen_symbol:
                continue
            if token in seen_token:
                log.warning(
                    "Dropping %s — token %s already used",
                    symbol,
                    token,
                )
                continue
            seen_symbol.add(symbol)
            seen_token.add(token)
            out.append(raw)
    return out


def lookup_nse_eq_rows(timeout: int = 45) -> dict:
    """Angel scrip master: NSE cash EQ tradingsymbol → {name, symbol, token}."""
    res = requests.get(SCRIP_MASTER_URL, timeout=timeout)
    res.raise_for_status()
    rows = {}
    for row in res.json():
        if row.get("exch_seg") != "NSE":
            continue
        symbol = row.get("symbol") or ""
        if not symbol.endswith("-EQ"):
            continue
        token = str(row.get("token") or "")
        if not token:
            continue
        name = (row.get("name") or symbol.replace("-EQ", "")).strip()
        rows[symbol] = {"name": name.title() if name.isupper() else name,
                        "symbol": symbol, "token": token}
    return rows


def lookup_nse_eq_tokens(timeout: int = 30) -> dict:
    return {sym: row["token"] for sym, row in lookup_nse_eq_rows(timeout).items()}


def parse_nifty500_csv(text: str) -> list:
    """Return NSE cash symbols (without -EQ) from ind_nifty500list.csv."""
    import csv
    from io import StringIO

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        return []
    fields = {name.lower(): name for name in reader.fieldnames}
    sym_key = fields.get("symbol")
    series_key = fields.get("series")
    if not sym_key:
        return []
    out, seen = [], set()
    for row in reader:
        if series_key:
            series = (row.get(series_key) or "").strip().upper()
            if series and series not in ("EQ", "BE"):
                continue
        raw = (row.get(sym_key) or "").strip().upper()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
    return out


def fetch_nifty500_symbols(timeout: int = 30) -> list:
    last_err = None
    for url in NIFTY500_CSV_URLS:
        try:
            res = requests.get(url, headers=NSE_HTTP_HEADERS, timeout=timeout)
            res.raise_for_status()
            symbols = parse_nifty500_csv(res.text)
            if len(symbols) >= 200:
                return symbols
            last_err = RuntimeError(f"{url} returned {len(symbols)} rows")
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Nifty 500 list unavailable: {last_err}")


def load_bundled_nifty500_symbols(path=None) -> list:
    """Offline snapshot of NSE cash symbols (no -EQ suffix)."""
    snap = path or NIFTY500_SNAPSHOT
    if not snap.is_file():
        return []
    out, seen = [], set()
    for line in snap.read_text(encoding="utf-8").splitlines():
        raw = line.strip().upper()
        if not raw or raw.startswith("#") or raw in seen:
            continue
        seen.add(raw)
        out.append(raw)
    return out


def resolve_nifty500_symbols() -> list:
    """Live NSE CSV first; repo snapshot if GitHub/US IPs cannot reach NSE."""
    try:
        live = fetch_nifty500_symbols()
        if len(live) >= 200:
            return live
    except Exception as e:
        log.warning("Live Nifty 500 CSV failed (%s)", e)
    bundled = load_bundled_nifty500_symbols()
    if len(bundled) >= 200:
        log.info("Using bundled Nifty 500 snapshot (%s names)", len(bundled))
        return bundled
    raise RuntimeError("Nifty 500 list unavailable (live and snapshot empty)")


def join_index_to_scrip(index_symbols: list, scrip: dict) -> list:
    built = []
    missing = 0
    for raw in index_symbols:
        key = raw if str(raw).endswith("-EQ") else f"{raw}-EQ"
        row = scrip.get(key)
        if not row:
            missing += 1
            continue
        built.append(dict(row))
    if missing:
        log.info("Nifty 500 symbols with no Angel EQ token: %s", missing)
    return merge_universe(built)


def apply_session_universe() -> list:
    """
    Replace config.BROAD_UNIVERSE in place.

    Best default: Nifty 500 (liquid, wide enough to study the strategy)
    then LTP-screen; RSI still runs only on the top movers.
    """
    import config

    bundled = list(config.BROAD_UNIVERSE)
    mode = getattr(config, "UNIVERSE_MODE", "nifty500")

    if mode == "bundled":
        refreshed = refresh_tokens_from_master(bundled)
        config.BROAD_UNIVERSE[:] = refreshed
        log.info("Universe bundled: %s names", len(config.BROAD_UNIVERSE))
        return config.BROAD_UNIVERSE

    try:
        scrip = lookup_nse_eq_rows()
        symbols = resolve_nifty500_symbols()
        built = join_index_to_scrip(symbols, scrip)
        if len(built) < 80:
            raise RuntimeError(f"joined universe too small ({len(built)})")
        config.BROAD_UNIVERSE[:] = built
        config.STOCKS[:] = built
        log.info("Universe nifty500: %s names (LTP screen; RSI on top movers only)",
                 len(built))
    except Exception as e:
        log.warning("Nifty 500 universe failed (%s) — bundled %s names",
                    e, len(bundled))
        config.BROAD_UNIVERSE[:] = refresh_tokens_from_master(bundled)
    return config.BROAD_UNIVERSE


def refresh_tokens_from_master(stocks: list) -> list:
    """Overwrite tokens from Angel's public instrument dump. Offline = keep list."""
    patched = [copy.deepcopy(s) for s in stocks]
    try:
        mapping = lookup_nse_eq_tokens()
    except Exception as e:
        log.warning("Scrip master unavailable (%s) — using bundled tokens", e)
        return patched

    updated = 0
    for s in patched:
        fresh = mapping.get(s["symbol"])
        if fresh and fresh != str(s["token"]):
            log.info("Token %s: %s → %s", s["symbol"], s["token"], fresh)
            s["token"] = fresh
            updated += 1
    if updated:
        log.info("Updated %s tokens from scrip master", updated)
    return patched
