import argparse
import glob
import json
import os
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

# Public API host used throughout this project
API_BASE = "https://ncaa-api.henrygd.me"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# --- Resolve DATA_ROOT safely ---
# Prefer your central paths.py, but fall back to deriving from this file location
try:
    # paths.py lives in Scripts/ and is already used elsewhere in your repo
    from paths import DATA_DIR  # type: ignore

    DATA_ROOT = str(DATA_DIR)
except Exception:
    # Fallback: project root is parent of Scripts/
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    DATA_ROOT = str(PROJECT_ROOT / "data")

BASELINES_DIR = os.path.join(DATA_ROOT, "processed", "baselines")
PBP_ROOT = os.path.join(DATA_ROOT, "raw", "pbp")
LOG_DIR = os.path.join(DATA_ROOT, "logs")

os.makedirs(PBP_ROOT, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Retry statuses that are commonly transient
RETRY_STATUSES = {429, 500, 502, 503, 504}


class RateLimiter:
    """
    Simple global rate limiter:
    Ensures we do not exceed max_rps overall, even with multiple worker threads.
    """
    def __init__(self, max_rps: float):
        self.interval = 1.0 / max_rps if max_rps and max_rps > 0 else 0.0
        self._lock = threading.Lock()
        self._next_time = time.monotonic()

    def wait(self):
        if self.interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                time.sleep(self._next_time - now)
            self._next_time = max(self._next_time + self.interval, time.monotonic())


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        # Keep file compact (no indent) to reduce disk overhead for large pulls
        json.dump(obj, f, ensure_ascii=False)


def pick_default_baseline_file() -> Optional[str]:
    """
    Pick the newest last4_YYYY-MM-DD.json (or last*_*.json) in baselines dir.
    """
    if not os.path.isdir(BASELINES_DIR):
        return None
    candidates = sorted(
        glob.glob(os.path.join(BASELINES_DIR, "last4_*.json")) +
        glob.glob(os.path.join(BASELINES_DIR, "last*_*.json")),
        key=lambda p: os.path.getmtime(p),
        reverse=True
    )
    return candidates[0] if candidates else None


def fetch_pbp_with_retries(session: requests.Session, game_id: str, timeout: int, max_tries: int) -> Tuple[int, str, Optional[dict], str]:
    """
    Fetch play-by-play payload with retries/backoff for transient statuses.
    Returns: (status_code, url, payload_or_none, response_text_snippet)
    """
    url = f"{API_BASE}/game/{game_id}/play-by-play"
    last_text = ""
    for attempt in range(1, max_tries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            status = r.status_code
            last_text = (r.text or "")[:300]

            if status == 200:
                return status, url, r.json(), last_text

            if status in RETRY_STATUSES:
                # exponential backoff + jitter
                wait = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
                time.sleep(wait)
                continue

            # non-retryable
            return status, url, None, last_text
        except Exception as e:
            # network exception: retry
            wait = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0, 0.5)
            last_text = f"exception: {e}"
            time.sleep(wait)

    return 0, url, None, last_text


def build_game_to_teams(baseline: dict) -> Dict[str, set]:
    """
    baseline["teams"] expected to be: team_seo -> list of game records containing "gameID"
    Build mapping: gameID -> set(team_seo)
    """
    teams = baseline.get("teams", {}) or {}
    game_to_teams: Dict[str, set] = {}
    for team_seo, games in teams.items():
        if not isinstance(games, list):
            continue
        for g in games:
            if not isinstance(g, dict):
                continue
            gid = str(g.get("gameID") or "").strip()
            if not gid:
                continue
            game_to_teams.setdefault(gid, set()).add(team_seo)
    return game_to_teams


def worker_fetch_and_save(
    gid: str,
    teams_for_game: List[str],
    limiter: RateLimiter,
    timeout: int,
    max_tries: int,
) -> Tuple[str, str, List[str], Optional[int], Optional[str], Optional[str]]:
    """
    Returns tuple:
      (kind, gameID, teams_for_game, status, url, note)
    kind: "skip" | "ok" | "fail"
    """
    # per-team target paths (save the same payload under each team's folder)
    per_team_paths = [os.path.join(PBP_ROOT, t, f"{gid}.json") for t in teams_for_game]

    # if all exist, skip
    if all(os.path.exists(p) for p in per_team_paths):
        return ("skip", gid, teams_for_game, None, None, None)

    # Rate limit globally across all workers
    limiter.wait()

    # Use one session per call (thread-safe enough at this scale)
    with requests.Session() as session:
        status, url, payload, text_snip = fetch_pbp_with_retries(
            session=session,
            game_id=gid,
            timeout=timeout,
            max_tries=max_tries,
        )

    if status != 200 or payload is None:
        note = f"status={status} body_snip={text_snip!r}"
        return ("fail", gid, teams_for_game, status, url, note)

    # Save payload under each team folder
    for path in per_team_paths:
        save_json(path, payload)

    return ("ok", gid, teams_for_game, 200, url, None)


def parse_args():
    ap = argparse.ArgumentParser(description="Download baseline play-by-play files (per-team copies).")
    ap.add_argument(
        "--baseline",
        default=None,
        help="Path to baseline manifest JSON (e.g., last4_YYYY-MM-DD.json). If omitted, newest baseline in data/processed/baselines is used.",
    )
    ap.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent download workers (threads).",
    )
    ap.add_argument(
        "--max-rps",
        type=float,
        default=4.0,
        help="Global max requests per second across all workers (polite default).",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=45,
        help="HTTP timeout in seconds for each request.",
    )
    ap.add_argument(
        "--max-tries",
        type=int,
        default=6,
        help="Max retry attempts for transient failures (429/5xx/network).",
    )
    return ap.parse_args()


