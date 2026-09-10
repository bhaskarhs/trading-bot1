"""
screener.py — Market direction detection + candidate filtering

Market modes detected:
  STRONG_UP   → Nifty gap or intraday > +2.0%  → scan top gainers
  MILD_UP     → Nifty up +0.5% to +2.0%        → scan gainers > 1%  ← catches gradual recovery
  FLAT        → Nifty ±0.5%                     → scan both directions > 1%
  DOWN        → Nifty down < -0.5%              → scan top fallers

Fallback: if LTP API fails or finds 0 candidates → scan all stocks in universe
"""

import time
from angel_client import get_angel
import config

MIN_MOVE_PCT   = config.SCREENER_MIN_MOVE_PCT   # 1.0%
MAX_CANDIDATES = 50
BATCH_SIZE     = 25    # reduced from 50 → smaller batches = less timeout risk
NIFTY_TOKEN    = "99926000"

BROAD_UNIVERSE = [
    # Nifty 50
    {"name": "Adani Enterprises",   "symbol": "ADANIENT-EQ",    "token": "25"},
    {"name": "Adani Ports",         "symbol": "ADANIPORTS-EQ",  "token": "15083"},
    {"name": "Apollo Hospitals",    "symbol": "APOLLOHOSP-EQ",  "token": "157"},
    {"name": "Asian Paints",        "symbol": "ASIANPAINT-EQ",  "token": "236"},
    {"name": "Axis Bank",           "symbol": "AXISBANK-EQ",    "token": "5900"},
    {"name": "Bajaj Auto",          "symbol": "BAJAJ-AUTO-EQ",  "token": "16669"},
    {"name": "Bajaj Finance",       "symbol": "BAJFINANCE-EQ",  "token": "317"},
    {"name": "Bajaj Finserv",       "symbol": "BAJAJFINSV-EQ",  "token": "16675"},
    {"name": "BPCL",                "symbol": "BPCL-EQ",        "token": "526"},
    {"name": "Bharti Airtel",       "symbol": "BHARTIARTL-EQ",  "token": "10604"},
    {"name": "Britannia",           "symbol": "BRITANNIA-EQ",   "token": "547"},
    {"name": "Cipla",               "symbol": "CIPLA-EQ",       "token": "694"},
    {"name": "Coal India",          "symbol": "COALINDIA-EQ",   "token": "20374"},
    {"name": "Divi's Labs",         "symbol": "DIVISLAB-EQ",    "token": "10940"},
    {"name": "Dr Reddy's",          "symbol": "DRREDDY-EQ",     "token": "881"},
    {"name": "Eicher Motors",       "symbol": "EICHERMOT-EQ",   "token": "910"},
    {"name": "Grasim",              "symbol": "GRASIM-EQ",      "token": "1232"},
    {"name": "HCL Tech",            "symbol": "HCLTECH-EQ",     "token": "7229"},
    {"name": "HDFC Bank",           "symbol": "HDFCBANK-EQ",    "token": "1333"},
    {"name": "HDFC Life",           "symbol": "HDFCLIFE-EQ",    "token": "467"},
    {"name": "Hero MotoCorp",       "symbol": "HEROMOTOCO-EQ",  "token": "1348"},
    {"name": "Hindalco",            "symbol": "HINDALCO-EQ",    "token": "1363"},
    {"name": "HUL",                 "symbol": "HINDUNILVR-EQ",  "token": "1394"},
    {"name": "ICICI Bank",          "symbol": "ICICIBANK-EQ",   "token": "4963"},
    {"name": "IndusInd Bank",       "symbol": "INDUSINDBK-EQ",  "token": "5258"},
    {"name": "Infosys",             "symbol": "INFY-EQ",        "token": "1594"},
    {"name": "ITC",                 "symbol": "ITC-EQ",         "token": "1660"},
    {"name": "JSW Steel",           "symbol": "JSWSTEEL-EQ",    "token": "11723"},
    {"name": "Kotak Bank",          "symbol": "KOTAKBANK-EQ",   "token": "1922"},
    {"name": "LT",                  "symbol": "LT-EQ",          "token": "11483"},
    {"name": "M&M",                 "symbol": "M&M-EQ",         "token": "2031"},
    {"name": "Maruti Suzuki",       "symbol": "MARUTI-EQ",      "token": "10999"},
    {"name": "NTPC",                "symbol": "NTPC-EQ",        "token": "11630"},
    {"name": "Nestle India",        "symbol": "NESTLEIND-EQ",   "token": "17963"},
    {"name": "ONGC",                "symbol": "ONGC-EQ",        "token": "2475"},
    {"name": "Power Grid",          "symbol": "POWERGRID-EQ",   "token": "14977"},
    {"name": "Reliance",            "symbol": "RELIANCE-EQ",    "token": "2885"},
    {"name": "SBI",                 "symbol": "SBIN-EQ",        "token": "3045"},
    {"name": "SBI Life",            "symbol": "SBILIFE-EQ",     "token": "21808"},
    {"name": "Shriram Finance",     "symbol": "SHRIRAMFIN-EQ",  "token": "4306"},
    {"name": "Sun Pharma",          "symbol": "SUNPHARMA-EQ",   "token": "3351"},
    {"name": "Tata Consumer",       "symbol": "TATACONSUM-EQ",  "token": "3432"},
    {"name": "Tata Motors",         "symbol": "TATAMOTORS-EQ",  "token": "3456"},
    {"name": "Tata Steel",          "symbol": "TATASTEEL-EQ",   "token": "3499"},
    {"name": "TCS",                 "symbol": "TCS-EQ",         "token": "11536"},
    {"name": "Tech Mahindra",       "symbol": "TECHM-EQ",       "token": "13538"},
    {"name": "Titan",               "symbol": "TITAN-EQ",       "token": "3506"},
    {"name": "UltraTech Cement",    "symbol": "ULTRACEMCO-EQ",  "token": "11532"},
    {"name": "Wipro",               "symbol": "WIPRO-EQ",       "token": "3787"},
    {"name": "Zomato",              "symbol": "ZOMATO-EQ",      "token": "5097"},
    # Nifty Next 50
    {"name": "ABB India",           "symbol": "ABB-EQ",         "token": "13"},
    {"name": "Ambuja Cements",      "symbol": "AMBUJACEM-EQ",   "token": "1270"},
    {"name": "Avenue Supermarts",   "symbol": "DMART-EQ",       "token": "11287"},
    {"name": "Berger Paints",       "symbol": "BERGEPAINT-EQ",  "token": "404"},
    {"name": "Biocon",              "symbol": "BIOCON-EQ",      "token": "1522"},
    {"name": "Bosch",               "symbol": "BOSCHLTD-EQ",    "token": "2181"},
    {"name": "Canara Bank",         "symbol": "CANBK-EQ",       "token": "10794"},
    {"name": "Cholamandalam",       "symbol": "CHOLAFIN-EQ",    "token": "685"},
    {"name": "Colgate",             "symbol": "COLPAL-EQ",      "token": "1429"},
    {"name": "Cummins India",       "symbol": "CUMMINSIND-EQ",  "token": "1901"},
    {"name": "DLF",                 "symbol": "DLF-EQ",         "token": "14732"},
    {"name": "Dabur India",         "symbol": "DABUR-EQ",       "token": "772"},
    {"name": "Godrej Consumer",     "symbol": "GODREJCP-EQ",    "token": "10099"},
    {"name": "Godrej Properties",   "symbol": "GODREJPROP-EQ",  "token": "17875"},
    {"name": "Havells India",       "symbol": "HAVELLS-EQ",     "token": "14419"},
    {"name": "IDFC First Bank",     "symbol": "IDFCFIRSTB-EQ",  "token": "11184"},
    {"name": "Indian Hotels",       "symbol": "INDHOTEL-EQ",    "token": "1512"},
    {"name": "Indian Oil",          "symbol": "IOC-EQ",         "token": "1624"},
    {"name": "IndiGo",              "symbol": "INDIGO-EQ",      "token": "11195"},
    {"name": "LIC Housing",         "symbol": "LICHSGFIN-EQ",   "token": "1997"},
    {"name": "Lupin",               "symbol": "LUPIN-EQ",       "token": "10440"},
    {"name": "Muthoot Finance",     "symbol": "MUTHOOTFIN-EQ",  "token": "7892"},
    {"name": "Naukri",              "symbol": "NAUKRI-EQ",      "token": "13751"},
    {"name": "Persistent Systems",  "symbol": "PERSISTENT-EQ",  "token": "18365"},
    {"name": "Pidilite",            "symbol": "PIDILITIND-EQ",  "token": "2664"},
    {"name": "PNB",                 "symbol": "PNB-EQ",         "token": "2730"},
    {"name": "Polycab India",       "symbol": "POLYCAB-EQ",     "token": "20368"},
    {"name": "SBI Cards",           "symbol": "SBICARD-EQ",     "token": "10204"},
    {"name": "Siemens",             "symbol": "SIEMENS-EQ",     "token": "3150"},
    {"name": "Tata Power",          "symbol": "TATAPOWER-EQ",   "token": "3426"},
    {"name": "Trent",               "symbol": "TRENT-EQ",       "token": "1964"},
    {"name": "TVS Motor",           "symbol": "TVSMOTOR-EQ",    "token": "2170"},
    {"name": "Varun Beverages",     "symbol": "VBL-EQ",         "token": "19561"},
    {"name": "Vedanta",             "symbol": "VEDL-EQ",        "token": "3063"},
    {"name": "Voltas",              "symbol": "VOLTAS-EQ",      "token": "3083"},
    {"name": "Yes Bank",            "symbol": "YESBANK-EQ",     "token": "11915"},
    {"name": "Zydus Lifesciences",  "symbol": "ZYDUSLIFE-EQ",   "token": "7929"},
    # Midcap picks
    {"name": "AU Small Finance",    "symbol": "AUBANK-EQ",      "token": "18860"},
    {"name": "Bank of Baroda",      "symbol": "BANKBARODA-EQ",  "token": "4668"},
    {"name": "BSE Ltd",             "symbol": "BSE-EQ",         "token": "543257"},
    {"name": "Coforge",             "symbol": "COFORGE-EQ",     "token": "11543"},
    {"name": "Dixon Tech",          "symbol": "DIXON-EQ",       "token": "19913"},
    {"name": "Federal Bank",        "symbol": "FEDERALBNK-EQ",  "token": "1023"},
    {"name": "HPCL",                "symbol": "HINDPETRO-EQ",   "token": "1406"},
    {"name": "IDBI Bank",           "symbol": "IDBI-EQ",        "token": "4650"},
    {"name": "IRCTC",               "symbol": "IRCTC-EQ",       "token": "13611"},
    {"name": "IRFC",                "symbol": "IRFC-EQ",        "token": "18143"},
    {"name": "Jubilant Food",       "symbol": "JUBLFOOD-EQ",    "token": "18096"},
    {"name": "L&T Finance",         "symbol": "LTF-EQ",         "token": "18975"},
    {"name": "Manappuram Fin",      "symbol": "MANAPPURAM-EQ",  "token": "10720"},
    {"name": "Max Healthcare",      "symbol": "MAXHEALTH-EQ",   "token": "27913"},
    {"name": "MCX India",           "symbol": "MCX-EQ",         "token": "11850"},
    {"name": "MRF",                 "symbol": "MRF-EQ",         "token": "2277"},
    {"name": "NMDC",                "symbol": "NMDC-EQ",        "token": "15332"},
    {"name": "Oracle Fin Services", "symbol": "OFSS-EQ",        "token": "2725"},
    {"name": "Page Industries",     "symbol": "PAGEIND-EQ",     "token": "14413"},
    {"name": "Petronet LNG",        "symbol": "PETRONET-EQ",    "token": "11351"},
    {"name": "Phoenix Mills",       "symbol": "PHOENIXLTD-EQ",  "token": "17524"},
    {"name": "PI Industries",       "symbol": "PIIND-EQ",       "token": "13813"},
    {"name": "Rail Vikas Nigam",    "symbol": "RVNL-EQ",        "token": "532955"},
    {"name": "Torrent Pharma",      "symbol": "TORNTPHARM-EQ",  "token": "3518"},
    {"name": "Torrent Power",       "symbol": "TORNTPOWER-EQ",  "token": "3545"},
    {"name": "Union Bank",          "symbol": "UNIONBANK-EQ",   "token": "2752"},
]


