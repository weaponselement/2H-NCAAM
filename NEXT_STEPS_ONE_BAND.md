# One-Band Roadmap

## Current State

- Operational mode: one band only
- Current band policy:
  - `<=60`: half-width `3`
  - `61-70`: half-width `4`
  - `71-80`: half-width `4`
  - `81+`: half-width `3`
- Current workbook metrics:
  - `2H hit rate`: `64.4%`
  - `Total hit rate`: `64.3%`
  - `2H midpoint MAE`: `3.649`
  - `Total midpoint MAE`: `3.649`
  - `Winner accuracy`: `59.0%`
- Current kept production checkpoint:
  - change: market lines integration (Covers.com closing lines, 1247/1426 games covered)
  - features added: `market_spread_home_close`, `market_total_close`, `market_home_implied_prob`

## Current Best Pass

1. Kept pass:
   - market lines integration via Covers.com closing lines
   - `market_spread_home_close`, `market_total_close`, `market_home_implied_prob`
   - 1247 of 1426 workbook games covered; uncovered games use neutral defaults
2. Why it stays:
   - improved midpoint MAE from 3.680 → 3.649 and hit rate from 64.1%/64.2% → 64.4%/64.3%

## Recent Rejected Passes

1. Rejected:
   - schedule/rest context (`home_days_rest`, `away_days_rest` from scoreboard_daily cache)
   - feature importances ~0.003-0.006 (near zero); workbook fell to `63.2%` hit for both `2H` and `total` with MAE 3.660
2. Rejected:
   - turnover-composition and foul-pressure persistence
   - workbook fell to `63.0%` hit for both `2H` and `total`
3. Rejected:
   - segment-volatility and late-pressure features
   - workbook fell to `63.6%` hit for both `2H` and `total`
4. Rejected:
   - baseline-relative deviations versus recent baseline
   - workbook landed at `64.0%` hit for both `2H` and `total`
5. Rejected:
   - dual-horizon priors using season-to-date plus `last4` deltas
   - workbook fell to `63.7%` hit for both `2H` and `total`
6. Rejected:
   - opponent-interaction product terms
   - workbook fell to `63.4%` `2H` and `63.5%` `total`
7. Rejected:
   - Random Forest hyperparameter tuning (`400 trees`, `max_depth=14`, `min_samples_leaf=2`, `min_samples_split=6`, `max_features=0.6`)
   - holdout improved, but workbook collapsed to `52.7%` hit for both `2H` and `total`

## Natural Next Steps

1. Keep the current one-band policy stable as the baseline.
2. Re-run live halftime tasks during actual game flow to confirm production still behaves cleanly.
3. Treat the current feature set as near-plateaued unless a new information source is introduced.

## Pragmatic Steps

1. Improve midpoint quality before touching width again.
2. Avoid re-testing recently rejected internal feature families unless the setup materially changes.
3. Consider lightweight new information sources next:
   - reliable schedule/rest context
   - market totals or spreads if available
4. If staying internal-only, prefer small structural experiments over broader feature expansion.
5. Keep width policy separate from feature work.
6. Add game-specific uncertainty later if needed.

## Feature Priorities

1. New information sources
   - schedule/rest context if a reliable cache path is built
   - market totals/spreads if accessible
2. Small structural experiments
   - conservative RF tuning only if workbook-gated from scratch
   - no broad model-family changes without workbook proof
3. Only then revisit feature expansion
   - internal PBP feature families are showing diminishing returns

## Decision Rule

Keep a change only if it improves the single-band outcome honestly.

- Preferred wins:
  - lower midpoint MAE
  - higher single-band hit rate at similar width
  - same hit rate at tighter width
- Reject changes that only improve metrics by widening the range.

## Recommended Order

1. Validate the current baseline on live games.
2. If continuing model improvement, prioritize schedule/rest or market priors over more internal interaction features.
3. Benchmark each change on workbook one-band hit rate first, midpoint MAE second.
4. Reject anything that improves holdout but weakens workbook behavior.