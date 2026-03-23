import json
import statistics
from datetime import datetime
from pathlib import Path


DEFAULT_TEAM_AVG = 70.0

FEATURE_NAMES = [
    'home_lead',
    'abs_home_lead',
    'pace_run_and_gun',
    'pace_moderate',
    'pace_grinder',
    'date_days',
    'home_avg_scored',
    'home_avg_allowed',
    'away_avg_scored',
    'away_avg_allowed',
    'halftime_total',
    'pace_bucket',
    'game_density',
    'home_offense_diff',
    'away_offense_diff',
    'home_score_share',
    'away_score_share',
    'expected_game_total',
    'expected_first_half_total',
    'home_ht_vs_expected',
    'away_ht_vs_expected',
    'halftime_total_vs_expected',
    'second_half_baseline',
    'halftime_total_ratio_to_expected',
    'home_share_vs_expected',
    'away_share_vs_expected',
    'home_three_rate',
    'away_three_rate',
    'home_paint_share',
    'away_paint_share',
    'home_ft_rate',
    'away_ft_rate',
    'home_turnover_rate',
    'away_turnover_rate',
    'home_live_ball_turnover_share',
    'away_live_ball_turnover_share',
    'home_orb_rate',
    'away_orb_rate',
]


DEFAULT_PBP_FEATURES = {
    'home_three_rate': 0.33,
    'away_three_rate': 0.33,
    'home_paint_share': 0.40,
    'away_paint_share': 0.40,
    'home_ft_rate': 0.25,
    'away_ft_rate': 0.25,
    'home_turnover_rate': 0.18,
    'away_turnover_rate': 0.18,
    'home_live_ball_turnover_share': 0.40,
    'away_live_ball_turnover_share': 0.40,
    'home_orb_rate': 0.28,
    'away_orb_rate': 0.28,
}


def load_team_stats(date_str):
    path = Path(__file__).resolve().parent.parent / 'data' / 'processed' / 'baselines' / f'last4_{date_str}.json'
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    teams = data.get('teams', {})
    stats = {}
    for team, games in teams.items():
        if not games:
            continue
        scores_for = [int(g['score_for']) for g in games if g.get('score_for')]
        scores_against = [int(g['score_against']) for g in games if g.get('score_against')]
        if scores_for and scores_against:
            stats[team] = {
                'avg_scored': statistics.mean(scores_for),
                'avg_allowed': statistics.mean(scores_against),
            }
    return stats


def resolve_team_stats(stats, team_name):
    team_stats = stats.get(team_name, {}) if stats else {}
    return (
        float(team_stats.get('avg_scored', DEFAULT_TEAM_AVG)),
        float(team_stats.get('avg_allowed', DEFAULT_TEAM_AVG)),
    )


def parse_halftime_score(halftime_score):
    if halftime_score is None or '-' not in str(halftime_score):
        return None, None, None, None
    left, right = str(halftime_score).split('-', 1)
    try:
        away_ht = float(left.strip())
        home_ht = float(right.strip())
    except Exception:
        return None, None, None, None
    return away_ht, home_ht, home_ht - away_ht, away_ht + home_ht


def date_to_days(date_value):
    try:
        date_str = str(date_value).split(' ')[0]
        current = datetime.strptime(date_str, '%Y-%m-%d')
        start = datetime(2026, 1, 1)
        return (current - start).days
    except Exception:
        return 0


def halftime_total_bucket(halftime_total):
    try:
        total = float(halftime_total)
    except Exception:
        total = 0.0
    if total <= 60:
        return '<=60'
    if total <= 70:
        return '61-70'
    if total <= 80:
        return '71-80'
    return '81+'


def range_half_widths_for_halftime_total(halftime_total):
    bucket = halftime_total_bucket(halftime_total)
    policy = {
        '<=60': {'narrow': 3, 'wide': 5},
        '61-70': {'narrow': 5, 'wide': 7},
        '71-80': {'narrow': 4, 'wide': 6},
        '81+': {'narrow': 4, 'wide': 6},
    }
    widths = policy[bucket]
    return bucket, widths['narrow'], widths['wide']


