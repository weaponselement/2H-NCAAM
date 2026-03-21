import json
import os
import sys
from collections import Counter
import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

DATA_ROOT = r"C:\NCAA Model\data"
OUT_DIR = os.path.join(DATA_ROOT, "processed", "schema_inspection")
os.makedirs(OUT_DIR, exist_ok=True)

def fetch_pbp(game_id: str) -> dict:
    # PBP endpoint (same one you used for baseline downloads) [1](https://www.ncaa.com/sports/basketball-men/d1)
    url = f"{API_BASE}/game/{game_id}/play-by-play"
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.json()

def find_play_list(payload: dict):
    """
    Return (plays_list, plays_path_string).
    We search common keys and then do a light brute-force scan.
    """
    # common top-level keys
    for k in ["plays", "playByPlay", "pbp", "events"]:
        v = payload.get(k)
        if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], dict)):
            return v, k

    # common nested keys
    for parent in ["game", "data"]:
        v = payload.get(parent)
        if isinstance(v, dict):
            for k in ["plays", "playByPlay", "pbp", "events"]:
                vv = v.get(k)
                if isinstance(vv, list) and (len(vv) == 0 or isinstance(vv[0], dict)):
                    return vv, f"{parent}.{k}"

    # fallback: brute scan 2 levels deep for a list-of-dicts that smells like PBP
    best = None
    best_path = None
    for k, v in payload.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, list) and vv and isinstance(vv[0], dict):
                    keys = set(vv[0].keys())
                    # heuristic: pbp-like items often have at least one of these
                    if {"period", "clock", "time", "description", "text"} & keys:
                        best = vv
                        best_path = f"{k}.{kk}"
                        break
    return best, best_path

def flatten_keys(d: dict, prefix=""):
    """
    Flatten keys one level deep for inspection (not a full recursive flattener),
    so we can see nested structures like player/team blocks.
    """
    out = []
    for k, v in d.items():
        if isinstance(v, dict):
            out.append(prefix + k + " (dict)")
            # show nested keys (one level)
            for kk in list(v.keys())[:30]:
                out.append(prefix + f"  - {k}.{kk}")
        elif isinstance(v, list):
            out.append(prefix + k + f" (list,len={len(v)})")
        else:
            out.append(prefix + k)
    return out

def guess_field_candidates(plays: list):
    """
    Look across plays to see which keys appear often.
    Then highlight likely: period/half, clock/time, event type, text/description, player fields.
    """
    key_counts = Counter()
    for p in plays[:3000]:  # cap for speed
        if isinstance(p, dict):
            key_counts.update(p.keys())

    common = [k for k, c in key_counts.most_common(40)]

    def pick_any(cands):
        return [k for k in cands if k in key_counts]

    candidates = {
        "period_or_half_keys": pick_any(["half","period","periodNumber","frame","quarter","segment","periodDisplay","periodName"]),
        "clock_or_time_keys": pick_any(["clock","time","gameClock","clockDisplay","timeRemaining","time_display","timestamp","wallClock"]),
        "event_type_keys": pick_any(["type","eventType","action","playType","actionType","category"]),
        "text_keys": pick_any(["description","text","playText","summary","shortText","longText"]),
        "player_keys": pick_any(["player","playerName","athlete","participants","foulOn","fouler","shooter","assist","rebounder","turnoverBy"]),
        "team_keys": pick_any(["team","teamSeo","teamId","teamName","homeAway","side"]),
        "score_keys": pick_any(["homeScore","awayScore","scoreHome","scoreAway","home_score","away_score","score","scoring"])
    }

    return common, candidates

def main():
    game_id = sys.argv[1] if len(sys.argv) > 1 else "6503596"
    print(f"\nInspecting PBP schema for gameID={game_id}\n")

    payload = fetch_pbp(game_id)

    # Save raw for reference
    raw_path = os.path.join(OUT_DIR, f"pbp_raw_{game_id}.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    plays, path = find_play_list(payload)
    if not plays:
        print(f"Could not find a plays list (or plays list empty). Raw saved to: {raw_path}")
        print("Next step: we’ll inspect the raw file and pin the correct path.")
        return

    print(f"✅ Plays list located at path: {path}")
    print(f"✅ Number of plays in payload: {len(plays)}")
    print(f"✅ Raw saved to: {raw_path}\n")

    # Identify a “typical” play item (first dict)
    sample = next((p for p in plays if isinstance(p, dict)), None)
    if not sample:
        print("Plays list did not contain dict items—unexpected. Raw saved above.")
        return

    # Print top-level keys for sample play
    print("=== Sample play item: top-level keys (and 1-level nested keys) ===")
    for line in flatten_keys(sample):
        print(line)

    # Summarize frequent keys and candidates
    common, candidates = guess_field_candidates(plays)
    print("\n=== Most common play keys (top 40) ===")
    print(common)

    print("\n=== Candidate field groups (what we’ll use for the feature report) ===")
    for k, v in candidates.items():
        print(f"- {k}: {v}")

    # Save a compact schema summary
    schema_summary = {
        "gameID": game_id,
        "plays_path": path,
        "num_plays": len(plays),
        "sample_play_keys": list(sample.keys()),
        "common_keys_top40": common,
        "candidates": candidates,
    }
    summary_path = os.path.join(OUT_DIR, f"schema_summary_{game_id}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(schema_summary, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Schema summary saved to: {summary_path}\n")

if __name__ == "__main__":
    main()