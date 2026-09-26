import os
import re
import json
import hashlib
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ============================================================
# CONFIGURATION
# ============================================================

MIN_YEAR = 2021
MAX_KM = 10_000
MAX_PRICE = 14_000

STATE_FILE = Path("seen.json")

SEARCHES = [
    (
        "AutoScout24",
        "https://www.autoscout24.ch/fr/s/mo-r-nine-t/mk-bmw/vc-motorcycle",
    ),
    (
        "AutoScout24-R12",
        "https://www.autoscout24.ch/fr/s/mo-r-12/mk-bmw/vc-motorcycle",
    ),
    (
        "MotoScout24",
        "https://www.motoscout24.ch/fr/s/mo-nine-t/mk-bmw",
    ),
    (
        "MotoScout24-R12",
        "https://www.motoscout24.ch/fr/s/mo-r-12/mk-bmw",
    ),
]


# Modèles acceptés
TITLE_RE = re.compile(
    r"""
    (
        r\s*nine\s*t\s*pure
        |
        r\s*1200\s*nine\s*t\s*pure
        |
        r\s*12\s*nine\s*t
        |
        r\s*12\s*nine\s*t\s*pure
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


PRICE_RE = re.compile(
    r"(?:CHF\s*)?([\d'’\s]{3,})\s*(?:\.–|-)?",
    re.IGNORECASE,
)

KM_RE = re.compile(
    r"([\d'’\s]+)\s*km\b",
    re.IGNORECASE,
)

DATE_RE = re.compile(
    r"\b(?:0?[1-9]|1[0-2])\.(20\d{2})\b"
)

YEAR_RE = re.compile(
    r"\b(20\d{2})\b"
)


# ============================================================
# OUTILS
# ============================================================

def num(value):
    if not value:
        return None

    digits = re.sub(r"[^\d]", "", value)

    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


def clean_text(text):
    return " ".join(text.split())


def listing_id(url, title, price, year, km):
    raw = f"{url}|{title}|{price}|{year}|{km}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


# ============================================================
# EXTRACTION D'UNE ANNONCE
# ============================================================

def extract_listing(source, url, text):
    text = clean_text(text)

    # --------------------------------------------------------
    # Titre
    # --------------------------------------------------------

    title_match = TITLE_RE.search(text)

    if not title_match:
        return None

    title = title_match.group(0).strip()

    # --------------------------------------------------------
    # Prix
    # --------------------------------------------------------

    price = None

    price_match = re.search(
        r"CHF\s*([\d'’\s]{3,})",
        text,
        re.IGNORECASE,
    )

    if price_match:
        price = num(price_match.group(1))

    # --------------------------------------------------------
    # Kilométrage
    # --------------------------------------------------------

    km = None

    km_match = KM_RE.search(text)

    if km_match:
        km = num(km_match.group(1))

    # --------------------------------------------------------
    # Année
    # --------------------------------------------------------

    year = None

    # On privilégie les dates de première immatriculation
    date_matches = DATE_RE.findall(text)

    if date_matches:
        possible_years = [
            int(y)
            for y in date_matches
            if MIN_YEAR <= int(y) <= 2030
        ]

        if possible_years:
            year = possible_years[0]

    # Fallback
    if year is None:
        possible_years = [
            int(y)
            for y in YEAR_RE.findall(text)
            if 2000 <= int(y) <= 2030
        ]

        if possible_years:
            year = max(possible_years)

    # --------------------------------------------------------
    # Vérification des critères
    # --------------------------------------------------------

    if price is None:
        return None

    if km is None:
        return None

    if year is None:
        return None

    if year < MIN_YEAR:
        return None

    if km > MAX_KM:
        return None

    if price >= MAX_PRICE:
        return None

    uid = listing_id(
        url,
        title,
        price,
        year,
        km,
    )

    return {
        "id": uid,
        "source": source,
        "title": title,
        "price": price,
        "km": km,
        "year": year,
        "url": url,
    }


# ============================================================
# RECHERCHE AVEC PLAYWRIGHT
# ============================================================

def scrape_search_page(browser, source, search_url):
    listings = []

    page = browser.new_page(
        viewport={
            "width": 1440,
            "height": 1000,
        },
        locale="fr-CH",
    )

    try:
        print(f"[INFO] Ouverture: {search_url}")

        response = page.goto(
            search_url,
            wait_until="domcontentloaded",
            timeout=45_000,
        )

        if response:
            print(
                f"[INFO] HTTP {response.status} - {search_url}"
            )

        # Laisse le JavaScript de la page terminer son travail.
        page.wait_for_timeout(5_000)

        body_text = page.locator("body").inner_text()

        if "403 Forbidden" in body_text:
            raise RuntimeError(
                "Le site retourne encore 403 Forbidden."
            )

        # ----------------------------------------------------
        # Recherche des liens d'annonces
        # ----------------------------------------------------

        links = page.locator("a[href*='/d/']")

        count = links.count()

        print(
            f"[INFO] {count} liens d'annonces trouvés sur {source}"
        )

        seen_urls = set()

        for i in range(count):

            try:
                link = links.nth(i)

                href = link.get_attribute("href")

                if not href:
                    continue

                full_url = urljoin(
                    search_url,
                    href,
                )

                if full_url in seen_urls:
                    continue

                seen_urls.add(full_url)

                link_text = clean_text(
                    link.inner_text()
                )

                # On évite d'ouvrir les annonces qui ne semblent
                # pas concerner nos modèles.
                if not TITLE_RE.search(link_text):
                    continue

                print(
                    f"[INFO] Annonce candidate: {full_url}"
                )

                # ------------------------------------------------
                # Ouvre la page individuelle
                # ------------------------------------------------

                detail = browser.new_page(
                    viewport={
                        "width": 1440,
                        "height": 1000,
                    },
                    locale="fr-CH",
                )

                try:
                    detail.goto(
                        full_url,
                        wait_until="domcontentloaded",
                        timeout=45_000,
                    )

                    detail.wait_for_timeout(2_500)

                    text = detail.locator(
                        "body"
                    ).inner_text()

                    listing = extract_listing(
                        source,
                        full_url,
                        text,
                    )

                    if listing:
                        listings.append(listing)

                except Exception as e:
                    print(
                        f"[WARN] Erreur annonce {full_url}: {e}"
                    )

                finally:
                    detail.close()

            except Exception as e:
                print(
                    f"[WARN] Erreur lecture lien: {e}"
                )

    except PlaywrightTimeoutError:
        raise RuntimeError(
            f"Timeout lors du chargement de {search_url}"
        )

    finally:
        page.close()

    return listings


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(listing):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID absent."
        )

    message = (
        "🏍️ NOUVELLE BMW DÉTECTÉE !\n\n"
        f"🏷️ {listing['title']}\n"
        f"📅 {listing['year']}\n"
        f"🛣️ {listing['km']:,} km\n"
        f"💰 CHF {listing['price']:,}\n"
        f"🌐 {listing['source']}\n\n"
        f"🔗 {listing['url']}"
    ).replace(",", "'")

    url = (
        f"https://api.telegram.org/bot{token}/sendMessage"
    )

    response = requests.post(
        url,
        data={
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


# ============================================================
# MAIN
# ============================================================

def main():

    all_matches = []
    errors = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
        )

        try:

            for source, url in SEARCHES:

                try:

                    matches = scrape_search_page(
                        browser,
                        source,
                        url,
                    )

                    all_matches.extend(matches)

                except Exception as e:

                    errors.append(
                        f"{source}: {e}"
                    )

        finally:
            browser.close()

    # --------------------------------------------------------
    # Déduplication
    # --------------------------------------------------------

    unique = {}

    for listing in all_matches:
        unique[listing["id"]] = listing

    # --------------------------------------------------------
    # Chargement des annonces déjà vues
    # --------------------------------------------------------

    seen = set()

    if STATE_FILE.exists():

        try:
            seen = set(
                json.loads(
                    STATE_FILE.read_text(
                        encoding="utf-8"
                    )
                )
            )

        except Exception:
            seen = set()

    # --------------------------------------------------------
    # Nouvelles annonces
    # --------------------------------------------------------

    new_listings = [
        listing
        for listing in unique.values()
        if listing["id"] not in seen
    ]

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    telegram_errors = []

    for listing in new_listings:

        try:

            send_telegram(listing)

            print(
                f"[TELEGRAM] Envoyé: {listing['url']}"
            )

        except Exception as e:

            telegram_errors.append(
                f"Telegram: {e}"
            )

    # --------------------------------------------------------
    # Mise à jour du fichier seen.json
    # --------------------------------------------------------

    seen.update(unique.keys())

    STATE_FILE.write_text(
        json.dumps(
            sorted(seen),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    errors.extend(telegram_errors)

    # --------------------------------------------------------
    # Résultat GitHub Actions
    # --------------------------------------------------------

    result = {
        "new": new_listings,
        "total_matches": len(unique),
        "errors": errors,
    }

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
