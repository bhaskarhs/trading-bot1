# Deploy on a free host and a real domain

This repo is two processes:

| Process | What it is | Fits free PaaS? |
|---|---|---|
| `dashboard.py` | HTTP site: P&L, how-it-works, demo RSI scan | Yes — Render / Fly / Railway web |
| `bot.py` | Infinite loop, Angel One, 09:15–15:25 IST | Needs a VM that does not sleep |

Do **not** put Angel MPIN / TOTP in git. Use the host’s secret store.

## Phase 0 — freeze paper mode

1. Keep `PAPER_TRADING = True` in `config.py`.
2. Confirm `python demo.py` and `python -m pytest` pass.
3. Create GitHub repo (this one) and push.

## Phase 1 — public dashboard (Render Free)

1. https://render.com → Sign up with GitHub → **New → Web Service**.
2. Connect `trading-bot1`.
3. Runtime Python. Build: `pip install -r requirements.txt`.
4. Start: `gunicorn dashboard:app --bind 0.0.0.0:$PORT`
5. Instance: **Free**.
6. Deploy. You get `https://<name>.onrender.com`.
7. Open `/`, `/how-it-works`, `/deploy`, `/health`.

Free web services **spin down after ~15 minutes idle**. That is fine for a dashboard. It is **not** fine for `bot.py`.

Optional keep-warm: a free cron (cron-job.org) GET `https://your-domain/health` every 10 minutes.

## Phase 2 — your domain (Cloudflare Free)

1. Register a domain (Cloudflare Registrar, Namecheap, etc.).
2. Add the zone to Cloudflare (free plan).
3. In Render → Settings → **Custom Domains** → `bot.yourdomain.com`.
4. In Cloudflare DNS:

   | Type | Name | Target | Proxy |
   |---|---|---|---|
   | CNAME | bot | `<name>.onrender.com` | Proxied |

5. Wait for SSL (Render + Cloudflare Full / Full strict).
6. Visit `https://bot.yourdomain.com`.

No paid CDN required.

## Phase 3 — the actual bot (Oracle Cloud Always Free)

Render’s free web process will kill a 6-hour loop. Use a tiny always-on VM.

1. Oracle Cloud Free Tier → Ampere A1 (ARM) or AMD micro.
2. Ubuntu image, open egress HTTPS (Angel + Telegram).
3. SSH in:

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
git clone https://github.com/bhaskarhs/trading-bot1.git
cd trading-bot1
python3 -m venv trading_env
source trading_env/bin/activate
pip install -r requirements.txt
nano .env   # paste Angel + Telegram
```

4. systemd so it restarts:

```ini
# /etc/systemd/system/nse-bot.service
[Unit]
Description=NSE paper trading bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/trading-bot1
EnvironmentFile=/home/ubuntu/trading-bot1/.env
ExecStart=/home/ubuntu/trading-bot1/trading_env/bin/python bot.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now nse-bot
journalctl -u nse-bot -f
```

5. Copy `paper_trades.json` / `open_positions.json` off the VM daily, or rsync them to the dashboard host if you want the website to update. Render’s filesystem is ephemeral unless you add a disk.

## Phase 4 — alternatives if Oracle is blocked

- **Fly.io** `fly launch` with `Dockerfile` (below) and `min_machines_running = 1` (may need a card).
- **Railway** hobby / trial credits — one worker + one web.
- **PythonAnywhere** free: cannot run a all-day socket loop reliably; skip.

## Dockerfile (Fly / Railway)

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8080
CMD gunicorn dashboard:app --bind 0.0.0.0:${PORT}
```

Use a second process/image with `CMD python bot.py` for the worker.

## Go-live checklist

- [ ] Dashboard loads on `onrender.com` and on your CNAME
- [ ] `/health` returns `{"ok": true}`
- [ ] VM `bot.py` logs “PAPER TRADING” and Angel login
- [ ] Telegram start alert (optional)
- [ ] After one week of paper, only then consider `PAPER_TRADING = False`
- [ ] Fix duplicate tokens in `config.py` before any live order
