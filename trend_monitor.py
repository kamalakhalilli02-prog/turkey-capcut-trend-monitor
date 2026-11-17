import os
import re
import json
import time
import urllib.request
import urllib.parse
import urllib.error

from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# =========================================================
# AYARLAR
# =========================================================

ENDLESS_URL = "https://endless.app/radar/tiktok/turkey"
CAPCUT_URL = "https://www.capcut.com/template"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

HISTORY_FILE = Path("capcut_history.json")

MAX_SOUNDS = 10
MAX_HASHTAGS = 10
MAX_TEMPLATES_PER_SOUND = 30

REQUEST_TIMEOUT = 30
PAGE_TIMEOUT = 45000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


# =========================================================
# ÜMUMİ FUNKSİYALAR
# =========================================================

def log(message):
    print(message, flush=True)


def normalize_text(value):
    value = str(value or "").lower()
    value = value.replace("ı", "i")
    value = value.replace("İ", "i")
    value = re.sub(r"[^a-z0-9ğüşöçıə\s]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_html(url):
    request = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT
    ) as response:
        return response.read().decode("utf-8", errors="replace")


def load_history():
    if not HISTORY_FILE.exists():
        return {"templates": []}

    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return {"templates": []}

        if not isinstance(data.get("templates"), list):
            data["templates"] = []

        return data

    except Exception as error:
        log(f"Tarixçə oxunmadı: {error}")
        return {"templates": []}


def save_history(history):
    try:
        with HISTORY_FILE.open("w", encoding="utf-8") as file:
            json.dump(
                history,
                file,
                ensure_ascii=False,
                indent=2
            )

        log("Şablon tarixçəsi yadda saxlanıldı.")

    except Exception as error:
        log(f"Tarixçə yadda saxlanmadı: {error}")


# =========================================================
# ENDLESS SƏHİFƏSİNDƏN MƏLUMAT TOPLAMA
# =========================================================

class EndlessParser(HTMLParser):

    def __init__(self):
        super().__init__()
        self.links = []
        self.current_link = None
        self.page_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "a":
            href = attrs.get("href", "")

            if href:
                self.current_link = {
                    "url": urllib.parse.urljoin(ENDLESS_URL, href),
                    "text": ""
                }

    def handle_data(self, data):
        text = data.strip()

        if not text:
            return

        self.page_text.append(text)

        if self.current_link is not None:
            self.current_link["text"] += " " + text

    def handle_endtag(self, tag):
        if tag == "a" and self.current_link is not None:
            self.links.append(self.current_link)
            self.current_link = None


def get_endless_trends():
    log("Endless səhifəsi açılır...")

    html = get_html(ENDLESS_URL)

    parser = EndlessParser()
    parser.feed(html)

    sounds = []
    seen_sound_urls = set()

    for item in parser.links:
        url = item["url"]
        label = re.sub(r"\s+", " ", item["text"]).strip()

        if "/music/" not in url:
            continue

        if url in seen_sound_urls:
            continue

        seen_sound_urls.add(url)

        if not label:
            label = "TikTok musiqisi"

        sounds.append({
            "name": label[:150],
            "url": url
        })

    page_text = " ".join(parser.page_text)

    hashtags = re.findall(
        r"#[\wğüşöçıİĞÜŞÖÇ]+",
        page_text,
        flags=re.UNICODE
    )

    unique_hashtags = []
    seen_hashtags = set()

    for hashtag in hashtags:
        key = hashtag.lower()

        if key not in seen_hashtags:
            seen_hashtags.add(key)
            unique_hashtags.append(hashtag)

    log(f"Endless musiqi sayı: {len(sounds)}")
    log(f"Endless hashtag sayı: {len(unique_hashtags)}")

    return (
        sounds[:MAX_SOUNDS],
        unique_hashtags[:MAX_HASHTAGS]
    )


# =========================================================
# CAPCUT AXTARIŞI
# =========================================================

def is_original_sound(sound_name):
    text = normalize_text(sound_name)

    return (
        "original sound" in text
        or "orijinal ses" in text
        or text.startswith("original")
    )


