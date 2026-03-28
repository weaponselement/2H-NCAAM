#!/usr/bin/env python3
"""
Simpler window optimization test: generates window variants from existing baselines
and tests each via modified evaluator.
Uses the existing last4 baselines and tests windows 3,4,5,6,7,8.
"""

import json
import sys
from pathlib import Path
import subprocess
import time
from datetime import datetime, timedelta

BASELINES_DIR = Path(__file__).resolve().parent.parent / 'data' / 'processed' / 'baselines'
LOGS_DIR = Path(__file__).resolve().parent.parent / 'logs'
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parent.parent

WINDOWS = [3, 4, 5, 6, 7, 8]


def _looks_numeric(value):
    if value is None:
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str) and value.strip().isdigit():
        return True
    return False


def is_completed_game(game_obj: dict) -> bool:
    for key in ['gameState', 'status', 'state']:
        val = game_obj.get(key)
        if isinstance(val, str) and val.lower() in {'final', 'complete', 'completed'}:
            return True

    status = game_obj.get('gameStatus') or game_obj.get('status') or {}
    if isinstance(status, dict):
        st = status.get('state') or status.get('status') or ''
        if isinstance(st, str) and st.lower() in {'final', 'complete', 'completed'}:
            return True

    away_score = (game_obj.get('away') or {}).get('score')
    home_score = (game_obj.get('home') or {}).get('score')
    return _looks_numeric(away_score) and _looks_numeric(home_score)


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _load_completed_games_by_date(cache_root: Path):
    """Index cached scoreboard files as {date_str: [completed_game_rows]}.

    Each row stores the minimal fields needed to build team last-N manifests.
    """
    out = {}
    for path in sorted(cache_root.glob('scoreboard_*.json')):
        date_str = path.stem.replace('scoreboard_', '')
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
        except Exception:
            continue
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue

        rows = []
        for item in payload.get('games', []):
            g = item.get('game') or {}
            if not is_completed_game(g):
                continue
            gid = str(g.get('gameID') or '').strip()
            away = g.get('away') or {}
            home = g.get('home') or {}
            away_names = away.get('names') or {}
            home_names = home.get('names') or {}
            away_seo = str(away_names.get('seo') or '').strip()
            home_seo = str(home_names.get('seo') or '').strip()
            if not gid or not away_seo or not home_seo:
                continue

            rows.append(
                {
                    'gameID': gid,
                    'away_seo': away_seo,
                    'home_seo': home_seo,
                    'away_score': _safe_int(away.get('score')),
                    'home_score': _safe_int(home.get('score')),
                    'url': g.get('url'),
                    'neutralSite': g.get('neutralSite'),
                }
            )
        out[date_str] = rows
    return out


def _build_lastn_from_cache(run_date: str, team_seos: list[str], max_window: int, max_days_back: int, games_by_date: dict):
    """Return {team_seo: [game_records]} with up to max_window prior completed games."""
    target = {seo: [] for seo in team_seos}
    seen = {seo: set() for seo in team_seos}
    team_set = set(team_seos)

    anchor = datetime.strptime(run_date, '%Y-%m-%d')
    dt = anchor - timedelta(days=1)
    checked = 0

    while checked < max_days_back:
        if all(len(target[seo]) >= max_window for seo in team_seos):
            break
        d = dt.strftime('%Y-%m-%d')
        for g in games_by_date.get(d, []):
            away_seo = g['away_seo']
            home_seo = g['home_seo']
            gid = g['gameID']
            if away_seo in team_set and len(target[away_seo]) < max_window and gid not in seen[away_seo]:
                seen[away_seo].add(gid)
                target[away_seo].append(
                    {
                        'date': d,
                        'gameID': gid,
                        'opponent_seo': home_seo,
                        'home_away': 'away',
                        'score_for': g['away_score'],
                        'score_against': g['home_score'],
                        'url': g.get('url'),
                        'neutralSite': g.get('neutralSite'),
                    }
                )
            if home_seo in team_set and len(target[home_seo]) < max_window and gid not in seen[home_seo]:
                seen[home_seo].add(gid)
                target[home_seo].append(
                    {
                        'date': d,
                        'gameID': gid,
                        'opponent_seo': away_seo,
                        'home_away': 'home',
                        'score_for': g['home_score'],
                        'score_against': g['away_score'],
                        'url': g.get('url'),
                        'neutralSite': g.get('neutralSite'),
                    }
                )
        dt -= timedelta(days=1)
        checked += 1

    return target

