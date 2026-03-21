import json
import os
import re
import glob
from statistics import mean
from datetime import datetime

DATA_ROOT = r"C:\NCAA Model\data"

# Inputs
BASELINE_MANIFEST = os.path.join(DATA_ROOT, "processed", "baselines", "last4_2026-02-24.json")
BASELINE_PBP_ROOT = os.path.join(DATA_ROOT, "raw", "pbp")
PBP_LIVE_ROOT = os.path.join(DATA_ROOT, "raw", "pbp_live")

# Output
REPORT_DIR = os.path.join(DATA_ROOT, "processed", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def latest_halftime_file(game_id: str):
    """
    Find the newest pbp_first_half_*.json under data/raw/pbp_live/<game_id>/
    """
    folder = os.path.join(PBP_LIVE_ROOT, str(game_id))
    pattern = os.path.join(folder, "pbp_first_half_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        return None
    return files[-1]


def halftime_score_from_plays(plays):
    home = away = None
    for p in reversed(plays):
        if not isinstance(p, dict):
            continue
        if "homeScore" in p and "visitorScore" in p:
            home = p.get("homeScore")
            away = p.get("visitorScore")
            break
    return safe_int(home), safe_int(away)


def normalize_name(fn, ln):
    fn = (fn or "").strip()
    ln = (ln or "").strip()
    name = (fn + " " + ln).strip()
    return re.sub(r"\s+", " ", name)


def classify_event(desc):
    d = (desc or "").lower()

    # meta
    if "end of" in d:
        return "end"
    if "timeout" in d or "commercial" in d:
        return "timeout"
    if "subbing" in d:
        return "sub"

    # fouls
    if "offensive foul" in d:
        return "foul_offensive"
    if "shooting foul" in d:
        return "foul_shooting"
    if "personal foul" in d or "foul on" in d or "foul by" in d:
        return "foul_personal"

    # turnovers / steals
    if "turnover" in d:
        return "turnover"
    if "steal" in d:
        return "steal"

    # rebounds / blocks
    if "offensive rebound" in d:
        return "orb"
    if "defensive rebound" in d or "rebound" in d:
        return "drb"
    if "block" in d:
        return "block"

    # free throws
    if "free throw" in d:
        if "missed" in d:
            return "ft_miss"
        return "ft_make"

    # shots: detect 3pt explicitly
    if "3 pointer" in d or "three point" in d:
        if "missed" in d:
            return "3_miss"
        return "3_make"

    # 2pt keywords
    if "2 pointer" in d or "layup" in d or "slam dunk" in d or "dunk" in d:
        if "missed" in d:
            return "2_miss"
        return "2_make"

    # jumper: ambiguous 2/3, treat as 2 unless explicitly 3
    if "jumper" in d:
        if "missed" in d:
            return "2_miss"
        return "2_make"

    # assists (sometimes separate lines)
    if d.startswith("assist by") or " assists" in d:
        return "assist"

    return "other"


def points_from_event(cat):
    if cat == "3_make":
        return 3
    if cat == "2_make":
        return 2
    if cat == "ft_make":
        return 1
    return 0


def infer_home_away_team_ids(plays):
    """
    Determine likely home and away teamIds from isHome frequency.
    Ignores teamId 0.
    """
    home_counts = {}
    away_counts = {}
    for p in plays:
        if not isinstance(p, dict):
            continue
        tid = p.get("teamId")
        if tid in (None, 0):
            continue
        if p.get("isHome") is True:
            home_counts[tid] = home_counts.get(tid, 0) + 1
        elif p.get("isHome") is False:
            away_counts[tid] = away_counts.get(tid, 0) + 1

    home_tid = max(home_counts.items(), key=lambda x: x[1])[0] if home_counts else None
    away_tid = max(away_counts.items(), key=lambda x: x[1])[0] if away_counts else None
    return home_tid, away_tid


def compute_features_for_team(plays, team_id):
    """
    Compute first-half features for a specific numeric teamId using eventDescription text.
    """
    f = {
        "FGA": 0, "FGM": 0, "2PA": 0, "2PM": 0, "3PA": 0, "3PM": 0,
        "FTA": 0, "FTM": 0,
        "TO": 0, "ORB": 0, "DRB": 0,
        "STL": 0, "BLK": 0,
        "PF": 0, "PF_offensive": 0, "PF_shooting": 0,
        "points_inferred": 0,
        "player_points": {},
        "player_fouls": {}
    }

    for p in plays:
        if not isinstance(p, dict):
            continue
        if p.get("teamId") != team_id:
            continue

        desc = p.get("eventDescription") or ""
        cat = classify_event(desc)

        # shots
        if cat in ("2_make", "2_miss"):
            f["FGA"] += 1
            f["2PA"] += 1
            if cat == "2_make":
                f["FGM"] += 1
                f["2PM"] += 1

        if cat in ("3_make", "3_miss"):
            f["FGA"] += 1
            f["3PA"] += 1
            if cat == "3_make":
                f["FGM"] += 1
                f["3PM"] += 1

        # free throws
        if cat in ("ft_make", "ft_miss"):
            f["FTA"] += 1
            if cat == "ft_make":
                f["FTM"] += 1

        # rebounds
        if cat == "orb":
            f["ORB"] += 1
        if cat == "drb":
            f["DRB"] += 1

        # turnovers/steals/blocks
        if cat == "turnover":
            f["TO"] += 1
        if cat == "steal":
            f["STL"] += 1
        if cat == "block":
            f["BLK"] += 1

        # fouls + foul trouble
        if cat.startswith("foul_"):
            f["PF"] += 1
            if cat == "foul_offensive":
                f["PF_offensive"] += 1
            if cat == "foul_shooting":
                f["PF_shooting"] += 1

            name = normalize_name(p.get("firstName"), p.get("lastName"))
            if not name:
                m = re.search(r"(?:on|by) [^']*'s ([A-Za-z\\.\\- ]+?)\\s*(?:\\(|$)", desc, flags=re.I)
                name = m.group(1).strip() if m else ""
            if name:
                f["player_fouls"][name] = f["player_fouls"].get(name, 0) + 1

        # points + player points
        pts = points_from_event(cat)
        if pts:
            f["points_inferred"] += pts
            scorer = normalize_name(p.get("firstName"), p.get("lastName"))
            if scorer:
                f["player_points"][scorer] = f["player_points"].get(scorer, 0) + pts

    # Possession estimate: FGA - ORB + TO + 0.44*FTA
    f["poss_est"] = round(f["FGA"] - f["ORB"] + f["TO"] + 0.44 * f["FTA"], 2)
    return f


def extract_first_half_plays_from_baseline_payload(payload):
    """
    Confirmed baseline schema: periods[].playbyplayStats with periodNumber==1 for first half. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    """
    periods = payload.get("periods")
    if not isinstance(periods, list):
        return []
    for p in periods:
        if not isinstance(p, dict):
            continue
        pn = p.get("periodNumber")
        pd = (p.get("periodDisplay") or "").lower()
        if pn == 1 or "1st half" in pd or "first half" in pd:
            plays = p.get("playbyplayStats")
            return plays if isinstance(plays, list) else []
    return []


def team_id_from_baseline_payload(payload, team_seo):
    """
    Map a team seo (e.g., 'michigan') to numeric teamId from baseline payload teams[].seoname. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    """
    teams = payload.get("teams")
    if not isinstance(teams, list):
        return None
    for t in teams:
        if not isinstance(t, dict):
            continue
        if t.get("seoname") == team_seo:
            return safe_int(t.get("teamId"))
    return None


def baseline_aggregate(team_seo, game_ids):
    per_game = []
    for gid in game_ids:
        fp = os.path.join(BASELINE_PBP_ROOT, team_seo, f"{gid}.json")
        if not os.path.exists(fp):
            continue
        payload = load_json(fp)
        plays = extract_first_half_plays_from_baseline_payload(payload)
        tid = team_id_from_baseline_payload(payload, team_seo)
        if tid is None or not plays:
            continue
        feats = compute_features_for_team(plays, tid)
        per_game.append({"gameID": gid, "features": feats})

    # Aggregate numeric keys
    keys = ["points_inferred","poss_est","PF","TO","FGA","3PA","FTA","ORB","DRB","STL","BLK"]
    agg = {}
    for k in keys:
        vals = [g["features"].get(k) for g in per_game if g["features"].get(k) is not None]
        if vals:
            agg[k] = {"mean": round(mean(vals), 2), "min": min(vals), "max": max(vals)}
    return per_game, agg


def main():
    if len(os.sys.argv) < 2:
        print("Usage: python step4b_feature_report_from_file_v2.py <gameID>")
        print("Example: python step4b_feature_report_from_file_v2.py 6503505")
        return

    game_id = os.sys.argv[1].strip()
    halftime_path = latest_halftime_file(game_id)
    if halftime_path is None:
        print(f"No halftime file found under: {os.path.join(PBP_LIVE_ROOT, game_id)}")
        print("Make sure you ran: step4_pull_halftime_pbp_v2.py <gameID> at halftime.")
        return

    halftime = load_json(halftime_path)
    plays = halftime.get("first_half_plays", [])
    if not plays:
        print("Halftime file exists but first_half_plays is empty.")
        print(f"File: {halftime_path}")
        return

    home_ht, away_ht = halftime_score_from_plays(plays)

    # Load baseline + selected games to determine home/away seos
    baseline = load_json(BASELINE_MANIFEST)
    run_date = baseline.get("run_date", "unknown-date")

    selected_path = os.path.join(DATA_ROOT, "processed", "selected_games", f"selected_games_{run_date}.json")
    if not os.path.exists(selected_path):
        print(f"Selected games file not found: {selected_path}")
        print("Cannot map home/away team seos without it.")
        return

    selected = load_json(selected_path)
    sel = next((g for g in selected if str(g.get("gameID")) == str(game_id)), None)
    if not sel:
        print(f"GameID {game_id} not found in {selected_path}")
        return

    home_seo = sel["home_seo"]
    away_seo = sel["away_seo"]

    # Determine numeric teamIds in halftime plays
    home_tid, away_tid = infer_home_away_team_ids(plays)

    live_home = compute_features_for_team(plays, home_tid) if home_tid else None
    live_away = compute_features_for_team(plays, away_tid) if away_tid else None

    # Baseline last4 IDs
    teams_baseline = baseline.get("teams", {})
    home_last4 = [x["gameID"] for x in teams_baseline.get(home_seo, [])]
    away_last4 = [x["gameID"] for x in teams_baseline.get(away_seo, [])]

    home_games, home_agg = baseline_aggregate(home_seo, home_last4)
    away_games, away_agg = baseline_aggregate(away_seo, away_last4)

    ts = halftime.get("extracted_at", datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_path = os.path.join(REPORT_DIR, f"feature_report_{game_id}_{ts}.json")

    report = {
        "gameID": game_id,
        "run_date": run_date,
        "halftime_file": halftime_path,
        "teams": {
            "home": {"seo": home_seo, "teamId": home_tid, "halftime_score": home_ht, "live_first_half": live_home, "baseline_agg": home_agg},
            "away": {"seo": away_seo, "teamId": away_tid, "halftime_score": away_ht, "live_first_half": live_away, "baseline_agg": away_agg},
        },
        "notes": {
            "live_teamId_inference": "home/away inferred by isHome frequency; teamId=0 events ignored.",
            "baseline_first_half_extraction": "periods[periodNumber==1].playbyplayStats",
        }
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Console summary
    print(f"\nFeature Report saved -> {out_path}")
    print(f"Halftime score: {home_seo} {home_ht} - {away_seo} {away_ht}\n")

    def print_block(label, live, agg):
        if not live:
            print(f"{label}: live features not available (teamId mapping failed).")
            return
        print(f"== {label} (LIVE 1H) ==")
        print(f"Points (inferred): {live['points_inferred']}")
        print(f"Poss est: {live['poss_est']} | FGA {live['FGA']} | ORB {live['ORB']} | TO {live['TO']} | FTA {live['FTA']}")
        print(f"Fouls: {live['PF']} (shooting {live['PF_shooting']}, offensive {live['PF_offensive']})")

        top_pts = sorted(live["player_points"].items(), key=lambda x: x[1], reverse=True)[:5]
        if top_pts:
            print("Top points (inferred): " + ", ".join([f"{n} {p}" for n, p in top_pts]))

        foul_list = sorted(live["player_fouls"].items(), key=lambda x: x[1], reverse=True)[:8]
        if foul_list:
            print("Fouls by player: " + ", ".join([f"{n} ({c})" for n, c in foul_list]))

        for k in ["points_inferred","poss_est","PF","TO","FGA","3PA","FTA"]:
            if k in agg:
                print(f"Baseline {k}: mean {agg[k]['mean']} (min {agg[k]['min']}, max {agg[k]['max']})")
        print("")

    print_block(f"HOME {home_seo}", live_home, home_agg)
    print_block(f"AWAY {away_seo}", live_away, away_agg)


if __name__ == "__main__":
    main()