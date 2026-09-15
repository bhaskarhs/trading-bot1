from datetime import datetime
import json

import bot
from daily_report import analyze_day, format_alert, run_reports
from market_hours import IST


TRADES = [
    {"timestamp": "2026-09-14 10:00:00", "action": "BUY", "symbol": "INFY-EQ",
     "stock": "Infosys", "price": 100, "quantity": 2, "value": 200},
    {"timestamp": "2026-09-15 11:00:00", "action": "SELL", "symbol": "INFY-EQ",
     "stock": "Infosys", "price": 110, "quantity": 2, "value": 220},
]


def test_run_reports_writes_day_files_and_log(tmp_path):
    results = run_reports(trades=TRADES, reports_dir=str(tmp_path), quiet=True)
    assert [r["date"] for r in results] == ["2026-09-14", "2026-09-15"]
    assert (tmp_path / "2026-09-14.json").exists()
    assert (tmp_path / "2026-09-14.txt").exists()
    assert (tmp_path / "2026-09-15.txt").exists()
    log = json.loads((tmp_path / "daily_log.json").read_text())
    assert [e["date"] for e in log] == ["2026-09-14", "2026-09-15"]
    assert log[0]["realised_pnl"] == 0
    assert log[1]["realised_pnl"] == 20.0
    assert log[1]["matched_trades"] == 1


def test_only_date_writes_empty_session_track(tmp_path):
    results = run_reports(
        only_date="2026-09-16",
        trades=[],
        reports_dir=str(tmp_path),
        quiet=True,
    )
    assert results[0]["date"] == "2026-09-16"
    assert results[0]["total_trades"] == 0
    log = json.loads((tmp_path / "daily_log.json").read_text())
    assert len(log) == 1
    assert log[0]["date"] == "2026-09-16"
    assert log[0]["total_trades"] == 0
    assert log[0]["realised_pnl"] == 0


def test_same_date_replaces_log_row(tmp_path):
    run_reports(only_date="2026-09-15", trades=TRADES,
                reports_dir=str(tmp_path), quiet=True)
    extra = TRADES + [
        {"timestamp": "2026-09-15 14:00:00", "action": "BUY", "symbol": "TCS-EQ",
         "stock": "TCS", "price": 50, "quantity": 1, "value": 50},
    ]
    run_reports(only_date="2026-09-15", trades=extra,
                reports_dir=str(tmp_path), quiet=True)
    log = json.loads((tmp_path / "daily_log.json").read_text())
    assert len(log) == 1
    assert log[0]["total_trades"] == 2  # sell + new buy on the 15th


def test_format_alert_includes_date_and_pnl():
    result = analyze_day("2026-09-15", TRADES)
    text = format_alert(result)
    assert "2026-09-15" in text
    assert "+₹20.0" in text or "+₹20" in text


def test_eod_report_once_per_day(tmp_path, monkeypatch):
    calls = []

    def fake_run_reports(only_date=None, quiet=True, **kwargs):
        calls.append(only_date)
        return [{"date": only_date, "total_trades": 0, "matched_trades": 0,
                 "realised_pnl": 0, "win_rate": 0, "open_positions": 0,
                 "total_buys": 0, "total_sells": 0, "profitable": 0,
                 "losing": 0, "open_exposure": 0}]

    monkeypatch.setattr(bot, "run_reports", fake_run_reports)
    monkeypatch.setattr(bot, "send_alert", lambda msg: None)
    bot._eod_report_day = None
    now = IST.localize(datetime(2026, 9, 15, 15, 20, 0))
    assert bot.run_eod_daily_report(now)["date"] == "2026-09-15"
    assert bot.run_eod_daily_report(now) is None
    next_day = IST.localize(datetime(2026, 9, 16, 15, 20, 0))
    assert bot.run_eod_daily_report(next_day)["date"] == "2026-09-16"
    assert calls == ["2026-09-15", "2026-09-16"]
