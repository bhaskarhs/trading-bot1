import requests
import config


def send_alert(message: str):
    """
    Sends a message to your Telegram bot.
    Silently skips if Telegram is not configured.
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return

    try:
        url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id":    config.TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception as e:
        print(f"Telegram alert failed: {e}")
