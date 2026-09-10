"""
Read-only dashboard for paper trades, bot status, and a no-login demo scan.

This is what you deploy on a free web host. The live Angel One loop (bot.py)
is a separate process — see DEPLOY.md.
"""

import os
from datetime import datetime

import pytz
from flask import Flask, jsonify, render_template_string

import config
from demo import make_closes, run_demo
from ledger import fifo_round_trips
from persist import load_json
from strategy import calculate_rsi, get_signal

IST = pytz.timezone("Asia/Kolkata")
PAPER_LOG_FILE = "paper_trades.json"
POSITIONS_FILE = "open_positions.json"

app = Flask(__name__)


def market_clock():
    now = datetime.now(IST)
    open_now = now.weekday() < 5 and config.MARKET_OPEN <= (now.hour, now.minute) <= config.MARKET_CLOSE
    return {
        "ist": now.strftime("%Y-%m-%d %H:%M:%S IST"),
        "weekday": now.strftime("%A"),
        "market_open": open_now,
    }


def paper_stats():
    trades = load_json(PAPER_LOG_FILE, [])
    open_pos = load_json(POSITIONS_FILE, {}) or {}
    closed, _unmatched = fifo_round_trips(trades)
    total_pnl = round(sum(c["pnl"] for c in closed), 2)
    wins = [c for c in closed if c["pnl"] > 0]
    losses = [c for c in closed if c["pnl"] < 0]
    return {
        "trade_count": len(trades),
        "closed_count": len(closed),
        "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
        "realised_pnl": total_pnl,
        "avg_win": round(sum(c["pnl"] for c in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(c["pnl"] for c in losses) / len(losses), 2) if losses else 0,
        "open_count": len(open_pos),
        "closed": closed[-12:][::-1],
        "recent_trades": list(reversed(trades[-15:])),
        "open_positions": open_pos,
    }


def demo_scan_payload():
    samples = [
        ("Coal India", "oversold"),
        ("TCS", "overbought"),
        ("Reliance", "breakout"),
        ("HDFC Bank", "chop"),
    ]
    rows = []
    for mode in ["MEAN_REVERSION", "FLAT", "MILD_MOMENTUM", "STRONG_MOMENTUM"]:
        for name, kind in samples:
            closes = make_closes(kind)
            rsi = calculate_rsi(closes, config.RSI_PERIOD)
            signal = get_signal(
                rsi=rsi,
                oversold=config.RSI_OVERSOLD,
                overbought=config.RSI_OVERBOUGHT,
                mode=mode,
                closes=closes,
                is_flat_market=(mode == "FLAT"),
            )
            rows.append({
                "mode": mode,
                "stock": name,
                "kind": kind,
                "price": closes[-1],
                "rsi": rsi,
                "signal": signal,
            })
    return rows


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NSE RSI Trading Bot</title>
  <style>
    :root { --bg:#0b1220; --card:#121a2b; --line:#243049; --text:#e8eefc; --muted:#93a0b8; --buy:#3dd68c; --sell:#ff6b7a; --hold:#8ea0c2; }
    * { box-sizing: border-box; }
    body { margin:0; font-family: ui-sans-serif, system-ui, Segoe UI, sans-serif; background: radial-gradient(1200px 500px at 10% -10%, #1b2a4a 0%, var(--bg) 55%); color: var(--text); }
    header, main { max-width: 1100px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 8px; font-size: 28px; }
    .sub { color: var(--muted); margin-bottom: 20px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
    .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px; margin-bottom: 16px; }
    .k { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .v { font-size: 26px; font-weight: 700; margin-top: 6px; }
    .ok { color: var(--buy); } .bad { color: var(--sell); }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { text-align: left; padding: 8px 8px; border-bottom: 1px solid var(--line); }
    th { color: var(--muted); font-weight: 600; }
    .BUY { color: var(--buy); font-weight: 700; }
    .SELL { color: var(--sell); font-weight: 700; }
    .HOLD { color: var(--hold); }
    pre { white-space: pre-wrap; background: #0a101c; padding: 14px; border-radius: 10px; overflow: auto; font-size: 13px; line-height: 1.45; }
    a { color: #8cb4ff; }
    nav a { margin-right: 14px; }
  </style>
</head>
<body>
<header>
  <h1>NSE Trading Bot</h1>
  <p class="sub">RSI scanner + VIX circuit breaker + market-relative stop loss. Paper mode by default.</p>
  <nav>
    <a href="/">Dashboard</a>
    <a href="/how-it-works">How it is written</a>
    <a href="/deploy">Deploy + domain</a>
    <a href="/api/demo">Demo JSON</a>
  </nav>
</header>
<main>
  <div class="grid">
    <div class="card"><div class="k">Clock (IST)</div><div class="v" style="font-size:18px">{{ clock.ist }}</div><div class="sub">{{ clock.weekday }} · {{ 'Market open' if clock.market_open else 'Market closed' }}</div></div>
    <div class="card"><div class="k">Realised P&L</div><div class="v {{ 'ok' if stats.realised_pnl >= 0 else 'bad' }}">₹{{ stats.realised_pnl }}</div></div>
    <div class="card"><div class="k">Win rate</div><div class="v">{{ stats.win_rate }}%</div><div class="sub">{{ stats.closed_count }} closed round-trips</div></div>
    <div class="card"><div class="k">Open slots</div><div class="v">{{ stats.open_count }}/{{ max_pos }}</div></div>
  </div>

  <div class="card">
    <div class="k">Demo scan (synthetic candles, no Angel login)</div>
    <table>
      <tr><th>Mode</th><th>Stock</th><th>Regime</th><th>Price</th><th>RSI</th><th>Signal</th></tr>
      {% for r in demo %}
      <tr>
        <td>{{ r.mode }}</td>
        <td>{{ r.stock }}</td>
        <td>{{ r.kind }}</td>
        <td>₹{{ r.price }}</td>
        <td>{{ r.rsi }}</td>
        <td class="{{ r.signal }}">{{ r.signal }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div class="card">
    <div class="k">Closed paper trades (latest)</div>
    <table>
      <tr><th>Stock</th><th>Buy</th><th>Sell</th><th>Qty</th><th>P&L</th></tr>
      {% for c in stats.closed %}
      <tr>
        <td>{{ c.stock }}</td>
        <td>₹{{ c.buy_price }}</td>
        <td>₹{{ c.sell_price }}</td>
        <td>{{ c.qty }}</td>
        <td class="{{ 'ok' if c.pnl >= 0 else 'bad' }}">₹{{ c.pnl }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</main>
</body>
</html>
"""

HOWTO = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>How this bot is written</title>
<style>
  body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:#0b1220; color:#e8eefc; }
  main { max-width: 900px; margin: 0 auto; padding: 24px; }
  a { color:#8cb4ff; }
  pre { background:#0a101c; padding:14px; border-radius:10px; overflow:auto; }
  h2 { margin-top: 28px; }
  .muted { color:#93a0b8; }
</style></head>
<body><main>
<a href="/">← Dashboard</a>
<h1>How the code is written</h1>
<p class="muted">A weekday loop, not a website. Each file has one job.</p>

<h2>1. bot.py is the conductor</h2>
<p><code>main()</code> logs into Angel One, then loops forever. If IST time is between 09:15 and 15:25 on a weekday it calls <code>run_scan()</code> and sleeps 5 minutes. Otherwise it sleeps 60 seconds. A scan always does the same ten steps:</p>
<pre>VIX check → screener/market mode → stop-loss on holdings
→ RSI on candidates → breadth filter → VIX caution blocks BUYs
→ print → execute_trade → print open slots</pre>
<p>If VIX is DEFENSE or CRISIS it sells everything and returns early (it does not actually halt the process — that is a gap).</p>

<h2>2. config.py is the knobs</h2>
<p>Capital (₹1,00,000 / ₹20,000 / 5 slots), RSI 14 / 25 / 78, 15-minute candles, VIX bands 15 / 20 / 25, relative stop 1.5% vs Nifty, 30-minute hold protection, ₹500 absolute floor. <code>PAPER_TRADING = True</code> so orders are JSON, not live.</p>

<h2>3. angel_client.py talks to the broker</h2>
<p>TOTP + MPIN session is cached in a module global. Candles come from historical API with retries on AB1019/AB1021 rate limits. Close is candle field index 4.</p>

<h2>4. screener.py picks the battlefield</h2>
<p>Nifty LTP vs open (and gap vs previous close) maps to STRONG_UP / MILD_UP / FLAT / DOWN. Then LTP batches of 25 over a ~100 name universe keep names that moved ≥1% in the “right” direction, plus anything already held. Fallback: scan the first 50 names if nothing qualifies.</p>

<h2>5. strategy.py is a switch, not ML</h2>
<p>Wilder-style RSI via pandas EWM. Four mutually exclusive modes with hard RSI cutoffs. STRONG_MOMENTUM also requires price within 3% of the 10-bar high.</p>

<h2>6. trader.py is a tiny ledger</h2>
<p>Quantity = floor(CAPITAL_PER_TRADE / price). BUY skipped if already held or slots full. SELL uses stored qty. Paper path appends <code>paper_trades.json</code> and rewrites <code>open_positions.json</code>. Live path places NSE INTRADAY MARKET orders.</p>

<h2>7. vix_monitor.py / notifier.py / reports</h2>
<p>India VIX token 99919003, cached 4 minutes, default 15 on failure. Telegram is optional HTML. <code>summary.py</code> FIFO-matches all history. <code>daily_report.py</code> currently matches <em>inside each calendar day only</em>, so overnight holds look like zero P&L that day.</p>
</main></body></html>
"""

DEPLOY = """
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deploy this bot</title>
<style>
  body { margin:0; font-family: ui-sans-serif, system-ui, sans-serif; background:#0b1220; color:#e8eefc; }
  main { max-width: 900px; margin: 0 auto; padding: 24px; }
  a { color:#8cb4ff; }
  ol { line-height: 1.6; }
  code { background:#1b2438; padding: 1px 6px; border-radius: 6px; }
</style></head>
<body><main>
<a href="/">← Dashboard</a>
<h1>Roadmap: free host + your domain</h1>
<p>Split the product in two. This Flask app is the public site. <code>bot.py</code> is a long-running worker that must stay awake through the NSE session.</p>
<ol>
  <li><b>Put secrets in the host, never in git.</b> Copy <code>.env.example</code> to the platform env vars: Angel key, client id, MPIN, TOTP secret, optional Telegram.</li>
  <li><b>Dashboard (this page) on Render Free.</b> New Web Service → this repo → build <code>pip install -r requirements.txt</code> → start <code>gunicorn dashboard:app --bind 0.0.0.0:$PORT</code>. You get <code>https://something.onrender.com</code>. Free tier sleeps after idle; ping it or use a cron hit to <code>/health</code>.</li>
  <li><b>Custom domain for free.</b> Buy a cheap name (or use a Namecheap/Freenom leftover). In Cloudflare (free), add the domain, then in Render: Settings → Custom Domain → add <code>bot.yourdomain.com</code>. Cloudflare DNS: CNAME to the Render hostname, proxy on. SSL is automatic.</li>
  <li><b>Worker for the actual bot.</b> Render free web processes get killed; a 6.5h loop needs an Always Free VM. Best free option: Oracle Cloud ARM Ampere (Always Free) — install Python, clone, systemd: <code>python bot.py</code> 09:15–15:30 IST. Alternative: a cheap Railway/Fly.io VM if Oracle is blocked.</li>
  <li><b>Do not turn PAPER_TRADING off</b> until paper results and token map are verified. Live orders are real money.</li>
  <li><b>Health.</b> <code>/health</code> should return 200 for Render. Keep <code>open_positions.json</code> on a persistent disk (Render disk or the Oracle VM), not ephemeral web storage.</li>
</ol>
<p>Full copy-paste commands live in <code>DEPLOY.md</code> in the repo.</p>
</main></body></html>
"""


@app.route("/")
def home():
    return render_template_string(
        PAGE,
        clock=market_clock(),
        stats=paper_stats(),
        demo=demo_scan_payload(),
        max_pos=config.MAX_OPEN_POSITIONS,
    )


@app.route("/how-it-works")
def how():
    return HOWTO


@app.route("/deploy")
def deploy():
    return DEPLOY


@app.route("/health")
def health():
    return jsonify({"ok": True, **market_clock(), "paper": config.PAPER_TRADING})


@app.route("/api/stats")
def api_stats():
    return jsonify({"clock": market_clock(), "stats": paper_stats()})


@app.route("/api/demo")
def api_demo():
    return jsonify(demo_scan_payload())


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    # Touch demo printer so `python dashboard.py` still shows CLI output once
    if os.environ.get("PRINT_DEMO") == "1":
        run_demo()
    app.run(host="0.0.0.0", port=port)
