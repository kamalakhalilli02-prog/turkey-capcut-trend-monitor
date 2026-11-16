import os
import re
import json
import urllib.request
import urllib.parse
from html import unescape
from html.parser import HTMLParser

ENDLESS_URL = "https://endless.app/radar/tiktok/turkey"
CAPCUT_URL = "https://www.capcut.com/tr-tr/explore/capcut-all-templates-trending/7497638301391407120"

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

def get_page(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")

class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.current = None
        self.html = html

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            self.current = {
                "href": attrs.get("href", ""),
                "text": ""
            }

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None

def get_count(text, unit):
    pattern = r"([\d.,]+[KMBT]?)\s*" + unit
    match = re.search(pattern, text, re.I)
    return match.group(1) + " " + unit if match else "Göstərilməyib"

def collect_tiktok():
    html = get_page(ENDLESS_URL)
    parser = PageParser(html)

    sounds = []
    hashtags = []

    for item in parser.links:
        url = item["href"]
        name = unescape(item["text"]).strip()

        if not name or name.isdigit():
            continue

        if "tiktok.com/music/" in url and len(sounds) < 10:
            sounds.append((name, url))

        if "tiktok.com/tag/" in url and len(hashtags) < 10:
            hashtags.append((name, url))

    return sounds, hashtags

def collect_capcut():
    html = get_page(CAPCUT_URL)
    parser = PageParser(html)

    templates = []

    for item in parser.links:
        url = item["href"]
        name = unescape(item["text"]).strip()

        if "capcut.com" not in url:
            continue

        if "template-detail" not in url:
            continue

        if not name or name.isdigit():
            continue

        templates.append((name, url))

        if len(templates) == 10:
            break

    return templates

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": "true"
    }).encode()

    req = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(req, timeout=30) as response:
        result = json.loads(response.read())

    if not result.get("ok"):
        raise RuntimeError("Telegram mesajı göndərilmədi.")

def make_section(title, items):
    lines = [title]

    if not items:
        lines.append("Bu gün məlumat əldə edilmədi.")
        return "\n".join(lines)

    for index, item in enumerate(items, 1):
        name, url = item
        lines.append(f"{index}. {name}\n{url}")

    return "\n".join(lines)

def main():
    report = ["🇹🇷 TURKEY TREND MONITOR", "Gündəlik hesabat", ""]

    try:
        sounds, hashtags = collect_tiktok()
        report.append(make_section("🎵 TIKTOK SƏSLƏRİ — TOP 10", sounds))
        report.append("")
        report.append(make_section("#️⃣ TIKTOK HASHTAG-LARI — TOP 10", hashtags))
    except Exception as error:
        report.append("TikTok məlumatları əldə edilmədi.")
        report.append(str(error)[:250])

    report.append("")

    try:
        templates = collect_capcut()
        report.append(make_section("🎬 CAPCUT ŞABLONLARI — TOP 10", templates))
        report.append("")
        report.append("Qeyd: CapCut siyahısı Türkiyə regionuna aid olduğu təsdiqlənməyən açıq kolleksiyadır.")
    except Exception as error:
        report.append("CapCut məlumatları əldə edilmədi.")
        report.append(str(error)[:250])

    report.append("")
    report.append("Mənbələr:")
    report.append(ENDLESS_URL)
    report.append(CAPCUT_URL)

    send_telegram("\n".join(report))

if __name__ == "__main__":
    main()
      
