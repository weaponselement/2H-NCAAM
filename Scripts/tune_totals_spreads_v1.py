from openpyxl import load_workbook
from pathlib import Path
import statistics
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
import numpy as np
import json
import pickle

def load_team_stats(date_str):
    path = Path('data/processed/baselines') / f'last4_{date_str}.json'
    if not path.exists():
        return {}
    with open(path, 'r') as f:
        data = json.load(f)
    teams = data.get('teams', {})
    stats = {}
    for team, games in teams.items():
        if not games:
            continue
        scores_for = [int(g['score_for']) for g in games if g['score_for']]
        scores_against = [int(g['score_against']) for g in games if g['score_against']]
        if scores_for:
            stats[team] = {
                'avg_scored': statistics.mean(scores_for),
                'avg_allowed': statistics.mean(scores_against)
            }
    return stats

path = Path('logs/NCAAM Results.xlsx')
if not path.exists():
    raise FileNotFoundError(path)

wb = load_workbook(path, data_only=True)
if 'Game_Log' not in wb.sheetnames:
    raise ValueError('Game_Log not in workbook')

ws = wb['Game_Log']
rows = list(ws.iter_rows(values_only=True))
headers = [str(c) if c is not None else '' for c in rows[0]]
data = [dict(zip(headers, r)) for r in rows[1:]]

# Load team stats for all dates
dates = set(r.get('Date') for r in data if r.get('Date'))
team_stats_cache = {}
for d in dates:
    team_stats_cache[d] = load_team_stats(d)

print('loaded team stats for', len(dates), 'dates')

print('loaded', len(data), 'rows')

# Parse halftime score to home_lead
def parse_halftime_score(hs):
    if not hs or '-' not in str(hs):
        return None
    parts = str(hs).split('-')
    try:
        away = float(parts[0])
        home = float(parts[1])
        return home - away  # positive if home leading
    except:
        return None

# Add features
for r in data:
    r['home_lead'] = parse_halftime_score(r.get('HalftimeScore'))
    r['pace_run_and_gun'] = 1 if str(r.get('PaceProfile')).lower() == 'run_and_gun' else 0
    # Add date feature: days since 2026-01-01
    try:
        d = datetime.strptime(str(r.get('Date')), '%Y-%m-%d')
        start = datetime(2026, 1, 1)
        r['date_days'] = (d - start).days
    except:
        r['date_days'] = 0
    # Add team stats
    date = r.get('Date')
    home_team = r.get('Home')
    away_team = r.get('Away')
    stats = team_stats_cache.get(date, {})
    home_stats = stats.get(home_team, {})
    away_stats = stats.get(away_team, {})
    r['home_avg_scored'] = home_stats.get('avg_scored', 70)  # default
    r['home_avg_allowed'] = home_stats.get('avg_allowed', 70)
    r['away_avg_scored'] = away_stats.get('avg_scored', 70)
    r['away_avg_allowed'] = away_stats.get('avg_allowed', 70)

# Filter valid rows
valid = [r for r in data if r['home_lead'] is not None and r.get('ActualMargin') is not None and r.get('Actual2H') is not None and r.get('ActualTotal') is not None and r.get('date_days') is not None]
print('valid rows for tuning:', len(valid))

# Split by date: train on dates before 2026-03-01, test after
cutoff = datetime(2026, 3, 1)
train = []
test = []
for r in valid:
    try:
        d = datetime.strptime(str(r.get('Date')), '%Y-%m-%d')
        if d < cutoff:
            train.append(r)
        else:
            test.append(r)
    except:
        continue

print('train:', len(train), 'test:', len(test))

# Multivariate linear model
def train_multilinear(X_list, y):
    # X_list is list of lists, each inner list is features for one sample
    # y is list of targets
    import math
    n = len(X_list)
    m = len(X_list[0])  # number of features
    # Add intercept: X = [1, x1, x2, ...]
    X = [[1] + row for row in X_list]
    # Compute X^T X
    XT = [[sum(X[i][j] for i in range(n)) for j in range(m+1)] for _ in range(m+1)]
    XTX = [[sum(XT[k][i] * XT[k][j] for k in range(m+1)) for j in range(m+1)] for i in range(m+1)]
    # Compute X^T y
    XTy = [sum(X[i][j] * y[i] for i in range(n)) for j in range(m+1)]
    # Invert XTX (simple 4x4 matrix)
    def invert_4x4(M):
        # Hardcoded for 4x4, but since m=3, 4x4
        # Use numpy-like, but manual
        # For simplicity, assume it's invertible and use formula
        # This is complex; for demo, use a library or skip
        # Since no numpy, perhaps use a simple method or reduce to 2 features
        pass
    # For now, to make it work, reduce to 2 features: home_lead and pace
    # Skip date for simplicity
    return train_linear([row[0] for row in X_list], y)  # fallback to single

