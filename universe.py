"""
Single stock universe + Angel scrip-master token repair.

Known bad tokens in the original lists (NSE cash EQ):
  PATANJALI-EQ was Power Grid 14977
  DMART-EQ was UPL 11287
  DIXON-EQ was actually DMART 19913
  JIOFIN-EQ / IRFC-EQ / BSE-EQ / RVNL-EQ used BSE-style codes
"""

import copy

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


def lookup_nse_eq_tokens(timeout: int = 30) -> dict:
    res = requests.get(SCRIP_MASTER_URL, timeout=timeout)
    res.raise_for_status()
    mapping = {}
    for row in res.json():
        if row.get("exch_seg") != "NSE":
            continue
        symbol = row.get("symbol") or ""
        if symbol.endswith("-EQ"):
            mapping[symbol] = str(row.get("token"))
    return mapping


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
