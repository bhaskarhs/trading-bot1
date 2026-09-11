# Run 09:15–15:30 IST with no domain

You do not need a website or a purchased domain. The bot is a **weekday worker**. The free resource you already have is **GitHub Actions** on this repository.

```
09:10 IST  workflow starts (cron 03:40 UTC, Mon–Fri)
09:15      morning job scans until 12:15 IST
12:15      afternoon job continues the same ledger
15:15      square-off INTRADAY
15:30      process exits; ledger committed back to the repo
```

GitHub’s free hosted job cap is **6 hours**. 09:15–15:30 is longer than that, so the day is two jobs in one workflow. No Render, no Cloudflare, no Oracle, no DNS.

## 1. One-time setup (GitHub UI)

1. Open https://github.com/bhaskarhs/trading-bot1/settings/secrets/actions
2. New repository secret, one each:

   | Name | What |
   |---|---|
   | `ANGEL_API_KEY` | SmartAPI key |
   | `ANGEL_CLIENT_ID` | Client ID |
   | `ANGEL_MPIN` | MPIN |
   | `ANGEL_TOTP_SECRET` | TOTP secret (not the 6-digit code) |
   | `TELEGRAM_BOT_TOKEN` | optional |
   | `TELEGRAM_CHAT_ID` | optional |

3. **Actions** must be allowed: Settings → Actions → General → “Allow all actions”.
4. Keep `PAPER_TRADING=true` in the workflow (already set). Do not turn live on from CI.

If the repo is **private**, GitHub’s free allowance is about 2,000 minutes/month (~5 full trading days). Make the repo **public** (or use a larger Actions plan) if you want every weekday for free. Public repos do not spend that private-minute quota.

## 2. Turn it on

The workflow file is `.github/workflows/nse-session.yml`.

- After it is on `master`, GitHub will fire it **Mon–Fri ~09:10 IST**.
- Cron is often 5–15 minutes late. The bot waits until 09:15, then scans.
- For a dry run: Actions → **NSE market session** → **Run workflow**.
  - If you click this on a weekend or after 15:25 IST, the bot exits immediately (success).

## 3. What you look at (still no domain)

| Where | What |
|---|---|
| Actions tab → latest run → logs | Same scan printout as a local `bot.py` |
| `paper_trades.json` / `open_positions.json` on `master` | Afternoon job commits these after the close |
| `python summary.py` locally after pull | P&L |
| Telegram | If those two secrets are set |

Optional local UI, still free, still no domain: `python dashboard.py` then http://127.0.0.1:5000

## 4. How the code exits

`RUN_MARKET_SESSION=1 python bot.py`

- Weekend or after 15:25 IST → exit 0
- `SESSION_END=12:15` → stop at 12:15 **without** flattening (afternoon continues)
- `SESSION_END=15:30` → flatten at 15:15, then exit

Local laptop (old behaviour, stays up overnight):

```bash
python bot.py
```

## 5. Limits to know

- GitHub runners sit in the US. Angel One usually answers; if login fails, read the Action log.
- The scan list is **Nifty 500** (~500 liquid names), not every NSE stock. LTP-screen those; RSI only the top movers (`MAX_CANDIDATES = 50`). If NSE’s CSV is blocked from GitHub, the bot uses `data/nifty500_symbols.txt` plus Angel’s scrip master.
- NSE holidays are still weekdays; the bot will try to scan (LTP may be stale). Pause the workflow that week if needed.
- Do not put secrets in the repo. `.env` stays gitignored.
- First morning after merge: add secrets **before** 09:10 IST or the job will fail on purpose.

## 6. What we are not doing

- Buying a domain
- Render / Fly public URL
- An always-on VM

Those remain possible later; they are not required to trade 09:15–15:30.
