import os
import urllib.parse
import urllib.request


def send(text):
    """Print always; also Telegram if TG_TOKEN and TG_CHAT env vars are set."""
    print(text)
    tok, chat = os.getenv("TG_TOKEN"), os.getenv("TG_CHAT")
    if not (tok and chat):
        return
    try:
        body = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=body, timeout=10)
    except Exception as e:
        print("telegram failed:", e)
