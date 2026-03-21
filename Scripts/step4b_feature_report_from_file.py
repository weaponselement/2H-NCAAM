import json
import os
import re
from statistics import mean

DATA_ROOT = r"C:\NCAA Model\data"

# INPUTS (edit only if needed)
HALFTIME_FILE = r"C:\NCAA Model\data\raw\pbp_live\6503505\pbp_first_half_20260224_203714.json"
BASELINE_MANIFEST = r"C:\NCAA Model\data\processed\baselines\last4_2026-02-24.json"
BASELINE_PBP_ROOT = os.path.join(DATA_ROOT, "raw", "pbp")

# OUTPUT
REPORT_DIR = os.path.join(DATA_ROOT, "processed", "reports")
os.makedirs(REPORT_DIR, exist_ok=True)

# --- Helpers ---
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def extract_first_half_plays_from_payload(payload):
    """
    Uses the confirmed NCAAM schema:
      payload['periods'][i]['playbyplayStats'] where periodNumber==1 is 1st half. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    Some saved PBP files may wrap this under other keys; handle both.
    """
    if isinstance(payload, dict) and "periods" in payload and isinstance(payload["periods"], list):
        periods = payload["periods"]
    elif isinstance(payload, dict) and "game" in payload and isinstance(payload["game"], dict) and "periods" in payload["game"]:
        periods = payload["game"]["periods"]
    else:
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
    if "end of" in d: return "end"
    if "timeout" in d: return "timeout"
    if "commercial" in d: return "timeout"
    if "subbing" in d: return "sub"

    # fouls
    if "offensive foul" in d: return "foul_offensive"
    if "shooting foul" in d: return "foul_shooting"
    if "personal foul" in d or "foul on" in d or "foul by" in d: return "foul_personal"

    # turnovers / steals
    if "turnover" in d: return "turnover"
    if "steal" in d: return "steal"

    # rebounds / blocks
    if "offensive rebound" in d: return "orb"
    if "defensive rebound" in d or "rebound" in d: return "drb"
    if "block" in d: return "block"

    # free throws
    if "free throw" in d:
        if "missed" in d: return "ft_miss"
        return "ft_make"

    # shots: detect 3pt explicitly
    if "3 pointer" in d or "three point" in d:
        if "missed" in d: return "3_miss"
        return "3_make"
    # 2pt keywords
    if "2 pointer" in d or "layup" in d or "slam dunk" in d or "dunk" in d:
        if "missed" in d: return "2_miss"
        return "2_make"
    # jumper: ambiguous 2/3, treat as 2 unless explicitly 3
    if "jumper" in d:
        if "missed" in d: return "2_miss"
        return "2_make"

    # assists (often separate event lines)
    if d.startswith("assist by") or " assists" in d:
        return "assist"

    return "other"

def points_from_event(cat):
    if cat == "3_make": return 3
    if cat == "2_make": return 2
    if cat == "ft_make": return 1
    return 0

def build_team_map_from_halftime(plays):
    """
    Infer team names from eventDescription like:
      "Jumper by Michigan's ..." or "Personal Foul on Minnesota's ..."
    Returns mapping: teamId -> team_name_guess
    """
    team_map = {}
    for p in plays:
        if not isinstance(p, dict):
            continue
        tid = p.get("teamId")
        if tid in (None, 0):
            continue
        desc = p.get("eventDescription") or ""
        m = re.search(r"by ([A-Za-z .&()\\-]+?)'s ", desc)
        if not m:
            m = re.search(r"on ([A-Za-z .&()\\-]+?)'s ", desc)
        if m:
            name = m.group(1).strip()
            # keep first seen
            team_map.setdefault(tid, name)
        # stop early if we got two teams
        if len(team_map) >= 2:
            # still allow more evidence but fine
            pass
    return team_map

