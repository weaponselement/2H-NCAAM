import argparse
import os
import re
import subprocess
import sys
from collections import OrderedDict

PROJECT_ROOT = r"C:\NCAA Model"
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "Scripts")
DEFAULT_TXT = os.path.join(PROJECT_ROOT, "logs", "Pick Results-.txt")


def extract_game_ids(txt_path: str):
    with open(txt_path, "r", encoding="utf-8") as f:
        text = f.read()

    ids = re.findall(r'(?<!\d)(\d{7})(?!\d)', text)
    return list(OrderedDict.fromkeys(ids))


def run_script(py_exe: str, script_name: str, game_id: str):
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    cmd = [py_exe, script_path, game_id]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def main():
    parser = argparse.ArgumentParser(
        description="Batch log predictions and update postgame results from a txt file of game IDs."
    )
    parser.add_argument(
        "--txt",
        default=DEFAULT_TXT,
        help=r'Path to Pick Results txt file (default: C:\NCAA Model\logs\Pick Results-.txt)'
    )
    args = parser.parse_args()

    txt_path = args.txt
    if not os.path.exists(txt_path):
        print(f"TXT file not found: {txt_path}")
        print(r"Put your Pick Results-.txt file in C:\NCAA Model\logs\ or pass --txt with the full path.")
        sys.exit(1)

    game_ids = extract_game_ids(txt_path)
    if not game_ids:
        print(f"No 7-digit game IDs found in: {txt_path}")
        sys.exit(1)

    py_exe = sys.executable

    print(f"Found {len(game_ids)} game IDs in: {txt_path}")
    print("Starting batch process...\n")

    summary = {
        "logged_ok": [],
        "logged_fail": [],
        "updated_ok": [],
        "updated_fail": [],
    }

    for i, gid in enumerate(game_ids, start=1):
        print(f"[{i}/{len(game_ids)}] GameID {gid}")

        code1, out1, err1 = run_script(py_exe, "log_prediction_to_results_v1.py", gid)
        if code1 == 0:
            summary["logged_ok"].append(gid)
            print("  LOG  : OK")
            if out1:
                for line in out1.splitlines():
                    print(f"         {line}")
        else:
            summary["logged_fail"].append((gid, err1 or out1 or "Unknown error"))
            print("  LOG  : FAIL")
            if out1:
                for line in out1.splitlines():
                    print(f"         {line}")
            if err1:
                for line in err1.splitlines():
                    print(f"         {line}")

        code2, out2, err2 = run_script(py_exe, "update_results_postgame_v1.py", gid)
        if code2 == 0:
            summary["updated_ok"].append(gid)
            print("  POST : OK")
            if out2:
                for line in out2.splitlines():
                    print(f"         {line}")
        else:
            summary["updated_fail"].append((gid, err2 or out2 or "Unknown error"))
            print("  POST : FAIL")
            if out2:
                for line in out2.splitlines():
                    print(f"         {line}")
            if err2:
                for line in err2.splitlines():
                    print(f"         {line}")

        print()

    print("=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Logged OK   : {len(summary['logged_ok'])}")
    print(f"Logged FAIL : {len(summary['logged_fail'])}")
    print(f"Updated OK  : {len(summary['updated_ok'])}")
    print(f"Updated FAIL: {len(summary['updated_fail'])}")

    if summary["logged_fail"]:
        print("\nLog failures:")
        for gid, msg in summary["logged_fail"]:
            print(f"  - {gid}: {msg}")

    if summary["updated_fail"]:
        print("\nPostgame update failures:")
        for gid, msg in summary["updated_fail"]:
            print(f"  - {gid}: {msg}")


if __name__ == "__main__":
    main()