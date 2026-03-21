import json
import re
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

API_BASE = "https://ncaa-api.henrygd.me"

def norm(s: str) -> str:
    """Normalize for matching: lowercase, remove punctuation except () and spaces."""
    s = (s or "").lower().strip()
    s = s.replace("&", "and")
    s = re.sub(r"[^a-z0-9\s\(\)]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s

def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_today_ymd_central():
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y"), now.strftime("%m"), now.strftime("%d")

def extract_games(scoreboard_json: dict):
    """Extract using the exact structure proven by your screenshots."""
    games = []
    for item in scoreboard_json.get("games", []):
        game = item.get("game", {})
        game_id = game.get("gameID")  # confirmed by your screenshot
        away_short = (((game.get("away") or {}).get("names") or {}).get("short"))
        home_short = (((game.get("home") or {}).get("names") or {}).get("short"))
        away_seo = (((game.get("away") or {}).get("names") or {}).get("seo"))
        home_seo = (((game.get("home") or {}).get("names") or {}).get("seo"))
        url = game.get("url")  # like "/game/6501881"

        if game_id and away_short and home_short:
            games.append({
                "game_id": str(game_id),
                "away": away_short,
                "home": home_short,
                "away_seo": away_seo,
                "home_seo": home_seo,
                "url": url,
            })
    return games

def main():
    yyyy, mm, dd = get_today_ymd_central()
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"
    print(f"Fetching scoreboard: {url}\n")

    sb = fetch_json(url)
    games = extract_games(sb)

    if not games:
        print("Parsed 0 games. If this happens, paste the top-level keys and one games[0].game block.")
        sys.exit(2)

    print("All parsed games (today):")
    for g in games:
        print(f"- {g['away']} @ {g['home']} | gameID={g['game_id']} | url={g.get('url')}")

    # If user provided focus teams, filter
    if len(sys.argv) > 1:
        focus = [norm(x) for x in sys.argv[1:]]
        focus_set = set(focus)

        # Also allow matching against SEO slugs (handy if names differ like "Eastern Mich.")
        focus_set2 = focus_set.copy()

        print("\nMatches for your focus teams:")
        found = False
        for g in games:
            away_n = norm(g["away"])
            home_n = norm(g["home"])
            away_seo = norm(g.get("away_seo") or "")
            home_seo = norm(g.get("home_seo") or "")

            if (away_n in focus_set2) or (home_n in focus_set2) or (away_seo in focus_set2) or (home_seo in focus_set2):
                found = True
                print(f"- {g['away']} @ {g['home']} | gameID={g['game_id']}")

        if not found:
            print("No matches found.")
            print("Tip: try the exact display short names shown in the 'All parsed games' list.")

if __name__ == "__main__":
    main()
