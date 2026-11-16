
import os
import json
import urllib.request
from html.parser import HTMLParser

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT": "https://www.capcut.com/tr-tr/explore/CapCut-yeni-trendler/7512833274387318785"
}

class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.active = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            item = {"url": dict(attrs).get("href", ""), "text": ""}
            self.active.append(item)

    def handle_data(self, data):
        for item in self.active:
            item["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.active:
            item = self.active.pop()
            self.links.append(item)

def main():
    report = ["🔎 TREND LINK TESTİ"]

    for name, url in SITES.items():
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode("utf-8", errors="replace")

            parser = Parser()
            parser.feed(html)

            if name == "ENDLESS":
                groups = {
                    "TikTok music": lambda x: "tiktok.com/music/" in x,
                    "TikTok tag": lambda x: "tiktok.com/tag/" in x
                }
            else:
                groups = {
                    "CapCut template": lambda x: "template" in x.lower()
                }

            report.append(f"\n{name}: {len(html)} simvol")

            for title, check in groups.items():
                found = [x for x in parser.links if check(x["url"])]
                report.append(f"\n{title}: {len(found)} link")

                for item in found[:5]:
                    report.append(
                        f"- {item['text'].strip()[:70]}\n{item['url'][:180]}"
                    )

            if name == "ENDLESS":
                for phrase in [
                    "Trending sounds and songs this week",
                    "Trending hashtags this week"
                ]:
                    report.append(
                        f"{phrase}: {'VAR' if phrase in html else 'TAPILMADI'}"
                    )

        except Exception as error:
            report.append(f"\n{name}: XƏTA: {str(error)[:200]}")

    data = json.dumps({
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": "\n".join(report)
    }).encode()

    request = urllib.request.Request(
        "https://api.telegram.org/bot"
        + os.environ["TELEGRAM_BOT_TOKEN"]
        + "/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.read().decode())

if __name__ == "__main__":
    main()
    
