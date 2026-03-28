#!/usr/bin/env python3
"""
Test script to find the optimal historical game lookback window.
Tests last 4, 5, 6, 7, 8 games per team.
"""

import sys
import json
import subprocess
import os
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parent.parent / 'data'
BASELINES_DIR = DATA_ROOT / 'processed' / 'baselines'
LOGS_DIR = Path(__file__).resolve().parent.parent / 'logs'

WINDOWS = [4, 5, 6, 7, 8]
RESULTS_SUMMARY = {}


def run_step2b_for_window(games_per_team: int, run_date: str = None):
    """Generate last-n baseline for a given window size."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / 'step2b_last4_from_scoreboard_v2.py'),
        '--data-root', str(DATA_ROOT),
        '--games-per-team', str(games_per_team),
    ]
    if run_date:
        cmd.extend(['--run-date', run_date])
    
    print(f"\n{'='*70}")
    print(f"Generating baselines for last {games_per_team} games per team...")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent))
    return result.returncode == 0


def load_evaluator_results(window: int) -> dict:
    """Load the JSON results from the last evaluator run (if they exist)."""
    results_path = LOGS_DIR / f'pregame_eval_results_last{window}.json'
    if results_path.exists():
        try:
            with open(results_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Failed to load results for window {window}: {e}")
    return {}


def run_evaluator_for_window(window: int):
    """Run the pregame evaluator after generating baselines."""
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / 'evaluate_pregame_total_model_v1.py'),
        '--odds', '-110',
        '--min-bets', '20',
        '--full-gap', '10',
        '--half-gap', '6',
        '--lookback-window', str(window),  # Pass window info to evaluator
    ]
    
    print(f"\n{'='*70}")
    print(f"Running evaluator for last {window} games window...")
    print(f"{'='*70}")
    
    result = subprocess.run(cmd, cwd=str(Path(__file__).resolve().parent))
    return result.returncode == 0


def extract_key_metrics(window: int) -> dict:
    """Parse evaluator output to extract key metrics."""
    # For now, return a placeholder - we'll enhance evaluator to output JSON
    return {
        'window': window,
        'status': 'pending'
    }


def main():
    print(f"\n{chr(27)}[1;36m{'='*70}")
    print(f"LOOKBACK WINDOW OPTIMIZATION TEST")
    print(f"Testing historical game windows: {WINDOWS}")
    print(f"{'='*70}{chr(27)}[0m\n")
    
    for window in WINDOWS:
        print(f"\n{chr(27)}[1;33m>>> WINDOW SIZE: {window} games{chr(27)}[0m")
        
        # Step 1: Generate baselines
        if not run_step2b_for_window(window):
            print(f"Failed to generate baselines for window {window}")
            continue
        
        # Step 2: Run evaluator
        if not run_evaluator_for_window(window):
            print(f"Failed to run evaluator for window {window}")
            continue
        
        # Step 3: Extract results
        metrics = extract_key_metrics(window)
        RESULTS_SUMMARY[window] = metrics
        
        print(f"✓ Completed window {window}")
    
    # Summary
    print(f"\n{chr(27)}[1;36m{'='*70}")
    print(f"RESULTS SUMMARY")
    print(f"{'='*70}{chr(27)}[0m]\n")
    
    for window in WINDOWS:
        if window in RESULTS_SUMMARY:
            metrics = RESULTS_SUMMARY[window]
            print(f"Window {window}: {json.dumps(metrics, indent=2)}")
    
    print(f"\n{chr(27)}[1;32mAnalysis complete.{chr(27)}[0m]\n")


if __name__ == '__main__':
    main()