def create_baseline_variants(source_date: str = '2026-03-26'):
    """Create true lastN variants for every baseline date from cached game history."""
    baseline_files = sorted(BASELINES_DIR.glob('last4_*.json'))
    if not baseline_files:
        print(f"[ERROR] No last4 baseline files found in {BASELINES_DIR}", flush=True)
        return False

    # Keep backward compatibility with a specific source date when provided.
    if source_date:
        candidate = BASELINES_DIR / f'last4_{source_date}.json'
        if candidate.exists():
            print(f"Using full baseline set; confirmed source date exists: {candidate.name}", flush=True)
        else:
            print(f"[WARN] Source date baseline not found ({candidate.name}); continuing with all available dates.", flush=True)

    print(f"Found {len(baseline_files)} daily baseline files to convert.", flush=True)

    cache_root = Path(__file__).resolve().parent.parent / 'data' / 'cache' / 'scoreboard_daily'
    games_by_date = _load_completed_games_by_date(cache_root)
    if not games_by_date:
        print(f"[ERROR] No scoreboard cache files found in {cache_root}", flush=True)
        return False
    print(f"Indexed completed games from {len(games_by_date)} scoreboard days.", flush=True)

    created_count = 0
    max_window = max(WINDOWS)
    max_days_back = 150
    for src_path in baseline_files:
        date_part = src_path.stem.replace('last4_', '')
        try:
            with open(src_path, 'r') as f:
                baseline = json.load(f)
        except Exception as e:
            print(f"[WARN] Skipping unreadable baseline {src_path.name}: {e}", flush=True)
            continue
        teams_data = baseline.get('teams', {})
        team_seos = sorted(list(teams_data.keys())) if isinstance(teams_data, dict) else []
        if not team_seos:
            continue

        true_lastn = _build_lastn_from_cache(
            run_date=date_part,
            team_seos=team_seos,
            max_window=max_window,
            max_days_back=max_days_back,
            games_by_date=games_by_date,
        )

        for window in WINDOWS:
            truncated_baseline = {
                'run_date': baseline.get('run_date'),
                'source': f'window_test_variant_{window}',
                'games_per_team': window,
                'teams': {}
            }

            for team_seo in team_seos:
                games_list = true_lastn.get(team_seo, [])
                truncated_baseline['teams'][team_seo] = games_list[:window]

            output_path = BASELINES_DIR / f'lastN_{window}_{date_part}.json'
            with open(output_path, 'w') as f:
                json.dump(truncated_baseline, f, indent=2)
            created_count += 1

    print(f"[*] Created/updated {created_count} window baseline files.", flush=True)
    return True

def run_window_evaluator(window: int, source_date: str = '2026-03-26'):
    """Run evaluator for a specific window."""
    print(f"\n{'='*70}", flush=True)
    print(f"Testing window={window} games", flush=True)
    print(f"{'='*70}", flush=True)
    
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / 'evaluate_window_optimization_v1.py'),
        '--window', str(window),
        '--source-date', source_date,
        '--odds', '-110',
        '--min-bets', '20',
        '--mode', 'walkforward',
        '--min-train-dates', '60',
        '--fold-size', '30',
    ]
    
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    time.sleep(1)
    return result.returncode == 0

