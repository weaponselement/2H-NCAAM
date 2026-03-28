#!/usr/bin/env python3
"""
Master script to test lookback window optimization (4-8 games).
Runs baseline generation and evaluation for each window, then compares results.
"""

import sys
import json
import subprocess
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = Path(__file__).resolve().parent.parent / 'data'
LOGS_DIR = Path(__file__).resolve().parent.parent / 'logs'
SELECTED_GAMES_PATH = LOGS_DIR / 'selected_games_2026-03-27.json'

WINDOWS = [4, 5, 6, 7, 8]

def run_baseline_generation(window: int):
    """Generate baseline with specified window size."""
    print(f"\n{'─'*70}", flush=True)
    print(f"Generating baselines for window={window} games", flush=True)
    print(f"{'─'*70}", flush=True)
    
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / 'step2b_last4_from_scoreboard_v2.py'),
        '--selected-games', str(SELECTED_GAMES_PATH),
        '--data-root', str(DATA_ROOT),
        '--games-per-team', str(window),
        '--max-days-back', '90',
    ]
    
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode == 0

def run_evaluator(window: int):
    """Run window optimization evaluator."""
    print(f"\n{'─'*70}", flush=True)
    print(f"Running evaluator for window={window} games", flush=True)
    print(f"{'─'*70}", flush=True)
    
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / 'evaluate_window_optimization_v1.py'),
        '--window', str(window),
        '--odds', '-110',
        '--min-bets', '20',
        '--full-gap', '10',
        '--half-gap', '6',
    ]
    
    result = subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    return result.returncode == 0

def load_results(window: int) -> dict:
    """Load JSON results for a window."""
    path = LOGS_DIR / f'window_test_results_{window}.json'
    if path.exists():
        with open(path, 'r') as f:
            return json.load(f)
    return {}

def print_comparison():
    """Load and print comparison across all windows."""
    print(f"\n{'='*70}", flush=True)
    print(f"WINDOW OPTIMIZATION RESULTS COMPARISON", flush=True)
    print(f"{'='*70}\n", flush=True)
    
    all_results = {}
    for window in WINDOWS:
        results = load_results(window)
        if results:
            all_results[window] = results

    if not all_results:
        print("No results found.", flush=True)
        return

    # Print MAE comparison
    print(f"{'WINDOW':<8} {'BASELINE_MAE':<15} {'RF_MAE':<15} {'DELTA':<10}", flush=True)
    print(f"{'-'*50}", flush=True)
    for window in sorted(all_results.keys()):
        metrics = all_results[window]['metrics']
        mae_bl = metrics['mae_baseline']
        mae_rf = metrics['mae_rf']
        delta = mae_rf - mae_bl
        print(f"{window:<8} {mae_bl:<15.3f} {mae_rf:<15.3f} {delta:+.3f}", flush=True)

    # Print best policy ROI comparison
    print(f"\n{'WINDOW':<8} {'BASELINE_ROI%':<15} {'RF_ROI%':<15} {'BASELINE_BETS':<15}", flush=True)
    print(f"{'-'*55}", flush=True)
    for window in sorted(all_results.keys()):
        bl_policy = all_results[window].get('baseline_policy')
        rf_policy = all_results[window].get('rf_policy')
        bl_roi = bl_policy['roi'] if bl_policy else 0
        rf_roi = rf_policy['roi'] if rf_policy else 0
        bl_bets = bl_policy['bets'] if bl_policy else 0
        print(f"{window:<8} {bl_roi:<15.2f} {rf_roi:<15.2f} {bl_bets:<15}", flush=True)

    # Print top features for each window
    print(f"\n{'='*70}", flush=True)
    print(f"TOP FEATURES BY WINDOW", flush=True)
    print(f"{'='*70}\n", flush=True)
    for window in sorted(all_results.keys()):
        features = all_results[window]['top_10_features']
        print(f"Window {window} (top 3 features):", flush=True)
        for i, (name, importance) in enumerate(list(sorted(features.items(), key=lambda x: x[1], reverse=True))[:3], 1):
            print(f"  {i}. {name}: {importance:.4f}", flush=True)
        print()

    # Identify best window
    print(f"\n{'='*70}", flush=True)
    print(f"ANALYSIS & RECOMMENDATIONS", flush=True)
    print(f"{'='*70}\n", flush=True)
    
    best_window = None
    best_roi = -float('inf')
    for window in sorted(all_results.keys()):
        bl_policy = all_results[window].get('baseline_policy')
        if bl_policy and bl_policy['roi'] > best_roi:
            best_roi = bl_policy['roi']
            best_window = window

    if best_window:
        print(f"✓ Best window by baseline ROI: {best_window} games ({best_roi:.2f}% ROI)", flush=True)
        results = all_results[best_window]
        bl_policy = results['baseline_policy']
        print(f"  Performance: {bl_policy['bets']} bets, {bl_policy['hit_rate']:.1f}% hit, +{bl_policy['units']:.2f}u", flush=True)

    # Check for diminishing returns or overfitting
    print(f"\nROI Trend:", flush=True)
    for window in sorted(all_results.keys()):
        bl_policy = all_results[window].get('baseline_policy')
        if bl_policy:
            roi = bl_policy['roi']
            print(f"  {window} games: {roi:+7.2f}%", flush=True)

    print()

def main():
    print(f"\n{'='*70}", flush=True)
    print(f"LOOKBACK WINDOW OPTIMIZATION TEST", flush=True)
    print(f"Testing: {WINDOWS}", flush=True)
    print(f"Start time: {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"{'='*70}\n", flush=True)

    # For each window, generate baseline and evaluate
    for i, window in enumerate(WINDOWS, 1):
        print(f"\n[{i}/{len(WINDOWS)}] Testing window={window}", flush=True)

        # Generate baselines
        if not run_baseline_generation(window):
            print(f"✗ Failed baseline generation for window {window}", flush=True)
            continue

        # Run evaluator
        if not run_evaluator(window):
            print(f"✗ Failed evaluator for window {window}", flush=True)
            continue

        print(f"✓ Completed window {window}", flush=True)
        time.sleep(2)  # Brief pause between windows

    # Print comparison
    print_comparison()

    print(f"\n{'='*70}", flush=True)
    print(f"Test complete! Results saved to logs/window_test_results_*.json", flush=True)
    print(f"{'='*70}\n", flush=True)

if __name__ == '__main__':
    main()
