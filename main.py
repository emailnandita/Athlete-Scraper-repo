"""
Main entry point — runs all scrapers sequentially:
  1. Athlete results  -> athletes_results/{date}/
  2. Rankings         -> rankings_athletes/{date}/

Usage:
  python main.py              # scrape all athletes + rankings (2025, 2026)
  python main.py --limit 5    # only scrape first 5 athletes (for testing)
"""
import subprocess
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PYTHON = os.path.join(SCRIPT_DIR, "venv", "Scripts", "python.exe")

RANKING_YEARS = ["2025", "2026"]


def run_script(script, args=None):
    cmd = [PYTHON, os.path.join(SCRIPT_DIR, script)]
    if args:
        cmd.extend(args)
    print(f"\n{'='*60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, cwd=SCRIPT_DIR)
    return result.returncode


def main():
    # Parse --limit flag
    limit_args = []
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--limit" and i + 1 < len(sys.argv) - 1:
            limit_args = [sys.argv[i + 2]]

    # Step 1: Scrape athlete results
    print("\n>>> STEP 1: Scraping athlete results...")
    rc = run_script("scrape_results.py", limit_args)
    if rc != 0:
        print(f"WARNING: scrape_results.py exited with code {rc}")

    # Step 2: Scrape rankings for each year
    for year in RANKING_YEARS:
        print(f"\n>>> STEP 2: Scraping rankings for {year}...")
        rc = run_script("scrape_rankings.py", [year])
        if rc != 0:
            print(f"WARNING: scrape_rankings.py ({year}) exited with code {rc}")

    print("\n" + "=" * 60)
    print("  ALL DONE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
