import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

DATA_ROOT = r"C:\NCAA Model\data"
SCOREBOARD_CACHE = os.path.join(DATA_ROOT, "cache", "scoreboard_daily")
BASELINE_OUTDIR = os.path.join(DATA_ROOT, "processed", "baselines")

os.makedirs(SCOREBOARD_CACHE, exist_ok=True)
os.makedirs(BASELINE_OUTDIR, exist_ok=True)

def load_selected_games(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def ymd(dt: datetime):
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")

def cache_path_for_date(dt: datetime):
    return os.path.join(SCOREBOARD_CACHE, f"scoreboard_{dt.strftime('%Y-%m-%d')}.json")

def fetch_scoreboard(dt: datetime):
    yyyy, mm, dd = ymd(dt)
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json(), url

def load_or_fetch_scoreboard(dt: datetime):
    cp = cache_path_for_date(dt)
    if os.path.exists(cp):
        with open(cp, "r", encoding="utf-8") as f:
            return json.load(f), f"CACHE:{cp}"
    sb, url = fetch_scoreboard(dt)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(sb, f, ensure_ascii=False)
    return sb, f"FETCH:{url}"

def is_completed_game(game_obj: dict) -> bool:
    """
    Scoreboard payloads vary by sport/season.
    We use conservative checks:
      - explicit gameState/status indicates final/complete
      - OR both scores exist and are numeric (common for finals)
    """
    g = game_obj

    # common status fields
    for key in ["gameState", "status", "state"]:
        val = (g.get(key) or "")
        if isinstance(val, str) and val.lower() in ("final", "complete", "completed"):
            return True

    # sometimes nested status
    status = g.get("gameStatus") or g.get("status") or {}
    if isinstance(status, dict):
        st = (status.get("state") or status.get("status") or "")
        if isinstance(st, str) and st.lower() in ("final", "complete", "completed"):
            return True

    # fallback: numeric scores present (works for most completed games)
    away_score = (g.get("away") or {}).get("score")
    home_score = (g.get("home") or {}).get("score")

    def looks_numeric(x):
        if x is None: return False
        if isinstance(x, int): return True
        if isinstance(x, str) and x.strip().isdigit(): return True
        return False

    return looks_numeric(away_score) and looks_numeric(home_score)

def extract_games_for_teams(sb_json: dict, team_seos: set):
    """
    From a day's scoreboard, return a list of completed games where either home or away seo matches.
    """
    hits = []
    for item in sb_json.get("games", []):
        g = (item.get("game") or {})
        gid = str(g.get("gameID") or "")

        away_names = ((g.get("away") or {}).get("names") or {})
        home_names = ((g.get("home") or {}).get("names") or {})
        away_seo = away_names.get("seo")
        home_seo = home_names.get("seo")

        if not gid or not away_seo or not home_seo:
            continue

        if away_seo not in team_seos and home_seo not in team_seos:
            continue

        if not is_completed_game(g):
            continue

        hits.append({
            "gameID": gid,
            "away_seo": away_seo,
            "away_short": away_names.get("short"),
            "away_score": (g.get("away") or {}).get("score"),
            "home_seo": home_seo,
            "home_short": home_names.get("short"),
            "home_score": (g.get("home") or {}).get("score"),
            "url": g.get("url"),
        })

    return hits

def main():
    selected_path = os.path.join(DATA_ROOT, "processed", "selected_games", "selected_games_2026-02-24.json")
    selected = load_selected_games(selected_path)

    run_date = selected[0]["date"]  # "2026-02-24"
    anchor = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo("America/Chicago"))

    # collect unique teams
    team_seos = set()
    for g in selected:
        team_seos.add(g["away_seo"])
        team_seos.add(g["home_seo"])

    # storage for last4
    last4 = {seo: [] for seo in team_seos}
    seen_game_ids = {seo: set() for seo in team_seos}

    # start searching from the day BEFORE the selected slate
    dt = anchor - timedelta(days=1)

    max_days_back = 90   # adjust if you want
    days_checked = 0

    print(f"\nFinding last 4 completed games per team (before {run_date})")
    print(f"Teams: {', '.join(sorted(team_seos))}\n")

    while days_checked < max_days_back:
        # stop early if all teams have 4
        if all(len(last4[seo]) >= 4 for seo in team_seos):
            break

        sb, src = load_or_fetch_scoreboard(dt)
        hits = extract_games_for_teams(sb, team_seos)

        if hits:
            # add games to appropriate teams
            for h in hits:
                # for away team
                if h["away_seo"] in team_seos and len(last4[h["away_seo"]]) < 4:
                    if h["gameID"] not in seen_game_ids[h["away_seo"]]:
                        seen_game_ids[h["away_seo"]].add(h["gameID"])
                        last4[h["away_seo"]].append({
                            "date": dt.strftime("%Y-%m-%d"),
                            "gameID": h["gameID"],
                            "opponent_seo": h["home_seo"],
                            "home_away": "away",
                            "score_for": h["away_score"],
                            "score_against": h["home_score"],
                            "url": h["url"],
                        })

                # for home team
                if h["home_seo"] in team_seos and len(last4[h["home_seo"]]) < 4:
                    if h["gameID"] not in seen_game_ids[h["home_seo"]]:
                        seen_game_ids[h["home_seo"]].add(h["gameID"])
                        last4[h["home_seo"]].append({
                            "date": dt.strftime("%Y-%m-%d"),
                            "gameID": h["gameID"],
                            "opponent_seo": h["away_seo"],
                            "home_away": "home",
                            "score_for": h["home_score"],
                            "score_against": h["away_score"],
                            "url": h["url"],
                        })

        dt -= timedelta(days=1)
        days_checked += 1

    # report
    print("Results (most recent first within the search window):")
    for seo in sorted(team_seos):
        print(f"\n{seo}: found {len(last4[seo])}/4")
        for rec in last4[seo]:
            print(f"  - {rec['date']} gameID={rec['gameID']} vs {rec['opponent_seo']} ({rec['home_away']}) "
                  f"{rec['score_for']}-{rec['score_against']}")

    out = {
        "run_date": run_date,
        "source": "scoreboard_backfill",
        "max_days_back": max_days_back,
        "teams": {seo: last4[seo] for seo in sorted(team_seos)}
    }

    out_path = os.path.join(BASELINE_OUTDIR, f"last4_{run_date}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"\nSaved baseline manifest -> {out_path}\n")

    # fail-fast warning if any team missing
    missing = [seo for seo in team_seos if len(last4[seo]) < 4]
    if missing:
        print("WARNING: Some teams did not reach 4 completed games within the search window:")
        for seo in sorted(missing):
            print(f"  - {seo} ({len(last4[seo])}/4)")
        print("If needed, increase max_days_back.\n")

if __name__ == "__main__":
    main()