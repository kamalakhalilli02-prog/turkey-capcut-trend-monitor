
import os
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone, date
from html.parser import HTMLParser
from urllib.parse import urljoin

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT": "https://www.capcut.com/tr-tr/explore/turkish-templates"
}

HISTORY_FILE = "capcut_history.json"
AZ_TZ = timezone(timedelta(hours=4))
DAYS_LIMIT = 30
MAX_TEMPLATES_TO_CHECK = 40


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
            "utf-8", errors="replace"
        )


def extract_number(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)

        if match:
            return match.group(1).strip()

    return "Tapılmadı"


def parse_usage(value):
    if not value or value == "Tapılmadı":
        return 0

    value = value.replace(",", ".").strip().upper()
    multiplier = 1

    if value.endswith("K"):
        multiplier = 1_000
        value = value[:-1]

    elif value.endswith("M"):
        multiplier = 1_000_000
        value = value[:-1]

    elif value.endswith("B"):
        multiplier = 1_000_000_000
        value = value[:-1]

    try:
        return int(float(value) * multiplier)

    except ValueError:
        return 0


def find_created_date(page_text, html):
    # Əvvəl brauzerdə görünən mətnə baxırıq.
    # Tarixin yanında istifadə sayı varsa, onu üstün tuturuq.

    date_patterns = [
        r"(\d{4}-\d{2}-\d{2})"
        r"(?=.{0,120}?\b(?:uses|kullanım)\b)",

        r"(\d{2}[./-]\d{2}[./-]\d{4})"
        r"(?=.{0,120}?\b(?:uses|kullanım)\b)"
    ]

    for source in [page_text, html]:
        for pattern in date_patterns:
            match = re.search(
                pattern,
                source,
                re.I | re.S
            )

            if match:
                value = match.group(1)

                for fmt in [
                    "%Y-%m-%d",
                    "%d.%m.%Y",
                    "%d/%m/%Y",
                    "%d-%m-%Y"
                ]:
                    try:
                        return datetime.strptime(
                            value, fmt
                        ).date()

                    except ValueError:
                        continue

    # Ehtiyat variant: səhifədə tarix ayrıca göstərilirsə
    for source in [page_text, html]:
        match = re.search(
            r"\b(20\d{2}-\d{2}-\d{2})\b",
            source
        )

        if match:
            try:
                return datetime.strptime(
                    match.group(1),
                    "%Y-%m-%d"
                ).date()

            except ValueError:
                pass

    return None


def get_template_details(url):
    html = get_page(url)

    parser = Parser()
    parser.feed(html)

    page_text = " ".join(parser.text)
    title = " ".join(parser.h1).strip()

    if not title:
        title = "Şablon adı tapılmadı"

    # Həm görünən mətn, həm HTML yoxlanılır.
    combined_text = page_text + "\n" + html

    created_at = find_created_date(
        page_text,
        html
    )

    uses = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+uses",
        r"([\d.,]+\s*[KMB]?)\s+kullanım"
    ], combined_text)

    likes = extract_number([
        r"([\d.,]+\s*[KMB]?)\s+likes",
        r"([\d.,]+\s*[KMB]?)\s+beğeni"
    ], combined_text)

    return title, uses, likes, created_at


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    except (json.JSONDecodeError, OSError):
        return {}


def save_history(history):
    with open(
        HISTORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            history,
            file,
            ensure_ascii=False,
            indent=2
        )


def get_template_id(url):
    match = re.search(
        r"/(\d+)(?:[/?#]|$)",
        url
    )

    if match:
        return match.group(1)

    return url


