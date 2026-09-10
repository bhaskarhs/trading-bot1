import os
from dotenv import load_dotenv

load_dotenv()

# Angel One credentials
ANGEL_API_KEY     = os.getenv("ANGEL_API_KEY")
ANGEL_CLIENT_ID   = os.getenv("ANGEL_CLIENT_ID")
ANGEL_MPIN        = os.getenv("ANGEL_MPIN")
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

# Anthropic (optional)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# ─── Capital Management ───────────────────────────────────────────────────────
TOTAL_CAPITAL        = 100000   # ₹1,00,000
CAPITAL_PER_TRADE    = 20000    # ₹20,000 per trade
MAX_OPEN_POSITIONS   = 5        # max 5 trades at a time (5 × ₹20,000 = ₹1,00,000)

# ─── Nifty 100 Stocks ─────────────────────────────────────────────────────────
# Nifty 50 + Nifty Next 50 = 100 stocks
STOCKS = [
    # ── Nifty 50 ──────────────────────────────────────────────────────────────
    {"name": "Adani Enterprises",  "symbol": "ADANIENT-EQ",    "token": "25"},
    {"name": "Adani Ports",        "symbol": "ADANIPORTS-EQ",  "token": "15083"},
    {"name": "Apollo Hospitals",   "symbol": "APOLLOHOSP-EQ",  "token": "157"},
    {"name": "Asian Paints",       "symbol": "ASIANPAINT-EQ",  "token": "236"},
    {"name": "Axis Bank",          "symbol": "AXISBANK-EQ",    "token": "5900"},
    {"name": "Bajaj Auto",         "symbol": "BAJAJ-AUTO-EQ",  "token": "16669"},
    {"name": "Bajaj Finance",      "symbol": "BAJFINANCE-EQ",  "token": "317"},
    {"name": "Bajaj Finserv",      "symbol": "BAJAJFINSV-EQ",  "token": "16675"},
    {"name": "BPCL",               "symbol": "BPCL-EQ",        "token": "526"},
    {"name": "Bharti Airtel",      "symbol": "BHARTIARTL-EQ",  "token": "10604"},
    {"name": "Britannia",          "symbol": "BRITANNIA-EQ",   "token": "547"},
    {"name": "Cipla",              "symbol": "CIPLA-EQ",       "token": "694"},
    {"name": "Coal India",         "symbol": "COALINDIA-EQ",   "token": "20374"},
    {"name": "Divi's Labs",        "symbol": "DIVISLAB-EQ",    "token": "10940"},
    {"name": "Dr Reddy's",         "symbol": "DRREDDY-EQ",     "token": "881"},
    {"name": "Eicher Motors",      "symbol": "EICHERMOT-EQ",   "token": "910"},
    {"name": "Grasim",             "symbol": "GRASIM-EQ",      "token": "1232"},
    {"name": "HCL Tech",           "symbol": "HCLTECH-EQ",     "token": "7229"},
    {"name": "HDFC Bank",          "symbol": "HDFCBANK-EQ",    "token": "1333"},
    {"name": "HDFC Life",          "symbol": "HDFCLIFE-EQ",    "token": "467"},
    {"name": "Hero MotoCorp",      "symbol": "HEROMOTOCO-EQ",  "token": "1348"},
    {"name": "Hindalco",           "symbol": "HINDALCO-EQ",    "token": "1363"},
    {"name": "HUL",                "symbol": "HINDUNILVR-EQ",  "token": "1394"},
    {"name": "ICICI Bank",         "symbol": "ICICIBANK-EQ",   "token": "4963"},
    {"name": "IndusInd Bank",      "symbol": "INDUSINDBK-EQ",  "token": "5258"},
    {"name": "Infosys",            "symbol": "INFY-EQ",        "token": "1594"},
    {"name": "ITC",                "symbol": "ITC-EQ",         "token": "1660"},
    {"name": "JSW Steel",          "symbol": "JSWSTEEL-EQ",    "token": "11723"},
    {"name": "Kotak Bank",         "symbol": "KOTAKBANK-EQ",   "token": "1922"},
    {"name": "LT",                 "symbol": "LT-EQ",          "token": "11483"},
    {"name": "M&M",                "symbol": "M&M-EQ",         "token": "2031"},
    {"name": "Maruti Suzuki",      "symbol": "MARUTI-EQ",      "token": "10999"},
    {"name": "NTPC",               "symbol": "NTPC-EQ",        "token": "11630"},
    {"name": "Nestle India",       "symbol": "NESTLEIND-EQ",   "token": "17963"},
    {"name": "ONGC",               "symbol": "ONGC-EQ",        "token": "2475"},
    {"name": "Power Grid",         "symbol": "POWERGRID-EQ",   "token": "14977"},
    {"name": "Reliance",           "symbol": "RELIANCE-EQ",    "token": "2885"},
    {"name": "SBI",                "symbol": "SBIN-EQ",        "token": "3045"},
    {"name": "SBI Life",           "symbol": "SBILIFE-EQ",     "token": "21808"},
    {"name": "Shriram Finance",    "symbol": "SHRIRAMFIN-EQ",  "token": "4306"},
    {"name": "Sun Pharma",         "symbol": "SUNPHARMA-EQ",   "token": "3351"},
    {"name": "Tata Consumer",      "symbol": "TATACONSUM-EQ",  "token": "3432"},
    {"name": "Tata Motors",        "symbol": "TATAMOTORS-EQ",  "token": "3456"},
    {"name": "Tata Steel",         "symbol": "TATASTEEL-EQ",   "token": "3499"},
    {"name": "TCS",                "symbol": "TCS-EQ",         "token": "11536"},
    {"name": "Tech Mahindra",      "symbol": "TECHM-EQ",       "token": "13538"},
    {"name": "Titan",              "symbol": "TITAN-EQ",       "token": "3506"},
    {"name": "UltraTech Cement",   "symbol": "ULTRACEMCO-EQ",  "token": "11532"},
    {"name": "Wipro",              "symbol": "WIPRO-EQ",       "token": "3787"},
    {"name": "Zomato",             "symbol": "ZOMATO-EQ",      "token": "5097"},

    # ── Nifty Next 50 ─────────────────────────────────────────────────────────
    {"name": "ABB India",          "symbol": "ABB-EQ",         "token": "13"},
    {"name": "Ambuja Cements",     "symbol": "AMBUJACEM-EQ",   "token": "1270"},
    {"name": "Astral",             "symbol": "ASTRAL-EQ",      "token": "14418"},
    {"name": "Avenue Supermarts",  "symbol": "DMART-EQ",       "token": "19913"},
    {"name": "Bajaj Holdings",     "symbol": "BAJAJHLDNG-EQ",  "token": "16117"},
    {"name": "Berger Paints",      "symbol": "BERGEPAINT-EQ",  "token": "404"},
    {"name": "Biocon",             "symbol": "BIOCON-EQ",      "token": "1522"},
    {"name": "Bosch",              "symbol": "BOSCHLTD-EQ",    "token": "2181"},
    {"name": "Canara Bank",        "symbol": "CANBK-EQ",       "token": "10794"},
    {"name": "Cholamandalam",      "symbol": "CHOLAFIN-EQ",    "token": "685"},
    {"name": "Colgate",            "symbol": "COLPAL-EQ",      "token": "1429"},
    {"name": "Cummins India",      "symbol": "CUMMINSIND-EQ",  "token": "1901"},
    {"name": "DLF",                "symbol": "DLF-EQ",         "token": "14732"},
    {"name": "Dabur India",        "symbol": "DABUR-EQ",       "token": "772"},
    {"name": "Godrej Consumer",    "symbol": "GODREJCP-EQ",    "token": "10099"},
    {"name": "Godrej Properties",  "symbol": "GODREJPROP-EQ",  "token": "17875"},
    {"name": "Havells India",      "symbol": "HAVELLS-EQ",     "token": "14419"},
    {"name": "IDBI Bank",          "symbol": "IDBI-EQ",        "token": "4650"},
    {"name": "IDFC First Bank",    "symbol": "IDFCFIRSTB-EQ",  "token": "11184"},
    {"name": "Indian Hotels",      "symbol": "INDHOTEL-EQ",    "token": "1512"},
    {"name": "Indian Oil",         "symbol": "IOC-EQ",         "token": "1624"},
    {"name": "Interglobe Aviation","symbol": "INDIGO-EQ",      "token": "11195"},
    {"name": "Jio Financial",      "symbol": "JIOFIN-EQ",      "token": "18143"},
    {"name": "LIC Housing",        "symbol": "LICHSGFIN-EQ",   "token": "1997"},
    {"name": "Lupin",              "symbol": "LUPIN-EQ",       "token": "10440"},
    {"name": "Muthoot Finance",    "symbol": "MUTHOOTFIN-EQ",  "token": "7892"},
    {"name": "Naukri (Info Edge)", "symbol": "NAUKRI-EQ",      "token": "13751"},
    {"name": "Oberoi Realty",      "symbol": "OBEROIRLTY-EQ",  "token": "20242"},
    {"name": "Patanjali Foods",    "symbol": "PATANJALI-EQ",   "token": "17029"},
    {"name": "Persistent Systems", "symbol": "PERSISTENT-EQ",  "token": "18365"},
    {"name": "Pidilite",           "symbol": "PIDILITIND-EQ",  "token": "2664"},
    {"name": "PNB",                "symbol": "PNB-EQ",         "token": "2730"},
    {"name": "Polycab India",      "symbol": "POLYCAB-EQ",     "token": "20368"},
    {"name": "Procter & Gamble",   "symbol": "PGHH-EQ",        "token": "2535"},
    {"name": "SBI Cards",          "symbol": "SBICARD-EQ",     "token": "10204"},
    {"name": "Siemens",            "symbol": "SIEMENS-EQ",     "token": "3150"},
    {"name": "Tata Power",         "symbol": "TATAPOWER-EQ",   "token": "3426"},
    {"name": "Trent",              "symbol": "TRENT-EQ",       "token": "1964"},
    {"name": "TVS Motor",          "symbol": "TVSMOTOR-EQ",    "token": "2170"},
    {"name": "UPL",                "symbol": "UPL-EQ",         "token": "11287"},
    {"name": "Varun Beverages",    "symbol": "VBL-EQ",         "token": "19561"},
    {"name": "Vedanta",            "symbol": "VEDL-EQ",        "token": "3063"},
    {"name": "Voltas",             "symbol": "VOLTAS-EQ",      "token": "3083"},
    {"name": "Whirlpool",          "symbol": "WHIRLPOOL-EQ",   "token": "18011"},
    {"name": "Yes Bank",           "symbol": "YESBANK-EQ",     "token": "11915"},
    {"name": "Zydus Lifesciences", "symbol": "ZYDUSLIFE-EQ",   "token": "7929"},
]

