# Market Lines Integration Guide

This document describes the safe, staged integration of sportsbook market lines into the NCAA model.

## Architecture: Three-Phase Pipeline

### Phase 1: Staging (Safe Matcher)
**File:** [Scripts/stage_market_lines_sgo_v1.py](Scripts/stage_market_lines_sgo_v1.py)

Reads raw SGO (sportsbook) JSON and matches games against selected_games using normalized team slugs.

**Usage:**
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/stage_market_lines_sgo_v1.py" `
  --input "path/to/sgo_events.json" `
  --date 2026-03-22 `
  --timezone "America/Chicago" `
  --label "my_sgo_run"
```

**Output:** 
- `data/processed/market_lines/sgo_stage_my_sgo_run.json` (detailed report)
- `data/processed/market_lines/sgo_stage_my_sgo_run.csv` (audit table)

**Key Safety Features:**
- Never touches Excel
- Only outputs non-matching rows with diagnostics
- Flags reversed home/away orientation
- Detects ambiguity (multiple candidates)
- Provides match status and reasons for traceability

**Match Statuses:**
- `EXACT`: one exact match on local_date + away_seo + home_seo → safe for next phase
- `UNMATCHED`: no safe match found
- `AMBIGUOUS`: multiple exact candidates (data conflict)

### Phase 2: Merge (Canonical Store)
**File:** [Scripts/merge_staged_lines_to_canonical_v1.py](Scripts/merge_staged_lines_to_canonical_v1.py)

Consolidates all `EXACT` matches from staged files into a deduplicated, GameID-keyed CSV.

**Usage:**
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/merge_staged_lines_to_canonical_v1.py" `
  --input "data/processed/market_lines/sgo_stage_*.json"
```

**Output:**
- `data/processed/market_lines/canonical_lines.csv`
  - Keyed by GameID
  - One row per game, never overwrites existing entries unless `--allow-overwrite`
  - Preserves SGO event ID and source file for traceability

**Fields in canonical_lines.csv:**
```
game_id, date, away_seo, home_seo,
spread_home, spread_away,
ml_home, ml_away,
total_game, total_2h,
sgo_event_id, source_file, staged_timestamp
```

### Phase 3: Feature Integration
**Files Modified:**
- [Scripts/model_feature_utils.py](Scripts/model_feature_utils.py)
- [Scripts/tune_totals_spreads_v1.py](Scripts/tune_totals_spreads_v1.py)
- [Scripts/update_all_predictions_ml.py](Scripts/update_all_predictions_ml.py)
- [Scripts/step4b_feature_report_from_file_v5_test.py](Scripts/step4b_feature_report_from_file_v5_test.py)

The pipeline now automatically:
1. Loads canonical market lines at startup
2. Looks up each game's lines by GameID
3. Extracts three pregame market features
4. Falls back to sensible defaults if lines are missing

**Three Pregame Market Features Added:**

- `market_spread_home_close`: closing home spread from sportsbook
  - Encodes market consensus on margin
  - Strong signal of team strength
  - Default: 0.0

- `market_total_close`: closing game total from sportsbook
  - Encodes market consensus on scoring pace/environment
  - Correlates with halftime totals
  - Default: 150.0

- `market_home_implied_prob`: derived from closing home moneyline
  - Converted from American odds to win probability
  - Ranges 0.0–1.0
  - Default: 0.5

## Feature Availability Rule

**Only add features at prediction time if they can be fetched live.**

- ✅ Pregame spread, total, ML → available at halftime → safe to train
- ❌ 2H total → only available after games start → do not train yet

Current policy: train only pregame market features. 2H lines reserved for Phase Two if live halftime market fetching is confirmed.

## Workflow: Getting SGO Data Into Training

### Step 1: Acquire SGO JSON
You need raw SGO JSON from sportsgameodds.com API.

Example structure:
```json
{
  "events": [
    {
      "id": "evt-12345",
      "startsAt": "2026-03-22T19:10:00Z",
      "away": {"name": "MIAMI_FL_NCAAB"},
      "home": {"name": "PURDUE_NCAAB"},
      "odds": {
        "points-home-game-sp-home": {"bookSpread": -7.5},
        "points-home-game-ml-home": {"bookOdds": -320},
        "points-all-game-ou-over": {"bookOverUnder": 149.5}
      }
    }
  ]
}
```

### Step 2: Stage the Data
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/stage_market_lines_sgo_v1.py" `
  --input "path/to/sgo_events.json" `
  --date 2026-03-22 `
  --label real_data_2026_03_22
```

### Step 3: Review Staging Output
Open `data/processed/market_lines/sgo_stage_real_data_2026_03_22.csv` and check:
- How many `EXACT` matches?
- Any `UNMATCHED` with interesting reasons? (check game pairs, dates)
- Any `AMBIGUOUS`? (would indicate duplicate games in selected_games)

### Step 4: Merge Exact Matches
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/merge_staged_lines_to_canonical_v1.py" `
  --input "data/processed/market_lines/sgo_stage_*.json"
```

### Step 5: Retrain
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/tune_totals_spreads_v1.py"
```

Training now includes `market_spread_home_close`, `market_total_close`, `market_home_implied_prob`.

### Step 6: Live Prediction
```powershell
& "c:/NCAA Model/.venv/Scripts/python.exe" "c:/NCAA Model/Scripts/update_all_predictions_ml.py"
```

Live predictions automatically load canonicallines and use market features.

## Troubleshooting

### "No market lines loaded"
- Check: does `data/processed/market_lines/canonical_lines.csv` exist?
- If not, run the merge script first
- If it exists, check it's not empty

### Feature shape mismatch in training
- The model was trained with market features, but you're using it without them loaded
- Solution: ensure `canonical_lines.csv` exists before calling training/prediction scripts

### Team name normalization issues
- Use the detailed CSV from step 1 to identify mismatches
- Add to `SGO_TO_SDIO` dictionary in [Scripts/stage_market_lines_sgo_v1.py](Scripts/stage_market_lines_sgo_v1.py) line 30
- Re-run staging with new mapping

## Safety Guarantees

1. **Never silently mismatches a line to a wrong game**
   - Only exact normalized slug + date matches auto-assign
   - All ambiguous cases stay in UNMATCHED

2. **Audit trail preserved**
   - Every row carries SGO event ID and source file
   - Traceability from raw provider → staging → canonical → model

3. **No workbook mutations in staging**
   - Staging is read-only on the workbook
   - Only produces JSON/CSV for review
   - Manual merge decision required

4. **Graceful degradation in live prediction**
   - Missing market lines fall back to sensible defaults
   - Models retrain with defaults if canonical_lines.csv unavailable
   - No crashes, just reduced signal

## Next Steps

1. **Get real SGO data** or have me wire the fetcher
2. **Run staging matcher** on one date
3. **Review CSV output** for quality
4. **Run merge script** to populate canonical_lines.csv
5. **Retrain** and compare to baseline:
   - Holdout MAE change?
   - One-band workbook hit rate change?
   - If positive, keep; if neutral or negative, investigate features

## Questions?

Refer to [MARKET_LINES_SCHEMA.md](MARKET_LINES_SCHEMA.md) for the canonical field spec and auto-match rules.
