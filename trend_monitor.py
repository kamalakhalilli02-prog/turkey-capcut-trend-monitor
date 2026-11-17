
import os
import json
import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT": "https://www.capcut.com/tr-tr/explore/turkish-templates"
}


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.text = []
        self.h1 = []
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current_link = {
                "url": dict(attrs).get("href", ""),
                "text": ""
            }
        if tag == "h1":
            self.in_h1 = True

    def handle_data(self, data):
        self.text.append(data)

        if self.current_link is not None:
            self.current_link["text"] += data

        if self.in_h1:
            self.h1.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            self.links.append(self.current_link)
            self.current_link = None

        if tag == "h1":
            self.in_h1 = False


def get_page(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0"}
    )

    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode(
            "utf-8", errors="replace"
        )


def extract_number(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1).strip()

    return "Tapılmadı"


def get_template_details(url):
    html = get_page(url)

    parser = Parser()
    parser.feed(html)

    page_text = " ".join(parser.text)

    title = " ".join(parser.h1).strip()

    if not title:
        title = "Şablon adı tapılmadı"

    uses = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+uses",
        r"([\d.,]+\s*[KMB]?)\s+kullanım"
    ], page_text)

    likes = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+likes",
        r"([\d.,]+\s*[KMB]?)\s+beğeni"
    ], page_text)

    return title, uses, likes


def main():
    report = ["🔎 TÜRKİYƏ TREND HESABATI"]

    # TIKTOK / ENDLESS
    try:
        html = get_page(SITES["ENDLESS"])

        parser = Parser()
        parser.feed(html)

        report.append(
            f"\n📌 ENDLESS: {len(html)} simvol"
        )

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

            report.append(
                f"\n{title}: {len(found)} link"
            )

            for item in found[:10]:
                name = item["text"].strip() or "Ad göstərilmir"

                report.append(
                    f"• {name[:80]}\n"
                    f"{urljoin(SITES['ENDLESS'], item['url'])}"
                )

        for phrase in [
            "Trending sounds and songs this week",
            "Trending hashtags this week"
        ]:
            report.append(
                f"{phrase}: "
                f"{'VAR' if phrase in html else 'TAPILMADI'}"
            )

    except Exception as error:
        report.append(
            f"\n❌ ENDLESS xətası: {str(error)[:200]}"
        )

    # CAPCUT
    try:
        capcut_url = SITES["CAPCUT"]
        html = get_page(capcut_url)

        parser = Parser()
        parser.feed(html)

        report.append(
            f"\n\n📌 CAPCUT: {len(html)} simvol"
        )

        templates = []
        seen = set()

        for item in parser.links:
            link = urljoin(capcut_url, item["url"])
            name = " ".join(item["text"].split())

            if (
                "/template-detail/" in link
                and link not in seen
            ):
                seen.add(link)

                templates.append({
                    "name": name,
                    "link": link
                })

        report.append(
            f"\n🎬 Konkret şablonlar: {len(templates)}"
        )

        for i, item in enumerate(templates[:10], 1):
            try:
                title, uses, likes = get_template_details(
                    item["link"]
                )

                if title == "Şablon adı tapılmadı":
                    title = item["name"] or title

                report.append(
                    f"\n{i}. {title[:100]}\n"
                    f"İstifadə: {uses}\n"
                    f"Bəyənmə: {likes}\n"
                    f"{item['link']}"
                )

            except Exception as error:
                report.append(
                    f"\n{i}. {item['name'] or 'Şablon'}\n"
                    f"Məlumat oxunmadı: {str(error)[:100]}\n"
                    f"{item['link']}"
                )

        if not templates:
            report.append(
                "Konkret şablon linkləri tapılmadı."
            )

        report.append(
            "\nQeyd: İstifadə sayı CapCut səhifəsində "
            "göstərilən ümumi göstəricidir."
        )

    except Exception as error:
        report.append(
            f"\n❌ CAPCUT xətası: {str(error)[:200]}"
        )

    # TELEGRAM
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    message = "\n".join(report)

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
            headers={
                "Content-Type": "application/json"
            }
        )

        with urllib.request.urlopen(
            request, timeout=30
        ) as response:
            print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