# ─── RSI settings ─────────────────────────────────────────────────────────────
RSI_PERIOD     = 14
RSI_OVERSOLD   = 25    # BUY signal
RSI_OVERBOUGHT = 78    # SELL signal

# ─── Trade settings ───────────────────────────────────────────────────────────
PAPER_TRADING      = True
CANDLE_INTERVAL    = "FIFTEEN_MINUTE"
CANDLES_NEEDED     = 25

# ─── Stop loss ────────────────────────────────────────────────────────────────
# Exit immediately if price drops this % from buy price — overrides RSI
STOP_LOSS_PCT = 1.5

# ─── Screener settings ────────────────────────────────────────────────────────
SCREENER_MIN_MOVE_PCT = 1.0

# ─── Market breadth filter ────────────────────────────────────────────────────
MAX_BUY_SIGNALS_PER_SCAN = 6

# ─── Scan delay between stocks ────────────────────────────────────────────────
DELAY_BETWEEN_STOCKS = 1.0  # candle cache + retries handle AB1021
CANDLE_CACHE_SECONDS  = 90
SESSION_REFRESH_SECONDS = 6 * 3600
VALIDATE_TOKENS_ON_START = True

# Flatten INTRADAY books before NSE close (15:15–15:25 IST)
SQUARE_OFF_TIME = (15, 15)
MARKET_OPEN     = (9, 15)
MARKET_CLOSE    = (15, 25)
SCAN_INTERVAL_SECONDS = 300
# ─── VIX circuit breaker ──────────────────────────────────────────────────────
# India VIX thresholds — bot behaviour changes at each level
VIX_NORMAL_MAX  = 15    # below this → trade freely
VIX_CAUTION_MAX = 20    # 15-20 → no new BUYs, hold existing
VIX_DEFENSE_MAX = 25    # 20-25 → exit all positions
                        # above 25 → CRISIS, bot halts

# ─── Smart stop loss ─────────────────────────────────────────────────────────
# Market-relative stop loss — exits only if stock underperforms market
# Exit when: stock_change < (nifty_change - STOP_LOSS_BUFFER)
# Example: Nifty -2%, buffer 1.5% → exit stocks worse than -3.5%
# On a flat day: Nifty 0% → exit stocks worse than -1.5%
STOP_LOSS_BUFFER  = 1.5    # % stock must underperform Nifty to trigger SL

# Minimum hold time before stop loss can fire
STOP_LOSS_MIN_HOLD_MINS = 30   # never exit within first 30 minutes of buying

# Absolute floor — always exit regardless of market if loss exceeds this
STOP_LOSS_ABS_FLOOR = 500      # ₹500 loss per position = always exit

from universe import MIDCAPS, apply_token_fixes, merge_universe

STOCKS = apply_token_fixes(STOCKS)
BROAD_UNIVERSE = merge_universe(STOCKS, MIDCAPS)
