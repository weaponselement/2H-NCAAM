#!/usr/bin/env python3
"""
One-off pregame prediction for specific games using the Window-5 RF model.
Trains on all available historical data, predicts totals for manually-specified matchups.
Usage: python Scripts/_predict_tonight_v1.py
"""
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import the deep-dive module (already tested, has all the loading functions)
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "deep", Path(__file__).resolve().parent / "analyze_pregame_model_depth_v1.py"
)
deep = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(deep)

import model_feature_utils as mfu
from sklearn.ensemble import RandomForestRegressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT    = PROJECT_ROOT / 'data'
LOGS_DIR     = PROJECT_ROOT / 'logs'
BASELINES_DIR = DATA_ROOT / 'processed' / 'baselines'
WORKBOOK_PATH = LOGS_DIR / 'NCAAM Results.xlsx'
CANONICAL_LINES_PATH = DATA_ROOT / 'processed' / 'market_lines' / 'canonical_lines.csv'

WINDOW = 5

PBP_PRIOR_KEYS = [
    'last4_three_rate', 'last4_paint_share', 'last4_ft_rate',
    'last4_turnover_rate', 'last4_orb_rate',
    'last4_possessions_per_team_1h', 'last4_pbp_coverage_count',
]

def safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


# -------------------------------------------------------
# Baseline + PBP prior loading
# -------------------------------------------------------
def load_team_stats_for_date(date_str):
    p = BASELINES_DIR / f'lastN_{WINDOW}_{date_str}.json'
    if not p.exists():
        return mfu.load_team_stats(date_str)
    try:
        with open(p, 'r', encoding='utf-8') as f:
            baseline = json.load(f)
    except Exception:
        return mfu.load_team_stats(date_str)
    stats = {}
    for team, games in (baseline.get('teams') or {}).items():
        if not isinstance(games, list) or not games:
            continue
        sf = [safe_float(g.get('score_for'))     for g in games]
        sa = [safe_float(g.get('score_against')) for g in games]
        sf = [x for x in sf if x is not None]
        sa = [x for x in sa if x is not None]
        if sf and sa:
            stats[team] = {'avg_scored': statistics.mean(sf), 'avg_allowed': statistics.mean(sa)}
    return stats


def load_priors_for_date(date_str):
    p = BASELINES_DIR / f'lastN_{WINDOW}_{date_str}.json'
    if not p.exists():
        return mfu.load_last4_pbp_priors(date_str, data_root=str(DATA_ROOT))
    try:
        with open(p, 'r') as f:
            baseline = json.load(f)
        priors = {}
        for team_seo, games in (baseline.get('teams') or {}).items():
            if not isinstance(games, list) or not games:
                continue
            prior_rows = []
            for g in games:
                gid = str((g or {}).get('gameID') or '').strip()
                if gid:
                    pbp = step4b.load_game_pbp_features(str(DATA_ROOT), gid)
                    if pbp:
                        prior_rows.append(pbp)
            if not prior_rows:
                priors[team_seo] = {
                    k: mfu.DEFAULT_PBP_FEATURES.get('home_last4_' + k,
                       mfu.DEFAULT_PBP_FEATURES.get(k, 0.0))
                    for k in PBP_PRIOR_KEYS
                }
                continue

            def _mean(key, default):
                vals = [float(r.get(key)) for r in prior_rows if r.get(key) is not None]
                return statistics.mean(vals) if vals else float(default)

            priors[team_seo] = {
                'last4_three_rate':              _mean('home_three_rate',            0.33),
                'last4_paint_share':             _mean('home_paint_share',           0.40),
                'last4_ft_rate':                 _mean('home_ft_rate',               0.25),
                'last4_turnover_rate':           _mean('home_turnover_rate',         0.18),
                'last4_orb_rate':                _mean('home_orb_rate',              0.28),
                'last4_possessions_per_team_1h': _mean('possessions_per_team_1h',    39.3),
                'last4_pbp_coverage_count':      float(len(prior_rows)),
            }
        return priors
    except Exception:
        return mfu.load_last4_pbp_priors(date_str, data_root=str(DATA_ROOT))


def get_team_priors(priors, team):
    td = (priors or {}).get(str(team or '').strip(), {})
    return {k: float(td.get(k, 0.0) or 0.0) for k in PBP_PRIOR_KEYS}


def expected_total(hs, ha, as_, aa):
    return ((hs + aa) / 2.0) + ((as_ + ha) / 2.0)


