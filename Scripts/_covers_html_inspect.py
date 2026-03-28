"""
Examine HTML structure of Covers.com game blocks.
"""
import requests
import re

URL = "https://www.covers.com/sports/ncaab/matchups?selectedDate=2026-02-18"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

r = requests.get(URL, headers=headers, timeout=15)
html = r.text

# Find the first "Cover By" occurrence and show big context
m = re.search(r'Cover By', html)
if m:
    start = max(0, m.start() - 3000)
    end = min(len(html), m.end() + 2000)
    with open('scripts/_covers_game_block.txt', 'w', encoding='utf-8') as f:
        f.write(html[start:end])
    print(f"Wrote context to scripts/_covers_game_block.txt ({end-start} chars)")
    print("\nContext around first 'Cover By':")
    print(html[max(0, m.start()-1500):m.end()+500])
