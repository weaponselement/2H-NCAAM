# Market Lines Schema

This repo should treat sportsbook lines as staged data first and model features second.

Compatibility note (March 2026):
- Canonical schema is shared across ingestion paths.
- Historical pregame ingestion currently uses Covers scraper data.
- The field name `sgo_event_id` remains for backward compatibility and may store provider-specific IDs (for example `covers-<id>`).

## Safety Rule

Never write external line data straight into the workbook from raw provider names.

Use a staging file keyed by normalized SDIO-style slugs, review exact versus unmatched rows, and only then merge exact matches by `GameID`.

## Canonical Staged Fields

Every staged row should carry these audit fields:

- `source_file`
- `sgo_event_id`
- `starts_at_utc`
- `local_date`
- `sgo_away_raw`
- `sgo_home_raw`
- `away_seo_candidate`
- `home_seo_candidate`
- `match_status`
- `match_reason`
- `matched_game_id`
- `matched_date`
- `matched_away`
- `matched_home`
- `candidate_count`
- `candidate_game_ids`
- `suggested_game_ids`
- `suggested_away`
- `suggested_home`

Every staged row should carry these line fields when available:

- `spread_home`
- `spread_away`
- `ml_home`
- `ml_away`
- `total_game`
- `total_2h`

## Auto-Match Rule

Auto-assign a line row only when all of the following are true:

1. `away_seo_candidate` matches one SDIO away slug.
2. `home_seo_candidate` matches one SDIO home slug.
3. `local_date` matches one SDIO slate date.
4. The candidate set resolves to exactly one game.

Everything else stays out of the workbook and out of training.

## Recommended Match Statuses

- `EXACT`: one exact match on `local_date + away_seo + home_seo`
- `UNMATCHED`: no safe match
- `AMBIGUOUS`: more than one exact candidate

Useful reasons:

- `date_away_home_exact`
- `home_away_reversed_candidate_exists`
- `team_pair_found_on_other_date`
- `multiple_exact_candidates`
- `no_exact_match`

## First Model Features To Add

Start with pregame market priors only:

- `market_spread_home_close`
- `market_total_close`
- `market_home_implied_prob`

Derived fields are preferred over raw price fields when possible.

## total_2h Field

`total_2h` is retained in the schema for backward compatibility but is **not used by the current pregame model**.
The 2H halftime model is permanently retired. Do not train on `total_2h`.