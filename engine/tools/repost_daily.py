"""One-off: re-send the daily close follow-up in English."""
import os, json, requests
tok, chat = os.environ["TG_CHANNEL_TOKEN"], os.environ["TG_CHANNEL_ID"]
r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", data={"chat_id": chat,
    "text": "3 more questions and your streak are waiting in today's Daily Close. Free, no sign-up.",
    "disable_web_page_preview": "true",
    "reply_markup": json.dumps({"inline_keyboard": [[{"text": "Open today's Daily Close", "url": "https://finrehearse.pages.dev/app/#daily"}]]})}, timeout=30).json()
print("send", r.get("ok"), r.get("description"))
