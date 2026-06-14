import json
import re
from datetime import date, datetime
from urllib.parse import parse_qs
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

BASE_URL = "https://iwf.sport/weightlifting_/athletes-bios/"
LISTING_URL = f"{BASE_URL}?athlete_name=&athlete_gender=all&athlete_nation=IND"

# Country code to full name mapping (add more as needed)
COUNTRY_NAMES = {
    "IND": "India", "USA": "United States", "CHN": "China", "GBR": "Great Britain",
    "JPN": "Japan", "KOR": "Korea", "GER": "Germany", "FRA": "France",
    "AUS": "Australia", "CAN": "Canada", "BRA": "Brazil", "RUS": "Russia",
    "ITA": "Italy", "ESP": "Spain", "TUR": "Turkey", "IRN": "Iran",
    "THA": "Thailand", "PHI": "Philippines", "INA": "Indonesia", "MAS": "Malaysia",
    "VIE": "Vietnam", "MYA": "Myanmar", "TPE": "Chinese Taipei", "PRK": "DPR Korea",
    "UZB": "Uzbekistan", "KAZ": "Kazakhstan", "GEO": "Georgia", "ARM": "Armenia",
    "COL": "Colombia", "CUB": "Cuba", "MEX": "Mexico", "EGY": "Egypt",
    "NGR": "Nigeria", "RSA": "South Africa", "NZL": "New Zealand",
}


def parse_listing(html):
    """Parse the athlete listing page to extract basic info from cards."""
    soup = BeautifulSoup(html, "html.parser")
    athletes = []

    for card in soup.select("a.card[href*='athlete=']"):
        href = card.get("href", "")
        if "id=" not in href:
            continue

        # Extract athlete_id and profile_slug from URL
        qs = parse_qs(href.split("?")[-1])
        athlete_id = qs.get("id", [""])[0]
        profile_slug = qs.get("athlete", [""])[0]

        # Extract name from .title .text
        name_el = card.select_one(".title .text")
        full_name = name_el.get_text(strip=True) if name_el else ""

        # Extract DOB text
        dob_el = card.select_one(".normal__text")
        dob_text = dob_el.get_text(strip=True).replace("Born:", "").strip() if dob_el else ""

        # Extract country code
        country_el = card.select_one("strong")
        country_code = country_el.get_text(strip=True) if country_el else ""

        # Parse name into first/last
        name_parts = full_name.rsplit(" ", 1) if full_name else ["", ""]
        if len(name_parts) == 2:
            # IWF format: "LASTNAME Firstname" — last name is typically all-caps
            # But it could also be "FIRSTNAME LASTNAME" — detect by caps
            first_name, last_name = name_parts[0], name_parts[1]
            # If the first part is all uppercase and second is mixed, swap
            if first_name.isupper() and not last_name.isupper():
                last_name, first_name = first_name, last_name
        else:
            first_name, last_name = full_name, ""

        athletes.append({
            "athlete_id": athlete_id,
            "profile_slug": profile_slug,
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "country_code": country_code,
            "dob_text": dob_text,
            "href": href,
        })

    return athletes


def parse_dob(dob_text):
    """Parse DOB from text like 'January 01, 1986' or '2002-06-05'."""
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(dob_text, fmt).date()
        except ValueError:
            continue
    return None


