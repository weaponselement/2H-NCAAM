import argparse
import glob
import json
import os
from openpyxl import load_workbook

RESULTS_XLSX = r"C:\NCAA Model\logs\NCAAM Results.xlsx"
DATA_ROOT = r"C:\NCAA Model\data"


def latest_report_path(game_id: str):
    pattern = os.path.join(
        DATA_ROOT,
        "processed",
        "reports",
        f"feature_report_v5_test_{game_id}_*.json"
    )
    matches = glob.glob(pattern)

    if not matches:
        pattern = os.path.join(
            DATA_ROOT,
            "processed",
            "reports",
            f"feature_report_v4_{game_id}_*.json"
        )
        matches = glob.glob(pattern)

    if not matches:
        return None

    matches.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return matches[0]


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def first_empty_row(ws):
    row = 2
    while ws[f"B{row}"].value not in (None, ""):
        row += 1
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("game_id")
    args = parser.parse_args()

    report_path = latest_report_path(args.game_id)

    if not report_path:
        print(f"No report found for game {args.game_id}")
        return

    report = load_json(report_path)

    halftime = report.get("halftime_score", {})
    projection = report.get("projection", {})
    game_state = report.get("game_state", {})

    teams = report.get("teams", {})
    away = (teams.get("away") or {}).get("seo", "")
    home = (teams.get("home") or {}).get("seo", "")

    away_ht = halftime.get("away")
    home_ht = halftime.get("home")

    halftime_score = ""
    if away_ht is not None and home_ht is not None:
        halftime_score = f"{away_ht}-{home_ht}"

    pred_margin = projection.get("winner_margin_range", "")
    pred_2h = (projection.get("second_half_points_projection") or {}).get("range", "")
    pred_total = (projection.get("full_game_total_projection") or {}).get("range", "")

    wb = load_workbook(RESULTS_XLSX)
    ws = wb["Game_Log"]

    row = first_empty_row(ws)

    ws[f"A{row}"] = report.get("run_date", "")
    ws[f"B{row}"] = args.game_id
    ws[f"C{row}"] = away
    ws[f"D{row}"] = home
    ws[f"E{row}"] = halftime_score
    ws[f"F{row}"] = game_state.get("pace_profile", "")
    ws[f"G{row}"] = projection.get("winner_projection", "")
    ws[f"H{row}"] = pred_margin
    ws[f"I{row}"] = pred_2h
    ws[f"J{row}"] = pred_total
    ws[f"K{row}"] = projection.get("confidence", "")

    wb.save(RESULTS_XLSX)

    print(f"Logged prediction for game {args.game_id} into row {row}")
    print(f"Workbook: {RESULTS_XLSX}")


if __name__ == "__main__":
    main()