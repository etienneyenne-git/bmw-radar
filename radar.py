
import os, re, json, hashlib, time
from pathlib import Path
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

MIN_YEAR = 2021
MAX_KM = 10_000
MAX_PRICE = 14_000

SEARCHES = [
    ("MotoScout24", "https://www.motoscout24.ch/de/s/mo-nine-t/mk-bmw?makeModelVersions%5B0%5D%5BversionFullName%5D=pure"),
    ("MotoScout24-R12", "https://www.motoscout24.ch/de/s/mo-r-12/mk-bmw"),
    ("AutoScout24", "https://www.autoscout24.ch/fr/s/mo-r-nine-t/mk-bmw/vc-motorcycle"),
    ("AutoScout24-R12", "https://www.autoscout24.ch/fr/s/mo-r-12/mk-bmw/vc-motorcycle"),
]

TITLE_RE = re.compile(r"(r\s*nine\s*t\s*pure|r\s*1200\s*nine\s*t\s*pure|r\s*12\s*nine\s*t)", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
PRICE_RE = re.compile(r"(?:CHF\s*)?([\d'’\s]{3,})\s*[.–-]?", re.I)
KM_RE = re.compile(r"([\d'’\s]+)\s*km\b", re.I)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 10; Mobile) AppleWebKit/537.36 Chrome/128 Safari/537.36",
    "Accept-Language": "fr-CH,fr;q=0.9,de-CH;q=0.8,en;q=0.7",
}

STATE_FILE = Path("seen.json")

def num(s):
    return int(re.sub(r"[^\d]", "", s)) if s and re.sub(r"[^\d]", "", s) else None

def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def parse_page(source, url, html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}
    for tag in soup.find_all(string=TITLE_RE):
        title = " ".join(tag.split())
        if not TITLE_RE.search(title):
            continue
        node = tag.parent
        # Walk upward until enough listing-like text is collected.
        container = node
        for _ in range(6):
            txt = " ".join(container.stripped_strings)
            if len(txt) > 100 and ("CHF" in txt or "km" in txt.lower()):
                break
            if container.parent:
                container = container.parent
        txt = " ".join(container.stripped_strings)

        price = None
        m = re.search(r"CHF\s*([\d'’\s]{3,})", txt, re.I)
        if m:
            price = num(m.group(1))

        km = None
        m = KM_RE.search(txt)
        if m:
            km = num(m.group(1))

        years = [int(x) for x in YEAR_RE.findall(txt)]
        year = max([y for y in years if 2000 <= y <= 2030], default=None)

        href = None
        # Prefer a link inside/near the container.
        a = container.find("a", href=True)
        if a:
            href = urljoin(url, a["href"])
        if not href:
            p = node
            for _ in range(5):
                if p and p.find("a", href=True):
                    href = urljoin(url, p.find("a", href=True)["href"])
                    break
                p = p.parent if p else None

        # Stable ID from URL if possible, otherwise title + metadata.
        raw_id = href or f"{source}|{title}|{price}|{year}|{km}"
        uid = hashlib.sha256(raw_id.encode()).hexdigest()[:20]

        if price is not None and km is not None and year is not None:
            if year >= MIN_YEAR and km <= MAX_KM and price < MAX_PRICE:
                found[uid] = {
                    "id": uid, "source": source, "title": title,
                    "price": price, "km": km, "year": year, "url": href or url
                }
    return list(found.values())

def main():
    all_matches = []
    errors = []
    for source, url in SEARCHES:
        try:
            html = fetch(url)
            all_matches.extend(parse_page(source, url, html))
        except Exception as e:
            errors.append(f"{source}: {e}")

    # Deduplicate same listing found through several searches.
    unique = {}
    for x in all_matches:
        unique[x["id"]] = x

    seen = set()
    if STATE_FILE.exists():
        try:
            seen = set(json.loads(STATE_FILE.read_text()))
        except Exception:
            pass

    new = [x for x in unique.values() if x["id"] not in seen]
    seen.update(unique.keys())
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False))

    print(json.dumps({"new": new, "errors": errors}, ensure_ascii=False))

if __name__ == "__main__":
    main()