def _fetch_ltp_batch(tokens: list, retries: int = 3) -> dict:
    """
    Fetches LTP for a batch of tokens.
    Retries up to 3 times on timeout with increasing wait.
    """
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
                wait = attempt * 3   # 3s, 6s, 9s
                print(f"  [SCREENER] Timeout on batch, waiting {wait}s "
                      f"(attempt {attempt}/{retries})...")
                time.sleep(wait)
                continue
            print(f"  [SCREENER] Batch error: {e}")
            return {}
    print(f"  [SCREENER] Batch failed after {retries} retries — skipping batch")
    return {}


def get_market_direction() -> tuple:
    """
    Returns (mode, nifty_pct, gap_pct)

    mode:
      STRONG_UP  → gap or intraday > +2.0%
      MILD_UP    → intraday +0.5% to +2.0%   ← NEW
      FLAT       → ±0.5%
      DOWN       → < -0.5%
    """
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

        ltp        = float(items[0].get("ltp",  0))
        open_price = float(items[0].get("open", 0))
        prev_close = float(items[0].get("previous_close", open_price))

        if open_price <= 0:
            return "FLAT", 0.0, 0.0

        pct     = round(((ltp - open_price) / open_price) * 100, 2)
        gap_pct = round(((open_price - prev_close) / prev_close) * 100, 2) \
                  if prev_close > 0 else 0.0

        # Gap override → strong move
        if gap_pct > 2.0 or pct > 2.0:
            return "STRONG_UP", pct, gap_pct
        elif gap_pct < -1.5:
            return "DOWN", pct, gap_pct

        # Intraday direction
        if   pct >  0.5: return "MILD_UP", pct, gap_pct
        elif pct < -0.5: return "DOWN",    pct, gap_pct
        else:            return "FLAT",    pct, gap_pct

    except Exception as e:
        print(f"  [SCREENER] Nifty direction error: {e}")
        return "FLAT", 0.0, 0.0


