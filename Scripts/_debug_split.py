"""Debug the block splitting."""
import requests
import re
import sys
sys.path.insert(0, r'c:\NCAA Model\Scripts')

URL = "https://www.covers.com/sports/ncaab/matchups?selectedDate=2026-02-18"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

r = requests.get(URL, headers=HEADERS, timeout=15)
html = r.text

print("HTML length:", len(html))

# Test split patterns
patterns_to_try = [
    r'class="gamebox-header"',
    r'gamebox-header',
    r'gamebox-time',
    r'scoring-and-betgraph',
]

for pat in patterns_to_try:
    count = len(re.findall(pat, html))
    print(f"Pattern '{pat}': {count} matches")

# Show what's around the first gamebox-header
m = re.search(r'gamebox-header', html)
if m:
    print("\nContext around 'gamebox-header':")
    start = max(0, m.start() - 100)
    end = min(len(html), m.end() + 300)
    print(repr(html[start:end]))
