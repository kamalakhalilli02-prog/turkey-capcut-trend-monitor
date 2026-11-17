
import os
import json
import re
import time
import unicodedata
import urllib.request

from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, quote


# =====================================================
# AYARLAR
# =====================================================

ENDLESS_URL = "https://endless.app/radar/tiktok/turkey"

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
# WEB SƏHİFƏSİ OXUMA
# =====================================================

def get_page(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=35
    ) as response:

        return response.read().decode(
            "utf-8",
            errors="replace"
        )


# =====================================================
# TARİXÇƏ
# =====================================================

def load_history():

    if not os.path.exists(HISTORY_FILE):
        return {
            "templates": {},
            "sound_matches": {}
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

        data.setdefault("templates", {})
        data.setdefault("sound_matches", {})

        return data

    except Exception:

        return {
            "templates": {},
            "sound_matches": {}
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


# =====================================================
# MƏLUMATLARIN TƏMİZLƏNMƏSİ
# =====================================================

def normalize_text(value):

    value = str(value or "").casefold()

    value = unicodedata.normalize(
        "NFKD",
        value
    )

    value = "".join(
        char for char in value
        if not unicodedata.combining(char)
    )

    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value
    )

    return " ".join(value.split())


def clean_sound_name(name):

    name = str(name or "").strip()

    name = re.sub(
        r"^\s*original\s+sound\s*[-–—:]\s*",
        "",
        name,
        flags=re.I
    )

    name = re.sub(
        r"^\s*original\s+audio\s*[-–—:]\s*",
        "",
        name,
        flags=re.I
    )

    name = name.strip(" .-_")

    generic = [
        "original sound",
        "original audio",
        "orijinal ses",
        "orijinal ses kaydi"
    ]

    if normalize_text(name) in generic:
        return ""

    return name


# =====================================================
# ENDLESS - TREND MUSİQİLƏRİ VƏ HASHTAGLAR
# =====================================================

def get_endless_data(report):

    html = get_page(ENDLESS_URL)

    parser = Parser()
    parser.feed(html)

    report.append(
        f"\n📌 ENDLESS: {len(html)} simvol"
    )

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

    return music, hashtags


# =====================================================
# CAPCUT AXTARIŞ URL
# =====================================================

def make_capcut_search_url(sound_name):

    # Axtarış ifadəsini URL üçün uyğun formaya salırıq.
    slug = "-".join(
        normalize_text(sound_name).split()
    )

    return (
        "https://www.capcut.com/explore/"
        + quote(slug, safe="-")
    )


# =====================================================
# CAPCUT ŞABLON LINKLƏRİNİN TAPILMASI
# =====================================================

def find_template_links(search_url):

    html = get_page(search_url)

    parser = Parser()
    parser.feed(html)

    found = []
    seen = set()

    for item in parser.links:

        link = urljoin(
            search_url,
            item.get("url", "")
        )

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
            "anchor": item.get("text", "").strip()
        })

    return found


# =====================================================
# ŞABLON TARİXİ
# =====================================================

def extract_upload_date(html):

    patterns = [
        r'["\']uploadDate["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']datePublished["\']\s*:\s*["\']?(\d{10,13})',
        r'["\']uploadDate["\']\s*:\s*["\'](20\d{2}-\d{2}-\d{2})',
        r'["\']datePublished["\']\s*:\s*["\'](20\d{2}-\d{2}-\d{2})'
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            re.I
        )

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

            now = datetime.now(AZ_TZ)

            # Gələcək tarixləri qəbul etmirik.
            if date > now:
                continue

            return date

        except (
            ValueError,
            OverflowError,
            OSError
        ):
            continue

    return None


# =====================================================
# İSTİFADƏ SAYI
# =====================================================

def number_to_int(value):

    if not value:
        return None

    value = str(value).upper()
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

        matches = re.findall(
            pattern,
            text,
            re.I
        )

        for value in matches:

            number = number_to_int(value)

            if number is not None:
                return number

    return None


# =====================================================
# ŞABLONDA MUSİQİ METADATA-SININ TAPILMASI
# =====================================================

def extract_audio_labels(html):

    labels = []

    # Yalnız musiqi/audio ilə əlaqəli açıq metadata
    # sahələrini axtarırıq.
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

        matches = re.findall(
            pattern,
            html,
            re.I
        )

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

        # Tam ifadə uyğunluğu
        if target == candidate:
            return True

        if target in candidate or candidate in target:
            return True

        candidate_words = set(candidate.split())

        # Çoxsözlü adlarda bütün əsas sözlər uyğun gəlməlidir.
        if len(target_words) >= 2:

            if target_words.issubset(candidate_words):
                return True

    return False


# =====================================================
# ŞABLON DETALLARININ YOXLANMASI
# =====================================================

def inspect_template(candidate, sound_name):

    html = get_page(candidate["url"])

    parser = Parser()
    parser.feed(html)

    page_text = " ".join(parser.text)

    title = page_text.split("\n")[0].strip()

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
# HƏR TREND SƏS ÜÇÜN CAPCUT AXTARIŞI
# =====================================================

