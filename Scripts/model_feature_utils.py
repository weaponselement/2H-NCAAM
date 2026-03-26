import csv
import json
import statistics
from datetime import datetime
from pathlib import Path


DEFAULT_TEAM_AVG = 70.0


def ml_to_implied_prob(american_odds):
    """Convert American moneyline odds to implied win probability.
    
    Args:
        american_odds: positive or negative integer (e.g., +150, -130)
    
    Returns:
        float between 0.0 and 1.0, or None if invalid
    """
    if american_odds is None:
        return None
    try:
        odds = float(american_odds)
        if odds > 0:
            return 1.0 / (1.0 + (odds / 100.0))
        else:
            return abs(odds) / (abs(odds) + 100.0)
    except (TypeError, ValueError):
        return None

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
    'possessions_per_team_1h',
    'dead_ball_rate',
    'long_gap_rate',
    'whistle_rate',
    'possession_change_rate',
    'accelerating_late',
    'slowing_late',
    'home_assist_rate',
    'away_assist_rate',
    'home_paint_fg_share',
    'away_paint_fg_share',
    'home_late_scoring_share',
    'away_late_scoring_share',
    'three_rate_gap',
    'paint_share_gap',
    'ft_rate_gap',
    'turnover_rate_gap',
    'live_ball_turnover_share_gap',
    'orb_rate_gap',
    'assist_rate_gap',
    'paint_fg_share_gap',
    'late_scoring_share_gap',
    'market_spread_home_close',
    'market_total_close',
    'market_home_implied_prob',
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
    'possessions_per_team_1h': 39.3,
    'dead_ball_rate': 2.2,
    'long_gap_rate': 0.06,
    'whistle_rate': 0.34,
    'possession_change_rate': 2.03,
    'accelerating_late': 0.0,
    'slowing_late': 0.0,
    'home_assist_rate': 0.46,
    'away_assist_rate': 0.46,
    'home_paint_fg_share': 0.53,
    'away_paint_fg_share': 0.53,
    'home_late_scoring_share': 0.19,
    'away_late_scoring_share': 0.19,
    'market_spread_home_close': 0.0,
    'market_total_close': 150.0,
    'market_home_implied_prob': 0.5,
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


def load_market_lines():
    """Load canonical market lines keyed by GameID for all games."""
    lines = {}
    path = Path(__file__).resolve().parent.parent / 'data' / 'processed' / 'market_lines' / 'canonical_lines.csv'
    if not path.exists():
        return lines
    try:
        import csv as csv_module
        with open(path, 'r', encoding='utf-8') as f:
            reader = csv_module.DictReader(f)
            for row in reader:
                gid = str(row.get('game_id') or '').strip()
                if not gid:
                    continue
                lines[gid] = {
                    'spread_home': row.get('spread_home'),
                    'spread_away': row.get('spread_away'),
                    'ml_home': row.get('ml_home'),
                    'ml_away': row.get('ml_away'),
                    'total_game': row.get('total_game'),
                    'total_2h': row.get('total_2h'),
                }
    except Exception:
        pass
    return lines


def load_rest_context(data_root=None):
    """Build a rest-context dict: {team_seo: sorted list of game date strings YYYY-MM-DD}.

    Only includes games whose gameState is 'final' (completed games).
    Used to compute days since a team's last game before any given date.
    """
    import glob as _glob
    if data_root is None:
        data_root = str(Path(__file__).resolve().parent.parent / 'data')
    pattern = str(Path(data_root) / 'cache' / 'scoreboard_daily' / 'scoreboard_*.json')
    rest: dict = {}
    for fpath in _glob.glob(pattern):
        fname = Path(fpath).name  # scoreboard_YYYY-MM-DD.json
        date_str = fname[len('scoreboard_'):-len('.json')]
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        try:
            with open(fpath, 'r', encoding='utf-8') as _f:
                payload = json.load(_f)
        except Exception:
            continue
        for item in payload.get('games', []):
            g = item.get('game') or {}
            state = str(g.get('gameState') or '').lower()
            if state not in {'final', 'complete', 'completed'}:
                continue
            away_seo = ((g.get('away') or {}).get('names') or {}).get('seo', '')
            home_seo = ((g.get('home') or {}).get('names') or {}).get('seo', '')
            for seo in (away_seo, home_seo):
                if seo:
                    rest.setdefault(seo, set()).add(date_str)
    # Convert sets to sorted lists for binary search
    return {seo: sorted(dates) for seo, dates in rest.items()}


def get_days_rest(rest_context, team_seo, game_date_str, cap=10):
    """Return days since team_seo's most recent game before game_date_str.

    Returns cap if no prior game is found (e.g. season start).
    """
    import bisect as _bisect
    dates = rest_context.get(team_seo)
    if not dates:
        return float(cap)
    # Find insertion point for game_date_str; games strictly before this date
    idx = _bisect.bisect_left(dates, game_date_str)
    if idx == 0:
        return float(cap)
    prev_date = dates[idx - 1]
    try:
        delta = datetime.strptime(game_date_str, '%Y-%m-%d') - datetime.strptime(prev_date, '%Y-%m-%d')
        return float(min(delta.days, cap))
    except Exception:
        return float(cap)


