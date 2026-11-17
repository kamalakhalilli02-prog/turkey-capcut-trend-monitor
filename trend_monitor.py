
import os
import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT": "https://www.capcut.com/tr-tr/template"
}

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            item = {
                "url": dict(attrs).get("href", ""),
                "text": ""
            }
            self.active.append(item)

    def handle_data(self, data):
        for item in self.active:
            item["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.active:
            item = self.active.pop()
            self.links.append(item)


def get_page(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def main():
    report = ["🔎 TÜRKİYƏ TREND HESABATI"]

    for name, url in SITES.items():
        try:
            html = get_page(url)

            parser = Parser()
            parser.feed(html)

            report.append(f"\n📌 {name}: {len(html)} simvol")

            if name == "ENDLESS":
                groups = {
                    "🎵 TikTok musiqiləri": "tiktok.com/music/",
                    "🏷 TikTok hashtagları": "tiktok.com/tag/"
                }

                for title, marker in groups.items():
                    found = []
                    seen = set()

                    for item in parser.links:
                        link = item["url"]
                        if marker in link and link not in seen:
                            seen.add(link)
                            found.append(item)

                    report.append(f"\n{title}: {len(found)} link")

                    for item in found[:10]:
                        report.append(
                            f"• {item['text'].strip()[:80] or 'Ad göstərilmir'}\n"
                            f"{urljoin(url, item['url'])}"
                        )

                for phrase in [
                    "Trending sounds and songs this week",
                    "Trending hashtags this week"
                ]:
                    report.append(
                        f"{phrase}: {'VAR' if phrase in html else 'TAPILMADI'}"
                    )

            else:
                found = []
                seen = set()

                for item in parser.links:
                    link = urljoin(url, item["url"])
                    text = " ".join(item["text"].split())

                    if (
                        "/template/" in link
                        and link not in seen
                        and text
                        and len(text) > 2
                    ):
                        seen.add(link)
                        found.append({
                            "name": text,
                            "link": link
                        })

                report.append(
                    f"\n🎬 CapCut şablon linkləri: {len(found)}"
                )

                for i, item in enumerate(found[:20], 1):
                    report.append(
                        f"\n{i}. {item['name'][:100]}\n{item['link']}"
                    )

                report.append(
                    "\nQeyd: Bunlar şablon səhifələridir; "
                    "hamısının trend olduğu təsdiqlənməyib."
                )

        except Exception as error:
            report.append(
                f"\n❌ {name} xətası: {str(error)[:250]}"
            )

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    message = "\n".join(report)

    # Telegram mesaj limitinə uyğun hissələrə bölürük.
    chunks = [
        message[i:i + 3500]
        for i in range(0, len(message), 3500)
    ]

    for chunk in chunks:
        data = json.dumps({
            "chat_id": chat_id,
            "text": chunk
        }).encode("utf-8")

        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            print(response.read().decode("utf-8"))

if __name__ == "__main__":
    main()