def update_template_history(history, template_id, uses):
    today = datetime.now(AZ_TZ).date()
    current_usage = parse_usage(uses)

    if current_usage <= 0:
        return None

    item = history.get(
        template_id,
        {"snapshots": []}
    )

    snapshots = item.get("snapshots", [])

    previous = None

    for snapshot in reversed(snapshots):
        if snapshot.get("date") != today.isoformat():
            previous = snapshot
            break

    growth = None
    daily_growth = None

    if previous:
        old_usage = previous.get("uses", 0)
        old_date = date.fromisoformat(
            previous["date"]
        )

        days = max(
            (today - old_date).days,
            1
        )

        growth = current_usage - old_usage
        daily_growth = round(growth / days)

    today_snapshot = {
        "date": today.isoformat(),
        "uses": current_usage
    }

    if (
        snapshots
        and snapshots[-1].get("date") == today.isoformat()
    ):
        snapshots[-1] = today_snapshot

    else:
        snapshots.append(today_snapshot)

    item["snapshots"] = snapshots[-60:]
    history[template_id] = item

    return {
        "growth": growth,
        "daily_growth": daily_growth
    }


def get_capcut_trends(report):
    today = datetime.now(AZ_TZ).date()
    cutoff = today - timedelta(days=DAYS_LIMIT)

    history = load_history()

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
        link = urljoin(
            capcut_url,
            item["url"]
        )

        name = " ".join(
            item["text"].split()
        )

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
        f"\n🔍 Tapılan şablon linkləri: "
        f"{len(templates)}"
    )

    recent_templates = []
    checked = 0
    no_date = 0
    old_templates = 0

    for item in templates[:MAX_TEMPLATES_TO_CHECK]:
        try:
            title, uses, likes, created_at = (
                get_template_details(item["link"])
            )

            checked += 1

            if created_at is None:
                no_date += 1
                continue

            if not (cutoff <= created_at <= today):
                old_templates += 1
                continue

            template_id = get_template_id(
                item["link"]
            )

            growth_info = update_template_history(
                history,
                template_id,
                uses
            )

            recent_templates.append({
                "title": (
                    title
                    if title != "Şablon adı tapılmadı"
                    else item["name"]
                ),
                "uses": uses,
                "usage_number": parse_usage(uses),
                "likes": likes,
                "created_at": created_at,
                "link": item["link"],
                "growth": growth_info
            })

        except Exception as error:
            print(
                "Şablon oxunmadı:",
                item["link"],
                str(error)[:150]
            )

    save_history(history)

    # Artım məlum olanlar əvvəl, sonra istifadə sayı.
    recent_templates.sort(
        key=lambda x: (
            (
                x["growth"] is not None
                and x["growth"]["daily_growth"] is not None
            ),
            (
                x["growth"]["daily_growth"]
                if x["growth"]
                and x["growth"]["daily_growth"] is not None
                else x["usage_number"]
            ),
            x["usage_number"]
        ),
        reverse=True
    )

    report.append(
        f"\n🔎 Yoxlanılan şablon: {checked}"
    )

    report.append(
        f"📅 Tarixi tapılmayan: {no_date}"
    )

    report.append(
        f"🕒 30 gündən köhnə: {old_templates}"
    )

    report.append(
        f"\n🆕 Son 30 gündə yayımlananlar: "
        f"{len(recent_templates)}"
    )

    for i, item in enumerate(
        recent_templates[:10],
        1
    ):
        growth = item["growth"]

        if (
            growth
            and growth["daily_growth"] is not None
        ):
            growth_text = (
                f"Gündəlik artım: "
                f"{growth['daily_growth']:+,} istifadə/gün"
            )

        else:
            growth_text = (
                "Gündəlik artım: İlk ölçmə, "
                "müqayisə üçün növbəti gün gözlənilir"
            )

        report.append(
            f"\n{i}. {item['title'][:100]}\n"
            f"Yayımlanma: {item['created_at']}\n"
            f"İstifadə: {item['uses']}\n"
            f"Bəyənmə: {item['likes']}\n"
            f"{growth_text}\n"
            f"{item['link']}"
        )

    if not recent_templates:
        report.append(
            "\nSon 30 gündə yayımlanması "
            "təsdiqlənən şablon tapılmadı."
        )

    report.append(
        "\nQeyd: Tarixi təsdiqlənməyən şablonlar "
        "yeni trend siyahısına daxil edilmir."
    )

    report.append(
        "İlk ölçmədə gündəlik artım bilinmir. "
        "Ən azı iki fərqli gündə ölçmə lazımdır."
    )


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
        get_capcut_trends(report)

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
    