def compute_features_for_team(plays, team_id):
    """
    Compute first-half features for a specific teamId.
    Uses eventDescription + firstName/lastName fields when present. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    """
    f = {
        "FGA": 0, "FGM": 0, "2PA": 0, "2PM": 0, "3PA": 0, "3PM": 0,
        "FTA": 0, "FTM": 0,
        "TO": 0, "ORB": 0, "DRB": 0,
        "STL": 0, "BLK": 0,
        "PF": 0, "PF_offensive": 0, "PF_shooting": 0,
        "assists_lines": 0,
        "timeout_lines": 0,
        "sub_lines": 0,
        "points_inferred": 0,
        "player_points": {},
        "player_fouls": {}
    }

    for p in plays:
        if not isinstance(p, dict):
            continue
        tid = p.get("teamId")
        if tid != team_id:
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

        # fouls
        if cat.startswith("foul_"):
            f["PF"] += 1
            if cat == "foul_offensive":
                f["PF_offensive"] += 1
            if cat == "foul_shooting":
                f["PF_shooting"] += 1

            # foul trouble: use firstName/lastName if present; else parse
            name = normalize_name(p.get("firstName"), p.get("lastName"))
            if not name:
                m = re.search(r"(?:on|by) [^']*'s ([A-Za-z\\.\\- ]+?)\\s*(?:\\(|$)", desc, flags=re.I)
                name = m.group(1).strip() if m else ""
            if name:
                f["player_fouls"][name] = f["player_fouls"].get(name, 0) + 1

        # assist lines
        if cat == "assist":
            f["assists_lines"] += 1

        # meta
        if cat == "timeout":
            f["timeout_lines"] += 1
        if cat == "sub":
            f["sub_lines"] += 1

        # points + player points
        pts = points_from_event(cat)
        if pts:
            f["points_inferred"] += pts
            scorer = normalize_name(p.get("firstName"), p.get("lastName"))
            if not scorer:
                # try parse "by TEAM's Name"
                m = re.search(r"'s ([A-Za-z\\.\\- ]+)$", desc)
                scorer = m.group(1).strip() if m else ""
            if scorer:
                f["player_points"][scorer] = f["player_points"].get(scorer, 0) + pts

    # pace proxy (classic estimate)
    # possessions ≈ FGA - ORB + TO + 0.44*FTA
    f["poss_est"] = round(f["FGA"] - f["ORB"] + f["TO"] + 0.44 * f["FTA"], 2)

    return f

def summarize_baseline(team_seo, baseline_game_ids):
    """
    For each baseline gameID, load the baseline PBP JSON and compute first-half features.
    Files are under: data/raw/pbp/<team_seo>/<gameID>.json (your Step 3 output). [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    """
    per_game = []
    for gid in baseline_game_ids:
        fp = os.path.join(BASELINE_PBP_ROOT, team_seo, f"{gid}.json")
        if not os.path.exists(fp):
            # If missing (should be rare), skip for now
            continue
        payload = load_json(fp)
        plays = extract_first_half_plays_from_payload(payload)
        # team_id isn't consistent across games; baseline files may not share the same numeric IDs.
        # So for baselines, compute features by parsing team name out of text? That’s brittle.
        # Instead: compute *team-neutral* first-half metrics using BOTH homeText/visitorText fields?
        # Practical approach: In these baseline PBP files, events are typically team-attributed via isHome + teamId.
        # We'll infer which teamId corresponds to this team by searching for the team seoname in event text is not present.
        # So we fall back to using the fact that the baseline file is saved under the team folder:
        # We compute features using ALL plays where eventDescription contains "<Team>'s" in a way that matches the team_seo? not available.
        # Better: Use isHome + teams[] mapping if present.
        #
        # We'll implement a robust mapping if payload has teams[] with seoname and teamId. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
        team_id = None
        teams_meta = payload.get("teams") or (payload.get("game", {}).get("teams") if isinstance(payload.get("game"), dict) else None)
        if isinstance(teams_meta, list):
            for t in teams_meta:
                if isinstance(t, dict) and (t.get("seoname") == team_seo or t.get("seoName") == team_seo):
                    team_id = safe_int(t.get("teamId")) if t.get("teamId") is not None else None
                    break

        if team_id is None:
            # Skip if we can't map team id in this baseline payload
            continue

        feats = compute_features_for_team(plays, team_id)
        per_game.append({"gameID": gid, "features": feats})

    # Aggregate
    agg = {}
    keys = ["FGA","FGM","2PA","2PM","3PA","3PM","FTA","FTM","TO","ORB","DRB","STL","BLK","PF","PF_offensive","PF_shooting","points_inferred","poss_est"]
    for k in keys:
        vals = [g["features"].get(k) for g in per_game if g["features"].get(k) is not None]
        if vals:
            agg[k] = {
                "mean": round(mean(vals), 2),
                "min": min(vals),
                "max": max(vals)
            }
    return per_game, agg

