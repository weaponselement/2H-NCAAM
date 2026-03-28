# NCAA Model – Current Runbook (March 2026)

This top section is the active operating guide.
Older notes lower in this file are preserved but should be treated as historical context.

START HERE FOR FULL CONTEXT:
- `MASTER_HANDOFF_PREGAME_MODEL_2026-03-27.txt` (single-source handoff for new chat sessions and next-season restart)

## 1) What to Use Going Forward

Use these as your primary scripts/tasks:

- Pregame slate prep: `Scripts/prepare_full_slate_v1.py`
- Baseline PBP download: `Scripts/step3_download_pbp_baselines.py`
- Halftime pull: `Scripts/step4_pull_halftime_pbp_v2.py`
- Halftime feature report: `Scripts/step4b_feature_report_from_file_v5_test.py`
- Log prediction to workbook: `Scripts/log_prediction_to_results_v1.py`
- Trigger/stake gate from workbook: `Scripts/trigger_gate_from_workbook_v1.py`
- Postgame results backfill (missing only): `Scripts/update_new_results_only_v1.py`
- VS Code orchestrator task runner: `Scripts/vscode_task_runner.ps1`

For pregame totals experiments with model output (not workbook writeback):

- Cached pregame totals predictor (recommended): `Scripts/predict_pregame_totals_cached_v1.py`

## 2) What Is Experimental / Analysis-Only

Keep these for research, not daily operations:

- Window evaluator: `Scripts/evaluate_window_optimization_v1.py`
- Window sweep harness: `Scripts/test_window_optimization_simple_v1.py`
- Deep-dive diagnostics: `Scripts/analyze_pregame_model_depth_v1.py`
- Legacy one-off tonight scripts: `Scripts/_predict_tonight_v1.py`, `Scripts/_predict_tonight_v2.py`

## 3) Fast vs Slow Pregame Totals Runs

- First run on new data day: cache miss, model trains (~7-10 minutes)
- Repeat runs with unchanged inputs: cache hit (usually under 30-60 seconds)

Run cached predictor:

```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "Scripts/predict_pregame_totals_cached_v1.py" `
  --window 5 `
  --game "michigan-st,uconn,136.5,Michigan State vs UConn,7:45 PM CST" `
  --game "tennessee,iowa-st,139.5,Tennessee vs Iowa State,9:25 PM CST"
```

Force retrain (ignore cache):

```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "Scripts/predict_pregame_totals_cached_v1.py" `
  --window 5 `
  --force-retrain `
  --game "michigan-st,uconn,136.5"
```

Cache files are saved to:

- `models/pregame_total_cache/pregame_total_rf_w5.pkl`
- `models/pregame_total_cache/pregame_total_rf_w5.meta.json`

---

# NCAA Model – Daily Flow (VS Code Terminal)

This project is designed to be run from the **VS Code integrated terminal** with the working directory set to: C:\NCAA Model

All commands below explicitly use the virtual environment Python:C:\NCAA Model.venv\Scripts\python.exe

---

## Step 0 — Prepare Slate, Selected Games, and Baselines (ONE command)

This step:
- pulls the D1 slate for a date
- builds `selected_games_YYYY-MM-DD.json`
- builds the `last4_YYYY-MM-DD.json` baseline manifest

### ✅ Run:
```powershell
& "c:\NCAA Model\.venv\Scripts\python.exe" "c:\NCAA Model\Scripts\prepare_full_slate_v1.py" --date YYYY-MM-DD

Files created/updated:
data\processed\slates\slate_d1_YYYY-MM-DD.json
data\processed\slates\slate_d1_YYYY-MM-DD.csv
data\processed\selected_games\selected_games_YYYY-MM-DD.json
data\processed\baselines\last4_YYYY-MM-DD.json

Show first 25 games with IDs:
 
Import-Csv "C:\NCAA Model\data\processed\slates\slate_d1_YYYY-MM-DD.csv" |
  Select-Object gameID, away_short, home_short |
  ForEach-Object { "{0}  |  {1} @ {2}" -f $_.gameID, $_.away_short, $_.home_short } |
  Select-Object -First 25

To show all games, remove:
    | Select-Object -First 25


Step 2 — Pull Halftime Play-by-Play for a Game
This step pulls live PBP and extracts first-half plays.
✅ Run:
& "c:\NCAA Model\.venv\Scripts\python.exe" "c:\NCAA Model\Scripts\step4_pull_halftime_pbp_v2.py" GAME_ID

✅ Files created:
data\raw\pbp_live\GAME_ID\pbp_full_<timestamp>.json
data\raw\pbp_live\GAME_ID\pbp_first_half_<timestamp>.json

Step 3 — Generate Halftime Feature Report
This reads:

the latest halftime PBP
the baseline manifest
the selected games file

✅ Run:
& "c:\NCAA Model\.venv\Scripts\python.exe" "c:\NCAA Model\Scripts\step4b_feature_report_from_file_v5_test.py" GAME_ID `
  --baseline-manifest "C:\NCAA Model\data\processed\baselines\last4_YYYY-MM-DD.json" `
  --selected-games "C:\NCAA Model\data\processed\selected_games\selected_games_YYYY-MM-DD.json"

  ✅ File created:
data\processed\reports\feature_report_v5_test_GAME_ID_<timestamp>.json

Step 4 — Log Prediction to Workbook (WRITES TO EXCEL)
⚠️ This writes immediately to Excel.
⚠️ Running it twice for the same game will create duplicates.
✅ Run:
& "c:\NCAA Model\.venv\Scripts\python.exe" "c:\NCAA Model\Scripts\log_prediction_to_results_v1.py" GAME_ID

✅ Workbook:
logs\NCAAM Results.xlsx

Optional — Verify Files Exist (Sanity Check)
Get-ChildItem `
  "C:\NCAA Model\data\processed\slates\slate_d1_YYYY-MM-DD.*", `
  "C:\NCAA Model\data\processed\selected_games\selected_games_YYYY-MM-DD.json", `
  "C:\NCAA Model\data\processed\baselines\last4_YYYY-MM-DD.json", `
  "C:\NCAA Model\data\raw\pbp_live\GAME_ID\pbp_first_half_*.json", `
  "C:\NCAA Model\data\processed\reports\feature_report_v5_test_GAME_ID_*.json" |
  Select-Object FullName, Length

  ✅ Verified Example (Known Good)
Date:
2026-02-26

GameID:
6502232

✅ Slate generated (57 games)
✅ Baselines built
✅ Halftime PBP pulled
✅ Feature report generated
✅ Workbook logging confirmed

⬆️ **End of paste** ⬆️

---

## ✅ What to do after pasting
1. **Save** the file  
2. Run:
   ```powershell
   git add README.md
   git commit -m "Add clear VS Code terminal daily flow instructions"
   git push