def build_feature_dict(
    date_value,
    pace_profile,
    home_ht,
    away_ht,
    home_avg_scored,
    home_avg_allowed,
    away_avg_scored,
    away_avg_allowed,
    pbp_features=None,
):
    halftime_total = float((home_ht or 0) + (away_ht or 0))
    pace_profile_normalized = str(pace_profile or '').strip().lower()
    pace_run_and_gun = 1 if pace_profile_normalized == 'run_and_gun' else 0
    pace_moderate = 1 if pace_profile_normalized == 'moderate' else 0
    pace_grinder = 1 if pace_profile_normalized == 'grinder' else 0

    if halftime_total <= 60:
        pace_bucket = 0
    elif halftime_total <= 70:
        pace_bucket = 1
    else:
        pace_bucket = 2

    home_lead = float((home_ht or 0) - (away_ht or 0))
    home_offense_diff = float(home_avg_scored - away_avg_allowed)
    away_offense_diff = float(away_avg_scored - home_avg_allowed)

    home_score_share = home_ht / halftime_total if halftime_total > 0 else 0.5
    away_score_share = away_ht / halftime_total if halftime_total > 0 else 0.5

    expected_home_total = (home_avg_scored + away_avg_allowed) / 2.0
    expected_away_total = (away_avg_scored + home_avg_allowed) / 2.0
    expected_game_total = expected_home_total + expected_away_total
    expected_first_half_total = expected_game_total / 2.0
    expected_home_share = expected_home_total / expected_game_total if expected_game_total > 0 else 0.5
    expected_away_share = expected_away_total / expected_game_total if expected_game_total > 0 else 0.5
    pbp_values = dict(DEFAULT_PBP_FEATURES)
    if pbp_features:
        for key, value in pbp_features.items():
            if key in pbp_values and value is not None:
                pbp_values[key] = float(value)

    return {
        'home_lead': home_lead,
        'abs_home_lead': abs(home_lead),
        'pace_run_and_gun': pace_run_and_gun,
        'pace_moderate': pace_moderate,
        'pace_grinder': pace_grinder,
        'date_days': date_to_days(date_value),
        'home_avg_scored': float(home_avg_scored),
        'home_avg_allowed': float(home_avg_allowed),
        'away_avg_scored': float(away_avg_scored),
        'away_avg_allowed': float(away_avg_allowed),
        'halftime_total': halftime_total,
        'pace_bucket': pace_bucket,
        'game_density': halftime_total / 20.0 if halftime_total > 0 else 0.0,
        'home_offense_diff': home_offense_diff,
        'away_offense_diff': away_offense_diff,
        'home_score_share': home_score_share,
        'away_score_share': away_score_share,
        'expected_game_total': expected_game_total,
        'expected_first_half_total': expected_first_half_total,
        'home_ht_vs_expected': float(home_ht - (expected_home_total / 2.0)),
        'away_ht_vs_expected': float(away_ht - (expected_away_total / 2.0)),
        'halftime_total_vs_expected': float(halftime_total - expected_first_half_total),
        'second_half_baseline': float(expected_game_total - halftime_total),
        'halftime_total_ratio_to_expected': halftime_total / expected_first_half_total if expected_first_half_total > 0 else 1.0,
        'home_share_vs_expected': home_score_share - expected_home_share,
        'away_share_vs_expected': away_score_share - expected_away_share,
        'home_three_rate': pbp_values['home_three_rate'],
        'away_three_rate': pbp_values['away_three_rate'],
        'home_paint_share': pbp_values['home_paint_share'],
        'away_paint_share': pbp_values['away_paint_share'],
        'home_ft_rate': pbp_values['home_ft_rate'],
        'away_ft_rate': pbp_values['away_ft_rate'],
        'home_turnover_rate': pbp_values['home_turnover_rate'],
        'away_turnover_rate': pbp_values['away_turnover_rate'],
        'home_live_ball_turnover_share': pbp_values['home_live_ball_turnover_share'],
        'away_live_ball_turnover_share': pbp_values['away_live_ball_turnover_share'],
        'home_orb_rate': pbp_values['home_orb_rate'],
        'away_orb_rate': pbp_values['away_orb_rate'],
    }


def build_feature_vector(*args, **kwargs):
    feature_dict = build_feature_dict(*args, **kwargs)
    return [feature_dict[name] for name in FEATURE_NAMES], feature_dict