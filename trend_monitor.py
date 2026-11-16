
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.parse import urljoin

URL = "https://www.capcut.com/tr-tr/template"

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.current = {
                "url": dict(attrs).get("href", ""),
                "text": ""
            }

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None

print("🔎 CAPCUT ŞABLON TESTİ")
print("Səhifə yoxlanılır...\n")

try:
    req = Request(URL, headers={
        "User-Agent": "Mozilla/5.0"
    })

    with urlopen(req, timeout=30) as response:
        html = response.read().decode("utf-8", errors="ignore")

    parser = LinkParser()
    parser.feed(html)

    trends = []
    pattern = re.compile(
        r"\d+(?:\.\d+)?[KMB]?·\d{2}:\d{2}"
    )

    for item in parser.links:
        name = " ".join(item["text"].split())

        if pattern.search(name) and item["url"]:
            link = urljoin(URL, item["url"])

            if link not in [x["link"] for x in trends]:
                trends.append({
                    "name": name,
                    "link": link
                })

    print("Səhifə ölçüsü:", len(html), "simvol")
    print("Tapılan konkret şablonlar:", len(trends))
    print("\n📌 ŞABLONLAR:\n")

    for i, item in enumerate(trends[:30], 1):
        print(f"{i}. {item['name']}")
        print(item["link"])

except Exception as e:
    print("XƏTA:", str(e))
    
