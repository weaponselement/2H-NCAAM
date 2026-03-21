import argparse
import json
import os
import time
from datetime import datetime
import requests
from paths import DATA_DIR

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DATA_ROOT = str(DATA_DIR)
BASELINE_FILE = os.path.join(DATA_ROOT, "processed", "baselines", "last4_2026-03-07.json")
PBP_ROOT = os.path.join(DATA_ROOT, "raw", "pbp")
LOG_DIR = os.path.join(DATA_ROOT, "logs")
os.makedirs(PBP_ROOT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)

def fetch_pbp(game_id: str):
    # Endpoint documented by the API for game PBP. [1](https://www.ncaa.com/news/basketball-men/article/2025-06-12/2026-march-madness-mens-ncaa-tournament-schedule-dates)
    url = f"{API_BASE}/game/{game_id}/play-by-play"
    r = requests.get(url, headers=HEADERS, timeout=45)
    return r.status_code, url, (r.json() if r.status_code == 200 else None), r.text

def main():
    baseline = load_json(BASELINE_FILE)
    run_date = baseline.get("run_date", "unknown-date")
    teams = baseline.get("teams", {})

    # Collect unique game IDs, but also track which team(s) reference each game
    game_to_teams = {}
    for team_seo, games in teams.items():
        for g in games:
            gid = str(g.get("gameID"))
            if not gid:
                continue
            game_to_teams.setdefault(gid, set()).add(team_seo)

    all_game_ids = sorted(game_to_teams.keys())
    total = len(all_game_ids)

    print(f"\nStep 3: Download baseline PBP")
    print(f"Baseline file: {BASELINE_FILE}")
    print(f"Run date: {run_date}")
    print(f"Unique baseline games to fetch: {total}\n")

    # Run log
    log = {
        "run_date": run_date,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": API_BASE,
        "total_games": total,
        "saved": [],
        "skipped_existing": [],
        "failed": []
    }

    # Rate limit (public host notes limits; keep it polite). [1](https://www.ncaa.com/news/basketball-men/article/2025-06-12/2026-march-madness-mens-ncaa-tournament-schedule-dates)
    sleep_seconds = 0.35  # ~3 req/sec

    for i, gid in enumerate(all_game_ids, start=1):
        teams_for_game = sorted(list(game_to_teams[gid]))
        # Save once per game, but place a copy under each team's folder for convenience
        # (This makes later per-team analysis simpler.)
        per_team_paths = [
            os.path.join(PBP_ROOT, t, f"{gid}.json") for t in teams_for_game
        ]

        # If all target paths exist, skip
        if all(os.path.exists(p) for p in per_team_paths):
            log["skipped_existing"].append({"gameID": gid, "teams": teams_for_game})
            print(f"[{i}/{total}] SKIP {gid} (already saved for {', '.join(teams_for_game)})")
            continue

        print(f"[{i}/{total}] FETCH {gid} for teams: {', '.join(teams_for_game)}")
        try:
            status, url, payload, raw_text = fetch_pbp(gid)
            if status != 200 or payload is None:
                # Don't crash; log failure and keep going
                log["failed"].append({
                    "gameID": gid,
                    "teams": teams_for_game,
                    "status": status,
                    "url": url,
                    "note": "Non-200 response or empty payload"
                })
                print(f"          FAIL status={status}")
            else:
                # Save payload under each team folder
                for path in per_team_paths:
                    save_json(path, payload)
                log["saved"].append({"gameID": gid, "teams": teams_for_game, "url": url})
                print(f"          OK saved -> {len(per_team_paths)} file(s)")
        except Exception as e:
            log["failed"].append({
                "gameID": gid,
                "teams": teams_for_game,
                "status": "exception",
                "error": str(e)
            })
            print(f"          EXCEPTION: {e}")

        time.sleep(sleep_seconds)

    log["finished_at"] = datetime.now().isoformat(timespec="seconds")

    log_path = os.path.join(LOG_DIR, f"pbp_download_{run_date}.json")
    save_json(log_path, log)

    print(f"\nDone.")
    print(f"Saved PBP root: {PBP_ROOT}")
    print(f"Run log: {log_path}\n")

    if log["failed"]:
        print("Some games failed to download PBP (this can happen due to upstream route availability).")
        print("We can re-run; it will skip existing files and only retry missing ones.\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download baseline play-by-play files")
    parser.add_argument(
        "--baseline",
        help="Path to baseline manifest JSON (last4_YYYY-MM-DD.json)",
        default=BASELINE_FILE
    )

    args = parser.parse_args()

    # Override baseline file if provided
    if args.baseline:
        globals()["BASELINE_FILE"] = args.baseline

    main()