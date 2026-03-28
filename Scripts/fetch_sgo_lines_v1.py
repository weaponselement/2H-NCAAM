"""
Fetch SGO (sportsgameodds.com v2) closing lines for a specific date.

This script queries the SGO API for NCAAB games on a given date,
extracts closing lines, and saves the raw event payload as JSON.

Usage:
  python fetch_sgo_lines_v1.py --date 2026-02-18
  python fetch_sgo_lines_v1.py --date 2026-02-18 --output custom_output.json

Environment:
  SPORTS_API_KEY: Your sportsgameodds.com API key (required)

Output:
  data/processed/market_lines/sgo_events_YYYY-MM-DD.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from paths import DATA_DIR

OUTPUT_DIR = DATA_DIR / "processed" / "market_lines"

# SGO API endpoint and ODD IDs
API_BASE = "https://api.sportsgameodds.com/v2/events"
LEAGUE_ID = "NCAAB"

ODD_IDS = [
    "points-home-game-sp-home",
    "points-away-game-sp-away",
    "points-home-game-ml-home",
    "points-away-game-ml-away",
    "points-all-game-ou-over",
    "points-all-game-ou-under",
    "points-all-2h-ou-over",
    "points-all-2h-ou-under",
]


def get_api_key():
    """Get SGO API key from environment."""
    key = os.environ.get("SPORTS_API_KEY", "").strip()
    if not key:
        raise ValueError(
            "SPORTS_API_KEY environment variable not set. "
            "Set it with: [System.Environment]::SetEnvironmentVariable('SPORTS_API_KEY', 'YOUR_KEY', 'User')"
        )
    return key


def parse_date(date_str: str) -> tuple:
    """Parse YYYY-MM-DD and return (startAfter, startBefore) as ISO 8601 UTC datetimes."""
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Use YYYY-MM-DD.")

    # For US games, the date typically spans from midnight UTC that day through end of day next day UTC
    # (late evening US games fall on the next UTC day)
    starts_after = date.replace(hour=0, minute=0, second=0, microsecond=0)
    starts_before = (date + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Use Z suffix (UTC) format as required by SGO API
    return starts_after.strftime("%Y-%m-%dT%H:%M:%SZ"), starts_before.strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_sgo_events(date_str: str) -> dict:
    """Fetch NCAAB events and closing lines from SGO for a date."""
    api_key = get_api_key()
    starts_after, starts_before = parse_date(date_str)

    params = {
        "apiKey": api_key,
        "leagueID": LEAGUE_ID,
        "finalized": "true",
        "startsAfter": starts_after,
        "startsBefore": starts_before,
        "oddID": ",".join(ODD_IDS),
        "includeOpenCloseOdds": "true",
        "limit": 100,
    }

    print(f"Querying SGO for NCAAB games on {date_str}...")
    print(f"  startsAfter:  {starts_after}")
    print(f"  startsBefore: {starts_before}")

    all_events = []
    cursor = None

    while True:
        if cursor:
            params["cursor"] = cursor

        try:
            response = requests.get(API_BASE, params=params, timeout=30)
            response.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"SGO API request failed: {e}")

        data = response.json()
        # SGO v2 API returns events under "data" key (not "events")
        events = data.get("data") or data.get("events") or []
        all_events.extend(events)

        print(f"  Fetched {len(events)} events (total so far: {len(all_events)})")

        # Debug: if first page returns 0 events, dump response keys for diagnosis
        if not all_events and not cursor:
            top_keys = list(data.keys()) if isinstance(data, dict) else type(data).__name__
            print(f"  [debug] Response keys: {top_keys}")
            if isinstance(data, dict):
                for k, v in data.items():
                    snippet = str(v)[:120] if not isinstance(v, (list, dict)) else f"({type(v).__name__}, len={len(v)})"
                    print(f"  [debug]   {k}: {snippet}")

        cursor = data.get("nextCursor") or data.get("cursor")
        if not cursor:
            break

    return {
        "date": date_str,
        "api_base": API_BASE,
        "league_id": LEAGUE_ID,
        "starts_after": starts_after,
        "starts_before": starts_before,
        "odd_ids": ODD_IDS,
        "event_count": len(all_events),
        "events": all_events,
    }


def save_json(path: Path, payload):
    """Save payload to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(payload.get('events', []))} events to {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Fetch SGO closing lines for NCAAB games on a specific date.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format (e.g., 2026-02-18)")
    parser.add_argument("--output", default=None, help="Custom output file path (default: auto-named in market_lines/)")
    args = parser.parse_args()

    try:
        payload = fetch_sgo_events(args.date)
    except Exception as e:
        print(f"Error fetching SGO data: {e}", file=sys.stderr)
        return 1

    if not payload["events"]:
        print(f"No events found for {args.date}")
        return 1

    if args.output:
        output_path = Path(args.output)
    else:
        output_path = OUTPUT_DIR / f"sgo_events_{args.date}.json"

    save_json(output_path, payload)

    print(f"\nFetch complete: {payload['event_count']} events")
    print(f"Next step: stage the data with stage_market_lines_sgo_v1.py")
    print(
        f"  python stage_market_lines_sgo_v1.py --input {output_path} "
        f"--date {args.date} --label sgo_real_{args.date}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
