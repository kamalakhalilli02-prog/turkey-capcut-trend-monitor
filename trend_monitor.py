
import os
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT": "https://www.capcut.com/tr-tr/explore/turkish-templates"
}

# Sənin göndərdiyin test şablonu
TEST_TEMPLATE = (
    "https://www.capcut.com/template-detail/"
    "erhanlyrics-capcutturkiye/7546996130886847797"
)

MAX_TEMPLATES_TO_CHECK = 5


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.text = []
        self.h1 = []
        self.in_h1 = False
        self.scripts = []
        self.in_script = False
        self.current_script = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            self.current_link = {
                "url": attrs.get("href", ""),
                "text": ""
            }

        if tag == "h1":
            self.in_h1 = True

        if tag == "script":
            self.in_script = True
            self.current_script = []

            self.scripts.append({
                "id": attrs.get("id", ""),
                "type": attrs.get("type", ""),
                "content": ""
            })

    def handle_data(self, data):
        self.text.append(data)

        if self.current_link is not None:
            self.current_link["text"] += data

        if self.in_h1:
            self.h1.append(data)

        if self.in_script and self.scripts:
            self.scripts[-1]["content"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            self.links.append(self.current_link)
            self.current_link = None

        if tag == "h1":
            self.in_h1 = False

        if tag == "script":
            self.in_script = False


def get_page(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        }
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def extract_number(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1).strip()

    return "Tapılmadı"


def inspect_template(url):
    html = get_page(url)

    parser = Parser()
    parser.feed(html)

    page_text = " ".join(parser.text)
    title = " ".join(parser.h1).strip()

    report = []

    report.append(
        f"\n🔗 {url}"
    )

    report.append(
        f"HTML ölçüsü: {len(html)} simvol"
    )

    report.append(
        f"Başlıq: {title or 'Tapılmadı'}"
    )

    # CapCut metadata markerləri
    for marker in [
        "MODERN_ROUTER_DATA",
        "RENDER_DATA",
        "createdAt",
        "createTime",
        "create_time",
        "publishTime",
        "publish_time"
    ]:
        report.append(
            f"{marker}: "
            f"{'VAR' if marker.lower() in html.lower() else 'YOX'}"
        )

    # Script məlumatları
    report.append(
        f"Script sayı: {len(parser.scripts)}"
    )

    for script in parser.scripts:
        script_id = script["id"]
        script_type = script["type"]
        content = script["content"]

        if (
            "RENDER_DATA" in script_id
            or "MODERN_ROUTER_DATA" in script_id
            or "application/json" in script_type
        ):
            report.append(
                f"Script ID: {script_id or 'Adsız'}"
            )

            report.append(
                f"Script ölçüsü: {len(content)}"
            )

    # Tarix formatlarını axtar
    date_patterns = [
        r"\b20\d{2}-\d{2}-\d{2}\b",
        r"\b\d{2}[./]\d{2}[./]20\d{2}\b",
        r"\b\d{2}-\d{2}-20\d{2}\b"
    ]

    found_dates = []

    for pattern in date_patterns:
        matches = re.findall(
            pattern,
            html
        )

        for value in matches:
            if value not in found_dates:
                found_dates.append(value)

    report.append(
        "\n📅 TAPILAN TARİXLƏR:"
    )

    if found_dates:
        for value in found_dates[:15]:
            report.append(f"• {value}")
    else:
        report.append("Heç bir tarix tapılmadı.")

    # Tarix sahələrinin yanında olan məlumatlar
    report.append(
        "\n🧩 TARİX METADATA SAHƏLƏRİ:"
    )

    field_patterns = [
        r'["\']?(createdAt|createTime|create_time)["\']?\s*[:=]\s*["\']?([^,"\'\s}]+)',
        r'["\']?(publishTime|publish_time)["\']?\s*[:=]\s*["\']?([^,"\'\s}]+)',
        r'["\']?(datePublished|uploadDate)["\']?\s*[:=]\s*["\']?([^,"\'\s}]+)'
    ]

    field_found = False

    for pattern in field_patterns:
        matches = re.findall(
            pattern,
            html,
            re.I
        )

        for field, value in matches[:5]:
            field_found = True

            report.append(
                f"{field}: {value[:80]}"
            )

    if not field_found:
        report.append(
            "Tarix sahəsi tapılmadı."
        )

    # Unix timestamp ehtimalı
    report.append(
        "\n⏱ TIMESTAMP MƏLUMATLARI:"
    )

    timestamp_patterns = [
        r'["\']?(createTime|create_time|createdAt)["\']?\s*[:=]\s*["\']?(\d{10,13})',
        r'["\']?(publishTime|publish_time)["\']?\s*[:=]\s*["\']?(\d{10,13})'
    ]

    timestamp_found = False

    for pattern in timestamp_patterns:
        matches = re.findall(
            pattern,
            html,
            re.I
        )

        for field, value in matches[:5]:
            try:
                timestamp = int(value)

                if len(value) == 13:
                    timestamp = timestamp / 1000

                converted = datetime.fromtimestamp(
                    timestamp,
                    timezone.utc
                )

                timestamp_found = True

                report.append(
                    f"{field}: "
                    f"{converted.strftime('%Y-%m-%d %H:%M UTC')}"
                )

            except (ValueError, OverflowError, OSError):
                pass

    if not timestamp_found:
        report.append(
            "Timestamp tapılmadı."
        )

    # İstifadə və bəyənmə göstəriciləri
    uses = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+uses",
        r"([\d.,]+\s*[KMB]?)\s+kullanım"
    ], page_text)

    likes = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+likes",
        r"([\d.,]+\s*[KMB]?)\s+beğeni"
    ], page_text)

    report.append(
        f"\nİstifadə: {uses}"
    )

    report.append(
        f"Bəyənmə: {likes}"
    )

    # Tarix ətrafındakı mətn nümunələri
    report.append(
        "\n🔬 TARİX ƏTRAFINDAKI HTML:"
    )

    for value in found_dates[:3]:
        position = html.find(value)

        if position >= 0:
            start = max(0, position - 180)
            end = min(
                len(html),
                position + 250
            )

            snippet = re.sub(
                r"\s+",
                " ",
                html[start:end]
            )

            report.append(
                snippet[:450]
            )

    return "\n".join(report)