def build_feature_dict(home_seo, away_seo, stats, priors):
    hs, ha   = mfu.resolve_team_stats(stats, home_seo)
    as_, aa  = mfu.resolve_team_stats(stats, away_seo)
    exp      = expected_total(hs, ha, as_, aa)
    hp       = get_team_priors(priors, home_seo)
    ap       = get_team_priors(priors, away_seo)
    features = {
        'home_avg_scored':      hs,
        'home_avg_allowed':     ha,
        'away_avg_scored':      as_,
        'away_avg_allowed':     aa,
        'expected_total':       exp,
        'home_offense_diff':    hs - aa,
        'away_offense_diff':    as_ - ha,
        'blended_possessions_1h':
            (hp['last4_possessions_per_team_1h'] + ap['last4_possessions_per_team_1h']) / 2.0,
        'blended_possessions_full':
            (hp['last4_possessions_per_team_1h'] + ap['last4_possessions_per_team_1h']),
        'blended_three_rate':
            (hp['last4_three_rate']    + ap['last4_three_rate'])    / 2.0,
        'blended_paint_share':
            (hp['last4_paint_share']   + ap['last4_paint_share'])   / 2.0,
        'blended_ft_rate':
            (hp['last4_ft_rate']       + ap['last4_ft_rate'])       / 2.0,
        'blended_turnover_rate':
            (hp['last4_turnover_rate'] + ap['last4_turnover_rate']) / 2.0,
        'blended_orb_rate':
            (hp['last4_orb_rate']      + ap['last4_orb_rate'])      / 2.0,
        'blended_pbp_coverage':
            (hp['last4_pbp_coverage_count'] + ap['last4_pbp_coverage_count']) / 2.0,
        'home_last4_three_rate':     hp['last4_three_rate'],
        'away_last4_three_rate':     ap['last4_three_rate'],
        'home_last4_ft_rate':        hp['last4_ft_rate'],
        'away_last4_ft_rate':        ap['last4_ft_rate'],
        'home_last4_turnover_rate':  hp['last4_turnover_rate'],
        'away_last4_turnover_rate':  ap['last4_turnover_rate'],
        'home_last4_orb_rate':       hp['last4_orb_rate'],
        'away_last4_orb_rate':       ap['last4_orb_rate'],
        'home_last4_possessions_1h': hp['last4_possessions_per_team_1h'],
        'away_last4_possessions_1h': ap['last4_possessions_per_team_1h'],
        'three_rate_gap':     hp['last4_three_rate']    - ap['last4_three_rate'],
        'ft_rate_gap':        hp['last4_ft_rate']       - ap['last4_ft_rate'],
        'turnover_rate_gap':  hp['last4_turnover_rate'] - ap['last4_turnover_rate'],
        'orb_rate_gap':       hp['last4_orb_rate']      - ap['last4_orb_rate'],
    }
    return features, exp


# -------------------------------------------------------
# Load all historical rows for model training
# -------------------------------------------------------
def build_historical_rows():
    wb = load_workbook(str(WORKBOOK_PATH), data_only=True)
    ws = wb['Game_Log']
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(c) if c is not None else '' for c in rows[0]]
    data = []
    for row in rows[1:]:
        if not any(v is not None for v in row):
            continue
        data.append({headers[i]: row[i] if i < len(row) else None for i in range(len(headers))})
    return data


def load_lines():
    out = {}
    with open(str(CANONICAL_LINES_PATH), 'r', encoding='utf-8', newline='') as f:
        for row in csv.DictReader(f):
            gid = str(row.get('game_id') or '').strip()
            if gid:
                out[gid] = safe_float(row.get('total_game'))
    return out


