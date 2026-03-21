import json
import os
import re
import time
from typing import Dict, List, Optional, Tuple

import requests

API_BASE = "https://ncaa-api.henrygd.me"

DATA_ROOT = r"C:\NCAA Model\data"
SCHEDULE_CACHE_DIR = os.path.join(DATA_ROOT, "cache", "team_schedules")
GAME_CACHE_DIR = os.path.join(DATA_ROOT, "cache", "games")

HEADERS = {"User-Agent": "Mozilla/5.0"}

def ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def save_json(path: str, obj: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)

def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def fetch_json(url: str, timeout: int = 30) -> dict:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()

def extract_team_seos(game_json: dict) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Try to pull stable team slugs (seo) and display names from the /game/{id} payload.
    We’ll print what we find; if fields differ, you’ll paste the output and we’ll adjust.
    """
    g = game_json.get("game", game_json)

    away = (g.get("away") or {}).get("names") or {}
    home = (g.get("home") or {}).get("names") or {}

    away_seo = away.get("seo")
    home_seo = home.get("seo")
    away_name = away.get("short") or away.get("full") or away_seo
    home_name = home.get("short") or home.get("full") or home_seo

    return away_seo, home_seo, away_name, home_name

def looks_like_schedule(payload: dict, team_seo: str) -> bool:
    """
    Heuristic check: schedule payload usually contains a list of games/contests and/or the team seo/name.
    We don’t assume exact keys yet—just enough to confirm we hit a schedule endpoint.
    """
    s = json.dumps(payload)[:20000].lower()
    if team_seo.lower() in s:
        return True
    # common schedule-ish keys
    for k in ["schedule", "games", "contests", "season", "opponents"]:
        if k in payload:
            return True
    return False

def candidate_schedule_paths(team_seo: str) -> List[str]:
    """
    These are common NCAA.com patterns. The henrygd wrapper works by mirroring NCAA.com paths. [2](https://github.com/henrygd/ncaa-api)[1](https://ncaa-api.henrygd.me/openapi)
    We’ll try several and stop on the first that returns schedule-like JSON.
    """
    return [
        f"/team/{team_seo}/schedule/basketball-men/d1",
        f"/team/{team_seo}/schedule",
        f"/teams/basketball-men/d1/{team_seo}/schedule",
        f"/teams/basketball-men/d1/{team_seo}",
        f"/schools/{team_seo}/basketball-men/schedule",
        f"/schools/{team_seo}/basketball-men",
    ]

def try_find_schedule(team_seo: str) -> Tuple[Optional[str], Optional[dict]]:
    for path in candidate_schedule_paths(team_seo):
        url = API_BASE + path
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            if r.status_code != 200:
                continue
            payload = r.json()
            if looks_like_schedule(payload, team_seo):
                return path, payload
        except Exception:
            continue
        finally:
            time.sleep(0.25)  # be polite to the public host
    return None, None

def main():
    ensure_dir(SCHEDULE_CACHE_DIR)
    ensure_dir(GAME_CACHE_DIR)

    game_ids = ["6530691", "6503505", "6504404", "6504012"]

    # 1) Pull game metadata for each selected game ID via /game/{id} [1](https://ncaa-api.henrygd.me/openapi)
    # 2) Extract team seos
    # 3) For each team, discover schedule endpoint and save JSON

    all_teams = {}  # seo -> display name

    print("\n=== STEP 2: Pull selected games and extract team SEO slugs ===\n")
    for gid in game_ids:
        game_url = f"{API_BASE}/game/{gid}"
        cache_file = os.path.join(GAME_CACHE_DIR, f"game_{gid}.json")

        if os.path.exists(cache_file):
            game_json = load_json(cache_file)
            source = "CACHE"
        else:
            game_json = fetch_json(game_url)
            save_json(cache_file, game_json)
            source = "FETCH"

        away_seo, home_seo, away_name, home_name = extract_team_seos(game_json)

        print(f"Game {gid} ({source}): away={away_name} seo={away_seo} | home={home_name} seo={home_seo}")

        if away_seo:
            all_teams[away_seo] = away_name
        if home_seo:
            all_teams[home_seo] = home_name

    print("\n=== STEP 2: Discover team schedule endpoints (stop on first match) ===\n")

    for team_seo, team_name in sorted(all_teams.items()):
        schedule_cache = os.path.join(SCHEDULE_CACHE_DIR, f"schedule_{team_seo}.json")

        if os.path.exists(schedule_cache):
            print(f"[SKIP] {team_name} ({team_seo}) schedule already cached: {schedule_cache}")
            continue

        path, payload = try_find_schedule(team_seo)
        if path and payload:
            save_json(schedule_cache, payload)
            print(f"[FOUND] {team_name} ({team_seo}) schedule endpoint: {path}")
            print(f"        saved -> {schedule_cache}")
        else:
            print(f"[MISS ] {team_name} ({team_seo}) could not find a working schedule endpoint from candidates.")
            print("        We’ll fix this by inspecting the /game/{id} JSON for a direct schedule URL field.\n")

if __name__ == "__main__":
    main()