def main():
    report = [
        "🔎 TÜRKİYƏ TREND DİAQNOSTİKASI"
    ]

    # ENDLESS - əvvəlki işləyən hissə
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

                if (
                    marker in link
                    and link not in seen
                ):
                    seen.add(link)
                    found.append(item)

            report.append(
                f"\n{title}: {len(found)} link"
            )

            for item in found[:10]:
                name = (
                    item["text"].strip()
                    or "Ad göstərilmir"
                )

                report.append(
                    f"• {name[:80]}\n"
                    f"{urljoin(SITES['ENDLESS'], item['url'])}"
                )

    except Exception as error:
        report.append(
            f"\n❌ ENDLESS xətası: {str(error)[:200]}"
        )

    # CAPCUT - test
    try:
        capcut_html = get_page(SITES["CAPCUT"])

        capcut_parser = Parser()
        capcut_parser.feed(capcut_html)

        templates = []
        seen = set()

        for item in capcut_parser.links:
            link = urljoin(
                SITES["CAPCUT"],
                item["url"]
            )

            if (
                "/template-detail/" in link
                and link not in seen
            ):
                seen.add(link)
                templates.append(link)

        report.append(
            f"\n\n📌 CAPCUT"
        )

        report.append(
            f"Tapılan şablon linkləri: {len(templates)}"
        )

        # Əvvəl konkret sənin göndərdiyin linki yoxla
        test_links = [TEST_TEMPLATE]

        # Sonra siyahıdan ilk 4 şablon
        for link in templates:
            if link not in test_links:
                test_links.append(link)

            if len(test_links) >= MAX_TEMPLATES_TO_CHECK:
                break

        for index, link in enumerate(test_links, 1):
            try:
                report.append(
                    f"\n\n========== ŞABLON {index} =========="
                )

                report.append(
                    inspect_template(link)
                )

            except Exception as error:
                report.append(
                    f"\n❌ Şablon xətası: {str(error)[:200]}"
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
            request,
            timeout=30
        ) as response:
            print(
                response.read().decode("utf-8")
            )


if __name__ == "__main__":
    main()