def load_neutral_court_games(data_root=None):
    """Return a set of gameID strings that were played on neutral courts.

    Uses the bracketRound and bracketId fields from scoreboard_daily cache.
    Any game with a non-empty bracketRound or bracketId is treated as neutral.
    """
    import glob as _glob
    if data_root is None:
        data_root = str(Path(__file__).resolve().parent.parent / 'data')
    pattern = str(Path(data_root) / 'cache' / 'scoreboard_daily' / 'scoreboard_*.json')
    neutral: set = set()
    for fpath in _glob.glob(pattern):
        try:
            with open(fpath, 'r', encoding='utf-8') as _f:
                payload = json.load(_f)
        except Exception:
            continue
        for item in payload.get('games', []):
            g = item.get('game') or {}
            br = g.get('bracketRound')
            bi = g.get('bracketId')
            if br or bi:
                gid = str(g.get('gameID') or '').strip()
                if gid:
                    neutral.add(gid)
    return neutral


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
        '<=60': {'narrow': 3, 'wide': 3},
        '61-70': {'narrow': 4, 'wide': 4},
        '71-80': {'narrow': 4, 'wide': 4},
        '81+': {'narrow': 3, 'wide': 3},
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
    game_id=None,
    market_lines_cache=None,
    home_team_seo=None,
    away_team_seo=None,
    rest_context=None,
    neutral_court_games=None,
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

    three_rate_gap = pbp_values['home_three_rate'] - pbp_values['away_three_rate']
    paint_share_gap = pbp_values['home_paint_share'] - pbp_values['away_paint_share']
    ft_rate_gap = pbp_values['home_ft_rate'] - pbp_values['away_ft_rate']
    turnover_rate_gap = pbp_values['home_turnover_rate'] - pbp_values['away_turnover_rate']
    live_ball_turnover_share_gap = (
        pbp_values['home_live_ball_turnover_share'] - pbp_values['away_live_ball_turnover_share']
    )
    orb_rate_gap = pbp_values['home_orb_rate'] - pbp_values['away_orb_rate']
    assist_rate_gap = pbp_values['home_assist_rate'] - pbp_values['away_assist_rate']
    paint_fg_share_gap = pbp_values['home_paint_fg_share'] - pbp_values['away_paint_fg_share']
    late_scoring_share_gap = pbp_values['home_late_scoring_share'] - pbp_values['away_late_scoring_share']

    market_spread_home_close = pbp_values['market_spread_home_close']
    market_total_close = pbp_values['market_total_close']
    market_home_implied_prob = pbp_values['market_home_implied_prob']

    if game_id and market_lines_cache is not None:
        game_id_key = str(game_id).strip()
        line_row = market_lines_cache.get(game_id_key)
        if line_row:
            spread_val = line_row.get('spread_home')
            total_val = line_row.get('total_game')
            ml_val = line_row.get('ml_home')

            if spread_val not in (None, ''):
                try:
                    import math as _math
                    s = float(spread_val)
                    market_spread_home_close = s
                    # Derive implied probability from spread when no ML is available
                    # logistic: ~0.065 pts per probability unit
                    market_home_implied_prob = 1.0 / (1.0 + _math.exp(s * 0.065))
                except (TypeError, ValueError):
                    pass
            if total_val not in (None, ''):
                try:
                    market_total_close = float(total_val)
                except (TypeError, ValueError):
                    pass
            if ml_val not in (None, ''):
                # Only use ML if it looks like American odds (large integer)
                # not a probability percentage from our scraper derivation
                implied = ml_to_implied_prob(ml_val)
                if implied is not None:
                    market_home_implied_prob = implied

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
        'possessions_per_team_1h': pbp_values['possessions_per_team_1h'],
        'dead_ball_rate': pbp_values['dead_ball_rate'],
        'long_gap_rate': pbp_values['long_gap_rate'],
        'whistle_rate': pbp_values['whistle_rate'],
        'possession_change_rate': pbp_values['possession_change_rate'],
        'accelerating_late': pbp_values['accelerating_late'],
        'slowing_late': pbp_values['slowing_late'],
        'home_assist_rate': pbp_values['home_assist_rate'],
        'away_assist_rate': pbp_values['away_assist_rate'],
        'home_paint_fg_share': pbp_values['home_paint_fg_share'],
        'away_paint_fg_share': pbp_values['away_paint_fg_share'],
        'home_late_scoring_share': pbp_values['home_late_scoring_share'],
        'away_late_scoring_share': pbp_values['away_late_scoring_share'],
        'three_rate_gap': three_rate_gap,
        'paint_share_gap': paint_share_gap,
        'ft_rate_gap': ft_rate_gap,
        'turnover_rate_gap': turnover_rate_gap,
        'live_ball_turnover_share_gap': live_ball_turnover_share_gap,
        'orb_rate_gap': orb_rate_gap,
        'assist_rate_gap': assist_rate_gap,
        'paint_fg_share_gap': paint_fg_share_gap,
        'late_scoring_share_gap': late_scoring_share_gap,
        'market_spread_home_close': market_spread_home_close,
        'market_total_close': market_total_close,
        'market_home_implied_prob': market_home_implied_prob,
    }


def build_feature_vector(*args, **kwargs):
    feature_dict = build_feature_dict(*args, **kwargs)
    return [feature_dict[name] for name in FEATURE_NAMES], feature_dict