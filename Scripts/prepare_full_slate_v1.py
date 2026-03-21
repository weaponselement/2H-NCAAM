import argparse
import subprocess
import sys
from datetime import datetime
import json
from pathlib import Path
from paths import PROJECT_ROOT

BASE_DIR = PROJECT_ROOT
SLATE_SCRIPT = BASE_DIR / "Scripts/slate_d1_game_ids.py"
LAST4_SCRIPT = BASE_DIR / "Scripts/step2b_last4_from_scoreboard_v2.py"
SLATE_DIR = BASE_DIR / "data/processed/slates"
SELECTED_DIR = BASE_DIR / "data/processed/selected_games"


def run(cmd):
    print("\nRunning:", " ".join(cmd))
    subprocess.run([sys.executable] + cmd[1:], check=True)


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="YYYY-MM-DD", default=None)

    args = parser.parse_args()

    if args.date:
        date = args.date
    else:
        date = datetime.now().strftime("%Y-%m-%d")

    print(f"\nPreparing FULL D1 slate for {date}")

    # Step 1 pull slate
    run(["python", str(SLATE_SCRIPT), "--date", date])

    slate_json = SLATE_DIR / f"slate_d1_{date}.json"

    if not slate_json.exists():
        raise RuntimeError("Slate JSON not found")

    print("\nLoading slate:", slate_json)

    with open(slate_json) as f:
        slate = json.load(f)

    games = slate["games"]

    selected_path = SELECTED_DIR / f"selected_games_{date}.json"

    print("Building selected games file:", selected_path)

    for g in games:
        g["date"] = date

    with open(selected_path, "w") as f:
        json.dump(games, f, indent=2)

    print(f"\nSelected games created ({len(games)} games)")

    # Step 2 build baselines
    run([
        "python",
        str(LAST4_SCRIPT),
        "--selected-games",
        str(selected_path)
    ])

    print("\nSLATE PREP COMPLETE")
    print("You can now run halftime analysis for ANY game in today's slate.")


if __name__ == "__main__":
    main()