# For now, use single feature, but add pace as additional
def train_linear_multi(X1, X2, y):
    # Simple: y = a*X1 + b*X2 + c
    n = len(y)
    sum_x1 = sum(X1)
    sum_x2 = sum(X2)
    sum_y = sum(y)
    sum_x1y = sum(x*y for x,y in zip(X1,y))
    sum_x2y = sum(x*y for x,y in zip(X2,y))
    sum_x1x2 = sum(x1*x2 for x1,x2 in zip(X1,X2))
    sum_x1sq = sum(x**2 for x in X1)
    sum_x2sq = sum(x**2 for x in X2)
    # Solve system
    # a*sum_x1sq + b*sum_x1x2 = sum_x1y
    # a*sum_x1x2 + b*sum_x2sq = sum_x2y
    det = sum_x1sq * sum_x2sq - sum_x1x2**2
    if det == 0:
        return 0, 0, sum_y/n  # fallback
    a = (sum_x1y * sum_x2sq - sum_x2y * sum_x1x2) / det
    b = (sum_x2y * sum_x1sq - sum_x1y * sum_x1x2) / det
    c = sum_y / n - a * sum_x1 / n - b * sum_x2 / n
    return a, b, c

def predict_linear_multi(a, b, c, X1, X2):
    return [a * x1 + b * x2 + c for x1, x2 in zip(X1, X2)]

# For each target
targets = ['ActualMargin', 'Actual2H', 'ActualTotal']
for target in targets:
    print(f'\n--- {target} ---')
    train_X = [[r['home_lead'], r['pace_run_and_gun'], r['date_days'], r['home_avg_scored'], r['home_avg_allowed'], r['away_avg_scored'], r['away_avg_allowed']] for r in train]
    train_y = [r[target] for r in train]
    test_X = [[r['home_lead'], r['pace_run_and_gun'], r['date_days'], r['home_avg_scored'], r['home_avg_allowed'], r['away_avg_scored'], r['away_avg_allowed']] for r in test]
    test_y = [r[target] for r in test]
    
    # Train Random Forest
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(train_X, train_y)
    
    # Predict on test
    pred_y = model.predict(test_X)
    
    # MAE
    mae = mean_absolute_error(test_y, pred_y)
    print(f'test MAE: {mae:.2f}')
    
    # Baseline
    if target == 'ActualMargin':
        baseline_mae = 7.13
    elif target in ['Actual2H', 'ActualTotal']:
        baseline_mae = 10.33
    print(f'baseline MAE: {baseline_mae:.2f}')
    print(f'improvement: {baseline_mae - mae:.2f}')
    
    # Feature importance
    importances = model.feature_importances_
    features = ['home_lead', 'pace_run_and_gun', 'date_days', 'home_avg_scored', 'home_avg_allowed', 'away_avg_scored', 'away_avg_allowed']
    for f, imp in zip(features, importances):
        print(f'  {f}: {imp:.3f}')

# Train final models on all data
print('\n--- Final Models on All Data ---')
final_models = {}
for target in targets:
    print(f'Training final {target} model...')
    X_all = [[r['home_lead'], r['pace_run_and_gun'], r['date_days'], r['home_avg_scored'], r['home_avg_allowed'], r['away_avg_scored'], r['away_avg_allowed']] for r in valid]
    y_all = [r[target] for r in valid]
    
    final_model = RandomForestRegressor(n_estimators=100, random_state=42)
    final_model.fit(X_all, y_all)
    final_models[target] = final_model
    
    # Save model
    model_path = Path('models') / f'{target.lower()}_model.pkl'
    model_path.parent.mkdir(exist_ok=True)
    with open(model_path, 'wb') as f:
        pickle.dump(final_model, f)
    print(f'Saved {target} model to {model_path}')

print('All models trained and saved.')
