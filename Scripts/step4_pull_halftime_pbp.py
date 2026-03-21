import json
import os
import sys
from datetime import datetime
import requests

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

DATA_ROOT = r"C:\NCAA Model\data"
OUT_ROOT = os.path.join(DATA_ROOT, "raw", "pbp_live")
LOG_DIR = os.path.join(DATA_ROOT, "logs")

os.makedirs(OUT_ROOT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def fetch_pbp(game_id: str) -> dict:
    url = f"{API_BASE}/game/{game_id}/play-by-play"  # documented endpoint [1](https://www.ncaa.com/sports/basketball-men/d1)
    r = requests.get(url, headers=HEADERS, timeout=45)
    r.raise_for_status()
    return r.json()

def find_play_list(payload: dict):
    """
    Different sports/years sometimes nest PBP under different keys.
    We’ll search for a list of dicts that looks like plays.
    """
    # common keys
    for k in ["plays", "playByPlay", "pbp", "events"]:
        v = payload.get(k)
        if isinstance(v, list) and (len(v) == 0 or isinstance(v[0], dict)):
            return v, k

    # deeper common nesting
    for k in ["game", "data"]:
        v = payload.get(k)
        if isinstance(v, dict):
            for kk in ["plays", "playByPlay", "pbp", "events"]:
                vv = v.get(kk)
                if isinstance(vv, list) and (len(vv) == 0 or isinstance(vv[0], dict)):
                    return vv, f"{k}.{kk}"

    # fallback: brute search shallowly
    for k, v in payload.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                if isinstance(vv, list) and (len(vv) == 0 or isinstance(vv[0], dict)):
                    # heuristic: list items often have "period"/"clock"/"time"/"description"
                    if len(vv) == 0:
                        continue
                    keys = set(vv[0].keys())
                    if {"period", "clock", "time", "description"} & keys:
                        return vv, f"{k}.{kk}"

    return None, None

def is_first_half_play(play: dict) -> bool:
    """
    Robust filters for “first half” across possible schemas.
    Priority order:
      1) Explicit period/half number
      2) Text labels like '1st Half'
      3) Period == 1
    """
    # Common numeric indicators
    for key in ["half", "period", "periodNumber", "frame", "quarter"]:
        if key in play:
            val = play.get(key)
            if isinstance(val, int) and val == 1:
                return True
            if isinstance(val, str):
                s = val.strip().lower()
                if s in ("1", "1st", "first", "first half", "1st half", "h1"):
                    return True

    # Common label fields
    for key in ["periodDisplay", "periodName", "segment", "header", "clockDisplay"]:
        v = play.get(key)
        if isinstance(v, str) and "1st" in v.lower() and "half" in v.lower():
            return True
        if isinstance(v, str) and v.strip().lower() in ("1st half", "first half"):
            return True

    # If nothing indicates first half, return False (better to be conservative)
    return False

def extract_first_half(plays: list) -> list:
    """
    Extract first-half plays. If schema lacks explicit half indicator, we fall back to:
      - If plays include 'period' values, take period==1
    """
    if not plays:
        return []

    # Determine if there is a usable period-like key across plays
    period_keys = ["half", "period", "periodNumber", "frame", "quarter"]
    present_key = None
    for pk in period_keys:
        if any(pk in p for p in plays):
            present_key = pk
            break

    if present_key:
        # If it looks numeric, use ==1
        vals = [p.get(present_key) for p in plays if present_key in p]
        if any(isinstance(v, int) for v in vals):
            return [p for p in plays if isinstance(p.get(present_key), int) and p.get(present_key) == 1]

        # If string-based, use is_first_half_play
        return [p for p in plays if is_first_half_play(p)]

    # Last resort: cannot confidently split
    return []

def summarize(plays_first_half: list):
    if not plays_first_half:
        return {"note": "No plays classified as first half. Schema may not include period/half fields."}

    # Try to locate score fields if present
    score_keys = [
        ("homeScore", "awayScore"),
        ("scoreHome", "scoreAway"),
        ("home_score", "away_score"),
    ]
    last = plays_first_half[0]
    # Determine ordering (sometimes latest-first vs earliest-first)
    # We'll just look at both ends for a score.
    candidates = [plays_first_half[0], plays_first_half[-1]]

    halftime_score = None
    for c in candidates:
        for hk, ak in score_keys:
            if hk in c and ak in c:
                halftime_score = (c.get(ak), c.get(hk))
                break
        if halftime_score:
            break

    # Count some common event types if present
    event_type = None
    for k in ["type", "eventType", "action", "playType"]:
        if k in plays_first_half[0]:
            event_type = k
            break

    counts = {}
    if event_type:
        for p in plays_first_half:
            t = str(p.get(event_type))
            counts[t] = counts.get(t, 0) + 1

    return {
        "first_half_plays": len(plays_first_half),
        "halftime_score_(away,home)": halftime_score,
        "event_type_key": event_type,
        "top_event_types": sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8] if counts else None
    }

def main():
    if len(sys.argv) < 2:
        print("Usage: python step4_pull_halftime_pbp.py <gameID>")
        sys.exit(1)

    game_id = sys.argv[1].strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    payload = fetch_pbp(game_id)

    plays, path = find_play_list(payload)
    if plays is None:
        # Save payload anyway for inspection
        full_path = os.path.join(OUT_ROOT, game_id, f"pbp_full_{ts}.json")
        save_json(full_path, payload)
        print(f"[OK] Saved full PBP JSON (could not locate plays list) -> {full_path}")
        print("Next: paste the key structure near where plays are stored, and we’ll pin the exact path.")
        sys.exit(0)

    first_half = extract_first_half(plays)

    # Save outputs
    game_dir = os.path.join(OUT_ROOT, game_id)
    full_path = os.path.join(game_dir, f"pbp_full_{ts}.json")
    half_path = os.path.join(game_dir, f"pbp_first_half_{ts}.json")

    save_json(full_path, payload)
    save_json(half_path, {
        "gameID": game_id,
        "plays_path": path,
        "first_half_plays": first_half
    })

    print(f"[OK] Plays found at: {path}")
    print(f"[OK] Saved full PBP -> {full_path}")
    print(f"[OK] Saved first-half-only -> {half_path}")

    info = summarize(first_half)
    print("\nSummary:")
    for k, v in info.items():
        print(f"- {k}: {v}")

if __name__ == "__main__":
    main()