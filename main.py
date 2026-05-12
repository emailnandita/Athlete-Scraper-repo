import os
import json
from flask import Flask, request, jsonify
from camoufox.sync_api import Camoufox
from bs4 import BeautifulSoup

app = Flask(__name__)

DEFAULT_URL = "https://iwf.sport/weightlifting_/athletes-bios/?athlete_name=&athlete_gender=all&athlete_nation=IND"


@app.route("/", methods=["GET"])
def scrape():
    url = request.args.get("url", DEFAULT_URL)

    try:
        with Camoufox(headless=True) as browser:
            page = browser.new_page()

            page.goto(url, wait_until="domcontentloaded", timeout=120000)

            # Wait for Cloudflare challenge to clear
            page.wait_for_function(
                "document.title !== 'Just a moment...'",
                timeout=60000
            )

            page.wait_for_load_state("networkidle", timeout=60000)
            page.wait_for_timeout(3000)

            html = page.content()

    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

    return jsonify({"count": len(athletes), "athletes": athletes})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
