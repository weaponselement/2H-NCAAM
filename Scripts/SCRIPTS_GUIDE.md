# Scripts Guide — NCAAM Model
_Last updated: 2026-03-27_

This document is the single reference for every file in the `Scripts/` folder.

---

## ⛔ DEFUNCT — 2H HALFTIME MODEL (DO NOT USE)

The 2H live-bet halftime model is **permanently retired**. These scripts exist only as historical
artifacts. Do **not** run, fix, audit, or reference them.

| Script | Why defunct |
|--------|-------------|
| `step4_pull_halftime_pbp_v2.py` | Pulls live halftime PBP — only used by retired 2H pipeline |
| `log_prediction_to_results_v1.py` | Writes 2H halftime predictions to workbook |
| `trigger_gate_from_workbook_v1.py` | 2H trigger/stake gate — reads dead workbook columns |
| `backfill_halftime_predictions_for_date_v1.py` | Backfills 2H halftime predictions |
| `backfill_halftime_predictions_for_date_task_v1.ps1` | PowerShell wrapper for 2H backfill |
| `postgame_export_to_log_v1.py` | 2H postgame export to workbook |
| `rebuild_reports_from_workbook_v2.py` | Rebuilds 2H feature reports from workbook |
| `rebuild_results_from_reports_v1.py` | Rebuilds 2H result columns from saved reports |
| `overwrite_predictions_in_place_v1.py` | Overwrites 2H workbook prediction columns |
| `update_all_predictions_ml.py` | Bulk-applies 2H ML models to workbook |
| `analyze_results_data.py` | Audits 2H model workbook columns — meaningless for pregame |
| `analyze_trigger_cohorts_v1.py` | 2H trigger cohort analysis |
| `explore_tight_range_triggers_v1.py` | 2H tight-range trigger exploration |
| `evaluate_model_vs_book_totals_v1.py` | Compares 2H model midpoints vs book totals |
| `evaluate_directional_triggers_v1.py` | Evaluates 2H directional trigger hit rates |
| `tune_totals_spreads_v1.py` | Trains the 2H RF models — not used by pregame model |
| `update_results_postgame_v1.py` | 2H postgame result update (use `update_new_results_only_v1.py` instead) |

The **only** workbook columns the pregame model uses: `Date`, `Home`, `Away`, `GameID`, `ActualTotal`.

---

## Model Persistence — Pregame Cache

- `predict_pregame_totals_cached_v1.py` trains on first run, saves to:
  - `models/pregame_total_cache/pregame_total_rf_w<N>.pkl`
  - `models/pregame_total_cache/pregame_total_rf_w<N>.meta.json`
- Repeat runs reuse the cache (fingerprint-matched) — no retraining.
- Force retrain: add `--force-retrain` flag.

---

## Tier 1 — Daily Production (run every game day)

| Script | Purpose | When |
|--------|---------|------|
| `vscode_task_runner.ps1` | Dispatcher (prep / download_pbp / list_slate / postgame_missing / pregame_cached) | Every action |
| `prepare_full_slate_v1.py` | Morning prep: builds slate, selected_games, lastN baseline files | Morning |
| `step1_get_today_game_ids.py` | Fetches today's game IDs | Called by prepare_full_slate |
| `step2b_last4_from_scoreboard_v2.py` | Builds per-team last-N baselines | Called by prepare_full_slate |
| `step3_download_pbp_baselines.py` | Downloads historical PBP files for today's teams | Morning |
| `step4b_feature_report_from_file_v5_test.py` | **Library** — `load_game_pbp_features()` used by pregame model for shot-mix priors | Imported, not run directly |
| `predict_pregame_totals_cached_v1.py` | Runs pregame total prediction with cache-backed RF model | Pre-tip |
| `update_new_results_only_v1.py` | Fills ActualTotal (and other result cols) for missing rows | Evening |

---

## Tier 2 — Shared Modules (imported — do not run directly)

| Script | Purpose |
|--------|---------|
| `model_feature_utils.py` | Core feature utilities: `FEATURE_NAMES`, `build_feature_vector`, `load_team_stats`, `load_market_lines`, `load_last4_pbp_priors`, etc. |
| `paths.py` | Centralized path constants: `PROJECT_ROOT`, `DATA_DIR`, `NCAAM_RESULTS_XLSX` |

---

## Tier 3 — Data Pipeline / Maintenance