def find_search_box(page):
    selectors = [
        'input[type="search"]',
        'input[placeholder*="Search" i]',
        'input[placeholder*="template" i]',
        'input[placeholder*="ara" i]',
        'input[aria-label*="search" i]',
        'input'
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first

            if locator.count() > 0 and locator.is_visible():
                return locator

        except Exception:
            continue

    return None


def search_capcut_templates(page, sound_name):
    log(f"CapCut axtarışı: {sound_name}")

    try:
        page.goto(
            CAPCUT_URL,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT
        )

        page.wait_for_timeout(4000)

        search_box = find_search_box(page)

        if search_box is None:
            log("CapCut axtarış xanası tapılmadı.")
            return []

        search_box.fill(sound_name)
        search_box.press("Enter")

        page.wait_for_timeout(6000)

        links = page.locator('a[href*="/template-detail/"]').evaluate_all(
            """
            elements => elements.map(element => ({
                href: element.href,
                text: element.innerText || ""
            }))
            """
        )

        results = []
        seen = set()

        for item in links:
            url = item.get("href", "").strip()

            if not url:
                continue

            if "/template-detail/" not in url:
                continue

            if url in seen:
                continue

            seen.add(url)

            results.append({
                "url": url,
                "title": item.get("text", "").strip()
            })

            if len(results) >= MAX_TEMPLATES_PER_SOUND:
                break

        log(f"CapCut nəticələrinin sayı: {len(results)}")

        return results

    except PlaywrightTimeoutError:
        log("CapCut axtarışı vaxt limitini keçdi.")
        return []

    except Exception as error:
        log(f"CapCut axtarış xətası: {error}")
        return []


# =========================================================
# CAPCUT ŞABLONUNU YOXLAMA
# =========================================================

def extract_usage(text):
    patterns = [
        r"([\d,.]+)\s*[Kk]\s*(?:uses|use|istifadə)",
        r"([\d,.]+)\s*[Mm]\s*(?:uses|use|istifadə)",
        r"([\d,.]+)\s*(?:uses|use|istifadə)",
        r"([\d,.]+)\s*(?:kullanım|kullanim)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if not match:
            continue

        value = match.group(1).replace(",", ".")

        try:
            number = float(value)

            if "m" in match.group(0).lower():
                number *= 1_000_000
            elif "k" in match.group(0).lower():
                number *= 1_000

            return int(number)

        except ValueError:
            continue

    return 0


def extract_date(text):
    patterns = [
        r"(20\d{2}[-/]\d{1,2}[-/]\d{1,2})",
        r"(20\d{2}\.\d{1,2}\.\d{1,2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return match.group(1)

    return ""


def date_to_timestamp(date_value):
    if not date_value:
        return 0

    for date_format in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d"
    ):
        try:
            return datetime.strptime(
                date_value,
                date_format
            ).replace(tzinfo=timezone.utc).timestamp()

        except ValueError:
            continue

    return 0


def sound_is_confirmed(sound_name, page_text):
    """
    Şablon səhifəsində musiqinin adı görünürsə,
    onu uyğun nəticə kimi qəbul edir.

    Musiqi adı səhifədə tapılmadıqda nəticə qəbul edilmir.
    """

    sound = normalize_text(sound_name)
    content = normalize_text(page_text)

    if not sound or not content:
        return False

    # Original sound adlarını axtarışda istifadə etmirik.
    if is_original_sound(sound_name):
        return False

    # Qısa və qeyri-dəqiq adlarla yanlış uyğunlaşmanın qarşısını alırıq.
    if len(sound) < 4:
        return False

    return sound in content


def inspect_template(page, template, sound_name):
    url = template["url"]

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=PAGE_TIMEOUT
        )

        page.wait_for_timeout(3500)

        title = page.title()

        body_text = page.locator("body").inner_text(
            timeout=10000
        )

        full_text = title + "\n" + body_text

        if not sound_is_confirmed(sound_name, full_text):
            return None

        usage = extract_usage(full_text)
        date_value = extract_date(full_text)

        return {
            "title": template.get("title") or title or "CapCut şablonu",
            "url": url,
            "sound": sound_name,
            "usage": usage,
            "date": date_value,
            "timestamp": date_to_timestamp(date_value)
        }

    except PlaywrightTimeoutError:
        log(f"Şablon səhifəsi açılmadı: {url}")
        return None

    except Exception as error:
        log(f"Şablon yoxlama xətası: {error}")
        return None


def get_capcut_results(sounds, history):
    log("Playwright brauzeri başladılır...")

    old_urls = {
        item.get("url")
        for item in history.get("templates", [])
        if isinstance(item, dict)
    }

    all_results = []
    new_history_items = []

    with sync_playwright() as playwright:

        browser = playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox"]
        )

        page = browser.new_page(
            user_agent=HEADERS["User-Agent"],
            locale="tr-TR"
        )

        for index, sound in enumerate(sounds, start=1):
            sound_name = sound["name"]

            log(
                f"Musiqi {index}/{len(sounds)}: "
                f"{sound_name}"
            )

            if is_original_sound(sound_name):
                log("Original sound olduğu üçün ötürüldü.")
                continue

            templates = search_capcut_templates(
                page,
                sound_name
            )

            verified = []

            for template in templates:
                result = inspect_template(
                    page,
                    template,
                    sound_name
                )

                if result is None:
                    continue

                verified.append(result)

                if result["url"] not in old_urls:
                    new_history_items.append(result)
                    old_urls.add(result["url"])

            if verified:
                # Ən çox istifadə olunan şablon
                popular = sorted(
                    verified,
                    key=lambda item: item["usage"],
                    reverse=True
                )[0]

                # Tarixi məlum olan ən yeni şablon
                dated = [
                    item for item in verified
                    if item["timestamp"] > 0
                ]

                newest = None

                if dated:
                    newest = sorted(
                        dated,
                        key=lambda item: item["timestamp"],
                        reverse=True
                    )[0]

                all_results.append({
                    "sound": sound_name,
                    "sound_url": sound["url"],
                    "popular": popular,
                    "newest": newest
                })

            else:
                all_results.append({
                    "sound": sound_name,
                    "sound_url": sound["url"],
                    "popular": None,
                    "newest": None
                })

        browser.close()

    history.setdefault("templates", [])
    history["templates"].extend(new_history_items)

    save_history(history)

    return all_results


