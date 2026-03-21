import json
import os
import csv
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

DATA_ROOT = r"C:\NCAA Model\data"
OUT_DIR = os.path.join(DATA_ROOT, "processed", "slates")
CACHE_DIR = os.path.join(DATA_ROOT, "cache", "scoreboard_daily")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

def today_central():
    now = datetime.now(ZoneInfo("America/Chicago"))
    return now.strftime("%Y-%m-%d")

def ymd_parts(date_str: str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

def fetch_scoreboard(date_str: str, use_cache: bool = True):
    yyyy, mm, dd = ymd_parts(date_str)
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"

    cache_path = os.path.join(CACHE_DIR, f"scoreboard_{date_str}.json")
    if use_cache and os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f), f"CACHE:{cache_path}"

    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    sb = r.json()

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(sb, f, ensure_ascii=False)

    return sb, f"FETCH:{url}"

def extract_games(sb: dict):
    games = []
    for item in sb.get("games", []):
        g = item.get("game", {})
        gid = str(g.get("gameID", "")).strip()
        if not gid:
            continue

        away = (g.get("away") or {}).get("names") or {}
        home = (g.get("home") or {}).get("names") or {}

        away_short = away.get("short") or away.get("seo") or ""
        home_short = home.get("short") or home.get("seo") or ""
        away_seo = away.get("seo") or ""
        home_seo = home.get("seo") or ""

        # optional fields vary by day
        # we store whatever is available without failing
        start_time = g.get("startTime") or g.get("startTimeEpoch") or g.get("gameTime") or ""
        network = g.get("network") or g.get("tvNetwork") or ""
        game_url = g.get("url") or f"/game/{gid}"

        games.append({
            "date": sb.get("date") or "",
            "gameID": gid,
            "away_short": away_short,
            "away_seo": away_seo,
            "home_short": home_short,
            "home_seo": home_seo,
            "start_time": start_time,
            "network": network,
            "url": game_url
        })
    return games

def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def write_csv(path, rows):
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

def main():
    parser = argparse.ArgumentParser(description="Get all D1 men's basketball game IDs for a date (NCAA via henrygd).")
    parser.add_argument("--date", type=str, default=today_central(), help="YYYY-MM-DD (default: today Central)")
    parser.add_argument("--no-cache", action="store_true", help="Do not use cached scoreboard JSON")
    parser.add_argument("--print", action="store_true", help="Print games to console")
    args = parser.parse_args()

    sb, source = fetch_scoreboard(args.date, use_cache=(not args.no_cache))
    games = extract_games(sb)

    out_json = os.path.join(OUT_DIR, f"slate_d1_{args.date}.json")
    out_csv  = os.path.join(OUT_DIR, f"slate_d1_{args.date}.csv")

    payload = {
        "run_date": args.date,
        "source": source,
        "count": len(games),
        "games": games
    }

    write_json(out_json, payload)
    write_csv(out_csv, games)

    print(f"\nD1 slate for {args.date}")
    print(f"Source: {source}")
    print(f"Games found: {len(games)}")
    print(f"Saved JSON: {out_json}")
    print(f"Saved CSV : {out_csv}\n")

    if args.print:
        for g in games:
            print(f"- {g['gameID']} | {g['away_short']} @ {g['home_short']} | url={g['url']}")

if __name__ == "__main__":
    main()