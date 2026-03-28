# Scripts Guide — NCAAM Model
_Last updated: 2026-03-27_

This document is the single reference for every file in the `Scripts/` folder.
Scripts are organized into tiers. **If you're not sure which script to touch, start with Tier 1.**

---

## Model Persistence — How It Works

**The halftime prediction model is already persistent.**

- `tune_totals_spreads_v1.py` trains the three Random Forest models and writes:
  - `models/actualmargin_model.pkl`
  - `models/actual2h_model.pkl`
  - `models/actualtotal_model.pkl`
  - `models/model_error_stats.json`
  - `models/model_strategy.json`

- `update_all_predictions_ml.py` (and the daily halftime run) **loads** those pkl files — it does NOT retrain.

- You only need to re-run `tune_totals_spreads_v1.py` when you intentionally want to retrain (e.g., after adding new games to the workbook or after a feature change).

The **pregame analysis scripts** (Tier 5–6 below) do retrain from scratch on each run because they use walk-forward validation — that is intentional for research. If/when a production pregame workflow is built, that model would be persisted the same way (save once, load daily).

---

## Tier 1 — Daily Production (run every game day)

These are the only scripts you normally interact with on game days.
They are driven by the VS Code tasks and `vscode_task_runner.ps1`.

| Script | Purpose | When |
|--------|---------|------|
| `vscode_task_runner.ps1` | Central dispatcher for all daily VS Code tasks | Every action |
| `prepare_full_slate_v1.py` | Morning prep: builds slate, selected_games, last4 files | Morning (Pregame task) |
| `step1_get_today_game_ids.py` | Fetches today's game IDs from SportsDataIO | Called by prepare_full_slate |
| `step2b_last4_from_scoreboard_v2.py` | Builds per-team last-4 game baselines from scoreboard cache | Called by prepare_full_slate |
| `step3_download_pbp_baselines.py` | Downloads historical PBP files for today's teams | Morning (Download PBP task) |
| `step4_pull_halftime_pbp_v2.py` | Pulls live halftime PBP from SportsDataIO API | At halftime |
| `step4b_feature_report_from_file_v5_test.py` | Builds JSON feature report from a raw PBP file | At halftime |
| `log_prediction_to_results_v1.py` | Writes halftime prediction to workbook (single game) | At halftime |
| `update_all_predictions_ml.py` | Applies saved pkl models to all workbook rows (bulk) | After backfills or retraining |
| `update_new_results_only_v1.py` | Postgame: fills result columns only where missing | Evening (Postgame task) |
| `trigger_gate_from_workbook_v1.py` | Labels rows ACTIONABLE/PASS; prints game card during halftime_run | At halftime (via task runner) |

---

## Tier 2 — Shared Modules (imported by other scripts — do not run directly)

| Script | Purpose |
|--------|---------|
| `model_feature_utils.py` | Core feature utilities: `FEATURE_NAMES`, `build_feature_vector`, `load_team_stats`, `load_market_lines`, `load_last4_pbp_priors`, `range_half_widths_for_halftime_total`, etc. |
| `paths.py` | Centralized path constants: `PROJECT_ROOT`, `DATA_DIR`, `NCAAM_RESULTS_XLSX` |

> **Important:** If you add a feature or change a path, these two files are your first stop.

---

## Tier 3 — Model Training (run when rebuilding the halftime model — not daily)

| Script | Purpose | When to run |
|--------|---------|------------|
| `tune_totals_spreads_v1.py` | Trains all three RF models from workbook data; saves pkl to `models/` | Only when intentionally retraining |
| `backfill_prior_season_v1.py` | 4-phase rebuild of full season data (PBP download + feature extraction + workbook write) | Season start or after workbook corruption |

> After running `tune_totals_spreads_v1.py`, the new models are live immediately for all future halftime runs.

---

## Tier 4 — Data Pipeline / Maintenance (run for setup, recovery, or market line refresh)

Scripts you reach for when something needs to be rebuilt, repaired, or backfilled.

| Script | Purpose |
|--------|---------|
| `ncaab_historical_lines_covers_v1.py` | Scrapes Covers.com for historical closing lines → staged CSV |
| `merge_staged_lines_to_canonical_v1.py` | Merges staged lines files into `data/processed/market_lines/canonical_lines.csv` |
| `backfill_halftime_predictions_for_date_v1.py` | Backfills halftime predictions for a specific past date (Python) |
| `backfill_halftime_predictions_for_date_task_v1.ps1` | PowerShell wrapper to run the above interactively (asks for date) |
| `rebuild_reports_from_workbook_v2.py` | Rebuilds feature reports from workbook rows (recovery after data wipe) |
| `rebuild_results_from_reports_v1.py` | Rebuilds result columns from saved reports |
| `repair_slates_and_selected_games_v1.py` | Repairs corrupted or missing slate/selected_games files |
| `build_missing_selected_games_from_slates_v1.py` | Fills selected_games entries from slate files where missing |
| `overwrite_predictions_in_place_v1.py` | Overwrites old prediction columns in workbook (e.g., after model retrain) |
| `postgame_export_to_log_v1.py` | Exports postgame data to results log |
| `update_all_results_v1.py` | Fills ALL result columns from scratch (vs only missing) |
| `update_results_postgame_v1.py` | Alternate postgame result update script |
| `check_missing_results.py` | Scans workbook for rows missing result columns |

