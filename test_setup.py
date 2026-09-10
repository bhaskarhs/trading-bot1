import os
from dotenv import load_dotenv

load_dotenv()

print("Testing all credentials...\n")

# Test 1 - Check .env loads correctly
api_key = os.getenv("ANGEL_API_KEY")
client_id = os.getenv("ANGEL_CLIENT_ID")
totp_secret = os.getenv("ANGEL_TOTP_SECRET")
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
# telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
# telegram_chat = os.getenv("TELEGRAM_CHAT_ID")

print("1. ENV file check:")
print(f"   Angel API Key     : {'OK' if api_key else 'MISSING'}")
print(f"   Client ID         : {'OK' if client_id else 'MISSING'}")
print(f"   TOTP Secret       : {'OK' if totp_secret else 'MISSING'}")
print(f"   Anthropic Key     : {'OK' if anthropic_key else 'MISSING'}")
# print(f"   Telegram Token    : {'OK' if telegram_token else 'MISSING'}")
# print(f"   Telegram Chat ID  : {'OK' if telegram_chat else 'MISSING'}")

# Test 2 - Angel One login
print("\n2. Angel One login test:")
try:
    import pyotp
    from SmartApi import SmartConnect
    totp = pyotp.TOTP(totp_secret).now()
    angel = SmartConnect(api_key=api_key)
    data = angel.generateSession(client_id, os.getenv("ANGEL_MPIN"), totp)
    if data['status']:
        print("   Angel One login   : OK")
    else:
        print("   Angel One login   : FAILED -", data['message'])
except Exception as e:
    print(f"   Angel One login   : FAILED - {e}")

# Test 3 - Anthropic API (optional, unused by the bot loop)
print("\n3. Claude API test:")
if not anthropic_key:
    print("   Claude API        : SKIPPED (not required)")
else:
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=anthropic_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=20,
            messages=[{"role": "user", "content": "Say OK"}]
        )
        print(f"   Claude API        : OK - {msg.content[0].text.strip()}")
    except Exception as e:
        print(f"   Claude API        : FAILED - {e}")

# Test 4 - Telegram
# print("\n4. Telegram bot test:")
# try:
#     import requests
#     url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
#     res = requests.post(url, json={
#         "chat_id": telegram_chat,
#         "text": "Trading bot setup successful!"
#     })
#     if res.json().get("ok"):
#         print("   Telegram          : OK - check your phone!")
#     else:
#         print("   Telegram          : FAILED -", res.json())
# except Exception as e:
#     print(f"   Telegram          : FAILED - {e}")

print("\nSetup complete!")