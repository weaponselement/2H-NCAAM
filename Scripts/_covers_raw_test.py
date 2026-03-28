"""
Test what raw HTML Covers.com delivers for NCAAB matchups.
Examine if game data is server-rendered or JS-rendered.
"""
import requests
import re

URL = "https://www.covers.com/sports/ncaab/matchups?selectedDate=2026-02-18"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

print("Fetching Covers.com page...")
r = requests.get(URL, headers=headers, timeout=15)
print(f"Status: {r.status_code}")
print(f"Content-Length: {len(r.text)}")

# Check if game data appears (look for array keywords in script tags)
html = r.text

# Look for key signals of server-rendered data
print("\nLooking for spread/total data...")
patterns = [
    (r'"spread"', "spread field"),
    (r'"total"', "total field"),
    (r'bookSpread', "bookSpread"),
    (r'awayScore', "awayScore"),
    (r'"odds"', "odds field"),
    (r'Cover By', "Cover By text"),
    (r'o/u Margin', "o/u Margin text"),
    (r'"away".*?"home"', "away/home pair"),
    (r'__NEXT_DATA__', "NextJS data"),
    (r'window\.__', "window globals"),
    (r'window\.initial', "window.initial"),
    (r'"gameEvents"', "gameEvents"),
    (r'"matchups"', "matchups key"),
    (r'"homeTeam"', "homeTeam key"),
    (r'"awayTeam"', "awayTeam key"),
    (r'"spreadHome"', "spreadHome"),
    (r'"spreadAway"', "spreadAway"),
    (r'"bookOdds"', "bookOdds"),
    (r'"gameTotal"', "gameTotal"),
    (r'"gameId"', "gameId"),
    (r'"coversByDate"', "coversByDate"),
]

for pat, desc in patterns:
    m = re.search(pat, html)
    if m:
        # Show context
        start = max(0, m.start() - 30)
        end = min(len(html), m.end() + 80)
        print(f"  [{desc}] found: ...{repr(html[start:end])}...")

# Save first 5000 and last 2000 chars for inspection
print("\n=== First 3000 chars ===")
print(html[:3000])
print("\n=== Last 2000 chars ===")
print(html[-2000:])
