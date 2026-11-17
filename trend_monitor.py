
import os
import json
import re
import time
import unicodedata
import urllib.request
import urllib.error

from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =====================================================
# SETTINGS
# =====================================================

ENDLESS_URL = "https://endless.app/radar/tiktok/turkey"
CAPCUT_URL = "https://www.capcut.com/template"

HISTORY_FILE = "capcut_history.json"

MAX_SOUNDS = 10
MAX_DETAILS_PER_SOUND = 10

AZ_TZ = timezone(timedelta(hours=4))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)


# =====================================================
# HTML PARSER
# =====================================================

class Parser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.text = []

    def handle_starttag(self, tag, attrs):

        attrs = dict(attrs)

        if tag == "a":
            self.current_link = {
                "url": attrs.get("href", ""),
                "text": ""
            }

    def handle_data(self, data):

        self.text.append(data)

        if self.current_link is not None:
            self.current_link["text"] += data

    def handle_endtag(self, tag):

        if tag == "a" and self.current_link is not None:
            self.links.append(self.current_link)
            self.current_link = None


# =====================================================
# WEB REQUEST
# =====================================================

def get_page(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        }
    )

    with urllib.request.urlopen(request, timeout=35) as response:
        return response.read().decode("utf-8", errors="replace")


# =====================================================
# HISTORY
# =====================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return {
            "templates": {},
            "sound_matches": {}
        }

    try:

        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Invalid history format")

        data.setdefault("templates", {})
        data.setdefault("sound_matches", {})

        return data

    except Exception as error:

        print(f"History oxunmadı: {error}", flush=True)

        return {
            "templates": {},
            "sound_matches": {}
        }


def save_history(history):

    with open(HISTORY_FILE, "w", encoding="utf-8") as file:
        json.dump(
            history,
            file,
            ensure_ascii=False,
            indent=2
        )

    print("Tarixçə saxlanıldı.", flush=True)


# =====================================================
# TEXT NORMALIZATION
# =====================================================

def normalize_text(value):

    value = str(value or "").casefold()

    value = unicodedata.normalize("NFKD", value)

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(r"[^a-z0-9\s]", " ", value)

    return " ".join(value.split())


def clean_sound_name(name):

    name = str(name or "").strip()

    if re.match(
        r"^\s*original\s+(sound|audio)\s*[-–—:]",
        name,
        re.I
    ):
        return ""

    if normalize_text(name) in [
        "original sound",
        "original audio",
        "orijinal ses",
        "orijinal ses kaydi"
    ]:
        return ""

    return name.strip(" .-_")


# =====================================================
# ENDLESS
# =====================================================

def get_endless_data(report):

    print("Endless səhifəsi yüklənir...", flush=True)

    html = get_page(ENDLESS_URL)

    parser = Parser()
    parser.feed(html)

    report.append(f"\n📌 ENDLESS: {len(html)} simvol")

    music = []
    hashtags = []

    seen_music = set()
    seen_tags = set()

    for item in parser.links:

        link = item.get("url", "")
        name = item.get("text", "").strip()

        if "tiktok.com/music/" in link:

            if link not in seen_music:

                seen_music.add(link)

                music.append({
                    "name": name or "Ad göstərilmir",
                    "search_name": clean_sound_name(name),
                    "url": urljoin(ENDLESS_URL, link)
                })

        elif "tiktok.com/tag/" in link:

            if link not in seen_tags:

                seen_tags.add(link)

                hashtags.append({
                    "name": name or "Hashtag",
                    "url": urljoin(ENDLESS_URL, link)
                })

    print(
        f"Endless tamamlandı: {len(music)} musiqi, "
        f"{len(hashtags)} hashtag",
        flush=True
    )

    return music, hashtags


# =====================================================
# DATE EXTRACTION
# =====================================================

