# NSE RSI Trading Bot

Paper-first intraday bot for NSE cash stocks via Angel One SmartAPI. It is a **weekday loop**, not a strategy notebook: every 5 minutes during market hours it reads India VIX, classifies Nifty’s day, screens movers, computes RSI, then paper-logs (or live-places) BUY/SELL.

## How it is written (file by file)

| File | Role |
|---|---|
| `bot.py` | Process owner. `is_market_open()` uses Asia/Kolkata 09:15–15:25 Mon–Fri. `run_scan()` is a 10-step pipeline. |
| `config.py` | All knobs + duplicated Nifty 100 token list. Credentials from `.env`. `PAPER_TRADING = True`. |
| `angel_client.py` | One cached `SmartConnect` session (TOTP). `fetch_candles()` with AB1019/AB1021 backoff. |
| `screener.py` | Nifty direction → strategy mode; batched LTP; keep ≥1% movers + current holdings. |
| `strategy.py` | Pandas EWM RSI + four hard-coded modes. |
| `trader.py` | Slot/qty rules; JSON ledger in paper; market INTRADAY orders in live. |
| `vix_monitor.py` | India VIX → NORMAL / CAUTION / DEFENSE / CRISIS. |
| `notifier.py` | Optional Telegram HTML. |
| `summary.py` | FIFO P&L across the whole `paper_trades.json`. |
| `daily_report.py` | Per-calendar-day reports (does **not** match overnight holds). |
| `dashboard.py` | Flask site for hosting on a free domain (read-only + demo scan). |
| `demo.py` | Same scan printout with synthetic candles (no broker). |

### Scan pipeline (as coded)

1. **VIX** — if DEFENSE/CRISIS, sell all and skip the rest of the scan.
2. **Screener** — Nifty % from open + gap vs previous close → `STRONG_MOMENTUM` / `MILD_MOMENTUM` / `FLAT` / `MEAN_REVERSION`.
3. **Smart stop** — after 30 minutes, exit if the stock underperforms Nifty by `STOP_LOSS_BUFFER` (1.5%) **or** cash loss ≥ ₹500.
4. **RSI 14** on 15-minute closes (`CANDLES_NEEDED = 25`).
5. **Breadth** — in mean-reversion only, drop all BUYs if more than 6 BUY signals.
6. **CAUTION** — VIX 15–20: clear BUY list, still process SELLs.
7. **Execute** — `execute_trade()` then Telegram.

### Strategy thresholds (as coded)

- **STRONG_MOMENTUM** (Nifty gap or intraday > +2%): BUY if RSI > 60 **and** last close ≥ 97% of 10-bar high; SELL if RSI < 50.
- **MILD_MOMENTUM** (+0.5% to +2%): BUY RSI > 52; SELL RSI < 44.
- **FLAT** (±0.5%): BUY RSI < 35; SELL RSI > 70.
- **MEAN_REVERSION** (< −0.5%): BUY RSI < 25; SELL RSI > 78.

Sells only fire if the symbol is already in `open_positions.json` (the bot does not short).

## Run locally

```bash
python -m venv trading_env
source trading_env/bin/activate   # Windows: trading_env\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # fill Angel + optional Telegram
python demo.py                    # no credentials
python summary.py               # uses saved paper_trades.json
python daily_report.py
python dashboard.py              # http://127.0.0.1:5000
# Market hours only, needs Angel:
python bot.py
```

`howtorun.txt` is the original schedule: start `bot.py` at 9:15 IST, stop ~3:30, then `daily_report.py`.

## What we already ran

With the committed `paper_trades.json` (42 paper fills, no live broker in this environment):

- `summary.py`: **21 closed round-trips, realised +₹637.70, win rate 11/21 (52%)**, 0 open.
- `daily_report.py`: multi-day total **−₹132.7** because it matches BUY→SELL **inside each calendar day only**. Overnight holds (e.g. bought 24 Apr, sold 27 Apr) do not count as realised P&L there. Trust `summary.py` for lifetime P&L.

`bot.py` cannot log into Angel here: there is no `.env`. Use `demo.py` for a scan-shaped log without the broker.

## Improve next (priority)

1. **Wrong tokens** — `PATANJALI-EQ` and `UPL-EQ` reuse Power Grid / DMart tokens. Deduplicate universe; load tokens from Angel’s instrument master, not a hand list in two files.
2. **Timezone crash** — stop-loss parses naive `buy_time` and subtracts from IST-aware `now` (Python 3.12 raises).
3. **CRISIS does not halt** — `should_exit_all` returns from the scan, then the loop keeps scanning.
4. **Unused** — `STOP_LOSS_PCT`, `is_safe_to_buy`, Anthropic key, `last_scan_day`, `is_flat_market` argument.
5. **Reports** — make `daily_report.py` FIFO across days like `summary.py`.
6. **Live risk** — no broker fill confirmation, no product-type square-off at 15:20, JSON files are not atomic, session never refreshes.
7. **Rate limits** — 2s × ~50 names per scan is slow and still hits AB1021; cache candles, use quote streaming.
8. **Tests** — strategy is now covered; add trader + SL tests with fakes.
9. **Ops** — structured logging instead of `print`; persist on a real disk; never commit `.env`.

## Deploy (free host + domain)

See [DEPLOY.md](DEPLOY.md). Short version: **Render Free** for `dashboard.py` + Cloudflare CNAME for your domain; **Oracle Always Free ARM** (or similar VM) for `bot.py` so the loop is not slept by a PaaS web dyno.
