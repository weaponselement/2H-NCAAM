"""Check the parent div data attributes."""
import requests, re

URL = "https://www.covers.com/sports/ncaab/matchups?selectedDate=2026-02-18"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get(URL, headers=HEADERS, timeout=15)
html = r.text

# Find a game container div by looking at what's just before id="gamebox-header"
m = re.search(r'id="gamebox-header"', html)
if m:
    start = max(0, m.start() - 1000)
    snippet = html[start:m.start() + 100]
    print("Container before gamebox-header:")
    print(snippet[-1000:])
