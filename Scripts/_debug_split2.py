"""Debug actual HTML pattern."""
import requests, re

URL = "https://www.covers.com/sports/ncaab/matchups?selectedDate=2026-02-18"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
r = requests.get(URL, headers=HEADERS, timeout=15)
html = r.text

# Find all occurrences of gamebox-header that appear in tag attributes
matches = [(m.start(), m.end()) for m in re.finditer(r'gamebox-header', html)]
print(f"Total 'gamebox-header' occurrences: {len(matches)}")

# Show context for positions 10-20 (skip CSS)
for pos, end in matches[10:14]:
    start = max(0, pos - 200)
    finish = min(len(html), end + 300)
    snippet = html[start:finish]
    if '<p' in snippet or '<div' in snippet:
        print(f"\n--- at pos {pos} ---")
        print(snippet)
        break

# Also find the gamebox-header elements directly
# Try with broader class patterns
test_patterns = [
    r'<p[^>]+gamebox-header[^>]*>',
    r'<\w+[^>]+gamebox-header[^>]*>',
    r'id="gamebox-header"',
    r'gamebox-header"',     # just "gamebox-header" followed by a quote
    r'"gamebox-header',
    r'Strong class="text-uppercase"',
    r'class="text-uppercase"',
]
for pat in test_patterns:
    n = len(re.findall(pat, html))
    if n > 0:
        print(f"'{pat}': {n} matches")
        m = re.search(pat, html)
        if m:
            print("  sample:", repr(html[max(0,m.start()-80):m.end()+200]))
