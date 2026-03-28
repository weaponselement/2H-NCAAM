"""
Merge SGO-staged market lines into a canonical GameID-keyed CSV file.

This script:
- Reads one or more sgo_stage_*.json files from market_lines/
- Extracts only EXACT matches
- Deduplicates by GameID (keeps first/oldest)
- Writes to a canonical lines file keyed by GameID
- Never overwrites existing GameID entries

Usage:
  python merge_staged_lines_to_canonical_v1.py --input data/processed/market_lines/sgo_stage_*.json
  python merge_staged_lines_to_canonical_v1.py --input data/processed/market_lines/sgo_stage_real_2026_03_22.json

Output:
  data/processed/market_lines/canonical_lines.csv
"""

import argparse
import csv
import json
import os
from collections import OrderedDict
from glob import glob
from pathlib import Path

from paths import DATA_DIR

OUTPUT_DIR = DATA_DIR / "processed" / "market_lines"
CANONICAL_FILE = OUTPUT_DIR / "canonical_lines.csv"

CANONICAL_FIELDS = [
    "game_id",
    "date",
    "away_seo",
    "home_seo",
    "spread_home",
    "spread_away",
    "ml_home",
    "ml_away",
    "total_game",
    "total_2h",
    "sgo_event_id",
    "source_file",
    "staged_timestamp",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def load_canonical_lines():
    """Load existing canonical lines keyed by GameID."""
    existing = {}
    if CANONICAL_FILE.exists():
        with CANONICAL_FILE.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                gid = str(row.get("game_id") or "").strip()
                if gid:
                    existing[gid] = row
    return existing


def staged_to_canonical(staged_row: dict, staged_file_name: str) -> dict | None:
    """Convert a staged EXACT row into canonical fields."""
    match_status = str(staged_row.get("match_status") or "").strip()
    if match_status != "EXACT":
        return None

    gid = str(staged_row.get("matched_game_id") or "").strip()
    if not gid:
        return None

    return {
        "game_id": gid,
        "date": staged_row.get("matched_date", ""),
        "away_seo": staged_row.get("matched_away", ""),
        "home_seo": staged_row.get("matched_home", ""),
        "spread_home": staged_row.get("spread_home", ""),
        "spread_away": staged_row.get("spread_away", ""),
        "ml_home": staged_row.get("ml_home", ""),
        "ml_away": staged_row.get("ml_away", ""),
        "total_game": staged_row.get("total_game", ""),
        "total_2h": staged_row.get("total_2h", ""),
        "sgo_event_id": staged_row.get("sgo_event_id", ""),
        "source_file": staged_file_name,
        "staged_timestamp": "",
    }


def main():
    parser = argparse.ArgumentParser(
        description="Merge SGO-staged EXACT matches into canonical GameID-keyed CSV.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Glob pattern for staged JSON files (e.g., 'data/processed/market_lines/sgo_stage_*.json')",
    )
    parser.add_argument(
        "--allow-overwrite",
        action="store_true",
        help="Allow overwriting existing GameID entries (default: skip duplicates)",
    )
    args = parser.parse_args()

    input_pattern = str(args.input)
    staged_files = sorted(glob(input_pattern))

    if not staged_files:
        print(f"No files matched pattern: {input_pattern}")
        return 1

    print(f"Found {len(staged_files)} staged file(s)")

    # Load existing canonical lines
    existing = load_canonical_lines()
    print(f"Existing canonical lines: {len(existing)} games")

    # Merge process
    merged_map = OrderedDict(existing)
    skipped = 0
    added = 0

    for staged_path in staged_files:
        staged = load_json(Path(staged_path))
        rows = staged.get("rows", [])
        file_name = os.path.basename(staged_path)

        for staged_row in rows:
            canonical_row = staged_to_canonical(staged_row, file_name)
            if not canonical_row:
                continue

            gid = canonical_row["game_id"]
            if gid in merged_map and not args.allow_overwrite:
                skipped += 1
                continue

            merged_map[gid] = canonical_row
            added += 1
            print(f"  Added: GameID={gid} {canonical_row['away_seo']} @ {canonical_row['home_seo']}")

    # Write merged result
    merged_rows = list(merged_map.values())
    save_csv(CANONICAL_FILE, merged_rows)

    print("")
    print("MERGE COMPLETE")
    print(f"Staged files: {len(staged_files)}")
    print(f"Added: {added}")
    print(f"Skipped (existing): {skipped}")
    print(f"Total canonical lines: {len(merged_rows)}")
    print(f"Output: {CANONICAL_FILE}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
