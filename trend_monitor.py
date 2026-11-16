import os
import urllib.request
import re
from html.parser import HTMLParser

SITES = {
    "TikTok Turkey": "https://endless.app/radar/tiktok/turkey",
    "CapCut Turkey": "https://www.capcut.com/explore/turkish-templates"
}

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {"href": dict(attrs).get("href", ""), "text": ""}

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None

def main():
    report = ["🔎 MƏNBƏ YOXLAMASI"]

    for name, url in SITES.items():
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                html = response.read().decode("utf-8", errors="replace")
                status = response.status

            parser = LinkParser()
            parser.feed(html)

            report.append(
                f"\n{name}\n"
                f"HTTP status: {status}\n"
                f"Səhifə ölçüsü: {len(html)} simvol\n"
                f"Tapılan linklər: {len(parser.links)}"
            )

            for link in parser.links[:5]:
                report.append(
                    f"- {link['text'].strip()[:70]} | {link['href'][:120]}"
                )

        except Exception as error:
            report.append(f"\n{name}: XƏTA: {str(error)[:200]}")

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    import json

    data = json.dumps({
        "chat_id": chat_id,
        "text": "\n".join(report)
    }).encode()

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.read().decode())

if __name__ == "__main__":
    main()
    
