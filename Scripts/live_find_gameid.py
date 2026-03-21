import json
from datetime import datetime
from zoneinfo import ZoneInfo
import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def today_ymd_central():
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

def norm(s: str) -> str:
    return (s or "").lower().strip()

def main():
    yyyy, mm, dd = today_ymd_central()
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"

    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    sb = r.json()

    targets = {"army", "lafayette"}

    matches = []
    for item in sb.get("games", []):
        g = item.get("game", {})
        gid = str(g.get("gameID", ""))

        away = (g.get("away") or {}).get("names") or {}
        home = (g.get("home") or {}).get("names") or {}

        away_short = away.get("short")
        home_short = home.get("short")
        away_seo = away.get("seo")
        home_seo = home.get("seo")

        if not gid or not away_short or not home_short:
            continue

        pair = {norm(away_short), norm(home_short)}
        # also allow matching by seo if short differs
        pair2 = {norm(away_seo), norm(home_seo)}

        if targets.issubset(pair) or targets.issubset(pair2):
            matches.append({
                "gameID": gid,
                "away_short": away_short, "away_seo": away_seo,
                "home_short": home_short, "home_seo": home_seo,
                "url": g.get("url")
            })

    if not matches:
        print("No Army vs Lafayette match found on today's D1 men's scoreboard.")
        print("If this is not D1 or not in basketball-men/d1, tell me and we’ll adjust the path.")
        return

    print("Found match(es):")
    for m in matches:
        print(f"- gameID={m['gameID']} | {m['away_short']} ({m['away_seo']}) @ {m['home_short']} ({m['home_seo']}) | {m['url']}")

if __name__ == "__main__":
    main()