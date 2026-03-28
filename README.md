# NCAA Model – Current Runbook (March 2026)

This top section is the active operating guide.
Older notes lower in this file are preserved but should be treated as historical context.

START HERE FOR FULL CONTEXT:
- `MASTER_HANDOFF_PREGAME_MODEL_2026-03-27.txt` (single-source handoff for new chat sessions and next-season restart)

## ⚠️ CRITICAL — READ BEFORE RUNNING ANYTHING

**The 2H live-bet halftime model is permanently retired. It does not exist for purposes of this project.**
Do not run, fix, audit, or reference:
`log_prediction_to_results_v1.py`, `trigger_gate_from_workbook_v1.py`,
`step4_pull_halftime_pbp_v2.py`, `backfill_halftime_predictions_for_date_v1.py`,
`postgame_export_to_log_v1.py`, `rebuild_reports_from_workbook_v2.py`,
`rebuild_results_from_reports_v1.py`, `overwrite_predictions_in_place_v1.py`,
`update_all_predictions_ml.py`, `analyze_results_data.py`, `analyze_trigger_cohorts_v1.py`,
`explore_tight_range_triggers_v1.py`, or the `halftime_run` VS Code task.

See `MASTER_HANDOFF_PREGAME_MODEL_2026-03-27.txt` for the complete list and rationale.

---

## 1) What to Use Going Forward

Active pregame model scripts:

- Cached pregame predictor: `Scripts/predict_pregame_totals_cached_v1.py`
- Pregame slate prep: `Scripts/prepare_full_slate_v1.py`
- Baseline PBP download: `Scripts/step3_download_pbp_baselines.py`
- Covers lines scraper: `Scripts/ncaab_historical_lines_covers_v1.py`
- Covers slug audit: `Scripts/audit_covers_matching_v1.py`
- Postgame results (fills ActualTotal only): `Scripts/update_new_results_only_v1.py`
- VS Code task runner (prep/download/list_slate/pregame actions only): `Scripts/vscode_task_runner.ps1`

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

Maintenance check (Covers matching health):

```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "Scripts/audit_covers_matching_v1.py" --recent-dates 21 --out "data/logs/covers_slug_audit_recent21.json"
```

This produces a ranked mismatch report used to update `slug_from_covers()` overrides.

---

# NCAA Model - Pregame Daily Flow

Run from workspace root: `C:\NCAA Model`

Python executable: `c:/NCAA Model/.venv/Scripts/python.exe`

## Step 1 — Prep slate and baselines (morning, before tip-off)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Scripts/vscode_task_runner.ps1 -Action prep
```

Or via VS Code task: **NCAAM: TODAY Pregame (prep + download baseline PBP + list slate)**

Expected outputs:
- `data/processed/slates/slate_d1_YYYY-MM-DD.csv` / `.json`
- `data/processed/selected_games/selected_games_YYYY-MM-DD.json`
- `data/processed/baselines/lastN_<window>_YYYY-MM-DD.json`

## Step 2 — Run pregame prediction

```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" Scripts/predict_pregame_totals_cached_v1.py `
  --window 5 `
  --game "home-slug,away-slug,line,Label,tipoff"
```

Example:
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" Scripts/predict_pregame_totals_cached_v1.py `
  --window 5 `
  --game "michigan-st,uconn,136.5,Michigan State vs UConn,7:45 PM CST"
```

First run after data change: ~7-10 min (cache miss, training)
Repeat runs same day: seconds (cache hit)

## Step 3 — Postgame results (fills ActualTotal for future training)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Scripts/vscode_task_runner.ps1 -Action postgame_missing
```

## Covers lines maintenance (run after adding new dates to workbook)

```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" Scripts/ncaab_historical_lines_covers_v1.py --since YYYY-MM-DD
```

Coverage health audit:
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" Scripts/audit_covers_matching_v1.py --recent-dates 21 --out data/logs/covers_slug_audit.json
```