def load_results(window: int) -> dict:
    """Load results for a window."""
    path = LOGS_DIR / f'window_test_results_{window}.json'
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def print_comparison():
    """Print comparison across all windows."""
    print(f"\n{'='*70}", flush=True)
    print(f"WINDOW OPTIMIZATION RESULTS", flush=True)
    print(f"{'='*70}\n", flush=True)
    
    all_results = {}
    for window in WINDOWS:
        results = load_results(window)
        if results:
            all_results[window] = results

    if not all_results:
        print("No results found.", flush=True)
        return

    # MAE comparison
    print(f"{'WINDOW':<10} {'BASELINE_MAE':<15} {'RF_MAE':<15} {'DELTA':<12}", flush=True)
    print(f"{'-'*55}", flush=True)
    for window in sorted(all_results.keys()):
        metrics = all_results[window]['metrics']
        mae_bl = metrics['mae_baseline']
        mae_rf = metrics['mae_rf']
        delta = mae_rf - mae_bl
        marker = " [BEST]" if mae_bl < 14.5 else ""
        print(f"{window:<10} {mae_bl:<15.3f} {mae_rf:<15.3f} {delta:+.3f}{marker}", flush=True)

    # Best policy ROI
    print(f"\n{'WINDOW':<10} {'BASELINE_ROI%':<15} {'RF_ROI%':<15} {'BL_HIT%':<12} {'BETS':<8}", flush=True)
    print(f"{'-'*65}", flush=True)
    best_window = None
    best_roi = -float('inf')
    for window in sorted(all_results.keys()):
        bl_policy = all_results[window].get('baseline_policy')
        rf_policy = all_results[window].get('rf_policy')
        bl_roi = bl_policy['roi'] if bl_policy else 0
        rf_roi = rf_policy['roi'] if rf_policy else 0
        bl_hit = bl_policy['hit_rate'] if bl_policy else 0
        bl_bets = bl_policy['bets'] if bl_policy else 0
        
        marker = " [TOP]" if bl_roi > best_roi else ""
        if bl_roi > best_roi:
            best_roi = bl_roi
            best_window = window
            
        print(f"{window:<10} {bl_roi:<15.2f} {rf_roi:<15.2f} {bl_hit:<12.1f} {bl_bets:<8}{marker}", flush=True)

    # Feature importance trends
    print(f"\n{'='*70}", flush=True)
    print(f"TOP FEATURE STABILITY (Top 3 by window)", flush=True)
    print(f"{'='*70}\n", flush=True)
    
    for window in sorted(all_results.keys()):
        features = all_results[window]['top_10_features']
        top3 = sorted(features.items(), key=lambda x: x[1], reverse=True)[:3]
        feature_names = [name for name, _ in top3]
        print(f"Window {window}: {', '.join(feature_names)}", flush=True)

    # Analysis
    print(f"\n{'='*70}", flush=True)
    print(f"ANALYSIS", flush=True)
    print(f"{'='*70}\n", flush=True)
    
    if best_window:
        results = all_results[best_window]
        bl_policy = results['baseline_policy']
        print(f"[BEST] Optimal window: {best_window} games", flush=True)
        print(f"  ROI: {bl_policy['roi']:.2f}%", flush=True)
        print(f"  Hit Rate: {bl_policy['hit_rate']:.1f}%", flush=True)
        print(f"  Sample: {bl_policy['bets']} bets, gap>={int(bl_policy['threshold'])}", flush=True)

    # Trend analysis
    print(f"\nROI Trend by window size:")
    roi_trend = []
    for window in sorted(all_results.keys()):
        bl_policy = all_results[window].get('baseline_policy')
        if bl_policy:
            roi_trend.append((window, bl_policy['roi']))
    
    if len(roi_trend) >= 2:
        for i in range(len(roi_trend)):
            window, roi = roi_trend[i]
            if i > 0:
                prev_roi = roi_trend[i-1][1]
                delta = roi - prev_roi
                trend = "[UP]" if delta > 0 else "[DOWN]" if delta < 0 else "[FLAT]"
                print(f"  {window} games: {roi:+7.2f}%  {trend} ({delta:+.2f}%)", flush=True)
            else:
                print(f"  {window} games: {roi:+7.2f}%", flush=True)

    # Check for overfitting/diminishing returns
    print(f"\nInterpretation:")
    if roi_trend:
        max_roi_window = max(roi_trend, key=lambda x: x[1])
        print(f"  Peak ROI at window={max_roi_window[0]} games ({max_roi_window[1]:.2f}%)", flush=True)
        
        # Check if adding more games hurts
        diminishing = False
        for i in range(1, len(roi_trend)):
            if roi_trend[i][1] < roi_trend[i-1][1]:
                diminishing = True
                break
        
        if diminishing:
            print(f"  [WARN] Adding more games begins to hurt performance (signal dilution detected)", flush=True)
        else:
            print(f"  [OK] Performance improves or stays stable with more games", flush=True)

    print()

def main():
    print (f"\n{'='*70}", flush=True)
    print(f"LOOKBACK WINDOW OPTIMIZATION", flush=True)
    print(f"Testing windows: {WINDOWS}", flush=True)
    print(f"{'='*70}\n", flush=True)

    # Step 1: Create baseline variants
    print("Step 1: Creating baseline variants...\n", flush=True)
    if not create_baseline_variants():
        print("Failed to create baseline variants")
        return

    # Step 2: Run evaluator for each window
    print(f"\nStep 2: Running evaluations...\n", flush=True)
    for i, window in enumerate(WINDOWS, 1):
        print(f"[{i}/{len(WINDOWS)}] Window {window}...", flush=True)
        if not run_window_evaluator(window):
            print(f"[WARN] Evaluator returned error for window {window}", flush=True)

    # Step 3: Print comparison
    print_comparison()

    print(f"[OK] Test complete! See logs/window_test_results_*.json for details.", flush=True)

if __name__ == '__main__':
    main()
