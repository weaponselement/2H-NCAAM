# Workbook Schema — Current & Going Forward

**Date:** 2026-03-28  
**Status:** Clean schema for pregame model only

## Active Columns (11 total)

| # | Column | Purpose | Source | When Filled |
|---|--------|---------|--------|------------|
| 1 | `Date` | Game date | Schedule | Pregame (before prediction) |
| 2 | `GameID` | Unique game ID | SportsDataIO | Pregame (before prediction) |
| 3 | `Away` | Away team SEO | Schedule | Pregame (before prediction) |
| 4 | `Home` | Home team SEO | Schedule | Pregame (before prediction) |
| 5 | `MarketTotalLine` | Closing sportsbook line | User input / Covers | Pregame (at prediction time) |
| 6 | `PregamePredTotal` | RF model prediction | `predict_pregame_totals_cached_v1.py` | Pregame (at prediction) |
| 7 | `PregamePredGap` | Signed gap (pred - line) | `predict_pregame_totals_cached_v1.py` | Pregame (at prediction) |
| 8 | `PregameLean` | Directional call (OVER/UNDER) | `predict_pregame_totals_cached_v1.py` | Pregame (at prediction) |
| 9 | `PregameTrigger` | Action tier (FULL SEND / LEAN / MONITOR / NO ACTION) | `predict_pregame_totals_cached_v1.py` | Pregame (at prediction) |
| 10 | `ActualWinner` | Winner of the game | `update_new_results_only_v1.py` | Postgame (after game ends) |
| 11 | `ActualTotal` | Combined final score | `update_new_results_only_v1.py` | Postgame (after game ends) |
| 12 | `PredictionHit` | Did lean come true? (1 = yes, 0 = no) | `log_pregame_prediction_v1.py` | Postgame (after results filled) |

## Workflow: Pregame → Postgame

### Pregame (2-3 hours before tipoff)
1. Schedule fetches today's games → fills Date, GameID, Home, Away
2. User enters market line → MediaTotalLine
3. Run predictor:
   ```powershell
   python Scripts/predict_pregame_totals_cached_v1.py --window 5 \
     --game "home,away,LINE,Label,Tipoff"
   ```
4. Log prediction to workbook:
   ```powershell
   python Scripts/log_pregame_prediction_v1.py \
     --date YYYY-MM-DD --home HOME --away AWAY --game-id GAMEID \
     --market-line 137.5 --pred-total 145.6 --pred-gap 9.1 \
     --lean OVER --trigger "LEAN (gap 8-9)"
   ```
   → Fills PregamePredTotal, PregamePredGap, PregameLean, PregameTrigger

### Postgame (after final score is known)
1. Run result update:
   ```powershell
   python Scripts/update_new_results_only_v1.py
   ```
   → Fills ActualWinner, ActualTotal

2. Update prediction hit:
   ```powershell
   python Scripts/log_pregame_prediction_v1.py \
     --date YYYY-MM-DD --home HOME --away AWAY --game-id GAMEID \
     --actual-winner WINNER --actual-total SCORE
   ```
   → Calculates and fills PredictionHit

## Why This Schema

**Old workbook (28 columns):**
- 17 dead 2H columns (ActualMargin, Actual2H, PredMargin, etc.) — never used by pregame model
- Confusing, bloated, made future audits unclear

**New workbook (11 columns):**
- Only columns relevant to current pregame model
- MarketTotalLine captured so predictions are self-contained (no need to cross-ref canonical_lines.csv)
- PredictionHit calculated automatically for easy evaluation
- One row = one complete game narrative (input → prediction → result → outcome)

## Historical Data

1,426 rows migrated from old schema, preserving:
- Date, GameID, Home, Away, ActualWinner, ActualTotal
- New columns (MarketTotalLine, PregamePred*) start empty for historical data

## Going Forward

Every pregame prediction will be logged via `log_pregame_prediction_v1.py`, creating a complete audit trail:
- What line was used?
- What did the model predict?
- What actually happened?
- Did the prediction come true?

This makes the workbook the single source of truth for model performance, not a half-used file with dead columns.