def search_capcut_for_sounds(music, report, history):

    results = []

    report.append(
        "\n\n🎬 CAPCUT - TREND SƏSLƏRƏ UYĞUN ŞABLONLAR"
    )

    for index, sound in enumerate(
        music[:MAX_SOUNDS],
        1
    ):

        sound_name = sound["name"]
        search_name = sound["search_name"]

        report.append(
            f"\n\n{'─' * 25}"
        )

        report.append(
            f"🎵 {index}. {sound_name}"
        )

        report.append(
            f"🔗 TikTok səsi: {sound['url']}"
        )

        if not search_name:

            report.append(
                "⚠️ Səsin axtarış üçün konkret adı yoxdur. "
                "CapCut axtarışı buraxıldı."
            )

            continue

        report.append(
            f"🔎 CapCut axtarışı: {search_name}"
        )

        search_url = make_capcut_search_url(
            search_name
        )

        try:

            candidates = find_template_links(
                search_url
            )

            report.append(
                f"Tapılan şablon linkləri: {len(candidates)}"
            )

        except Exception as error:

            report.append(
                f"❌ CapCut axtarış xətası: "
                f"{str(error)[:150]}"
            )

            continue

        candidates = candidates[:MAX_DETAILS_PER_SOUND]

        confirmed_templates = []

        for candidate in candidates:

            try:

                item = inspect_template(
                    candidate,
                    search_name
                )

                if item["confirmed"]:

                    confirmed_templates.append(item)

                time.sleep(0.4)

            except Exception as error:

                report.append(
                    f"⚠️ Şablon yoxlanmadı: "
                    f"{str(error)[:100]}"
                )

        report.append(
            f"Təsdiqlənmiş uyğun şablon: "
            f"{len(confirmed_templates)}"
        )

        if not confirmed_templates:

            report.append(
                "❌ Səslə uyğunluğu metadata əsasında "
                "təsdiqlənən şablon tapılmadı."
            )

            continue

        # ƏN POPULYAR
        popular_candidates = [
            item for item in confirmed_templates
            if item["usage"] is not None
        ]

        if popular_candidates:

            popular = max(
                popular_candidates,
                key=lambda x: x["usage"]
            )

            report.append(
                "\n🔥 ƏN POPULYAR ŞABLON"
            )

            report.append(
                f"📌 {popular['title']}"
            )

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

        # ƏN YENİ
        dated_candidates = [
            item for item in confirmed_templates
            if item["date"] is not None
        ]

        if dated_candidates:

            newest = max(
                dated_candidates,
                key=lambda x: x["date"]
            )

            report.append(
                "\n🆕 ƏN YENİ ŞABLON"
            )

            report.append(
                f"📌 {newest['title']}"
            )

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

        # Tarixçədə gündəlik istifadə göstəricisi
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

                today = datetime.now(AZ_TZ).strftime(
                    "%Y-%m-%d"
                )

                daily = record.setdefault(
                    "daily_usage",
                    []
                )

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

        results.append({
            "sound": sound_name,
            "templates": confirmed_templates
        })

    return results


# =====================================================
# TELEGRAM MESAJININ HAZIRLANMASI
# =====================================================

def send_telegram(report):

    token = os.environ.get(
        "TELEGRAM_BOT_TOKEN"
    )

    chat_id = os.environ.get(
        "TELEGRAM_CHAT_ID"
    )

    if not token or not chat_id:

        raise RuntimeError(
            "Telegram secret-ləri tapılmadı."
        )

    message = "\n".join(report)

    # Mesajları sətir sərhədlərində bölürük.
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


# =====================================================
# ƏSAS PROQRAM
# =====================================================

def main():

    report = [
        "🔎 TÜRKİYƏ TREND HESABATI",
        "📅 Tarix: "
        + datetime.now(AZ_TZ).strftime("%d.%m.%Y %H:%M")
    ]

    history = load_history()

    # ENDLESS
    try:

        music, hashtags = get_endless_data(report)

        report.append(
            f"\n🎵 TikTok musiqiləri: {len(music)}"
        )

        for item in music[:MAX_SOUNDS]:

            report.append(
                f"• {item['name'][:100]}\n"
                f"{item['url']}"
            )

        report.append(
            f"\n🏷 TikTok hashtagları: {len(hashtags)}"
        )

        for item in hashtags[:10]:

            report.append(
                f"• {item['name'][:80]}\n"
                f"{item['url']}"
            )

    except Exception as error:

        report.append(
            "\n❌ ENDLESS xətası: "
            + str(error)[:200]
        )

        music = []

    # CAPCUT
    if music:

        search_capcut_for_sounds(
            music,
            report,
            history
        )

    else:

        report.append(
            "\n⚠️ CapCut axtarışı üçün trend musiqi tapılmadı."
        )

    # TARİXÇƏNİ SAXLA
    save_history(history)

    # TELEGRAM
    send_telegram(report)


if __name__ == "__main__":
    main()
