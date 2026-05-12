import json
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

URL = "https://iwf.sport/weightlifting_/athletes-bios/?athlete_name=&athlete_gender=all&athlete_nation=IND"

with Camoufox(headless=False) as browser:
    page = browser.new_page()

    print(f"Loading: {URL}")
    page.goto(URL, wait_until="domcontentloaded", timeout=120000)

    # Wait until Cloudflare challenge is gone (page title changes from "Just a moment...")
    print("Waiting for Cloudflare to clear...")
    page.wait_for_function(
        "document.title !== 'Just a moment...'",
        timeout=60000
    )

    # Wait for actual page content to settle
    page.wait_for_load_state("networkidle", timeout=60000)
    page.wait_for_timeout(3000)

    print(f"Page title: {page.title()}")
    html = page.content()

# Save raw HTML for inspection
with open("page.html", "w", encoding="utf-8") as f:
    f.write(html)
print("Saved raw HTML to page.html")

# Parse athletes
soup = BeautifulSoup(html, "html.parser")

athletes = []

for card in soup.select("a[href*='athlete']"):
    name = card.get_text(strip=True)
    href = card.get("href", "")
    if name:
        athletes.append({"name": name, "url": href})

if not athletes:
    for row in soup.select("tr, .athlete, .bio, article"):
        text = row.get_text(" ", strip=True)
        if text:
            athletes.append({"text": text})

print(f"Found {len(athletes)} athlete entries")

with open("athletes.json", "w", encoding="utf-8") as f:
    json.dump(athletes, f, indent=2, ensure_ascii=False)
print("Saved to athletes.json")