| Script | Purpose |
|--------|---------|
| `ncaab_historical_lines_covers_v1.py` | Scrapes Covers.com for historical closing lines → canonical_lines.csv |
| `audit_covers_matching_v1.py` | Audits Covers slug match coverage, reports top mismatches |
| `merge_staged_lines_to_canonical_v1.py` | Merges staged lines files into canonical_lines.csv |
| `backfill_prior_season_v1.py` | Full season data rebuild (PBP download + baseline write) |
| `repair_slates_and_selected_games_v1.py` | Repairs corrupted or missing slate/selected_games files |
| `build_missing_selected_games_from_slates_v1.py` | Fills selected_games entries from slate files where missing |
| `update_all_results_v1.py` | Fills ALL result columns from scratch (full repair) |
| `check_missing_results.py` | Scans workbook for rows missing ActualTotal |

---

## Tier 4 — Analysis & Evaluation (research — not daily)

| Script | Purpose |
|--------|---------|
| `analyze_pregame_model_depth_v1.py` | Deep walk-forward analysis of pregame model. Run with `--window N` |
| `evaluate_window_optimization_v1.py` | Tests different lookback window sizes for the pregame model |
| `evaluate_pregame_total_model_v1.py` | Evaluates pregame total model vs closing lines |

---

## Tier 5 — Window Research Scripts (redundant pregame window investigation)

All three investigate the same question — which lookback window gives the best pregame edge.
`evaluate_window_optimization_v1.py` is the current preferred version.

| Script | Status |
|--------|--------|
| `run_window_optimization_tests_v1.py` | Older batch runner |
| `test_lookback_window_optimization_v1.py` | Earlier lookback window test |
| `test_window_optimization_simple_v1.py` | Simplified window test |

---

## Tier 6 — Utilities & Lookup (run on-demand)

| Script | Purpose |
|--------|---------|
| `inspect_workbook.py` | Prints workbook column headers and sample data |
| `live_find_gameid.py` | Looks up a game ID during a live game |
| `slate_d1_game_ids.py` | D1 game ID lookup helper |
| `audit_ncaam_model_paths_v1.py` | Audits that all model paths and pkl files exist |
| `audit_rebuild_coverage_v1.py` | Audits PBP file rebuild coverage across workbook |
| `check_sgo_quota.py` | Checks SGO API quota (API currently unresponsive) |
| `check_missing_results.py` | Scans workbook for rows missing ActualTotal |
| `step2a_gameids_to_team_seos.py` | Maps game IDs to team SEO slugs (older helper) |
| `step2_find_team_schedules.py` | Finds team schedules (older, superseded by step2b) |
| `step4a_find_play_paths_local.py` | Finds local PBP file paths for a game |
| `step4a_inspect_pbp_schema.py` | Inspects structure of a PBP data file |

---

## Tier 7 — Inactive Market Data (SGO API not used)

| Script | Status |
|--------|--------|
| `fetch_sgo_lines_v1.py` | SGO API lines fetcher — API unresponsive as of 2026-03 |
| `stage_market_lines_sgo_v1.py` | Stages SGO lines for merge — inactive |

> Active market lines source is Covers.com via `ncaab_historical_lines_covers_v1.py`.

---

## Tier 8 — Archived & Debug (underscore prefix = one-time or abandoned work)

| Script | Notes |
|--------|-------|
| `_covers_game_block.txt` | Raw Covers HTML sample |
| `_covers_html_inspect.py` | One-off Covers HTML inspection |
| `_covers_raw_test.py` | Covers scraper test |
| `_debug_split.py` / `_debug_split2.py` / `_debug_split3.py` | Debug scripts for model split investigation |
| `_holdout_validation.py` | Holdout validation experiment |
| `_inspect_scoreboard_neutral.py` | Neutral court data inspection |
| `_predict_tonight_v1.py` / `_predict_tonight_v2.py` | Early prototypes — superseded by task runner |
| `_wb_inspect_tmp.py` | Temporary workbook inspection |
| `foul_pressure_features_v1.py` | Foul pressure feature experiments — rejected (MAE worsened) |

---

## Quick Reference: Current Pregame Model Tasks

| Task | Script / VS Code Task |
|------|-----------------------|
| Morning game-day prep | VS Code task: **NCAAM: TODAY Pregame** |
| Pregame prediction | `predict_pregame_totals_cached_v1.py --window 5 --game ...` |
| Postgame fill results | VS Code task: **NCAAM: TODAY Postgame update** |
| Add new closing lines | `ncaab_historical_lines_covers_v1.py` then `merge_staged_lines_to_canonical_v1.py` |
| Slug coverage audit | `audit_covers_matching_v1.py --recent-dates 21` |
| Investigate model depth | `analyze_pregame_model_depth_v1.py --window 5` |
| Check workbook schema | `inspect_workbook.py` |