def calculate_age(dob):
    """Calculate age from date of birth."""
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def scrape_profile(page, href):
    """Visit an athlete profile page and extract gender + current category."""
    profile_url = BASE_URL + href if href.startswith("?") else href

    page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(3000)

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    gender = ""
    current_category = ""

    # Look for the info line: "IND / Born: 2002-06-05 / Gender: Male"
    # It's typically in a <p> or text near the athlete name
    page_text = soup.get_text(" ", strip=True)

    gender_match = re.search(r"Gender:\s*(Male|Female)", page_text, re.IGNORECASE)
    if gender_match:
        gender = gender_match.group(1).capitalize()

    # Get current category from the most recent competition result
    # The results table shows Category values like "81 kg"
    category_matches = re.findall(r"Category:\s*([+]?\d+\s*kg)", page_text)
    if category_matches:
        # The first one in the table is the most recent
        current_category = category_matches[0]

    # Retry once if gender is missing (page may not have loaded fully)
    if not gender:
        page.reload(wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(4000)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        page_text = soup.get_text(" ", strip=True)

        gender_match = re.search(r"Gender:\s*(Male|Female)", page_text, re.IGNORECASE)
        if gender_match:
            gender = gender_match.group(1).capitalize()
        if not current_category:
            category_matches = re.findall(r"Category:\s*([+]?\d+\s*kg)", page_text)
            if category_matches:
                current_category = category_matches[0]

    return gender, current_category


def main():
    with Camoufox(headless=False) as browser:
        page = browser.new_page()

        # Step 1: Load the listing page
        print(f"Loading listing: {LISTING_URL}")
        page.goto(LISTING_URL, wait_until="domcontentloaded", timeout=120000)

        print("Waiting for Cloudflare to clear...")
        page.wait_for_function(
            "document.title !== 'Just a moment...'",
            timeout=60000
        )
        page.wait_for_load_state("networkidle", timeout=60000)
        page.wait_for_timeout(3000)

        print(f"Page title: {page.title()}")
        listing_html = page.content()

        # Save raw HTML for inspection
        with open("page.html", "w", encoding="utf-8") as f:
            f.write(listing_html)
        print("Saved raw HTML to page.html")

        # Step 2: Parse listing
        athletes_raw = parse_listing(listing_html)
        print(f"Found {len(athletes_raw)} athletes in listing")

        if not athletes_raw:
            print("No athletes found! Check page.html for debugging.")
            return

        # Step 3: Load existing progress if any
        athletes = []
        athletes_by_id = {}
        try:
            with open("athletes.json", "r", encoding="utf-8") as f:
                athletes = json.load(f)
                athletes_by_id = {a["athlete_id"]: a for a in athletes}
            print(f"Resuming: {len(athletes)} athletes already scraped")
        except (FileNotFoundError, json.JSONDecodeError):
            pass

        # Find athletes that need re-scraping (missing gender or category)
        needs_rescrape = {
            aid for aid, a in athletes_by_id.items()
            if not a.get("gender") or not a.get("current_category")
        }
        if needs_rescrape:
            print(f"Will re-scrape {len(needs_rescrape)} athletes with missing data")

        total = len(athletes_raw)

        for i, raw in enumerate(athletes_raw, 1):
            aid = raw["athlete_id"]
            is_retry = aid in needs_rescrape
            if aid in athletes_by_id and not is_retry:
                print(f"[{i}/{total}] Skipping (complete): {raw['full_name']}")
                continue
            print(f"[{i}/{total}] {'Re-scraping' if is_retry else 'Scraping'}: {raw['full_name']}...")

            try:
                gender, current_category = scrape_profile(page, raw["href"])
            except Exception as e:
                print(f"  Error scraping profile: {e}")
                gender, current_category = "", ""

            dob = parse_dob(raw["dob_text"])
            dob_str = dob.isoformat() if dob else ""
            age = calculate_age(dob) if dob else None
            country_code = raw["country_code"]

            athlete = {
                "athlete_id": raw["athlete_id"],
                "profile_slug": raw["profile_slug"],
                "name": raw["full_name"],
                "first_name": raw["first_name"],
                "last_name": raw["last_name"],
                "gender": gender,
                "country": {
                    "code": country_code,
                    "name": COUNTRY_NAMES.get(country_code, country_code),
                },
                "dob": dob_str,
                "age": age,
                "current_category": current_category,
                "team": COUNTRY_NAMES.get(country_code, country_code),
            }
            if is_retry:
                # Update existing entry in-place
                idx = next(j for j, a in enumerate(athletes) if a["athlete_id"] == aid)
                athletes[idx] = athlete
            else:
                athletes.append(athlete)

            # Save progress every 20 athletes
            if i % 20 == 0:
                with open("athletes.json", "w", encoding="utf-8") as f:
                    json.dump(athletes, f, indent=2, ensure_ascii=False)
                print(f"  Progress saved ({i}/{total})")

    # Final save
    with open("athletes.json", "w", encoding="utf-8") as f:
        json.dump(athletes, f, indent=2, ensure_ascii=False)
    print(f"\nDone! Saved {len(athletes)} athletes to athletes.json")


if __name__ == "__main__":
    main()
