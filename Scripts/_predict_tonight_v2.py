#!/usr/bin/env python3
"""
One-off pregame prediction for specific games using the Window-5 RF model.
Reuses all loading functions from analyze_pregame_model_depth_v1.py.
Run as:
    python Scripts/_predict_tonight_v2.py 2>&1 | Out-File logs/tonight_prediction.txt
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "deep", Path(__file__).resolve().parent / "analyze_pregame_model_depth_v1.py"
)
deep = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(deep)

import model_feature_utils as mfu
from sklearn.ensemble import RandomForestRegressor

# -------------------------------------------------------
# Config
# -------------------------------------------------------
WINDOW = 5

# Tonight's games  (neutral court — home/away order is arbitrary for totals)
# Format: (label, tipoff, home_seo, away_seo, closing_line)
TONIGHT = [
    ("Michigan State vs UConn",  "7:45 PM CST",  "michigan-st", "uconn",   136.5),
    ("Tennessee vs Iowa State",  "9:25 PM CST",  "tennessee",   "iowa-st", 139.5),
]

# Most-recent W5 baseline date that contains each team
TEAM_BASELINE_DATE = {
    "michigan-st": "2026-03-21",
    "uconn":       "2026-03-22",
    "tennessee":   "2026-03-22",
    "iowa-st":     "2026-03-22",
}


def build_game_feature_row(home_seo, away_seo, stats_h, priors_h, stats_a, priors_a):
    """
    Build the 28-feature dict for a single game by merging
    per-team baselines from two potentially different dates.
    """
    hs, ha    = mfu.resolve_team_stats(stats_h, home_seo)
    as_, aa   = mfu.resolve_team_stats(stats_a, away_seo)
    exp       = deep.expected_total(hs, ha, as_, aa)

    # Merge stats so get_team_priors can look up from a combined dict
    merged_priors = {}
    merged_priors.update(priors_h)
    merged_priors.update(priors_a)

    hp = deep.get_team_priors(merged_priors, home_seo)
    ap = deep.get_team_priors(merged_priors, away_seo)

    features = {
        'home_avg_scored':          hs,
        'home_avg_allowed':         ha,
        'away_avg_scored':          as_,
        'away_avg_allowed':         aa,
        'expected_total':           exp,
        'home_offense_diff':        hs - aa,
        'away_offense_diff':        as_ - ha,
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
    return features, exp, hs, ha, as_, aa


def main():
    print("=" * 62)
    print("  TONIGHT'S ELITE EIGHT PREDICTIONS  |  Window-5 RF Model")
    print("  March 27, 2026")
    print("=" * 62)

    # ----------------------------------------------------------
    # Step 1: Load all historical data (needed for training)
    # ----------------------------------------------------------
    print("\n[1/3] Loading historical workbook rows...")
    workbook_rows = deep.build_rows()
    lines_map     = deep.load_lines()

    unique_dates = sorted({
        str(r.get('Date') or '').split(' ')[0].strip()
        for r in workbook_rows if r.get('Date') not in (None, '')
    })
    print(f"  {len(unique_dates)} unique game dates in workbook.")
    print("  Loading baselines + PBP priors for each date...")
    print("  (Same PBP preload step as deep-dive script — takes several minutes)")

    team_stats_by_date = {d: deep.load_team_stats_for_window(d, WINDOW) for d in unique_dates}
    priors_by_date     = {d: deep.load_priors_for_window(d, WINDOW)     for d in unique_dates}

    feature_rows = []
    for record in workbook_rows:
        built = deep.build_feature_row(record, team_stats_by_date, priors_by_date)
        if built is None:
            continue
        built['closing_total'] = lines_map.get(built['game_id'])
        feature_rows.append(built)

    print(f"  {len(feature_rows)} rows featurized and ready for training.")

    # ----------------------------------------------------------
    # Step 2: Train RF on ALL historical data
    # ----------------------------------------------------------
    print("\n[2/3] Training RandomForestRegressor on all historical data...")
    feature_names = list(feature_rows[0]['features'].keys())
    X = [[r['features'][n] for n in feature_names] for r in feature_rows]
    y = [r['actual_total']                          for r in feature_rows]

    model = RandomForestRegressor(
        n_estimators=400, min_samples_leaf=3, random_state=42, n_jobs=-1
    )
    model.fit(X, y)
    print(f"  Model trained on {len(X)} games.")

    # ----------------------------------------------------------
    # Step 3: Load tonight's team baselines and predict
    # ----------------------------------------------------------
    print("\n[3/3] Loading tonight's team baselines...")

    # Cache: only 2 dates needed (2026-03-21 and 2026-03-22)
    tonight_stats  = {}
    tonight_priors = {}
    for _, _, home_seo, away_seo, _ in TONIGHT:
        for seo in (home_seo, away_seo):
            d = TEAM_BASELINE_DATE[seo]
            if d not in tonight_stats:
                print(f"  date {d}")
                tonight_stats[d]  = deep.load_team_stats_for_window(d, WINDOW)
                tonight_priors[d] = deep.load_priors_for_window(d, WINDOW)

    print()
    print("=" * 62)
    print("  RESULTS")
    print("=" * 62)

    for label, tipoff, home_seo, away_seo, line in TONIGHT:
        hd = TEAM_BASELINE_DATE[home_seo]
        ad = TEAM_BASELINE_DATE[away_seo]

        feats, exp, hs, ha, as_, aa = build_game_feature_row(
            home_seo, away_seo,
            tonight_stats[hd],  tonight_priors[hd],
            tonight_stats[ad],  tonight_priors[ad],
        )

        x_vec  = [[feats[n] for n in feature_names]]
        pred   = float(model.predict(x_vec)[0])

        raw_gap   = pred - line       # positive = lean OVER
        abs_gap   = abs(raw_gap)
        direction = 'OVER' if raw_gap > 0 else 'UNDER'
        base_gap  = exp - line

        if abs_gap >= 10:
            signal = '*** FULL SEND ***'
        elif abs_gap >= 8:
            signal = '** LEAN (gap 8-9) **'
        elif abs_gap >= 5:
            signal = '* MONITOR (gap 5-7) *'
        else:
            signal = 'no action (gap < 5)'

        print(f"\n  {label}  —  {tipoff}")
        print(f"  {'-' * 50}")
        print(f"  {home_seo}: avg_scored={hs:.1f}, avg_allowed={ha:.1f}  (W{WINDOW}, as of {hd})")
        print(f"  {away_seo}: avg_scored={as_:.1f}, avg_allowed={aa:.1f}  (W{WINDOW}, as of {ad})")
        print(f"  Baseline expected total:  {exp:.1f}  (vs line {base_gap:+.1f})")
        print(f"  MODEL predicted total:    {pred:.1f}")
        print(f"  Closing line:             {line}")
        print(f"  Signed gap (pred-line):   {raw_gap:+.1f}  => lean {direction}")
        print(f"  Absolute gap:             {abs_gap:.1f}")
        print(f"  SIGNAL:                   {signal}")
        if abs_gap >= 8:
            print(f"")
            print(f"  --> ACTION: BET {direction} {line}")
        if direction == 'UNDER' and abs_gap >= 8:
            print(f"  --> Under-only historically strongest W5 signal (60.4% hit, +15.3% ROI)")

    print()
    print("=" * 62)
    print("Signal thresholds:")
    print("  Full Send : gap >= 10  (W5, 86.7% of days have a signal, avg 5.8/day)")
    print("  Lean      : gap >= 8   (W7 threshold, broader, both directions profitable)")
    print("Note: Neutral-court tournament games, home/away labels arbitrary.")
    print("=" * 62)


if __name__ == '__main__':
    main()
