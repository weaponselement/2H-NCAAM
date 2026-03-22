from openpyxl import load_workbook
from pathlib import Path
import statistics
from datetime import datetime
from sklearn.ensemble import RandomForestRegressor
import pickle
import json

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

# Load models
models_dir = Path('models')
models = {}
for target in ['ActualMargin', 'Actual2H', 'ActualTotal']:
    model_path = models_dir / f'{target.lower()}_model.pkl'
    if model_path.exists():
        with open(model_path, 'rb') as f:
            models[target] = pickle.load(f)
    else:
        print(f"Model {model_path} not found")
        models[target] = None

# Load workbook
path = Path('logs/NCAAM Results.xlsx')
if not path.exists():
    raise FileNotFoundError(path)

wb = load_workbook(path)
ws = wb['Game_Log']

# Load team stats for all dates
rows = list(ws.iter_rows(values_only=True))
headers = [str(c) if c is not None else '' for c in rows[0]]
data_indices = {h: i for i, h in enumerate(headers)}

team_stats_cache = {}
for row in rows[1:]:
    date = row[data_indices.get('Date')]
    if date:
        date_str = str(date).split(' ')[0]  # assume YYYY-MM-DD
        if date_str not in team_stats_cache:
            team_stats_cache[date_str] = load_team_stats(date_str)

# Update predictions
updated = 0
for i, row in enumerate(rows[1:], start=2):  # start=2 for 1-based row
    date = row[data_indices.get('Date')]
    halftime_score = row[data_indices.get('HalftimeScore')]
    pace = row[data_indices.get('PaceProfile')]
    home_team = row[data_indices.get('Home')]
    away_team = row[data_indices.get('Away')]

    if not halftime_score or not date or not home_team or not away_team:
        continue

    # Parse halftime lead
    if '-' not in str(halftime_score):
        continue
    parts = str(halftime_score).split('-')
    try:
        away_ht = float(parts[0])
        home_ht = float(parts[1])
        home_lead = home_ht - away_ht
    except:
        continue

    # Pace
    pace_run_and_gun = 1 if str(pace).lower() == 'run_and_gun' else 0

    # Date days
    try:
        d = datetime.strptime(str(date).split(' ')[0], '%Y-%m-%d')
        start = datetime(2026, 1, 1)
        date_days = (d - start).days
    except:
        date_days = 0

    # Team stats
    date_str = str(date).split(' ')[0]
    stats = team_stats_cache.get(date_str, {})
    home_stats = stats.get(home_team, {})
    away_stats = stats.get(away_team, {})
    home_avg_scored = home_stats.get('avg_scored', 70)
    home_avg_allowed = home_stats.get('avg_allowed', 70)
    away_avg_scored = away_stats.get('avg_scored', 70)
    away_avg_allowed = away_stats.get('avg_allowed', 70)

    features = [home_lead, pace_run_and_gun, date_days, home_avg_scored, home_avg_allowed, away_avg_scored, away_avg_allowed]

    # Predict
    pred_margin = models['ActualMargin'].predict([features])[0] if models['ActualMargin'] else None
    pred_2h = models['Actual2H'].predict([features])[0] if models['Actual2H'] else None
    pred_total = models['ActualTotal'].predict([features])[0] if models['ActualTotal'] else None

    if pred_margin is None:
        continue

    # Update winner
    winner = home_team if pred_margin > 0 else away_team
    ws[f"G{i}"] = winner

    # Margin range
    abs_margin = abs(pred_margin)
    if abs_margin >= 8:
        margin_range = "6-11"
        confidence = "MEDIUM-HIGH"
    elif abs_margin >= 5:
        margin_range = "3-8"
        confidence = "MEDIUM"
    else:
        margin_range = "1-5"
        confidence = "LOW-MEDIUM"
    ws[f"H{i}"] = margin_range
    ws[f"K{i}"] = confidence

    # 2H range
    if pred_2h is not None:
        range_half_width = 5
        low = pred_2h - range_half_width
        high = pred_2h + range_half_width
        ws[f"I{i}"] = f"{low:.1f}-{high:.1f}"

    # Total range
    if pred_total is not None:
        range_half_width = 6  # slightly wider for totals
        low = pred_total - range_half_width
        high = pred_total + range_half_width
        ws[f"J{i}"] = f"{low:.1f}-{high:.1f}"

    updated += 1
    if updated % 100 == 0:
        print(f"Updated {updated} rows")

wb.save(path)
print(f"Updated {updated} predictions in workbook")