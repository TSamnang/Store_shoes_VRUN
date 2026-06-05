import os
import sys

# Try to load environment variables using python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ python-dotenv is installed and loaded .env")
except ImportError:
    print("⚠️ python-dotenv is NOT installed in the active environment.")
    print("   Please run: pip install python-dotenv")
    print("   (Or activate your virtual environment first)\n")

# Fetch environment variables
token = os.environ.get('TELEGRAM_BOT_TOKEN')
chat_id = os.environ.get('TELEGRAM_CHAT_ID')

print(f"TELEGRAM_BOT_TOKEN: {token[:6]}... (length: {len(token)})" if token else "TELEGRAM_BOT_TOKEN: Not Set (None)")
print(f"TELEGRAM_CHAT_ID: {chat_id}" if chat_id else "TELEGRAM_CHAT_ID: Not Set (None)\n")

if not token or not chat_id:
    print("❌ Configuration missing! Please fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your .env file.")
    sys.exit(1)

print("Running test notification sending to Telegram...")

# Message payload
message = (
    "<b>🧪 VRUN Shoes Test Notification</b>\n\n"
    "If you see this message, your Telegram Bot and Chat ID are configured correctly! ✅"
)

import urllib.request
import urllib.parse
import json

url = f"https://api.telegram.org/bot{token}/sendMessage"
payload = {
    'chat_id': chat_id,
    'text': message,
    'parse_mode': 'HTML'
}

try:
    data = urllib.parse.urlencode(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, method='POST')
    with urllib.request.urlopen(req, timeout=10) as response:
        res_body = response.read().decode('utf-8')
        res_json = json.loads(res_body)
        if res_json.get('ok'):
            print("🎉 Success! The test message was successfully sent to your Telegram.")
        else:
            print(f"❌ Telegram API returned an error: {res_body}")
except Exception as e:
    print(f"❌ Error occurred while sending message: {e}")
