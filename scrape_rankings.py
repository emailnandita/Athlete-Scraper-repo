import json
import os
import re
import sys
from datetime import date, datetime
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

RANKING_URL = "https://iwf.sport/results/ranking-list/"

AGE_GROUPS = ["Senior", "Junior", "Youth"]
GENDERS = ["Men", "Women"]


def build_url(age_group, gender, year="2025"):
    """Build ranking list URL with filters (category=all loads all at once)."""
    return (
        f"{RANKING_URL}?ranking_category=all"
        f"&ranking_year={year}"
        f"&ranking_agegroup={age_group}"
        f"&ranking_gender={gender}"
        f"&ranking_lifter=all"
    )


def to_utc_date(date_str):
    """Convert 'May 01, 1999' to '1999-05-01T00:00:00Z' UTC format."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%b %d, %Y")
        return dt.strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        return date_str


def clean_text(el):
    """Get text from element, stripping mobile-only label prefixes."""
    if not el:
        return ""
    text = el.get_text(strip=True)
    text = re.sub(
        r"^(Rank|Name|Nation|Born|B\.weight|Snatch|CI&Jerk|Total|Event place & date):\s*",
        "", text
    )
    return text


def parse_ranking_cards(soup, age_group, gender):
    """Parse ranking cards from the page.

    Card structure:
      div.card > div.container > div.row
        col-md-4: Rank (col-1), Name (col-7), Nation/flag (col-4)
        col-md-3: Born (col-7), Bodyweight (col-5)
        col-md-2: Snatch (col-4), C&J (col-4), Total (col-4)
        col-md-3: Event place & date (col-12)
    """
    athletes = []
    cards = soup.select("div.card:not(.card__legend)")

    for card in cards:
        # --- col-md-4: Rank, Name, Nation ---
        title_section = card.select_one("div.col-md-4.title")
        if not title_section:
            continue

        cols_title = title_section.select("div[class*='col-']")
        rank = ""
        name = ""
        nation = ""

        for col in cols_title:
            classes = col.get("class", [])
            if "col-1" in classes:
                rank = clean_text(col)
            elif "col-7" in classes:
                name = clean_text(col)
            elif "col-4" in classes:
                img = col.select_one("img")
                if img:
                    nation = img.get("alt", "").strip()
                if not nation:
                    strong = col.select_one("strong")
                    nation = strong.get_text(strip=True) if strong else clean_text(col)

        # --- col-md-3 (first): Born, Bodyweight ---
        info_sections = card.select("div.col-md-3.print__3")
        born = ""
        bodyweight = ""
        event = ""

        if len(info_sections) >= 1:
            info_cols = info_sections[0].select("div[class*='col-']")
            for col in info_cols:
                classes = col.get("class", [])
                if "col-7" in classes:
                    born = clean_text(col)
                elif "col-5" in classes:
                    bodyweight = clean_text(col)

        # --- col-md-3 (second): Event place & date ---
        if len(info_sections) >= 2:
            event = clean_text(info_sections[1])

        # --- col-md-2: Snatch, C&J, Total ---
        stats_section = card.select_one("div.col-md-2.print__2")
        snatch = ""
        clean_jerk = ""
        total = ""

        if stats_section:
            stat_cols = stats_section.select("div.col-4")
            if len(stat_cols) >= 3:
                snatch = clean_text(stat_cols[0])
                clean_jerk = clean_text(stat_cols[1])
                total = clean_text(stat_cols[2])

        if name:
            athletes.append({
                "rank": rank,
                "name": name,
                "nation": nation,
                "born": to_utc_date(born),
                "bodyweight": bodyweight,
                "snatch": snatch,
                "clean_and_jerk": clean_jerk,
                "total": total,
                "event": event,
                "gender": gender,
                "age_group": age_group,
            })

    return athletes


def scrape_rankings_for_age_group(page, age_group, year="2025"):
    """Scrape all rankings for a given age group (both genders)."""
    all_athletes = []

    for gender in GENDERS:
        url = build_url(age_group, gender, year)
        print(f"  [{gender}] Loading: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(5000)

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        athletes = parse_ranking_cards(soup, age_group, gender)
        print(f"    Found {len(athletes)} ranked athletes")
        all_athletes.extend(athletes)

    return all_athletes


def main():
    # Usage: python scrape_rankings.py [year] [age_group]
    # e.g.: python scrape_rankings.py 2026
    # e.g.: python scrape_rankings.py 2026 Senior
    year = sys.argv[1] if len(sys.argv) > 1 else "2025"
    only_group = sys.argv[2] if len(sys.argv) > 2 else None
    groups_to_scrape = [only_group] if only_group else AGE_GROUPS

    script_dir = os.path.dirname(os.path.abspath(__file__))
    today_str = date.today().strftime("%Y-%m-%d")
    output_dir = os.path.join(script_dir, "rankings_athletes", today_str)
    os.makedirs(output_dir, exist_ok=True)
    print(f"Output folder: {output_dir}")

    with Camoufox(headless=False) as browser:
        page = browser.new_page()

        # Bypass Cloudflare
        print("Loading rankings page to bypass Cloudflare...")
        page.goto(
            build_url("Senior", "Men", year),
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
        print(f"Page loaded: {page.title()}")

        for group in groups_to_scrape:
            print(f"\n=== Scraping {group} rankings ===")
            athletes = scrape_rankings_for_age_group(page, group, year)

            filepath = os.path.join(output_dir, f"{group.lower()}_{year}.json")
            os.makedirs(output_dir, exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(athletes, f, indent=2, ensure_ascii=False)
            print(f"  Saved {len(athletes)} athletes -> {filepath}")

    print(f"\nDone! Rankings saved in: {output_dir}")


if __name__ == "__main__":
    main()
