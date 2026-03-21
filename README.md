
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