def extract_upload_date(html):

    patterns = [
        r'["\']uploadDate["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']datePublished["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']uploadDate["\']\s*:\s*["\'](20\d{2}-\d{2}-\d{2})',
        r'["\']datePublished["\']\s*:\s*["\'](20\d{2}-\d{2}-\d{2})'
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
                    timestamp /= 1000

                date = datetime.fromtimestamp(
                    timestamp,
                    timezone.utc
                ).astimezone(AZ_TZ)

            else:

                date = datetime.strptime(
                    value,
                    "%Y-%m-%d"
                ).replace(tzinfo=AZ_TZ)

            if date > datetime.now(AZ_TZ):
                continue

            return date

        except (ValueError, OverflowError, OSError):
            continue

    return None


# =====================================================
# USAGE EXTRACTION
# =====================================================

def number_to_int(value):

    if not value:
        return None

    value = str(value).upper()
    value = value.replace(" ", "").replace(",", ".")

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


# =====================================================
# AUDIO METADATA
# =====================================================

def extract_audio_labels(html):

    labels = []

    fields = [
        "musicName",
        "music_name",
        "songName",
        "song_name",
        "soundName",
        "sound_name",
        "audioName",
        "audio_name",
        "musicTitle",
        "audioTitle",
        "trackName",
        "track_name"
    ]

    for field in fields:

        pattern = (
            r'["\']'
            + re.escape(field)
            + r'["\']\s*:\s*["\']([^"\']{2,150})'
        )

        matches = re.findall(pattern, html, re.I)

        for value in matches:

            value = value.strip()

            if value and value not in labels:
                labels.append(value)

    return labels


def audio_matches(sound_name, audio_labels):

    target = normalize_text(sound_name)

    if not target:
        return False

    target_words = set(target.split())

    for label in audio_labels:

        candidate = normalize_text(label)

        if not candidate:
            continue

        if target == candidate:
            return True

        if target in candidate or candidate in target:
            return True

        candidate_words = set(candidate.split())

        if len(target_words) >= 2:
            if target_words.issubset(candidate_words):
                return True

    return False


# =====================================================
# PLAYWRIGHT SEARCH
# =====================================================

def find_search_box(page):

    selectors = [
        'input[type="search"]',
        'input[placeholder*="Search" i]',
        'input[placeholder*="template" i]',
        'input[placeholder*="search" i]',
        'input[aria-label*="search" i]',
        'input'
    ]

    for selector in selectors:

        locator = page.locator(selector)

        try:

            count = min(locator.count(), 10)

            for index in range(count):

                field = locator.nth(index)

                if field.is_visible() and field.is_enabled():
                    return field

        except Exception:
            continue

    return None


def find_template_links(page, sound_name):

    print(f"CapCut axtarışı: {sound_name}", flush=True)

    page.goto(
        CAPCUT_URL,
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(5000)

    search_box = find_search_box(page)

    if search_box is None:
        raise RuntimeError(
            "CapCut axtarış sahəsi tapılmadı."
        )

    search_box.fill(sound_name)
    search_box.press("Enter")

    page.wait_for_timeout(6000)

    links = page.locator("a").evaluate_all(
        """elements => elements.map(a => ({
            href: a.href,
            text: (a.innerText || a.textContent || "").trim()
        }))"""
    )

    found = []
    seen = set()

    for item in links:

        link = item.get("href", "")

        if not link:
            continue

        parsed = urlparse(link)

        if "capcut.com" not in parsed.netloc:
            continue

        if "/template-detail/" not in parsed.path:
            continue

        template_id = parsed.path.rstrip("/").split("/")[-1]

        if not template_id or template_id in seen:
            continue

        seen.add(template_id)

        found.append({
            "id": template_id,
            "url": link,
            "anchor": item.get("text", "")
        })

    return found


# =====================================================
# TEMPLATE INSPECTION
# =====================================================

def inspect_template(page, candidate, sound_name):

    page.goto(
        candidate["url"],
        wait_until="domcontentloaded",
        timeout=60000
    )

    page.wait_for_timeout(2500)

    html = page.content()

    try:
        page_text = page.locator("body").inner_text(timeout=10000)
    except Exception:
        page_text = ""

    try:
        title = page.locator("h1").first.inner_text(timeout=3000)
    except Exception:
        title = candidate.get("anchor") or "Başlıq tapılmadı"

    if not title:
        title = candidate.get("anchor") or "Başlıq tapılmadı"

    audio_labels = extract_audio_labels(html)

    confirmed = audio_matches(
        sound_name,
        audio_labels
    )

    return {
        "id": candidate["id"],
        "url": candidate["url"],
        "title": title[:120],
        "date": extract_upload_date(html),
        "usage": extract_usage(page_text),
        "audio_labels": audio_labels,
        "confirmed": confirmed
    }


# =====================================================
# CAPCUT PROCESS
# =====================================================

def search_capcut_for_sounds(music, report, history):

    report.append(
        "\n\n🎬 CAPCUT - TREND SƏSLƏRƏ UYĞUN ŞABLONLAR"
    )

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = browser.new_page(
            user_agent=USER_AGENT,
            locale="tr-TR"
        )

        page.set_default_timeout(15000)

        try:

            for index, sound in enumerate(music[:MAX_SOUNDS], 1):

                sound_name = sound["name"]
                search_name = sound["search_name"]

                report.append(f"\n\n{'─' * 25}")
                report.append(f"🎵 {index}. {sound_name}")
                report.append(f"🔗 TikTok səsi: {sound['url']}")

                if not search_name:

                    report.append(
                        "⚠️ Original sound və ya konkret adı olmayan səsdir. "
                        "Axtarış buraxıldı."
                    )

                    continue

                report.append(f"🔎 CapCut axtarışı: {search_name}")

                try:

                    candidates = find_template_links(
                        page,
                        search_name
                    )

                    report.append(
                        f"Tapılan şablon linkləri: {len(candidates)}"
                    )

                except Exception as error:

                    report.append(
                        "❌ CapCut axtarış xətası: "
                        + str(error)[:180]
                    )

                    continue

                candidates = candidates[:MAX_DETAILS_PER_SOUND]

                confirmed_templates = []

                for candidate in candidates:

                    try:

                        item = inspect_template(
                            page,
                            candidate,
                            search_name
                        )

                        if item["confirmed"]:
                            confirmed_templates.append(item)

                        time.sleep(0.5)

                    except Exception as error:

                        report.append(
                            "⚠️ Şablon yoxlanmadı: "
                            + str(error)[:100]
                        )

                report.append(
                    "Təsdiqlənmiş uyğun şablon: "
                    + str(len(confirmed_templates))
                )

                if not confirmed_templates:

                    report.append(
                        "❌ Səslə uyğunluğu metadata əsasında "
                        "təsdiqlənən şablon tapılmadı."
                    )

                    continue

                popular_candidates = [
                    item for item in confirmed_templates
                    if item["usage"] is not None
                ]

                if popular_candidates:

                    popular = max(
                        popular_candidates,
                        key=lambda item: item["usage"]
                    )

                    report.append("\n🔥 ƏN POPULYAR ŞABLON")
                    report.append(f"📌 {popular['title']}")
                    report.append(
                        f"İstifadə: {format_number(popular['usage'])}"
                    )

                    if popular["date"]:
                        report.append(
                            "📅 Tarix: "
                            + popular["date"].strftime("%d.%m.%Y")
                        )

                    report.append(popular["url"])

                else:

                    report.append(
                        "\n🔥 Ən populyar: istifadə sayı tapılmadı."
                    )

                dated_candidates = [
                    item for item in confirmed_templates
                    if item["date"] is not None
                ]

                if dated_candidates:

                    newest = max(
                        dated_candidates,
                        key=lambda item: item["date"]
                    )

                    report.append("\n🆕 ƏN YENİ ŞABLON")
                    report.append(f"📌 {newest['title']}")
                    report.append(
                        "📅 Tarix: "
                        + newest["date"].strftime("%d.%m.%Y")
                    )
                    report.append(
                        f"İstifadə: {format_number(newest['usage'])}"
                    )
                    report.append(newest["url"])

                else:

                    report.append(
                        "\n🆕 Ən yeni: yayımlanma tarixi tapılmadı."
                    )

                for item in confirmed_templates:

                    template_id = item["id"]

                    record = history["templates"].get(
                        template_id,
                        {}
                    )

                    record["title"] = item["title"]
                    record["url"] = item["url"]

                    if item["date"]:
                        record["upload_date"] = item["date"].isoformat()

                    if item["usage"] is not None:

                        today = datetime.now(AZ_TZ).strftime("%Y-%m-%d")

                        daily = record.setdefault("daily_usage", [])

                        if (
                            not daily
                            or daily[-1].get("date") != today
                        ):

                            daily.append({
                                "date": today,
                                "usage": item["usage"]
                            })

                        record["daily_usage"] = daily[-30:]
                        record["last_usage"] = item["usage"]

                    history["templates"][template_id] = record

        finally:
            browser.close()


# =====================================================
# TELEGRAM WITH DIAGNOSTICS
# =====================================================

def send_telegram(report):

    print("Telegram göndərişi başlayır...", flush=True)

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN secret tapılmadı.")

    if not chat_id:
        raise RuntimeError("TELEGRAM_CHAT_ID secret tapılmadı.")

    message = "\n".join(report)

    chunks = []
    current = ""

    for line in message.splitlines():

        if len(current) + len(line) + 1 > 3500:

            if current:
                chunks.append(current)

            current = line

        else:

            current += ("\n" if current else "") + line

    if current:
        chunks.append(current)

    print(
        f"Telegram-a göndəriləcək mesaj sayı: {len(chunks)}",
        flush=True
    )

    for index, chunk in enumerate(chunks, 1):

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

        try:

            with urllib.request.urlopen(
      