# -------------------------------------------------------
# MAIN
# -------------------------------------------------------
def main():
    print("=" * 60)
    print("TONIGHT'S ELITE EIGHT PREDICTIONS — Window 5")
    print("=" * 60)

    # Games to predict (neutral court — home/away order is arbitrary for totals)
    tonight = [
        {
            'label':      'Michigan State vs UConn',
            'time':       '7:45 PM CST',
            'home_seo':   'michigan-st',
            'away_seo':   'uconn',
            'line':       136.5,
            'home_date':  '2026-03-21',   # most recent baseline containing michigan-st
            'away_date':  '2026-03-22',   # most recent baseline containing uconn
        },
        {
            'label':      'Tennessee vs Iowa State',
            'time':       '9:25 PM CST',
            'home_seo':   'tennessee',
            'away_seo':   'iowa-st',
            'line':       139.5,
            'home_date':  '2026-03-22',
            'away_date':  '2026-03-22',
        },
    ]

    # Load baselines per date (cache)
    print("\n[1/4] Loading team baselines...")
    stats_cache  = {}
    priors_cache = {}
    for game in tonight:
        for role in ('home', 'away'):
            d = game[role + '_date']
            if d not in stats_cache:
                print(f"  Loading stats  for {d}...")
                stats_cache[d]  = load_team_stats_for_date(d)
            if d not in priors_cache:
                print(f"  Loading priors for {d}...")
                priors_cache[d] = load_priors_for_date(d)

    # Merge stats so we can pass a single dict per game
    # (combine the two date-specific dicts)
    def merge_stats(home_seo, home_date, away_seo, away_date):
        merged = {}
        for seo, date in [(home_seo, home_date), (away_seo, away_date)]:
            s = stats_cache[date]
            if seo in s:
                merged[seo] = s[seo]
        return merged

    def merge_priors(home_seo, home_date, away_seo, away_date):
        merged = {}
        for seo, date in [(home_seo, home_date), (away_seo, away_date)]:
            p = priors_cache[date]
            if seo in p:
                merged[seo] = p[seo]
        return merged

    # Report raw baselines
    print("\n[2/4] Pre-model expected totals (team averages only):")
    for game in tonight:
        merged_s = merge_stats(
            game['home_seo'], game['home_date'],
            game['away_seo'], game['away_date']
        )
        merged_p = merge_priors(
            game['home_seo'], game['home_date'],
            game['away_seo'], game['away_date']
        )
        _, exp = build_feature_dict(
            game['home_seo'], game['away_seo'], merged_s, merged_p
        )
        gap = exp - game['line']
        game['baseline_exp'] = exp
        game['merged_stats']  = merged_s
        game['merged_priors'] = merged_p
        print(f"  {game['label']}: baseline={exp:.1f}, line={game['line']}, gap={gap:+.1f}")

    # Load + featurize historical data
    print("\n[3/4] Loading historical data and training RF model...")
    historical_data  = build_historical_rows()
    lines_map        = load_lines()

    unique_dates = sorted({
        str(r.get('Date') or '').split(' ')[0].strip()
        for r in historical_data if r.get('Date') not in (None, '')
    })

    # Use same loading functions used in walk-forward (from analyze_pregame_model_depth_v1)
    from analyze_pregame_model_depth import build_feature_row as bfr

    # Inline build to avoid re-importing the whole deep analysis script
    # We replicate build_feature_row logic here for training rows
    hist_feature_rows = []
    ts_cache_hist  = {}
    pr_cache_hist  = {}
    for record in historical_data:
        date_str = str(record.get('Date') or '').split(' ')[0].strip()
        if not date_str:
            continue
        if date_str not in ts_cache_hist:
            ts_cache_hist[date_str]  = load_team_stats_for_date(date_str)
            pr_cache_hist[date_str]  = load_priors_for_date(date_str)

        home   = str(record.get('Home') or '').strip()
        away   = str(record.get('Away') or '').strip()
        actual = safe_float(record.get('ActualTotal'))
        gid    = str(record.get('GameID') or '').strip()
        if not date_str or not home or not away or actual is None or not gid:
            continue

        try:
            feats, exp = build_feature_dict(
                home, away, ts_cache_hist[date_str], pr_cache_hist[date_str]
            )
        except Exception:
            continue

        closing = lines_map.get(gid)
        hist_feature_rows.append({
            'game_id':      gid,
            'date':         date_str,
            'home':         home,
            'away':         away,
            'actual_total': actual,
            'features':     feats,
            'expected_total': exp,
            'closing_total':  closing,
        })

    feature_names = list(hist_feature_rows[0]['features'].keys())
    X_train = [[r['features'][n] for n in feature_names] for r in hist_feature_rows]
    y_train = [r['actual_total'] for r in hist_feature_rows]

    print(f"  Training on {len(X_train)} historical games...")
    model = RandomForestRegressor(
        n_estimators=400, min_samples_leaf=3, random_state=42, n_jobs=-1
    )
    model.fit(X_train, y_train)
    print("  Model trained.")

    # -------------------------------------------------------
    # Predict tonight's games
    # -------------------------------------------------------
    print("\n[4/4] PREDICTIONS:")
    print("=" * 60)
    for game in tonight:
        feats, exp = build_feature_dict(
            game['home_seo'], game['away_seo'],
            game['merged_stats'], game['merged_priors']
        )
        x_vec = [[feats[n] for n in feature_names]]
        pred  = float(model.predict(x_vec)[0])
        line  = game['line']
        raw_gap = pred - line          # signed: positive = model > line (lean OVER)
        abs_gap = abs(raw_gap)
        direction = 'OVER' if raw_gap > 0 else 'UNDER'

        baseline_gap = exp - line      # same for baseline

        if abs_gap >= 10:
            signal = 'FULL SEND'
        elif abs_gap >= 8:
            signal = 'LEAN (gap 8-9)'
        elif abs_gap >= 5:
            signal = 'MONITOR (gap 5-7)'
        else:
            signal = 'NO ACTION'

        print(f"\n  {game['label']}  ({game['time']})")
        print(f"  {'─'*44}")
        print(f"  Line (total):        {line}")
        print(f"  Baseline expected:   {exp:.1f}  (gap vs line: {baseline_gap:+.1f})")
        print(f"  MODEL prediction:    {pred:.1f}")
        print(f"  Signed gap:          {raw_gap:+.1f}  => lean {direction}")
        print(f"  Absolute gap:        {abs_gap:.1f}")
        print(f"  SIGNAL:              {signal}")
        if abs_gap >= 8:
            print(f"  ** {signal}: BET {direction} {line} **")

        # Under-only note
        if direction == 'UNDER' and abs_gap >= 8:
            print(f"  (Under-only rule applies — historically strongest signal)")

    print("\n" + "=" * 60)
    print("NOTE: These are neutral-court tournament games.")
    print("Home/away labels are arbitrary; totals formula is symmetric.")
    print("Model trained on full-season historical data (all windows).")
    print("=" * 60)


if __name__ == '__main__':
    main()
