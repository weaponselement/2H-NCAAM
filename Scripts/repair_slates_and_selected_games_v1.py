import os
import re
import json
import shutil
from glob import glob
from paths import DATA_DIR

DATA_ROOT = str(DATA_DIR)
SELECTED_DIR = os.path.join(DATA_ROOT, "processed", "selected_games")
SLATES_DIR = os.path.join(DATA_ROOT, "processed", "slates")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def extract_date_from_name(filename):
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def build_selected_games_from_slate(slate_payload, date_str):
    games = slate_payload.get("games", [])
    out = []

    for g in games:
        row = dict(g)
        row["date"] = date_str
        out.append(row)

    return out


def main():
    os.makedirs(SELECTED_DIR, exist_ok=True)
    os.makedirs(SLATES_DIR, exist_ok=True)

    moved = 0
    built = 0
    problems = []

    misplaced_json = glob(os.path.join(SELECTED_DIR, "slate_d1_*.json"))
    misplaced_csv = glob(os.path.join(SELECTED_DIR, "slate_d1_*.csv"))

    print("Found misplaced slate JSON files:", len(misplaced_json))
    print("Found misplaced slate CSV files :", len(misplaced_csv))
    print("")

    # Move slate JSON files into proper slates folder
    for src in misplaced_json:
        name = os.path.basename(src)
        dst = os.path.join(SLATES_DIR, name)

        if os.path.abspath(src) != os.path.abspath(dst):
            if not os.path.exists(dst):
                shutil.move(src, dst)
                print(f"MOVED JSON -> {dst}")
                moved += 1
            else:
                print(f"JSON already exists in slates, leaving source alone: {name}")

    # Move slate CSV files into proper slates folder
    for src in misplaced_csv:
        name = os.path.basename(src)
        dst = os.path.join(SLATES_DIR, name)

        if os.path.abspath(src) != os.path.abspath(dst):
            if not os.path.exists(dst):
                shutil.move(src, dst)
                print(f"MOVED CSV  -> {dst}")
                moved += 1
            else:
                print(f"CSV already exists in slates, leaving source alone: {name}")

    print("")
    print("Building selected_games_YYYY-MM-DD.json files from slate JSONs...")
    print("")

    slate_jsons = sorted(glob(os.path.join(SLATES_DIR, "slate_d1_*.json")))

    for slate_path in slate_jsons:
        name = os.path.basename(slate_path)
        date_str = extract_date_from_name(name)

        if not date_str:
            problems.append(f"Could not parse date from filename: {name}")
            continue

        try:
            payload = load_json(slate_path)
        except Exception as e:
            problems.append(f"Failed to load {name}: {e}")
            continue

        if not isinstance(payload, dict) or "games" not in payload:
            problems.append(f"Slate JSON has wrong structure: {name}")
            continue

        selected_games = build_selected_games_from_slate(payload, date_str)
        out_path = os.path.join(SELECTED_DIR, f"selected_games_{date_str}.json")

        save_json(out_path, selected_games)
        print(f"BUILT -> {out_path} ({len(selected_games)} games)")
        built += 1

    print("")
    print("REPAIR COMPLETE")
    print(f"Files moved: {moved}")
    print(f"selected_games files built: {built}")

    if problems:
        print("")
        print("Problems:")
        for p in problems:
            print(" -", p)


if __name__ == "__main__":
    main()