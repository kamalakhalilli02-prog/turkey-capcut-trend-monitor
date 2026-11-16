import os
import urllib.request
import urllib.parse

token = os.environ["TELEGRAM_BOT_TOKEN"]
chat_id = os.environ["TELEGRAM_CHAT_ID"]

message = (
    "🔎 CAPCUT TESTİ TAMAMLANDI\n\n"
    f"Tapılan şablon sayı: {len(trends)}\n\n"
    "Nəticə GitHub Actions jurnalında saxlanılır."
)

url = f"https://api.telegram.org/bot{token}/sendMessage"

data = urllib.parse.urlencode({
    "chat_id": chat_id,
    "text": message
}).encode()

req = urllib.request.Request(url, data=data)

with urllib.request.urlopen(req) as response:
    print("Telegram mesajı göndərildi:", response.status)
