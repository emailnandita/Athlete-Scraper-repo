import os
import json
import re
from datetime import date, datetime
from urllib.parse import parse_qs
from flask import Flask, request, jsonify
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

app = Flask(__name__)

BASE_URL = "https://iwf.sport/weightlifting_/athletes-bios/"
DEFAULT_URL = f"{BASE_URL}?athlete_name=&athlete_gender=all&athlete_nation=IND"

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
    soup = BeautifulSoup(html, "html.parser")
    athletes = []
    for card in soup.select("a.card[href*='athlete=']"):
        href = card.get("href", "")
        if "id=" not in href:
            continue
        qs = parse_qs(href.split("?")[-1])
        athlete_id = qs.get("id", [""])[0]
        profile_slug = qs.get("athlete", [""])[0]
        name_el = card.select_one(".title .text")
        full_name = name_el.get_text(strip=True) if name_el else ""
        dob_el = card.select_one(".normal__text")
        dob_text = dob_el.get_text(strip=True).replace("Born:", "").strip() if dob_el else ""
        country_el = card.select_one("strong")
        country_code = country_el.get_text(strip=True) if country_el else ""
        name_parts = full_name.rsplit(" ", 1) if full_name else ["", ""]
        if len(name_parts) == 2:
            first_name, last_name = name_parts[0], name_parts[1]
            if first_name.isupper() and not last_name.isupper():
                last_name, first_name = first_name, last_name
        else:
            first_name, last_name = full_name, ""
        athletes.append({
            "athlete_id": athlete_id, "profile_slug": profile_slug,
            "full_name": full_name, "first_name": first_name,
            "last_name": last_name, "country_code": country_code,
            "dob_text": dob_text, "href": href,
        })
    return athletes


def parse_dob(dob_text):
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(dob_text, fmt).date()
        except ValueError:
            continue
    return None


def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def scrape_profile(page, href):
    profile_url = BASE_URL + href if href.startswith("?") else href
    page.goto(profile_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")
    gender = ""
    current_category = ""
    page_text = soup.get_text(" ", strip=True)
    gender_match = re.search(r"Gender:\s*(Male|Female)", page_text, re.IGNORECASE)
    if gender_match:
        gender = gender_match.group(1).capitalize()
    category_matches = re.findall(r"Category:\s*(\d+\s*kg)", page_text)
    if category_matches:
        current_category = category_matches[0]
    return gender, current_category


@app.route("/", methods=["GET"])
def scrape():
    url = request.args.get("url", DEFAULT_URL)

    try:
        with Camoufox(headless=True) as browser:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_function(
                "document.title !== 'Just a moment...'",
                timeout=60000
            )
            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)
            listing_html = page.content()

            athletes_raw = parse_listing(listing_html)
            athletes = []

            for raw in athletes_raw:
                try:
                    gender, current_category = scrape_profile(page, raw["href"])
                except Exception:
                    gender, current_category = "", ""

                dob = parse_dob(raw["dob_text"])
                dob_str = dob.isoformat() if dob else ""
                age = calculate_age(dob) if dob else None
                cc = raw["country_code"]

                athletes.append({
                    "athlete_id": raw["athlete_id"],
                    "profile_slug": raw["profile_slug"],
                    "name": raw["full_name"],
                    "first_name": raw["first_name"],
                    "last_name": raw["last_name"],
                    "gender": gender,
                    "country": {"code": cc, "name": COUNTRY_NAMES.get(cc, cc)},
                    "dob": dob_str,
                    "age": age,
                    "current_category": current_category,
                    "team": COUNTRY_NAMES.get(cc, cc),
                })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"count": len(athletes), "athletes": athletes})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