def get_candidates(verbose: bool = True) -> tuple:
    """
    Returns (candidates_list, strategy_mode, gap_pct)

    strategy_mode matches strategy.py modes:
      STRONG_MOMENTUM, MILD_MOMENTUM, FLAT, MEAN_REVERSION
    """
    direction, nifty_pct, gap_pct = get_market_direction()

    # Map screener direction → strategy mode
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
        print(f"\n  [SCREENER] Market: {labels[direction]}")
        print(f"  [SCREENER] Universe: {len(BROAD_UNIVERSE)} stocks")

    # Deduplicate universe
    seen, unique = set(), []
    for s in BROAD_UNIVERSE:
        if s["token"] not in seen:
            seen.add(s["token"])
            unique.append(s)

    token_map = {s["token"]: s for s in unique}
    all_ltp   = {}

    for i in range(0, len(token_map), BATCH_SIZE):
        batch    = list(token_map.keys())[i:i + BATCH_SIZE]
        ltp_data = _fetch_ltp_batch(batch)
        all_ltp.update(ltp_data)
        time.sleep(1.5)   # increased from 0.5s → less pressure on Angel One servers

    from trader import open_positions
    candidates = []

    for token, stock in token_map.items():
        data = all_ltp.get(token)
        if not data:
            continue
        ltp        = data["ltp"]
        open_price = data["open"]
        if open_price <= 0 or ltp <= 0:
            continue

        pct     = ((ltp - open_price) / open_price) * 100
        is_held = stock["symbol"] in open_positions

        # Always include held positions
        if is_held:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
            continue

        if direction in ("STRONG_UP", "MILD_UP") and pct >= MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
        elif direction == "DOWN" and pct <= -MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})
        elif direction == "FLAT" and abs(pct) >= MIN_MOVE_PCT:
            candidates.append({**stock, "pct_change": round(pct, 2), "ltp": ltp})

    candidates.sort(key=lambda x: x["pct_change"],
                    reverse=(direction in ("STRONG_UP", "MILD_UP")))
    candidates = candidates[:MAX_CANDIDATES]

    if verbose:
        print(f"  [SCREENER] {len(candidates)} candidates:")
        for c in candidates[:8]:
            arrow = "↑" if c["pct_change"] > 0 else "↓"
            print(f"    {c['name']:<24} {arrow}{abs(c['pct_change']):>5.2f}%  ₹{c['ltp']}")
        if len(candidates) > 8:
            print(f"    ... and {len(candidates) - 8} more")

    # ── Fallback: if LTP API failed or market too flat, scan full universe ─────
    if not candidates:
        print(f"  [SCREENER] No candidates found — falling back to full universe scan")
        candidates = unique[:MAX_CANDIDATES]
        clean = [{"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
                 for s in candidates]
        return clean, strategy_mode, gap_pct

    clean = [{"name": s["name"], "symbol": s["symbol"], "token": s["token"]}
             for s in candidates]

    return clean, strategy_mode, gap_pct
