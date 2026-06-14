import json
import os
import re
from datetime import date, datetime
from urllib.parse import parse_qs
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

BASE_URL = "https://iwf.sport/weightlifting_/athletes-bios/"


def load_athletes(path="athletes.json"):
    """Load athletes from JSON and build href for each."""
    with open(path, "r", encoding="utf-8") as f:
        athletes = json.load(f)
    for a in athletes:
        a["href"] = f"?athlete={a['profile_slug']}&id={a['athlete_id']}"
    return athletes


def clean_text(el):
    """Get text from element, stripping mobile-only label prefixes."""
    if not el:
        return ""
    text = el.get_text(strip=True)
    # Remove mobile label prefixes like "Rank: ", "Category: ", etc.
    text = re.sub(r"^(Rank|Category|BWT|Snatch|CI&Jerk|Total|Date):\s*", "", text)
    return text


def parse_competition_cards(soup):
    """Parse competition result cards from the athlete profile page.

    Structure: div.cards > div.card (skip .card__legend)
    Each card row has:
      - <a> with event name + date
      - <div> with rank, category, bwt, snatch, c&j, total in p.normal__text
    """
    competitions = []

    cards_container = soup.select_one(".cards")
    if not cards_container:
        return competitions

    for card in cards_container.select("div.card:not(.card__legend)"):
        comp = {}

        # Event name + date from the <a> link
        title_link = card.select_one("a.title")
        if title_link:
            comp["event_url"] = title_link.get("href", "")

            name_el = title_link.select_one(".col-7 p.title")
            comp["event_name"] = clean_text(name_el)

            date_el = title_link.select_one(".col-5 p.title")
            comp["date"] = clean_text(date_el)

        # Stats are in the <div> sibling (not the <a>) with class col-md-6
        stats_div = card.select_one("div.col-md-6.not__cell__767__full")
        if stats_div:
            p_tags = stats_div.select("p.normal__text")
            texts = [clean_text(p) for p in p_tags]

            # Order: Rank, Category, BWT, Snatch, CI&Jerk, Total
            if len(texts) >= 6:
                comp["rank"] = texts[0]
                comp["category"] = texts[1]
                comp["bodyweight"] = texts[2]
                comp["snatch"] = texts[3]
                comp["clean_and_jerk"] = texts[4]
                comp["total"] = texts[5]

        if comp.get("event_name"):
            competitions.append(comp)

    return competitions


def group_by_year(competitions):
    """Group competitions by year extracted from date."""
    by_year = {}
    for comp in competitions:
        date_str = comp.get("date", "")
        year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
        year = year_match.group(0) if year_match else "unknown"
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(comp)
    return by_year


def scrape_athlete_results(page, athlete):
    """Scrape full competition results for one athlete."""
    href = athlete["href"]
    profile_url = BASE_URL + href if href.startswith("?") else href

    print(f"  Loading profile: {profile_url}")
    page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(5000)

    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Extract basic info
    page_text = soup.get_text(" ", strip=True)
    gender = ""
    gender_match = re.search(r"Gender:\s*(Male|Female)", page_text, re.IGNORECASE)
    if gender_match:
        gender = gender_match.group(1).capitalize()

    dob = ""
    dob_match = re.search(r"Born:\s*(\d{4}-\d{2}-\d{2})", page_text)
    if dob_match:
        dob = dob_match.group(1)

    country_code = ""
    country_match = re.search(r"([A-Z]{3})\s*/\s*Born:", page_text)
    if country_match:
        country_code = country_match.group(1)

    # Parse competition cards
    competitions = parse_competition_cards(soup)
    competitions_by_year = group_by_year(competitions)

    return {
        "athlete_id": athlete["athlete_id"],
        "name": athlete["name"],
        "gender": gender,
        "dob": dob,
        "country_code": country_code,
        "total_competitions": len(competitions),
        "results_by_year": competitions_by_year,
        "results": competitions,
    }


def save_athlete_result(output_dir, result):
    """Save a single athlete's results as {athlete_id}.json containing an array of competitions."""
    athlete_id = result["athlete_id"]
    filepath = os.path.join(output_dir, f"{athlete_id}.json")

    # Build the array: each competition object includes athlete info + competition data
    records = []
    for comp in result.get("results", []):
        record = {
            "athlete_id": result["athlete_id"],
            "name": result["name"],
            "gender": result["gender"],
            "dob": result["dob"],
            "country_code": result["country_code"],
            "event_url": comp.get("event_url", ""),
            "event_name": comp.get("event_name", ""),
            "date": comp.get("date", ""),
            "rank": comp.get("rank", ""),
            "category": comp.get("category", ""),
            "bodyweight": comp.get("bodyweight", ""),
            "snatch": comp.get("snatch", ""),
            "clean_and_jerk": comp.get("clean_and_jerk", ""),
            "total": comp.get("total", ""),
        }
        records.append(record)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    return filepath


def main():
    import sys
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    athletes = load_athletes("athletes.json")
    if limit:
        athletes = athletes[:limit]
    total = len(athletes)
    print(f"Starting competition results scraper for {total} athletes...")

    # Create output folder: athletes_results/{today's date}
    today_str = date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join("athletes_results", today_str)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output folder: {output_dir}")

    with Camoufox(headless=False) as browser:
        page = browser.new_page()

        # First bypass Cloudflare on the main page
        print("Loading main page to bypass Cloudflare...")
        page.goto(
            BASE_URL + "?athlete_name=&athlete_gender=all&athlete_nation=IND",
            wait_until="domcontentloaded",
            timeout=120000,
        )
        page.wait_for_function(
            "document.title !== 'Just a moment...'",
            timeout=60000,
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(5000)
        print(f"Main page loaded: {page.title()}")

        # Skip already scraped athletes (resume support)
        already_done = set(f.replace(".json", "") for f in os.listdir(output_dir) if f.endswith(".json"))
        skipped = 0

        for i, athlete in enumerate(athletes, 1):
            if athlete["athlete_id"] in already_done:
                skipped += 1
                continue
            print(f"\n[{i}/{total}] (skipped {skipped}) Scraping: {athlete['name']}")
            try:
                result = scrape_athlete_results(page, athlete)
                filepath = save_athlete_result(output_dir, result)
                print(f"  Found {result['total_competitions']} competitions -> {filepath}")
                for year, comps in result["results_by_year"].items():
                    print(f"    {year}: {len(comps)} competitions")
                    for c in comps:
                        print(f"      - {c.get('event_name', '?')} | Cat: {c.get('category', '?')} | "
                              f"Snatch: {c.get('snatch', '?')} | C&J: {c.get('clean_and_jerk', '?')} | "
                              f"Total: {c.get('total', '?')} | Rank: {c.get('rank', '?')}")
            except Exception as e:
                print(f"  Error: {e}")
                import traceback
                traceback.print_exc()
                # Save error file too so we know which athletes failed
                error_data = [{
                    "athlete_id": athlete["athlete_id"],
                    "name": athlete["name"],
                    "error": str(e),
                }]
                error_path = os.path.join(output_dir, f"{athlete['athlete_id']}.json")
                with open(error_path, "w", encoding="utf-8") as f:
                    json.dump(error_data, f, indent=2, ensure_ascii=False)

    print(f"\nDone! Results saved in: {output_dir}")


if __name__ == "__main__":
    main()
