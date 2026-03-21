import json
import os
import random
import sys
import time
from datetime import datetime
import requests
from paths import DATA_DIR

API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}
DATA_ROOT = str(DATA_DIR)
OUT_ROOT = os.path.join(DATA_ROOT, "raw", "pbp_live")
LOG_DIR = os.path.join(DATA_ROOT, "logs")
os.makedirs(OUT_ROOT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

RETRY_STATUSES = {429, 500, 502, 503, 504}


def save_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def fetch_pbp_with_retries(game_id: str, max_tries: int = 8, base_sleep: float = 2.0, timeout: int = 45) -> dict:
    """
    Pull PBP with retries for transient upstream/gateway failures.
    Endpoint: /game/{id}/play-by-play (henrygd API) [1](https://www.on3.com/college/duke-blue-devils/basketball/schedule/)
    """
    url = f"{API_BASE}/game/{game_id}/play-by-play"
    last_status = None
    last_body_snip = None

    for attempt in range(1, max_tries + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            last_status = r.status_code
            last_body_snip = (r.text or "")[:300]

            if r.status_code == 200:
                return r.json()

            if r.status_code in RETRY_STATUSES:
                # exponential backoff + jitter
                wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 1.0)
                print(f"[WARN] status={r.status_code} for PBP (attempt {attempt}/{max_tries}) -> wait {wait:.1f}s")
                time.sleep(wait)
                continue

            # Non-retryable
            r.raise_for_status()

        except Exception as e:
            wait = base_sleep * (2 ** (attempt - 1)) + random.uniform(0, 1.0)
            print(f"[WARN] exception on attempt {attempt}/{max_tries}: {e} -> wait {wait:.1f}s")
            time.sleep(wait)

    raise RuntimeError(f"PBP fetch failed after {max_tries} tries. last_status={last_status}, last_body_snip={last_body_snip!r}")


def extract_periods(payload: dict):
    """
    Confirmed NCAAM schema (example game 6503596):
      payload['periods'] is a list
      each period has 'periodNumber', 'periodDisplay', and 'playbyplayStats' [2](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_raw_6503596.json)
    """
    periods = payload.get("periods")
    return periods if isinstance(periods, list) else []


def extract_first_half_plays(payload: dict):
    periods = extract_periods(payload)
    for p in periods:
        if not isinstance(p, dict):
            continue
        pn = p.get("periodNumber")
        pd = (p.get("periodDisplay") or "").lower()
        if pn == 1 or "1st half" in pd or "first half" in pd:
            plays = p.get("playbyplayStats")
            return plays if isinstance(plays, list) else []
    return []


def halftime_score_from_first_half(first_half_plays: list):
    """
    Uses homeScore and visitorScore on the last play (if present) [2](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_raw_6503596.json)
    """
    if not first_half_plays:
        return None
    last = None
    # Find last dict with score fields
    for item in reversed(first_half_plays):
        if isinstance(item, dict) and ("homeScore" in item) and ("visitorScore" in item):
            last = item
            break
    if not last:
        return None
    return {
        "homeScore": last.get("homeScore"),
        "visitorScore": last.get("visitorScore"),
        "clock": last.get("clock"),
        "eventDescription": last.get("eventDescription"),
    }


def summarize(payload: dict):
    periods = extract_periods(payload)
    summary = {
        "num_periods_in_payload": len(periods),
        "period_summaries": [],
        "first_half_plays_count": 0,
        "halftime_score": None,
    }

    for p in periods:
        if not isinstance(p, dict):
            continue
        pn = p.get("periodNumber")
        pd = p.get("periodDisplay")
        plays = p.get("playbyplayStats") if isinstance(p.get("playbyplayStats"), list) else []
        summary["period_summaries"].append({
            "periodNumber": pn,
            "periodDisplay": pd,
            "playsCount": len(plays),
        })

    fh = extract_first_half_plays(payload)
    summary["first_half_plays_count"] = len(fh)
    summary["halftime_score"] = halftime_score_from_first_half(fh)
    return summary


def main():
    if len(sys.argv) < 2:
        print("Usage: python step4_pull_halftime_pbp_v2.py <gameID>")
        print("Example: python step4_pull_halftime_pbp_v2.py 6530691")
        sys.exit(1)

    game_id = sys.argv[1].strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    game_dir = os.path.join(OUT_ROOT, game_id)
    os.makedirs(game_dir, exist_ok=True)

    full_path = os.path.join(game_dir, f"pbp_full_{ts}.json")
    first_half_path = os.path.join(game_dir, f"pbp_first_half_{ts}.json")
    err_log_path = os.path.join(LOG_DIR, f"pbp_live_error_{game_id}_{ts}.json")

    try:
        payload = fetch_pbp_with_retries(game_id)
    except Exception as e:
        # Clean failure log (no traceback spam)
        save_json(err_log_path, {
            "gameID": game_id,
            "timestamp": ts,
            "error": str(e),
            "note": "Upstream PBP may be unavailable temporarily (502). Try again closer to halftime."
        })
        print(f"[FAIL] Could not fetch PBP for gameID={game_id}")
        print(f"       Error log saved -> {err_log_path}")
        sys.exit(2)

    # Save full payload
    save_json(full_path, payload)

    # Extract and save first-half plays using confirmed schema [2](https://htsag-my.sharepoint.com/personal/jrobinson_htsag_com/Documents/Microsoft%20Copilot%20Chat%20Files/pbp_raw_6503596.json)
    first_half_plays = extract_first_half_plays(payload)
    save_json(first_half_path, {
        "gameID": game_id,
        "extracted_at": ts,
        "schema_note": "first half = periods[periodNumber==1].playbyplayStats",
        "first_half_plays": first_half_plays
    })

    # Print summary
    s = summarize(payload)
    print(f"[OK] Saved full PBP -> {full_path}")
    print(f"[OK] Saved first-half PBP -> {first_half_path}")
    print("\nSummary:")
    print(f"- periods found: {s['num_periods_in_payload']}")
    for p in s["period_summaries"]:
        print(f"  - period {p['periodNumber']}: {p['periodDisplay']} | plays={p['playsCount']}")
    print(f"- first_half_plays_count: {s['first_half_plays_count']}")
    print(f"- halftime_score (if available): {s['halftime_score']}")

    # Helpful note if pregame/no plays yet
    if s["first_half_plays_count"] == 0:
        print("\nNote: first-half plays are 0. This can be normal pregame or if upstream PBP isn't populated yet.")
        print("Try again closer to tip or at halftime.\n")


if __name__ == "__main__":
    main()