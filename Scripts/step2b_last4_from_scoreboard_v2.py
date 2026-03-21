import argparse
import json
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DEFAULT_DATA_ROOT = r"C:\NCAA Model\data"


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def ymd(dt: datetime):
    return dt.strftime("%Y"), dt.strftime("%m"), dt.strftime("%d")


def cache_path_for_date(cache_root: str, dt: datetime):
    return os.path.join(cache_root, f"scoreboard_{dt.strftime('%Y-%m-%d')}.json")


def fetch_scoreboard(dt: datetime):
    yyyy, mm, dd = ymd(dt)
    url = f"{API_BASE}/scoreboard/basketball-men/d1/{yyyy}/{mm}/{dd}"
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json(), url


def load_or_fetch_scoreboard(cache_root: str, dt: datetime):
    cp = cache_path_for_date(cache_root, dt)
    if os.path.exists(cp):
        with open(cp, "r", encoding="utf-8") as f:
            return json.load(f), f"CACHE:{cp}"
    sb, url = fetch_scoreboard(dt)
    os.makedirs(os.path.dirname(cp), exist_ok=True)
    with open(cp, "w", encoding="utf-8") as f:
        json.dump(sb, f, ensure_ascii=False)
    return sb, f"FETCH:{url}"


def looks_numeric(x):
    if x is None:
        return False
    if isinstance(x, int):
        return True
    if isinstance(x, str) and x.strip().isdigit():
        return True
    return False


def is_completed_game(game_obj: dict) -> bool:
    g = game_obj
    for key in ["gameState", "status", "state"]:
        val = g.get(key)
        if isinstance(val, str) and val.lower() in {"final", "complete", "completed"}:
            return True

    status = g.get("gameStatus") or g.get("status") or {}
    if isinstance(status, dict):
        st = status.get("state") or status.get("status") or ""
        if isinstance(st, str) and st.lower() in {"final", "complete", "completed"}:
            return True

    away_score = (g.get("away") or {}).get("score")
    home_score = (g.get("home") or {}).get("score")
    return looks_numeric(away_score) and looks_numeric(home_score)


def extract_games_for_teams(sb_json: dict, team_seos: set[str]):
    hits = []
    for item in sb_json.get("games", []):
        g = item.get("game") or {}
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
        hits.append(
            {
                "gameID": gid,
                "away_seo": away_seo,
                "away_short": away_names.get("short"),
                "away_score": (g.get("away") or {}).get("score"),
                "home_seo": home_seo,
                "home_short": home_names.get("short"),
                "home_score": (g.get("home") or {}).get("score"),
                "url": g.get("url"),
                "neutralSite": g.get("neutralSite"),
            }
        )
    return hits


def build_last_n_completed_games(
    selected_games_path: str,
    data_root: str,
    games_per_team: int = 4,
    max_days_back: int = 90,
    tz_name: str = "America/Chicago",
):
    selected = load_json(selected_games_path)
    if not selected:
        raise ValueError(f"No selected games found in: {selected_games_path}")

    run_date = selected[0]["date"]
    anchor = datetime.strptime(run_date, "%Y-%m-%d").replace(tzinfo=ZoneInfo(tz_name))
    team_seos = sorted({g["away_seo"] for g in selected} | {g["home_seo"] for g in selected})

    cache_root = os.path.join(data_root, "cache", "scoreboard_daily")
    out_root = os.path.join(data_root, "processed", "baselines")
    os.makedirs(cache_root, exist_ok=True)
    os.makedirs(out_root, exist_ok=True)

    lastn = {seo: [] for seo in team_seos}
    seen_game_ids = {seo: set() for seo in team_seos}

    dt = anchor - timedelta(days=1)
    days_checked = 0

    print(f"\nFinding last {games_per_team} completed games per team (before {run_date})")
    print(f"Teams: {', '.join(team_seos)}\n")

    while days_checked < max_days_back:
        if all(len(lastn[seo]) >= games_per_team for seo in team_seos):
            break

        sb, src = load_or_fetch_scoreboard(cache_root, dt)
        hits = extract_games_for_teams(sb, set(team_seos))
        if hits:
            print(f"[{dt.strftime('%Y-%m-%d')}] {src} -> {len(hits)} matching completed games")
        for h in hits:
            away_seo = h["away_seo"]
            home_seo = h["home_seo"]
            gid = h["gameID"]
            if away_seo in lastn and len(lastn[away_seo]) < games_per_team and gid not in seen_game_ids[away_seo]:
                seen_game_ids[away_seo].add(gid)
                lastn[away_seo].append(
                    {
                        "date": dt.strftime("%Y-%m-%d"),
                        "gameID": gid,
                        "opponent_seo": home_seo,
                        "home_away": "away",
                        "score_for": h["away_score"],
                        "score_against": h["home_score"],
                        "url": h["url"],
                        "neutralSite": h.get("neutralSite"),
                    }
                )
            if home_seo in lastn and len(lastn[home_seo]) < games_per_team and gid not in seen_game_ids[home_seo]:
                seen_game_ids[home_seo].add(gid)
                lastn[home_seo].append(
                    {
                        "date": dt.strftime("%Y-%m-%d"),
                        "gameID": gid,
                        "opponent_seo": away_seo,
                        "home_away": "home",
                        "score_for": h["home_score"],
                        "score_against": h["away_score"],
                        "url": h["url"],
                        "neutralSite": h.get("neutralSite"),
                    }
                )

        dt -= timedelta(days=1)
        days_checked += 1

    out = {
        "run_date": run_date,
        "source": "scoreboard_backfill",
        "selected_games_path": selected_games_path,
        "games_per_team": games_per_team,
        "max_days_back": max_days_back,
        "teams": {seo: lastn[seo] for seo in team_seos},
    }

    out_path = os.path.join(out_root, f"last{games_per_team}_{run_date}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("\nResults:")
    for seo in team_seos:
        print(f"\n{seo}: found {len(lastn[seo])}/{games_per_team}")
        for rec in lastn[seo]:
            print(
                f"  - {rec['date']} gameID={rec['gameID']} vs {rec['opponent_seo']} "
                f"({rec['home_away']}) {rec['score_for']}-{rec['score_against']}"
            )

    missing = [seo for seo in team_seos if len(lastn[seo]) < games_per_team]
    if missing:
        print("\nWARNING: Some teams did not reach the target sample size:")
        for seo in missing:
            print(f"  - {seo}: {len(lastn[seo])}/{games_per_team}")

    print(f"\nSaved baseline manifest -> {out_path}\n")
    return out_path


def parse_args():
    ap = argparse.ArgumentParser(description="Build last-N completed games manifest for the current selected slate.")
    ap.add_argument("--selected-games", required=True, help="Path to selected_games_<date>.json")
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help="Root data folder. Default: C:\\NCAA Model\\data")
    ap.add_argument("--games-per-team", type=int, default=4, help="How many completed games to pull per team.")
    ap.add_argument("--max-days-back", type=int, default=90, help="How far back to search.")
    ap.add_argument("--timezone", default="America/Chicago", help="Timezone for slate anchor date.")
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    build_last_n_completed_games(
        selected_games_path=args.selected_games,
        data_root=args.data_root,
        games_per_team=args.games_per_team,
        max_days_back=args.max_days_back,
        tz_name=args.timezone,
    )
