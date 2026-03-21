import argparse
import glob
import json
import os
import re
from collections import Counter
from datetime import datetime
from statistics import mean

DEFAULT_DATA_ROOT = r"C:\NCAA Model\data"
SEGMENTS = [
    (20 * 60, 16 * 60, "20:00-16:00"),
    (16 * 60, 12 * 60, "15:59-12:00"),
    (12 * 60, 8 * 60, "11:59-8:00"),
    (8 * 60, 4 * 60, "7:59-4:00"),
    (4 * 60, 0, "3:59-0:00"),
]


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def mean_or_none(values):
    vals = [v for v in values if v is not None]
    return round(mean(vals), 3) if vals else None


def parse_clock_to_seconds(clock_value):
    if clock_value is None:
        return None
    s = str(clock_value).strip()
    m = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.match(r"^(\d{1,2}):(\d{2})\.(\d+)$", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def elapsed_half_seconds(clock_value):
    rem = parse_clock_to_seconds(clock_value)
    if rem is None:
        return None
    return max(0, 20 * 60 - rem)


def clock_bucket(clock_value):
    rem = parse_clock_to_seconds(clock_value)
    if rem is None:
        return "unknown"
    for start, end, label in SEGMENTS:
        if end < rem <= start or (label == "3:59-0:00" and 0 <= rem <= start):
            return label
    return "unknown"


def normalize_name(fn, ln):
    fn = (fn or "").strip()
    ln = (ln or "").strip()
    return re.sub(r"\s+", " ", (fn + " " + ln).strip())


def normalize_desc(desc):
    return re.sub(r"\s+", " ", (desc or "").strip())


def latest_halftime_file(data_root: str, game_id: str):
    folder = os.path.join(data_root, "raw", "pbp_live", str(game_id))
    pattern = os.path.join(folder, "pbp_first_half_*.json")
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


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


def infer_home_away_team_ids(plays):
    home_counts = Counter()
    away_counts = Counter()
    for p in plays:
        if not isinstance(p, dict):
            continue
        tid = p.get("teamId")
        if tid in (None, 0):
            continue
        if p.get("isHome") is True:
            home_counts[tid] += 1
        elif p.get("isHome") is False:
            away_counts[tid] += 1
    home_tid = home_counts.most_common(1)[0][0] if home_counts else None
    away_tid = away_counts.most_common(1)[0][0] if away_counts else None
    return home_tid, away_tid


def extract_first_half_plays_from_baseline_payload(payload):
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


def team_id_from_payload(payload, team_seo):
    teams = payload.get("teams")
    if not isinstance(teams, list):
        return None
    for t in teams:
        if isinstance(t, dict) and t.get("seoname") == team_seo:
            return safe_int(t.get("teamId"))
    return None


def detect_foul_type(desc: str):
    d = desc.lower()
    if "shooting foul" in d:
        return "shooting"
    if "offensive foul" in d or "charge" in d:
        return "offensive"
    if "technical foul" in d:
        return "technical"
    if "intentional foul" in d:
        return "intentional"
    if "loose ball foul" in d:
        return "loose_ball"
    if "personal foul" in d or "foul on" in d or "foul by" in d:
        return "personal"
    return None


def detect_turnover_type(desc: str):
    d = desc.lower()
    if "offensive foul" in d:
        return "offensive_foul"
    if "travel" in d:
        return "travel"
    if "shot clock" in d:
        return "shot_clock"
    if "out of bounds" in d:
        return "out_of_bounds"
    if "bad pass" in d:
        return "bad_pass"
    if "lost ball" in d:
        return "lost_ball"
    if "carried" in d or "carry" in d:
        return "carry"
    if "double dribble" in d:
        return "double_dribble"
    if "5 second" in d or "five second" in d:
        return "five_second"
    if "held ball" in d:
        return "held_ball"
    return "other"


def classify_shot(desc: str):
    d = desc.lower()
    if "free throw" in d:
        return None
    is_make = "missed" not in d
    if "3 pointer" in d or "three point" in d:
        return {"event": "3_make" if is_make else "3_miss", "zone": "three", "assisted": "assist" in d}
    if any(x in d for x in ["layup", "dunk", "slam dunk", "tip in", "tip-in", "putback", "hook shot"]):
        return {"event": "2_make" if is_make else "2_miss", "zone": "paint", "assisted": "assist" in d}
    if any(x in d for x in ["jumper", "jump shot", "fadeaway", "pullup", "pull-up"]):
        return {"event": "2_make" if is_make else "2_miss", "zone": "jumper", "assisted": "assist" in d}
    if "2 pointer" in d:
        return {"event": "2_make" if is_make else "2_miss", "zone": "two_generic", "assisted": "assist" in d}
    return None


def points_from_desc(desc: str):
    d = desc.lower()
    if "made free throw" in d or ("free throw" in d and "missed" not in d):
        return 1
    if "3 pointer" in d or "three point" in d:
        return 0 if "missed" in d else 3
    if any(x in d for x in ["layup", "dunk", "jumper", "jump shot", "fadeaway", "2 pointer", "tip in", "tip-in", "putback", "hook shot"]):
        return 0 if "missed" in d else 2
    return 0


def extract_fouler_name_from_text(desc: str):
    if not desc:
        return ""
    m = re.search(r"(?:on|by)\s+[^']*'s\s+(.+?)(?:\s*\(|$)", desc, flags=re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    m = re.search(r"^(.+?)\s+(?:shooting|personal|offensive|technical|intentional|loose ball)\s+foul", desc, flags=re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1).strip())
    return ""


def likely_dead_ball(cat: str, desc: str):
    d = desc.lower()
    if cat in {"timeout", "sub", "foul", "ft", "turnover_dead", "rebound", "made_fg", "end"}:
        return True
    if "turnover" in d and "steal" not in d:
        return True
    return False


def build_team_stats_skeleton():
    return {
        "points_inferred": 0,
        "FGA": 0, "FGM": 0, "2PA": 0, "2PM": 0, "3PA": 0, "3PM": 0,
        "FTA": 0, "FTM": 0,
        "TO": 0, "TO_live": 0, "TO_dead": 0,
        "ORB": 0, "DRB": 0,
        "STL": 0, "BLK": 0,
        "PF": 0, "PF_shooting": 0, "PF_offensive": 0, "PF_technical": 0,
        "assisted_FGM": 0,
        "paint_FGA": 0, "paint_FGM": 0,
        "jumper_FGA": 0, "jumper_FGM": 0,
        "second_chance_points": 0,
        "player_points": Counter(),
        "player_fouls": Counter(),
        "scoring_runs": [],
        "segment_points": Counter(),
        "segment_fouls": Counter(),
        "segment_turnovers": Counter(),
        "segment_timeouts": Counter(),
        "turnover_types": Counter(),
        "foul_types": Counter(),
        "shot_zones": Counter(),
        "timeouts_taken": 0,
        "subs": 0,
        "bonus_reached_at_clock": None,
        "live_ball_points_allowed": 0,
    }


def finalize_team_stats(f):
    f["player_points"] = dict(f["player_points"])
    f["player_fouls"] = dict(f["player_fouls"])
    f["segment_points"] = dict(f["segment_points"])
    f["segment_fouls"] = dict(f["segment_fouls"])
    f["segment_turnovers"] = dict(f["segment_turnovers"])
    f["segment_timeouts"] = dict(f["segment_timeouts"])
    f["turnover_types"] = dict(f["turnover_types"])
    f["foul_types"] = dict(f["foul_types"])
    f["shot_zones"] = dict(f["shot_zones"])
    f["poss_est"] = round(f["FGA"] - f["ORB"] + f["TO"] + 0.30 * f["FTA"], 2)
    f["assist_rate_made_fg"] = round(f["assisted_FGM"] / f["FGM"], 3) if f["FGM"] else None
    f["top_scorers"] = sorted(f["player_points"].items(), key=lambda x: x[1], reverse=True)[:5]
    pts = [x[1] for x in f["top_scorers"]]
    total_points = f["points_inferred"] or 0
    f["star_dependency"] = {
        "top1_share": round((pts[0] / total_points), 3) if total_points and pts else None,
        "top2_share": round((sum(pts[:2]) / total_points), 3) if total_points else None,
        "top1_points": pts[0] if pts else 0,
        "top2_points": sum(pts[:2]) if pts else 0,
    }
    return f


def compute_live_game_state(plays, home_tid, away_tid):
    teams = {home_tid: build_team_stats_skeleton(), away_tid: build_team_stats_skeleton()}
    neutral_segment = Counter()
    whistle_events = []
    dead_ball_events = 0
    long_dead_ball_gaps = 0
    possession_change_markers = 0
    last_scoring_team = None
    current_run_points = 0
    current_run_plays = 0
    current_run_start_clock = None
    last_turnover_team = None
    last_turnover_live = False
    last_orb_team = None
    possession_log = []

    for idx, p in enumerate(plays):
        if not isinstance(p, dict):
            continue

        desc = normalize_desc(p.get("eventDescription") or "")
        d = desc.lower()
        tid = p.get("teamId") if p.get("teamId") in teams else None
        bucket = clock_bucket(p.get("clock"))

        if idx > 0:
            prev_elapsed = elapsed_half_seconds(plays[idx - 1].get("clock")) if isinstance(plays[idx - 1], dict) else None
            elapsed = elapsed_half_seconds(p.get("clock"))
            if elapsed is not None and prev_elapsed is not None and elapsed - prev_elapsed >= 30:
                long_dead_ball_gaps += 1

        if "timeout" in d or "commercial" in d:
            dead_ball_events += 1
            if tid:
                teams[tid]["timeouts_taken"] += 1
                teams[tid]["segment_timeouts"][bucket] += 1
            continue

        if "subbing" in d or d.startswith("substitution"):
            dead_ball_events += 1
            if tid:
                teams[tid]["subs"] += 1
            continue

        if "end of" in d:
            dead_ball_events += 1
            continue

        foul_type = detect_foul_type(desc)
        if foul_type and tid:
            dead_ball_events += 1
            teams[tid]["PF"] += 1
            teams[tid]["foul_types"][foul_type] += 1
            teams[tid]["segment_fouls"][bucket] += 1
            whistle_events.append({"teamId": tid, "clock": p.get("clock"), "bucket": bucket, "type": foul_type})
            if foul_type == "shooting":
                teams[tid]["PF_shooting"] += 1
            elif foul_type == "offensive":
                teams[tid]["PF_offensive"] += 1
            elif foul_type == "technical":
                teams[tid]["PF_technical"] += 1
            name = normalize_name(p.get("firstName"), p.get("lastName")) or extract_fouler_name_from_text(desc)
            if name:
                teams[tid]["player_fouls"][name] += 1
            if teams[tid]["bonus_reached_at_clock"] is None and teams[tid]["PF"] >= 7:
                teams[tid]["bonus_reached_at_clock"] = p.get("clock")

        if "turnover" in d and tid:
            turnover_type = detect_turnover_type(desc)
            is_live = "steal" in d or turnover_type in {"bad_pass", "lost_ball"}
            teams[tid]["TO"] += 1
            teams[tid]["turnover_types"][turnover_type] += 1
            teams[tid]["segment_turnovers"][bucket] += 1
            if is_live:
                teams[tid]["TO_live"] += 1
                last_turnover_live = True
            else:
                teams[tid]["TO_dead"] += 1
                dead_ball_events += 1
                last_turnover_live = False
            last_turnover_team = tid
            possession_change_markers += 1
            possession_log.append({"kind": "turnover", "teamId": tid, "clock": p.get("clock"), "bucket": bucket, "live": is_live})

        if "steal" in d and tid:
            teams[tid]["STL"] += 1

        if "block" in d and tid:
            teams[tid]["BLK"] += 1

        if "offensive rebound" in d and tid:
            teams[tid]["ORB"] += 1
            last_orb_team = tid
            possession_log.append({"kind": "orb", "teamId": tid, "clock": p.get("clock"), "bucket": bucket})

        elif "defensive rebound" in d and tid:
            teams[tid]["DRB"] += 1
            last_orb_team = None
            possession_change_markers += 1
            possession_log.append({"kind": "drb", "teamId": tid, "clock": p.get("clock"), "bucket": bucket})

        shot = classify_shot(desc)
        if tid and shot:
            ev = shot["event"]
            zone = shot["zone"]
            teams[tid]["FGA"] += 1
            teams[tid]["shot_zones"][zone] += 1
            if zone == "paint":
                teams[tid]["paint_FGA"] += 1
            elif zone == "jumper":
                teams[tid]["jumper_FGA"] += 1
            if ev.startswith("2_"):
                teams[tid]["2PA"] += 1
            if ev.startswith("3_"):
                teams[tid]["3PA"] += 1
            if ev.endswith("make"):
                teams[tid]["FGM"] += 1
                if ev.startswith("2_"):
                    teams[tid]["2PM"] += 1
                if ev.startswith("3_"):
                    teams[tid]["3PM"] += 1
                if zone == "paint":
                    teams[tid]["paint_FGM"] += 1
                elif zone == "jumper":
                    teams[tid]["jumper_FGM"] += 1
                if shot["assisted"]:
                    teams[tid]["assisted_FGM"] += 1
            possession_change_markers += 1 if ev.endswith("make") else 0

        if "free throw" in d and tid:
            teams[tid]["FTA"] += 1
            dead_ball_events += 1
            if "missed" not in d:
                teams[tid]["FTM"] += 1

        pts = points_from_desc(desc) if tid else 0
        if pts and tid:
            teams[tid]["points_inferred"] += pts
            teams[tid]["segment_points"][bucket] += pts
            scorer = normalize_name(p.get("firstName"), p.get("lastName"))
            if scorer:
                teams[tid]["player_points"][scorer] += pts
            if last_orb_team == tid:
                teams[tid]["second_chance_points"] += pts
            if last_turnover_live and last_turnover_team and last_turnover_team != tid:
                teams[last_turnover_team]["live_ball_points_allowed"] += pts

            if last_scoring_team == tid:
                current_run_points += pts
                current_run_plays += 1
            else:
                if last_scoring_team is not None:
                    teams[last_scoring_team]["scoring_runs"].append(
                        {
                            "points": current_run_points,
                            "plays": current_run_plays,
                            "start_clock": current_run_start_clock,
                            "end_clock": p.get("clock"),
                        }
                    )
                last_scoring_team = tid
                current_run_points = pts
                current_run_plays = 1
                current_run_start_clock = p.get("clock")

        if likely_dead_ball("ft" if "free throw" in d else "other", desc):
            neutral_segment[bucket] += 1

    if last_scoring_team is not None and current_run_points > 0:
        teams[last_scoring_team]["scoring_runs"].append(
            {
                "points": current_run_points,
                "plays": current_run_plays,
                "start_clock": current_run_start_clock,
                "end_clock": "0:00",
            }
        )

    output = {
        "teams": {tid: finalize_team_stats(stats) for tid, stats in teams.items() if tid is not None},
        "game": {
            "dead_ball_events": dead_ball_events,
            "long_dead_ball_gaps": long_dead_ball_gaps,
            "possession_change_markers": possession_change_markers,
            "whistle_events_count": len(whistle_events),
            "neutral_segment_deadballs": dict(neutral_segment),
            "tempo_flags": {},
        },
        "possession_log": possession_log,
        "whistle_events": whistle_events,
    }

    home_stats = output["teams"].get(home_tid)
    away_stats = output["teams"].get(away_tid)

    if home_stats and away_stats:
        combined_poss = (home_stats["poss_est"] + away_stats["poss_est"]) / 2
        combined_poss = min(combined_poss, 42)

        live_ball_chaos = home_stats["TO_live"] + away_stats["TO_live"]

        output["game"]["estimated_possessions_per_team_1H"] = round(combined_poss, 2)

        is_true_run = (
            combined_poss >= 40 and
            live_ball_chaos >= 6
        )

        output["game"]["pace_profile"] = (
            "run_and_gun" if is_true_run else
            "moderate" if combined_poss >= 34 else
            "grinder"
        )

        early = home_stats["segment_points"].get("20:00-16:00", 0) + away_stats["segment_points"].get("20:00-16:00", 0)
        late = home_stats["segment_points"].get("3:59-0:00", 0) + away_stats["segment_points"].get("3:59-0:00", 0)

        output["game"]["tempo_flags"] = {
            "accelerating_late": late > early + 4,
            "slowing_late": early > late + 4,
        }

    return output


def baseline_aggregate(data_root: str, team_seo: str, game_ids):
    base_root = os.path.join(data_root, "raw", "pbp")
    per_game = []
    for gid in game_ids:
        fp = os.path.join(base_root, team_seo, f"{gid}.json")
        if not os.path.exists(fp):
            continue
        payload = load_json(fp)
        plays = extract_first_half_plays_from_baseline_payload(payload)
        tid = team_id_from_payload(payload, team_seo)
        if not plays or tid is None:
            continue
        state = compute_live_game_state(plays, tid, -999999)
        team_stats = state["teams"].get(tid)
        if team_stats:
            per_game.append({"gameID": gid, "features": team_stats})

    numeric_keys = [
        "points_inferred", "poss_est", "PF", "TO", "TO_live", "TO_dead", "FGA", "3PA", "FTA",
        "ORB", "DRB", "STL", "BLK", "second_chance_points", "paint_FGA", "paint_FGM",
    ]
    agg = {}
    for k in numeric_keys:
        vals = [g["features"].get(k) for g in per_game if g["features"].get(k) is not None]
        if vals:
            agg[k] = {"mean": round(mean(vals), 3), "min": min(vals), "max": max(vals)}

    dep_vals = [g["features"].get("star_dependency", {}).get("top2_share") for g in per_game]
    dep_vals = [v for v in dep_vals if v is not None]
    if dep_vals:
        agg["top2_share"] = {
            "mean": round(mean(dep_vals), 3),
            "min": min(dep_vals),
            "max": max(dep_vals),
        }
    return per_game, agg


def compare_to_baseline(live_stats: dict, baseline_agg: dict):
    out = {}
    for k, live_val in live_stats.items():
        if k not in baseline_agg:
            continue
        if not isinstance(baseline_agg[k], dict) or "mean" not in baseline_agg[k]:
            continue
        if not isinstance(live_val, (int, float)):
            continue
        mean_val = baseline_agg[k]["mean"]
        out[k] = {
            "live": live_val,
            "baseline_mean": mean_val,
            "delta": round(live_val - mean_val, 3),
            "outside_range": live_val < baseline_agg[k]["min"] or live_val > baseline_agg[k]["max"],
        }
    return out


def classify_rotation_state(stats: dict):
    foul_trouble_count = sum(1 for _, c in stats.get("player_fouls", {}).items() if c >= 2)
    subs = stats.get("subs", 0)
    top2 = stats.get("star_dependency", {}).get("top2_share")
    if foul_trouble_count >= 3 or subs >= 10:
        return "UNSTABLE"
    if foul_trouble_count >= 2 or (top2 is not None and top2 >= 0.68):
        return "ADJUSTING"
    return "SCRIPTED"


def summarize_team_structural(stats: dict, opp_stats: dict):
    top2_share = stats.get("star_dependency", {}).get("top2_share")
    foul_pressure = opp_stats.get("PF", 0)
    paint_share = round(stats["paint_FGA"] / stats["FGA"], 3) if stats.get("FGA") else None
    three_share = round(stats["3PA"] / stats["FGA"], 3) if stats.get("FGA") else None
    live_to_share = round(stats["TO_live"] / stats["TO"], 3) if stats.get("TO") else None
    return {
        "rotation_state": classify_rotation_state(stats),
        "star_dependency_top2_share": top2_share,
        "paint_attempt_share": paint_share,
        "three_attempt_share": three_share,
        "live_turnover_share": live_to_share,
        "fouls_drawn_estimate": foul_pressure,
        "largest_scoring_run": max([r.get("points", 0) for r in stats.get("scoring_runs", [])], default=0),
        "bonus_reached_at_clock": stats.get("bonus_reached_at_clock"),
    }


def build_foul_pressure_summary(home_stats: dict, away_stats: dict):
    home_pf = int(home_stats.get("PF", 0) or 0)
    away_pf = int(away_stats.get("PF", 0) or 0)

    home_bonus = home_pf >= 7
    away_bonus = away_pf >= 7

    home_fouls_per_min = round(home_pf / 20, 3)
    away_fouls_per_min = round(away_pf / 20, 3)

    if home_pf >= away_pf + 4:
        edge = "away"
    elif away_pf >= home_pf + 4:
        edge = "home"
    else:
        edge = "neutral"

    strong_escalation = (
        (home_bonus and away_bonus) or
        (abs(home_pf - away_pf) >= 4) or
        ((home_bonus or away_bonus) and (home_pf + away_pf >= 15))
    )

    return {
        "home_team_fouls": home_pf,
        "away_team_fouls": away_pf,
        "home_fouls_per_min": home_fouls_per_min,
        "away_fouls_per_min": away_fouls_per_min,
        "home_in_bonus": home_bonus,
        "away_in_bonus": away_bonus,
        "home_bonus_reached_at_clock": home_stats.get("bonus_reached_at_clock"),
        "away_bonus_reached_at_clock": away_stats.get("bonus_reached_at_clock"),
        "foul_pressure_edge": edge,
        "strong_foul_escalation": strong_escalation,
    }


def build_scoring_concentration_summary(home_stats: dict, away_stats: dict):
    home_top2 = home_stats.get("star_dependency", {}).get("top2_share")
    away_top2 = away_stats.get("star_dependency", {}).get("top2_share")

    home_high = home_top2 is not None and home_top2 >= 0.65
    away_high = away_top2 is not None and away_top2 >= 0.65

    if home_high and away_high:
        environment = "both_concentrated"
    elif home_high:
        environment = "home_concentrated"
    elif away_high:
        environment = "away_concentrated"
    else:
        environment = "balanced"

    return {
        "home_top2_share": home_top2,
        "away_top2_share": away_top2,
        "home_high_concentration": home_high,
        "away_high_concentration": away_high,
        "scoring_concentration_environment": environment,
    }


def compute_calibration_adjustment(
    home_ht: int,
    away_ht: int,
    expected_2h: int,
    pace_profile: str,
    scoring_concentration: dict,
):
    ht_total = (home_ht or 0) + (away_ht or 0)
    margin = (home_ht or 0) - (away_ht or 0)

    adjustment = 0
    reasons = []

    adjustment += 2
    reasons.append("base under-bias correction")

    if ht_total >= 85:
        adjustment += 4
        reasons.append("halftime total 85+")
    elif ht_total >= 75:
        adjustment += 2
        reasons.append("halftime total 75-84")

    if margin == 0:
        adjustment += 2
        reasons.append("tied at halftime")

    if -5 <= margin <= -1:
        adjustment += 1
        reasons.append("away leads by 1-5")

    if pace_profile == "moderate":
        adjustment += 2
        reasons.append("moderate pace undercall zone")
    elif pace_profile == "grinder":
        adjustment += 1
        reasons.append("grinder pace slight undercall zone")

    if 63 <= expected_2h <= 68:
        adjustment += 2
        reasons.append("raw 2H midpoint in 63-68 undercall zone")

    conc_env = scoring_concentration.get("scoring_concentration_environment", "balanced")
    if conc_env == "both_concentrated":
        adjustment -= 2
        reasons.append("both offenses highly concentrated")
    elif conc_env in {"home_concentrated", "away_concentrated"}:
        adjustment -= 1
        reasons.append("one offense highly concentrated")

    return adjustment, reasons


def synthesize_game(
    game_id: str,
    home_seo: str,
    away_seo: str,
    home_ht: int,
    away_ht: int,
    home_live: dict,
    away_live: dict,
    home_base: dict,
    away_base: dict,
    game_meta: dict,
    foul_pressure: dict,
    scoring_concentration: dict,
):
    margin = (home_ht or 0) - (away_ht or 0)
    combined_poss = game_meta.get("estimated_possessions_per_team_1H")
    whistle_heavy = game_meta.get("whistle_events_count", 0) >= 14
    dead_ball_heavy = game_meta.get("dead_ball_events", 0) >= 20
    tempo_flags = game_meta.get("tempo_flags", {})
    accelerating_late = tempo_flags.get("accelerating_late", False)
    slowing_late = tempo_flags.get("slowing_late", False)
    pace_profile = game_meta.get("pace_profile")

    home_dep = home_live.get("star_dependency", {}).get("top2_share")
    away_dep = away_live.get("star_dependency", {}).get("top2_share")
    home_to = home_live.get("TO", 0)
    away_to = away_live.get("TO", 0)
    home_live_to = home_live.get("TO_live", 0)
    away_live_to = away_live.get("TO_live", 0)

    home_second = home_live.get("second_chance_points", 0)
    away_second = away_live.get("second_chance_points", 0)

    home_big_run = max([r.get("points", 0) for r in home_live.get("scoring_runs", [])], default=0)
    away_big_run = max([r.get("points", 0) for r in away_live.get("scoring_runs", [])], default=0)

    structural_home = 0.0
    structural_away = 0.0
    reasons = []

    if margin > 0:
        structural_home += 1.5
        reasons.append(f"{home_seo} leads by {margin} at half")
    elif margin < 0:
        structural_away += 1.5
        reasons.append(f"{away_seo} leads by {-margin} at half")

    if home_to < away_to:
        structural_home += 1.0
        reasons.append(f"{home_seo} has better ball security ({home_to} TO vs {away_to})")
    elif away_to < home_to:
        structural_away += 1.0
        reasons.append(f"{away_seo} has better ball security ({away_to} TO vs {home_to})")

    if home_live_to + 2 <= away_live_to:
        structural_home += 0.75
        reasons.append(f"{away_seo} committed more damaging live-ball turnovers ({away_live_to} vs {home_live_to})")
    elif away_live_to + 2 <= home_live_to:
        structural_away += 0.75
        reasons.append(f"{home_seo} committed more damaging live-ball turnovers ({home_live_to} vs {away_live_to})")

    if home_second > away_second:
        structural_home += 0.75
        reasons.append(f"{home_seo} created more second-chance scoring")
    elif away_second > home_second:
        structural_away += 0.75
        reasons.append(f"{away_seo} created more second-chance scoring")

    if home_dep is not None and away_dep is not None:
        if home_dep + 0.08 < away_dep:
            structural_home += 0.75
            reasons.append(f"{home_seo} offense is less concentrated in 1-2 scorers")
        elif away_dep + 0.08 < home_dep:
            structural_away += 0.75
            reasons.append(f"{away_seo} offense is less concentrated in 1-2 scorers")

    if home_live.get("PF", 0) + 2 < away_live.get("PF", 0):
        structural_home += 0.5
        reasons.append(f"{home_seo} avoided foul trouble better")
    elif away_live.get("PF", 0) + 2 < home_live.get("PF", 0):
        structural_away += 0.5
        reasons.append(f"{away_seo} avoided foul trouble better")

    if home_big_run >= away_big_run + 4:
        structural_home += 0.5
        reasons.append(f"{home_seo} showed stronger sustained run creation (best run {home_big_run}-{away_big_run})")
    elif away_big_run >= home_big_run + 4:
        structural_away += 0.5
        reasons.append(f"{away_seo} showed stronger sustained run creation (best run {away_big_run}-{home_big_run})")

    if combined_poss is not None:
        if combined_poss < 32:
            raw_expected_2h = 61
            variance = "LOW-MED"
        elif combined_poss < 36:
            raw_expected_2h = 67
            variance = "MEDIUM"
        else:
            raw_expected_2h = 73
            variance = "MEDIUM-HIGH"
    else:
        raw_expected_2h = 67
        variance = "MEDIUM"

    if whistle_heavy:
        raw_expected_2h += 3
    if dead_ball_heavy:
        raw_expected_2h -= 2
    if accelerating_late:
        raw_expected_2h += 2
    if slowing_late:
        raw_expected_2h -= 2

    if foul_pressure.get("strong_foul_escalation", False):
        raw_expected_2h += 2
        reasons.append("Strong foul escalation environment supports extra 2H scoring")

        if foul_pressure.get("foul_pressure_edge") == "home":
            structural_home += 0.35
            reasons.append(f"{away_seo} committed much heavier foul volume")
        elif foul_pressure.get("foul_pressure_edge") == "away":
            structural_away += 0.35
            reasons.append(f"{home_seo} committed much heavier foul volume")

    calibration_adjustment, calibration_reasons = compute_calibration_adjustment(
        home_ht=home_ht,
        away_ht=away_ht,
        expected_2h=raw_expected_2h,
        pace_profile=pace_profile,
        scoring_concentration=scoring_concentration,
    )

    calibrated_expected_2h = raw_expected_2h + calibration_adjustment

    range_half_width = 5

    if foul_pressure.get("strong_foul_escalation", False):
        range_half_width += 1

    conc_env = scoring_concentration.get("scoring_concentration_environment", "balanced")
    if conc_env == "both_concentrated":
        range_half_width += 1

    if margin == 0:
        range_half_width += 1

    if pace_profile == "moderate":
        range_half_width += 1

    for r in calibration_reasons:
        reasons.append(f"calibration: {r}")

    winner = home_seo if structural_home >= structural_away else away_seo
    edge = abs(structural_home - structural_away)

    if edge >= 2.75:
        margin_range = "6-11"
        confidence = "MEDIUM-HIGH"
    elif edge >= 1.5:
        margin_range = "3-8"
        confidence = "MEDIUM"
    else:
        margin_range = "1-5"
        confidence = "LOW-MEDIUM"

    final_total_mid = (home_ht or 0) + (away_ht or 0) + calibrated_expected_2h
    total_range = f"{final_total_mid - (range_half_width + 1)}-{final_total_mid + (range_half_width + 1)}"

    biggest_uncertainty = "Whether 1H scoring came from repeatable creation or from fragile shot variance."
    if home_dep is not None and home_dep >= 0.68:
        biggest_uncertainty = f"{home_seo}'s heavy scorer concentration could flatten if that primary creator cools or gets loaded up on."
    elif away_dep is not None and away_dep >= 0.68:
        biggest_uncertainty = f"{away_seo}'s heavy scorer concentration could flatten if that primary creator cools or gets loaded up on."

    what_flips = "A whistle swing, foul trouble on key handlers, or live-ball turnover surge would flip the projection fastest."
    if abs(home_live_to - away_live_to) >= 3:
        what_flips = "If the team currently losing the live-ball turnover battle stabilizes that, the game state can flip quickly."

    return {
        "gameID": game_id,
        "winner_projection": winner,
        "winner_margin_range": margin_range,
        "structural_scores": {home_seo: structural_home, away_seo: structural_away},
        "reasons": reasons,
        "second_half_points_projection": {
            "raw_mid": raw_expected_2h,
            "calibration_adjustment": calibration_adjustment,
            "mid": calibrated_expected_2h,
            "range": f"{calibrated_expected_2h - range_half_width}-{calibrated_expected_2h + range_half_width}",
            "variance": variance,
        },
        "full_game_total_projection": {
            "mid": final_total_mid,
            "range": total_range,
            "lean": "OVER" if calibrated_expected_2h >= 70 else "UNDER" if calibrated_expected_2h <= 64 else "NO STRONG LEAN",
        },
        "confidence": confidence,
        "biggest_uncertainty": biggest_uncertainty,
        "flip_condition": what_flips,
        "key_assumption": "1H possession environment and whistle texture stay broadly similar into the first 10 minutes of 2H.",
    }


def parse_args():
    ap = argparse.ArgumentParser(description="Generate a structural halftime feature report from saved first-half PBP.")
    ap.add_argument("game_id", help="NCAA gameID")
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    ap.add_argument("--baseline-manifest", help="Path to baseline manifest; if omitted, latest last*_*.json for the run date must exist.")
    ap.add_argument("--selected-games", help="Path to selected_games_<date>.json; if omitted, derived from run date.")
    return ap.parse_args()


def main():
    args = parse_args()
    data_root = args.data_root
    halftime_path = latest_halftime_file(data_root, args.game_id)
    if halftime_path is None:
        print(f"No halftime file found for gameID={args.game_id}")
        return

    halftime = load_json(halftime_path)
    plays = halftime.get("first_half_plays", [])
    if not plays:
        print(f"Halftime file exists but first_half_plays is empty: {halftime_path}")
        return

    home_ht, away_ht = halftime_score_from_plays(plays)
    home_tid, away_tid = infer_home_away_team_ids(plays)
    if home_tid is None or away_tid is None:
        print("Could not infer home/away team IDs from halftime PBP.")
        return

    manifest_path = args.baseline_manifest
    if manifest_path is None:
        baseline_dir = os.path.join(data_root, "processed", "baselines")
        manifests = sorted(glob.glob(os.path.join(baseline_dir, "last*_*.json")))
        if not manifests:
            print("No baseline manifest found. Run the last-N baseline builder first.")
            return
        manifest_path = manifests[-1]

    baseline = load_json(manifest_path)
    run_date = baseline.get("run_date", "unknown-date")
    selected_path = args.selected_games or os.path.join(
        data_root, "processed", "selected_games", f"selected_games_{run_date}.json"
    )
    if not os.path.exists(selected_path):
        print(f"Selected games file not found: {selected_path}")
        return

    selected = load_json(selected_path)
    sel = next((g for g in selected if str(g.get("gameID")) == str(args.game_id)), None)
    if not sel:
        print(f"GameID {args.game_id} not found in {selected_path}")
        return

    home_seo = sel["home_seo"]
    away_seo = sel["away_seo"]

    live_state = compute_live_game_state(plays, home_tid, away_tid)
    home_live = live_state["teams"][home_tid]
    away_live = live_state["teams"][away_tid]

    teams_baseline = baseline.get("teams", {})
    home_last = [x["gameID"] for x in teams_baseline.get(home_seo, [])]
    away_last = [x["gameID"] for x in teams_baseline.get(away_seo, [])]
    home_games, home_base = baseline_aggregate(data_root, home_seo, home_last)
    away_games, away_base = baseline_aggregate(data_root, away_seo, away_last)

    home_compare = compare_to_baseline(home_live, home_base)
    away_compare = compare_to_baseline(away_live, away_base)

    foul_pressure = build_foul_pressure_summary(home_live, away_live)
    scoring_concentration = build_scoring_concentration_summary(home_live, away_live)

    report = {
        "gameID": args.game_id,
        "run_date": run_date,
        "halftime_file": halftime_path,
        "selected_games_file": selected_path,
        "baseline_manifest": manifest_path,
        "halftime_score": {"home": home_ht, "away": away_ht},
        "foul_pressure": foul_pressure,
        "scoring_concentration": scoring_concentration,
        "teams": {
            "home": {
                "seo": home_seo,
                "teamId": home_tid,
                "live_first_half": home_live,
                "baseline_agg": home_base,
                "baseline_per_game": home_games,
                "comparison_to_baseline": home_compare,
                "structural_summary": summarize_team_structural(home_live, away_live),
            },
            "away": {
                "seo": away_seo,
                "teamId": away_tid,
                "live_first_half": away_live,
                "baseline_agg": away_base,
                "baseline_per_game": away_games,
                "comparison_to_baseline": away_compare,
                "structural_summary": summarize_team_structural(away_live, home_live),
            },
        },
        "game_state": live_state["game"],
    }

    report["projection"] = synthesize_game(
        args.game_id,
        home_seo,
        away_seo,
        home_ht,
        away_ht,
        home_live,
        away_live,
        home_base,
        away_base,
        live_state["game"],
        foul_pressure,
        scoring_concentration,
    )

    out_dir = os.path.join(data_root, "processed", "reports")
    ts = halftime.get("extracted_at", datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_path = os.path.join(out_dir, f"feature_report_v5_test_{args.game_id}_{ts}.json")
    save_json(out_path, report)

    print(f"\nSaved report -> {out_path}")
    print(f"Halftime: {home_seo} {home_ht} - {away_seo} {away_ht}")
    print(f"Pace profile: {report['game_state'].get('pace_profile')}")
    print(f"Foul pressure: {report['foul_pressure']}")
    print(f"Scoring concentration: {report['scoring_concentration']}")
    print(f"Projected winner: {report['projection']['winner_projection']} by {report['projection']['winner_margin_range']}")
    print(f"2H points: {report['projection']['second_half_points_projection']['range']}")
    print(f"Full-game total: {report['projection']['full_game_total_projection']['range']}")
    print(f"Confidence: {report['projection']['confidence']}")


if __name__ == "__main__":
    main()