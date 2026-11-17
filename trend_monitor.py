
import os
import json
import re
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

SITES = {
    "ENDLESS": "https://endless.app/radar/tiktok/turkey",
    "CAPCUT_PAGES": [
        "https://www.capcut.com/tr-tr/explore/turkish-templates",
        "https://www.capcut.com/explore/latest-trending-templates",
        "https://www.capcut.com/explore/new-trending-on-CapCut",
        "https://www.capcut.com/explore/Latest",
        "https://www.capcut.com/template"
    ]
}

HISTORY_FILE = "capcut_history.json"

DAYS_BACK = 30
MAX_DETAILS_TO_CHECK = 35
MAX_NEW_TO_REPORT = 15
MAX_GROWTH_TO_REPORT = 10

AZ_TZ = timezone(timedelta(hours=4))


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.text = []
        self.h1 = []
        self.in_h1 = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            self.current_link = {
                "url": attrs.get("href", ""),
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
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        }
    )

    with urllib.request.urlopen(req, timeout=35) as response:
        return response.read().decode(
            "utf-8",
            errors="replace"
        )


def get_template_id(url):
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1]


def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {
            "reported": [],
            "templates": {}
        }

    try:
        with open(
            HISTORY_FILE,
            "r",
            encoding="utf-8"
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("History formatı düzgün deyil")

        data.setdefault("reported", [])
        data.setdefault("templates", {})

        return data

    except Exception:
        return {
            "reported": [],
            "templates": {}
        }


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


def extract_upload_date(html):
    """
    Əsas tarix sahəsi uploadDate-dir.
    Ümumi createTime sahəsi dərc tarixi kimi istifadə edilmir.
    """

    patterns = [
        r'["\']uploadDate["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']datePublished["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']uploadDate["\']\s*:\s*["\'](20\d{2}-\d{2}-\d{2})'
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.I)

        if not match:
            continue

        value = match.group(1)

        try:
            if value.isdigit():
                timestamp = int(value)

                if len(value) == 13:
                    timestamp = timestamp / 1000

                return datetime.fromtimestamp(
                    timestamp,
                    timezone.utc
                ).astimezone(AZ_TZ)

            return datetime.strptime(
                value,
                "%Y-%m-%d"
            ).replace(tzinfo=AZ_TZ)

        except (ValueError, OverflowError, OSError):
            continue

    return None


def number_to_int(value):
    if not value or value == "Tapılmadı":
        return None

    value = value.upper()
    value = value.replace(" ", "")
    value = value.replace(",", ".")

    multiplier = 1

    if value.endswith("K"):
        multiplier = 1000
        value = value[:-1]

    elif value.endswith("M"):
        multiplier = 1000000
        value = value[:-1]

    elif value.endswith("B"):
        multiplier = 1000000000
        value = value[:-1]

    try:
        return int(float(value) * multiplier)
    except ValueError:
        return None


def format_number(number):
    if number is None:
        return "Tapılmadı"

    if number >= 1000000:
        return f"{number / 1000000:.2f}M"

    if number >= 1000:
        return f"{number / 1000:.2f}K"

    return str(number)


def extract_usage(text):
    patterns = [
        r'([\d.,]+\s*[KMB]?)\s*(?:uses|use)',
        r'([\d.,]+\s*[KMB]?)\s*(?:kullanım|kullan)',
        r'([\d.,]+\s*[KMB])'
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.I)

        for value in matches:
            number = number_to_int(value)

            if number is not None:
                return number

    return None


def inspect_template(url):
    html = get_page(url)

    parser = Parser()
    parser.feed(html)

    page_text = " ".join(parser.text)
    title = " ".join(parser.h1).strip()

    if not title:
        title = "Başlıq tapılmadı"

    upload_date = extract_upload_date(html)
    usage = extract_usage(page_text)

    return {
        "id": get_template_id(url),
        "url": url,
        "title": title,
        "date": upload_date,
        "usage": usage
    }


def discover_templates(report):
    found = []
    seen = set()

    for page_url in SITES["CAPCUT_PAGES"]:
        try:
            html = get_page(page_url)

            parser = Parser()
            parser.feed(html)

            page_count = 0

            for item in parser.links:
                link = urljoin(page_url, item["url"])
                parsed = urlparse(link)

                if (
                    "capcut.com" not in parsed.netloc
                    or "/template-detail/" not in parsed.path
                ):
                    continue

                template_id = get_template_id(link)

                if not template_id or template_id in seen:
                    continue

                seen.add(template_id)

                found.append({
                    "url": link,
                    "source": page_url,
                    "anchor": item["text"].strip()
                })

                page_count += 1

            report.append(
                f"• {page_url}: {page_count} yeni link"
            )

        except Exception as error:
            report.append(
                f"❌ Səhifə xətası: {page_url}\n"
                f"{str(error)[:150]}"
            )

    return found


def main():
    report = [
        "🔎 TÜRKİYƏ TREND HESABATI",
        f"📅 Tarix: {datetime.now(AZ_TZ).strftime('%d.%m.%Y %H:%M')}"
    ]

    # -----------------------------
    # ENDLESS - MUSİQİ VƏ HASHTAG
    # -----------------------------

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

    # -----------------------------
    # CAPCUT - ÇOX MƏNBƏDƏN AXTARIŞ
    # -----------------------------

    report.append("\n\n📌 CAPCUT ŞABLON AXTARIŞI")
    report.append("Yoxlanılan mənbələr:")

    candidates = discover_templates(report)

    report.append(
        f"\nToplam unikal şablon linki: {len(candidates)}"
    )

    candidates = candidates[:MAX_DETAILS_TO_CHECK]

    report.append(
        f"Detallı yoxlanılacaq şablon: {len(candidates)}"
    )

    now = datetime.now(AZ_TZ)
    cutoff = now - timedelta(days=DAYS_BACK)

    history = load_history()
    reported_ids = set(history.get("reported", []))
    template_history = history.get("templates", {})

    recent_templates = []
    unknown_dates = 0
    old_templates = 0
    checked = 0

    for candidate in candidates:
        try:
            item = inspect_template(candidate["url"])
            checked += 1

            if item["date"] is None:
                unknown_dates += 1
                continue

            if not (cutoff <= item["date"] <= now):
                old_templates += 1
                continue

            template_id = item["id"]
            previous = template_history.get(
                template_id,
                {}
            )

            previous_usage = previous.get("last_usage")
            current_usage = item["usage"]

            growth = None

            if (
                previous_usage is not None
                and current_usage is not None
            ):
                growth = current_usage - previous_usage

            item["growth"] = growth
            item["previous_usage"] = previous_usage

            recent_templates.append(item)

            # Tarixçə məlumatlarını yenilə
            if template_id not in template_history:
                template_history[template_id] = {
                    "title": item["title"],
                    "url": item["url"],
                    "upload_date": item["date"].isoformat(),
                    "first_seen": now.isoformat(),
                    "daily_usage": []
                }

            record = template_history[template_id]

            record["title"] = item["title"]
            record["url"] = item["url"]
            record["upload_date"] = item["date"].isoformat()

            if current_usage is not None:
                record["last_usage"] = current_usage

                daily_usage = record.setdefault(
                    "daily_usage",
                    []
                )

                today = now.strftime("%Y-%m-%d")

                if not daily_usage or daily_usage[-1].get("date") != today:
                    daily_usage.append({
                        "date": today,
                        "usage": current_usage
                    })

                record["daily_usage"] = daily_usage[-30:]

        except Exception as error:
            report.append(
                f"\n⚠️ Şablon yoxlanmadı: "
                f"{str(error)[:120]}"
            )

    # İstifadə sayına görə sıralama
    recent_templates.sort(
        key=lambda x: (
            x["usage"] is not None,
            x["usage"] or 0
        ),
        reverse=True
    )

    report.append("\n📊 YOXLAMA NƏTİCƏSİ")
    report.append(f"Yoxlanılan: {checked}")
    report.append(f"Tarixi tapılmayan: {unknown_dates}")
    report.append(f"30 gündən köhnə: {old_templates}")
    report.append(
        f"Son 30 gündə yayımlanan: {len(recent_templates)}"
    )

    # İlk dəfə tapılan şablonlar
    new_templates = [
        item for item in recent_templates
        if item["id"] not in reported_ids
    ]

    report.append("\n🆕 YENİ TAPILAN ŞABLONLAR")

    if new_templates:
        for index, item in enumerate(
            new_templates[:MAX_NEW_TO_REPORT],
            1
        ):
            report.append(
                f"\n{index}. {item['title']}"
            )
            report.append(
                f"📅 Tarix: {item['date'].strftime('%d.%m.%Y')}"
            )
            report.append(
                f"🔥 İstifadə: {format_number(item['usage'])}"
            )
            report.append(item["url"])

            reported_ids.add(item["id"])

    else:
        report.append(
            "Bu gün yeni və uyğun şablon tapılmadı."
        )

    # İstifadəsi artan şablonlar
    growth_templates = [
        item for item in recent_templates
        if item["growth"] is not None and item["growth"] > 0
    ]

    growth_templates.sort(
        key=lambda x: x["growth"],
        reverse=True
    )

    report.append("\n📈 İSTİFADƏSİ ARTAN ŞABLONLAR")

    if growth_templates:
        for index, item in enumerate(
            growth_templates[:MAX_GROWTH_TO_REPORT],
            1
        ):
            report.append(
                f"\n{index}. {item['title']}"
            )
            report.append(
                f"İndiki istifadə: {format_number(item['usage'])}"
            )
            report.append(
                f"Əvvəlki göstəricidən artım: "
                f"+{format_number(item['growth'])}"
            )
            report.append(item["url"])

    else:
        report.append(
            "Müqayisə üçün əvvəlki günlük göstərici yoxdur "
            "və ya artım qeydə alınmayıb."
        )

    # Tarix tapılmayan şablonlarla bağlı xəbərdarlıq
    if unknown_dates:
        report.append(
            "\n⚠️ Qeyd: Tarixi tapılmayan şablonlar "
            "30 günlük siyahıya daxil edilməyib."
        )

    history["reported"] = list(reported_ids)
    history["templates"] = template_history

    save_history(history)

    # -----------------------------
    # TELEGRAM
    # -----------------------------

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "Telegram secret-ləri tapılmadı."
        )

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
    
