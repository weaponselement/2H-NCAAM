# One-Band Roadmap

## Current State

- Operational mode: one band only
- Current band policy:
  - `<=60`: half-width `3`
  - `61-70`: half-width `4`
  - `71-80`: half-width `4`
  - `81+`: half-width `3`
- Current workbook metrics:
  - `2H hit rate`: `63.5%`
  - `Total hit rate`: `63.5%`
  - `Midpoint MAE`: `3.794`
  - `Winner accuracy`: `59.0%`

## Natural Next Steps

1. Keep the current one-band policy stable as the baseline.
2. Re-run live halftime tasks during actual game flow to confirm the earlier task failure was transient.
3. Compare fresh live results against workbook expectations before changing widths again.

## Pragmatic Steps

1. Improve midpoint quality before touching width again.
2. Add cleaner possession and stoppage features from first-half PBP.
3. Add sustainability features already available in the feed.
4. Retrain and benchmark after each feature pass.
5. Keep width policy separate from feature work.
6. Add game-specific uncertainty later if needed.
7. Consider outside inputs only after internal PBP features plateau.

## Feature Priorities

1. Possession and stoppage quality
   - possession stability by segment
   - long dead-ball gap frequency
   - dead-ball event density
   - pace consistency instead of raw pace alone

2. Sustainability features
   - turnover pressure
   - live-ball turnover share
   - free-throw dependence
   - paint vs perimeter shot mix
   - offensive rebound pressure

3. Team and context features
   - opponent-adjusted baselines
   - days since last game
   - schedule/rest context

4. Optional external priors later
   - full-game market total
   - closing line or live book prior

## Decision Rule

Keep a change only if it improves the single-band outcome honestly.

- Preferred wins:
  - lower midpoint MAE
  - higher single-band hit rate at similar width
  - same hit rate at tighter width
- Reject changes that only improve metrics by widening the range.

## Recommended Order

1. Validate the one-band baseline on live games.
2. Add possession and stoppage features.
3. Retrain and refresh workbook.
4. Measure one-band hit rate and midpoint MAE.
5. Add sustainability features.
6. Retrain and re-measure.
7. Only then evaluate external data inputs.