import os
import json
import glob
import re
from paths import DATA_DIR

DATA_ROOT = str(DATA_DIR)
SLATES_DIR = os.path.join(DATA_ROOT, "processed", "slates")
SELECTED_DIR = os.path.join(DATA_ROOT, "processed", "selected_games")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def extract_date(name):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", name)
    return m.group(1) if m else None


def extract_games(payload):
    if isinstance(payload, dict):
        games = payload.get("games", [])
        return games if isinstance(games, list) else []
    if isinstance(payload, list):
        return payload
    return []


def main():
    os.makedirs(SELECTED_DIR, exist_ok=True)

    slate_paths = sorted(glob.glob(os.path.join(SLATES_DIR, "slate_d1_*.json")))
    built = 0
    skipped = 0
    failed = 0

    for slate_path in slate_paths:
        name = os.path.basename(slate_path)
        date_str = extract_date(name)

        if not date_str:
            print(f"SKIP bad filename: {name}")
            failed += 1
            continue

        out_path = os.path.join(SELECTED_DIR, f"selected_games_{date_str}.json")

        if os.path.exists(out_path):
            print(f"SKIP exists: {out_path}")
            skipped += 1
            continue

        try:
            payload = load_json(slate_path)
            games = extract_games(payload)

            if not isinstance(games, list):
                print(f"FAIL: {name} -> games payload is not a list")
                failed += 1
                continue

            selected_games = []
            for g in games:
                if not isinstance(g, dict):
                    continue
                row = dict(g)
                row["date"] = date_str
                selected_games.append(row)

            save_json(out_path, selected_games)
            print(f"BUILT: {out_path} ({len(selected_games)} games)")
            built += 1

        except Exception as e:
            print(f"FAIL: {name} -> {e}")
            failed += 1

    print("")
    print("DONE")
    print(f"Built   : {built}")
    print(f"Skipped : {skipped}")
    print(f"Failed  : {failed}")


if __name__ == "__main__":
    main()