def main():
    halftime = load_json(HALFTIME_FILE)
    plays = halftime.get("first_half_plays", [])
    if not plays:
        print("No first_half_plays found in halftime file.")
        return

    # Identify teams in this live game from the text
    team_map = build_team_map_from_halftime(plays)  # teamId -> team name guess
    team_ids = [tid for tid in team_map.keys() if tid not in (None, 0)]
    if len(team_ids) < 2:
        # fallback: use any nonzero teamIds in file
        team_ids = sorted({p.get("teamId") for p in plays if isinstance(p, dict) and p.get("teamId") not in (None, 0)})

    # Halftime score
    home, away = halftime_score_from_plays(plays)

    # Load baseline manifest
    baseline = load_json(BASELINE_MANIFEST)
    run_date = baseline.get("run_date", "unknown")
    teams_baseline = baseline.get("teams", {})

    # We need team seos for this matchup
    # From your earlier selected games, Minnesota is visitor and Michigan is home for 6503505. [1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)[1](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_first_half_20260224_203714.json)
    # We'll hard-set the pair for this report.
    home_seo = "michigan"
    away_seo = "minnesota"

    # Baseline IDs for each team
    home_last4 = [x["gameID"] for x in teams_baseline.get(home_seo, [])]
    away_last4 = [x["gameID"] for x in teams_baseline.get(away_seo, [])]

    # Compute live features for both teams by matching team names in team_map
    # Find which numeric teamId corresponds to Michigan/Minnesota by comparing inferred names.
    def match_team_id(target_name):
        target = target_name.lower()
        for tid, nm in team_map.items():
            if nm and nm.lower() == target:
                return tid
        return None

    mich_id = match_team_id("Michigan")
    minn_id = match_team_id("Minnesota")

    # If name inference failed, fall back to isHome markers in plays
    if mich_id is None or minn_id is None:
        # pick most common nonzero teamId among isHome==True as home team
        counts_home = {}
        counts_away = {}
        for p in plays:
            if not isinstance(p, dict): continue
            tid = p.get("teamId")
            if tid in (None, 0): continue
            if p.get("isHome") is True:
                counts_home[tid] = counts_home.get(tid, 0) + 1
            elif p.get("isHome") is False:
                counts_away[tid] = counts_away.get(tid, 0) + 1
        if mich_id is None and counts_home:
            mich_id = max(counts_home.items(), key=lambda x: x[1])[0]
        if minn_id is None and counts_away:
            minn_id = max(counts_away.items(), key=lambda x: x[1])[0]

    live_mich = compute_features_for_team(plays, mich_id) if mich_id else None
    live_minn = compute_features_for_team(plays, minn_id) if minn_id else None

    # Baselines
    mich_games, mich_agg = summarize_baseline(home_seo, home_last4)
    minn_games, minn_agg = summarize_baseline(away_seo, away_last4)

    # Build report
    report = {
        "gameID": halftime.get("gameID"),
        "run_date": run_date,
        "halftime_score": {"home_michigan": home, "away_minnesota": away},
        "team_ids_inferred": team_map,
        "live_first_half": {
            "michigan": live_mich,
            "minnesota": live_minn
        },
        "baseline": {
            "michigan_last4_gameIDs": home_last4,
            "minnesota_last4_gameIDs": away_last4,
            "michigan_aggregate": mich_agg,
            "minnesota_aggregate": minn_agg
        }
    }

    # Save report
    ts = halftime.get("extracted_at", "unknown")
    out_path = os.path.join(REPORT_DIR, f"feature_report_{halftime.get('gameID')}_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print quick console summary (halftime-friendly)
    print(f"\nFeature Report saved -> {out_path}")
    print(f"Halftime score: Michigan {home} - Minnesota {away}\n")

    def print_team_block(label, live, agg):
        if not live:
            print(f"{label}: No live features computed (teamId mapping failed).")
            return
        print(f"== {label} (LIVE 1H) ==")
        print(f"Points (inferred from events): {live['points_inferred']}")
        print(f"Possessions est: {live['poss_est']} | FGA {live['FGA']} | ORB {live['ORB']} | TO {live['TO']} | FTA {live['FTA']}")
        print(f"Fouls: {live['PF']} (shooting {live['PF_shooting']}, offensive {live['PF_offensive']})")
        # Top scorers
        top_pts = sorted(live['player_points'].items(), key=lambda x: x[1], reverse=True)[:5]
        if top_pts:
            print("Top points (inferred): " + ", ".join([f\"{n} {p}\" for n,p in top_pts]))
        # Foul trouble
        foul_list = sorted(live['player_fouls'].items(), key=lambda x: x[1], reverse=True)[:8]
        if foul_list:
            print("Fouls by player: " + ", ".join([f\"{n} ({c})\" for n,c in foul_list]))

        # Baseline comparison (a few core metrics)
        if agg:
            for k in ["points_inferred", "poss_est", "PF", "TO", "FGA"]:
                if k in agg:
                    print(f"Baseline {k}: mean {agg[k]['mean']} (min {agg[k]['min']}, max {agg[k]['max']})")
        print("")

    print_team_block("Michigan", live_mich, mich_agg)
    print_team_block("Minnesota", live_minn, minn_agg)

if __name__ == "__main__":
    main()