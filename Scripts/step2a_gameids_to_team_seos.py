import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://ncaa-api.henrygd.me"
DATA_ROOT = r"C:\NCAA Model\data"
OUT_DIR = os.path.join(DATA_ROOT, "processed", "selected_games")
os.makedirs(OUT_DIR, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}

def today_ymd_central():
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

def fetch_scoreboard(yyyy, mm, dd):
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json(), url

def main():
    # Your selected games
    target_ids = {"6530691", "6503505", "6504404", "6504012"}

    yyyy, mm, dd = today_ymd_central()
    sb, src = fetch_scoreboard(yyyy, mm, dd)

    matches = []
    for item in sb.get("games", []):
        g = item.get("game", {})
        gid = str(g.get("gameID", ""))
        if gid not in target_ids:
            continue

        away = (g.get("away") or {}).get("names") or {}
        home = (g.get("home") or {}).get("names") or {}

        rec = {
            "gameID": gid,
            "away_short": away.get("short"),
            "away_seo": away.get("seo"),
            "home_short": home.get("short"),
            "home_seo": home.get("seo"),
            "url": g.get("url"),
            "scoreboard_source": src,
            "date": f"{yyyy}-{mm}-{dd}",
        }
        matches.append(rec)

    print(f"\nScoreboard source: {src}")
    print(f"Found {len(matches)} of {len(target_ids)} target games.\n")

    for m in matches:
        print(f"- gameID={m['gameID']} | {m['away_short']} ({m['away_seo']}) @ {m['home_short']} ({m['home_seo']})")

    # Save selection for reuse
    out_path = os.path.join(OUT_DIR, f"selected_games_{yyyy}-{mm}-{dd}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(matches, f, ensure_ascii=False, indent=2)

    print(f"\nSaved selection -> {out_path}\n")

    # If any are missing, tell user which
    found_ids = {m["gameID"] for m in matches}
    missing = sorted(list(target_ids - found_ids))
    if missing:
        print("Missing gameIDs (not found on today's scoreboard):")
        for gid in missing:
            print(f"  - {gid}")
        print("\nIf these are not today’s games, we’ll add a --date option next.\n")

if __name__ == "__main__":
    main()