---

## Tier 5 — Analysis & Evaluation (run for research — not daily)

These scripts retrain models internally for evaluation purposes. Results are printed to console or saved to `logs/`.

| Script | Purpose |
|--------|---------|
| `analyze_pregame_model_depth_v1.py` | Deep walk-forward analysis of pregame totals model: fold consistency, threshold curve, O/U split, monthly breakdown. Run with `--window N` |
| `evaluate_window_optimization_v1.py` | Tests different lookback window sizes (last-N games) for the pregame model. Outputs JSON to `logs/` |
| `evaluate_pregame_total_model_v1.py` | Evaluates the pregame total model against closing lines |
| `evaluate_model_vs_book_totals_v1.py` | Compares halftime model midpoints vs book closing totals |
| `evaluate_directional_triggers_v1.py` | Evaluates the directional (O/U) hit rate of trigger cohorts |
| `analyze_trigger_cohorts_v1.py` | Analyzes performance breakdown of ACTIONABLE trigger cohorts |
| `analyze_results_data.py` | General analysis of workbook results data |
| `explore_tight_range_triggers_v1.py` | Exploratory script for tight-range trigger conditions |

---

## Tier 6 — Window Research Scripts (a cluster for pregame window investigation)

These three scripts all investigate the same question — which lookback window gives the best pregame edge. They are redundant to each other; `evaluate_window_optimization_v1.py` is the current preferred version.

| Script | Status |
|--------|--------|
| `run_window_optimization_tests_v1.py` | Older batch runner for window tests |
| `test_lookback_window_optimization_v1.py` | Earlier lookback window test |
| `test_window_optimization_simple_v1.py` | Simplified/cleaned window test |

> These can be safely ignored unless actively researching window selection for the pregame model.

---

## Tier 7 — Utilities & Lookup (run on-demand for specific tasks)

| Script | Purpose |
|--------|---------|
| `inspect_workbook.py` | Prints workbook column headers and sample data — useful for schema checks |
| `live_find_gameid.py` | Looks up a game ID during a live game (by team name or date) |
| `slate_d1_game_ids.py` | D1 game ID lookup helper |
| `audit_ncaam_model_paths_v1.py` | Audits that all model paths and pkl files exist and are valid |
| `audit_rebuild_coverage_v1.py` | Audits PBP file rebuild coverage across the workbook |
| `check_sgo_quota.py` | Checks SGO API quota remaining (SGO is currently unresponsive) |
| `step2a_gameids_to_team_seos.py` | Maps game IDs to team SEO slugs (older step2 helper; step2b is current) |
| `step2_find_team_schedules.py` | Finds team schedules — older version superseded by step2b |
| `step4a_find_play_paths_local.py` | Finds local PBP file paths for a game |
| `step4a_inspect_pbp_schema.py` | Inspects structure of a PBP data file |

---

## Tier 8 — Inactive Market Data (SGO API not currently used)

| Script | Status |
|--------|--------|
| `fetch_sgo_lines_v1.py` | SGO API lines fetcher — API unresponsive as of 2026-03 |
| `stage_market_lines_sgo_v1.py` | Stages SGO lines for merge — inactive |

> The active market lines source is Covers.com via `ncaab_historical_lines_covers_v1.py`.

---

## Tier 9 — Archived & Debug (underscore prefix = one-time or abandoned work)

These were written for debugging, one-off analysis, or feature experiments that were reverted.
They are safe to ignore. The underscore prefix (`_`) is the convention for "not part of the active pipeline."

| Script | Notes |
|--------|-------|
| `_covers_game_block.txt` | Raw Covers scraper HTML sample — not executable |
| `_covers_html_inspect.py` | One-off Covers HTML inspection |
| `_covers_raw_test.py` | Covers scraper test |
| `_debug_split.py` / `_debug_split2.py` / `_debug_split3.py` | Debug scripts for model split investigation |
| `_holdout_validation.py` | Holdout validation experiment |
| `_inspect_scoreboard_neutral.py` | Neutral court data inspection |
| `_predict_tonight_v1.py` / `_predict_tonight_v2.py` | Early prototypes for predict-tonight; superseded by the task runner workflow |
| `_wb_inspect_tmp.py` | Temporary workbook inspection |
| `foul_pressure_features_v1.py` | Foul pressure feature experiments — rejected (workbook hit rate fell to 63.0%) |

---

## Quick Reference: What to Run for Common Tasks

| Task | Script / VS Code Task |
|------|-----------------------|
| Morning game-day prep | VS Code task: **Pregame** |
| Live halftime prediction | VS Code task: **Halftime run** |
| Enter postgame results | VS Code task: **Postgame update** |
| Backfill a past date's predictions | `backfill_halftime_predictions_for_date_task_v1.ps1` |
| Retrain the halftime model | `tune_totals_spreads_v1.py` |
| Add new closing lines | `ncaab_historical_lines_covers_v1.py` → `merge_staged_lines_to_canonical_v1.py` → retrain |
| Investigate pregame betting edge | `analyze_pregame_model_depth_v1.py --window 7` |
| Check which games are ACTIONABLE | `trigger_gate_from_workbook_v1.py` |
| Fix a corrupted workbook | `backfill_prior_season_v1.py --phases 4 --skip-pbp` |
| Check workbook schema | `inspect_workbook.py` |