def main():
    args = parse_args()

    baseline_file = args.baseline or pick_default_baseline_file()
    if not baseline_file or not os.path.exists(baseline_file):
        print("Baseline manifest not found.")
        print("Pass --baseline with a file like:")
        print(r"  C:\NCAA Model\data\processed\baselines\last4_YYYY-MM-DD.json")
        return

    baseline = load_json(baseline_file)
    run_date = baseline.get("run_date", "unknown-date")

    game_to_teams = build_game_to_teams(baseline)
    all_game_ids = sorted(game_to_teams.keys())
    total = len(all_game_ids)

    print("\nStep 3: Download baseline PBP")
    print(f"Baseline file: {baseline_file}")
    print(f"Run date: {run_date}")
    print(f"Unique baseline games to fetch: {total}")
    print(f"Workers: {args.workers}")
    print(f"Max RPS (global): {args.max_rps}\n")

    log = {
        "run_date": run_date,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": API_BASE,
        "baseline_file": baseline_file,
        "total_games": total,
        "workers": args.workers,
        "max_rps": args.max_rps,
        "timeout": args.timeout,
        "max_tries": args.max_tries,
        "saved": [],
        "skipped_existing": [],
        "failed": [],
    }

    limiter = RateLimiter(max_rps=float(args.max_rps))

    futures = {}
    completed = 0
    saved_count = 0
    skipped_count = 0
    failed_count = 0

    with ThreadPoolExecutor(max_workers=max(1, int(args.workers))) as ex:
        for gid in all_game_ids:
            teams_for_game = sorted(list(game_to_teams[gid]))
            fut = ex.submit(
                worker_fetch_and_save,
                gid,
                teams_for_game,
                limiter,
                int(args.timeout),
                int(args.max_tries),
            )
            futures[fut] = gid

        for fut in as_completed(futures):
            completed += 1
            kind, gid, teams_for_game, status, url, note = fut.result()

            if kind == "skip":
                skipped_count += 1
                log["skipped_existing"].append({"gameID": gid, "teams": teams_for_game})
                print(f"[{completed}/{total}] SKIP {gid} (already saved for {', '.join(teams_for_game)})")
                continue

            if kind == "fail":
                failed_count += 1
                log["failed"].append({
                    "gameID": gid,
                    "teams": teams_for_game,
                    "status": status,
                    "url": url,
                    "note": note,
                })
                print(f"[{completed}/{total}] FAIL {gid} {note}")
                continue

            # ok
            saved_count += 1
            log["saved"].append({"gameID": gid, "teams": teams_for_game, "url": url})
            print(f"[{completed}/{total}] OK {gid} saved -> {len(teams_for_game)} team file(s)")

    log["finished_at"] = datetime.now().isoformat(timespec="seconds")

    log_path = os.path.join(LOG_DIR, f"pbp_download_{run_date}.json")
    save_json(log_path, log)

    print("\nDone.")
    print(f"Saved PBP root: {PBP_ROOT}")
    print(f"Run log: {log_path}")
    print(f"Summary: saved={saved_count}, skipped_existing={skipped_count}, failed={failed_count}\n")

    if failed_count:
        print("Some games failed to download PBP (transient failures can happen).")
        print("Re-run this command; it skips existing files and retries only missing ones.\n")


if __name__ == "__main__":
    main()