# =========================================================
# TELEGRAM MESAJI
# =========================================================

def split_message(message, max_length=3900):
    chunks = []
    current = ""

    for line in message.split("\n"):
        if len(current) + len(line) + 1 > max_length:
            if current:
                chunks.append(current)

            current = line
        else:
            if current:
                current += "\n"

            current += line

    if current:
        chunks.append(current)

    return chunks


def send_telegram(message):
    log("Telegram göndərişi başlayır...")

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN GitHub Secrets-də tapılmadı."
        )

    if not TELEGRAM_CHAT_ID:
        raise RuntimeError(
            "TELEGRAM_CHAT_ID GitHub Secrets-də tapılmadı."
        )

    api_url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )

    chunks = split_message(message)

    for index, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True
        }

        data = json.dumps(payload).encode("utf-8")

        request = urllib.request.Request(
            api_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "TurkeyTrendMonitor/1.0"
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=30
            ) as response:
                response_body = response.read().decode(
                    "utf-8",
                    errors="replace"
                )

            result = json.loads(response_body)

            if not result.get("ok"):
                raise RuntimeError(
                    "Telegram API mesajı qəbul etmədi: "
                    + str(result)
                )

            log(
                f"Telegram mesajı {index}/{len(chunks)} "
                "uğurla göndərildi."
            )

        except urllib.error.HTTPError as error:
            body = error.read().decode(
                "utf-8",
                errors="replace"
            )

            raise RuntimeError(
                f"Telegram HTTP xətası {error.code}: {body}"
            ) from error

        except Exception as error:
            raise RuntimeError(
                f"Telegram göndəriş xətası: {error}"
            ) from error


# =========================================================
# HESABATIN HAZIRLANMASI
# =========================================================

def build_report(sounds, hashtags, capcut_results):
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    lines = [
        "🇹🇷 TÜRKİYƏ TİKTOK TREND HESABATI",
        f"📅 {now}",
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🎵 TREND MUSİQİLƏRİ",
        "━━━━━━━━━━━━━━━━━━"
    ]

    if not sounds:
        lines.append("Musiqi məlumatı tapılmadı.")

    for index, sound in enumerate(sounds, start=1):
        lines.append(
            f"\n{index}. {sound['name']}"
        )
        lines.append(sound["url"])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "🎬 CAPCUT ŞABLONLARI",
        "━━━━━━━━━━━━━━━━━━"
    ])

    if not capcut_results:
        lines.append("CapCut nəticəsi tapılmadı.")

    for item in capcut_results:
        lines.append("")
        lines.append(f"🎵 Musiqi: {item['sound']}")

        popular = item.get("popular")
        newest = item.get("newest")

        if popular:
            lines.append("")
            lines.append("🔥 ƏN ÇOX İSTİFADƏ OLUNAN:")

            lines.append(
                f"Şablon: {popular['title'][:100]}"
            )

            lines.append(
                f"İstifadə sayı: {popular['usage'] or 'Məlum deyil'}"
            )

            if popular["date"]:
                lines.append(
                    f"Tarix: {popular['date']}"
                )

            lines.append(popular["url"])

        else:
            lines.append(
                "Uyğunluğu təsdiqlənmiş şablon tapılmadı."
            )

        if newest:
            lines.append("")
            lines.append("🆕 ƏN YENİ:")

            lines.append(
                f"Şablon: {newest['title'][:100]}"
            )

            lines.append(
                f"Tarix: {newest['date']}"
            )

            lines.append(newest["url"])

    lines.extend([
        "",
        "━━━━━━━━━━━━━━━━━━",
        "#️⃣ TREND HASHTAG-LƏR",
        "━━━━━━━━━━━━━━━━━━"
    ])

    if hashtags:
        lines.append(" ".join(hashtags))
    else:
        lines.append("Hashtag tapılmadı.")

    lines.extend([
        "",
        "ℹ️ Qeyd: CapCut şablonları yalnız səhifədə "
        "musiqi adı tapıldıqda uyğun nəticə kimi göstərilir."
    ])

    return "\n".join(lines)


# =========================================================
# ƏSAS PROQRAM
# =========================================================

def main():
    log("1. Proqram başladı.")

    sounds, hashtags = get_endless_trends()

    history = load_history()

    capcut_results = get_capcut_results(
        sounds,
        history
    )

    report = build_report(
        sounds,
        hashtags,
        capcut_results
    )

    log("Hesabat hazırlandı.")
    log(report)

    send_telegram(report)

    log("2. MAIN funksiyası tamamlandı.")


if __name__ == "__main__":
    log("Python faylı işə düşdü.")

    try:
        main()

    except Exception as error:
        log(
            f"PROQRAM XƏTASI: "
            f"{type(error).__name__}: {error}"
        )
        raise

    log("3. Proqram bitdi.")
