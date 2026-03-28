#!/usr/bin/env python3
"""
Predict pregame totals for specific games using the Window-N RF model.

Key behavior:
- Trains a RF model from historical workbook rows only when source data changed.
- Caches model + feature names + metadata under models/pregame_total_cache/.
- Reuses cache for fast repeat predictions.

Examples:
  python Scripts/predict_pregame_totals_cached_v1.py \
    --window 5 \
    --game "michigan-st,uconn,136.5,Michigan State vs UConn,7:45 PM CST" \
    --game "tennessee,iowa-st,139.5,Tennessee vs Iowa State,9:25 PM CST"

  python Scripts/predict_pregame_totals_cached_v1.py --window 5 --force-retrain --game "michigan-st,uconn,136.5"
"""

import argparse
import hashlib
import json
import pickle
import time
from pathlib import Path

import importlib.util as _ilu
import sys

from sklearn.ensemble import RandomForestRegressor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "Scripts"

sys.path.insert(0, str(SCRIPTS_DIR))

# Reuse tested loading/feature helpers from existing deep-dive script.
_spec = _ilu.spec_from_file_location(
    "deep", SCRIPTS_DIR / "analyze_pregame_model_depth_v1.py"
)
deep = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(deep)

import model_feature_utils as mfu

CACHE_DIR = PROJECT_ROOT / "models" / "pregame_total_cache"
SCRIPT_VERSION = "2026-03-27-v1"


def parse_game_arg(raw):
    """Parse --game: home,away,line[,label[,tipoff]]."""
    parts = [p.strip() for p in str(raw).split(",")]
    if len(parts) < 3:
        raise ValueError(
            f"Invalid --game '{raw}'. Expected at least home,away,line"
        )
    home = parts[0]
    away = parts[1]
    try:
        line = float(parts[2])
    except Exception as exc:
        raise ValueError(f"Invalid line in --game '{raw}'") from exc
    label = parts[3] if len(parts) >= 4 and parts[3] else f"{away} @ {home}"
    tipoff = parts[4] if len(parts) >= 5 and parts[4] else ""
    return {
        "home": home,
        "away": away,
        "line": line,
        "label": label,
        "tipoff": tipoff,
    }


def fingerprint_for_window(window):
    """Build a stable fingerprint from key source files/inputs."""
    workbook = PROJECT_ROOT / "logs" / "NCAAM Results.xlsx"
    lines_csv = PROJECT_ROOT / "data" / "processed" / "market_lines" / "canonical_lines.csv"
    baselines_dir = PROJECT_ROOT / "data" / "processed" / "baselines"

    parts = {
        "script_version": SCRIPT_VERSION,
        "window": int(window),
        "workbook_mtime": workbook.stat().st_mtime if workbook.exists() else None,
        "workbook_size": workbook.stat().st_size if workbook.exists() else None,
        "lines_mtime": lines_csv.stat().st_mtime if lines_csv.exists() else None,
        "lines_size": lines_csv.stat().st_size if lines_csv.exists() else None,
    }

    baseline_files = sorted(
        baselines_dir.glob(f"lastN_{window}_*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    parts["baseline_count"] = len(baseline_files)
    if baseline_files:
        latest = baseline_files[0]
        parts["latest_baseline_name"] = latest.name
        parts["latest_baseline_mtime"] = latest.stat().st_mtime
        parts["latest_baseline_size"] = latest.stat().st_size

    payload = json.dumps(parts, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return digest, parts


def cache_paths(window):
    model_path = CACHE_DIR / f"pregame_total_rf_w{window}.pkl"
    meta_path = CACHE_DIR / f"pregame_total_rf_w{window}.meta.json"
    return model_path, meta_path


def load_cached(window, fingerprint):
    model_path, meta_path = cache_paths(window)
    if not model_path.exists() or not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("fingerprint") != fingerprint:
            return None
        with open(model_path, "rb") as f:
            payload = pickle.load(f)
        model = payload.get("model")
        feature_names = payload.get("feature_names")
        if model is None or not feature_names:
            return None
        return {
            "model": model,
            "feature_names": feature_names,
            "meta": meta,
        }
    except Exception:
        return None


def save_cached(window, fingerprint, fingerprint_parts, model, feature_names, train_rows):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    model_path, meta_path = cache_paths(window)
    with open(model_path, "wb") as f:
        pickle.dump({"model": model, "feature_names": feature_names}, f)
    meta = {
        "fingerprint": fingerprint,
        "fingerprint_parts": fingerprint_parts,
        "train_rows": int(train_rows),
        "window": int(window),
        "saved_epoch": time.time(),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def train_model(window):
    t0 = time.time()
    workbook_rows = deep.build_rows()
    lines = deep.load_lines()

    unique_dates = sorted(
        {
            str(r.get("Date") or "").split(" ")[0].strip()
            for r in workbook_rows
            if r.get("Date") not in (None, "")
        }
    )

    team_stats_by_date = {
        d: deep.load_team_stats_for_window(d, window)
        for d in unique_dates
    }
    priors_by_date = {
        d: deep.load_priors_for_window(d, window)
        for d in unique_dates
    }

    feature_rows = []
    for record in workbook_rows:
        built = deep.build_feature_row(record, team_stats_by_date, priors_by_date)
        if built is None:
            continue
        built["closing_total"] = lines.get(built["game_id"])
        feature_rows.append(built)

    if not feature_rows:
        raise RuntimeError("No feature rows built from workbook")

    feature_names = list(feature_rows[0]["features"].keys())
    X = [[r["features"][n] for n in feature_names] for r in feature_rows]
    y = [r["actual_total"] for r in feature_rows]

    model = RandomForestRegressor(
        n_estimators=400,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)

    elapsed = time.time() - t0
    return model, feature_names, len(feature_rows), elapsed


def latest_baseline_date_for_team(window, team_seo):
    """Find newest baseline date where team exists."""
    baselines_dir = PROJECT_ROOT / "data" / "processed" / "baselines"
    files = sorted(
        baselines_dir.glob(f"lastN_{window}_*.json"),
        key=lambda p: p.name,
        reverse=True,
    )
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            teams = d.get("teams", {})
            if team_seo in teams:
                # lastN_W_YYYY-MM-DD.json -> YYYY-MM-DD
                stem = p.stem
                return stem.split("_")[-1]
        except Exception:
            continue
    return None


def build_single_game_features(window, home, away, home_date, away_date):
    # Use date-specific stats/priors for each team, then merge in one feature row.
    stats_h = deep.load_team_stats_for_window(home_date, window)
    stats_a = deep.load_team_stats_for_window(away_date, window)
    pri_h = deep.load_priors_for_window(home_date, window)
    pri_a = deep.load_priors_for_window(away_date, window)

    hs, ha = mfu.resolve_team_stats(stats_h, home)
    as_, aa = mfu.resolve_team_stats(stats_a, away)
    exp = deep.expected_total(hs, ha, as_, aa)

    merged_priors = {}
    merged_priors.update(pri_h)
    merged_priors.update(pri_a)

    hp = deep.get_team_priors(merged_priors, home)
    ap = deep.get_team_priors(merged_priors, away)

    features = {
        "home_avg_scored": hs,
        "home_avg_allowed": ha,
        "away_avg_scored": as_,
        "away_avg_allowed": aa,
        "expected_total": exp,
        "home_offense_diff": hs - aa,
        "away_offense_diff": as_ - ha,
        "blended_possessions_1h": (hp["last4_possessions_per_team_1h"] + ap["last4_possessions_per_team_1h"]) / 2.0,
        "blended_possessions_full": (hp["last4_possessions_per_team_1h"] + ap["last4_possessions_per_team_1h"]),
        "blended_three_rate": (hp["last4_three_rate"] + ap["last4_three_rate"]) / 2.0,
        "blended_paint_share": (hp["last4_paint_share"] + ap["last4_paint_share"]) / 2.0,
        "blended_ft_rate": (hp["last4_ft_rate"] + ap["last4_ft_rate"]) / 2.0,
        "blended_turnover_rate": (hp["last4_turnover_rate"] + ap["last4_turnover_rate"]) / 2.0,
        "blended_orb_rate": (hp["last4_orb_rate"] + ap["last4_orb_rate"]) / 2.0,
        "blended_pbp_coverage": (hp["last4_pbp_coverage_count"] + ap["last4_pbp_coverage_count"]) / 2.0,
        "home_last4_three_rate": hp["last4_three_rate"],
        "away_last4_three_rate": ap["last4_three_rate"],
        "home_last4_ft_rate": hp["last4_ft_rate"],
        "away_last4_ft_rate": ap["last4_ft_rate"],
        "home_last4_turnover_rate": hp["last4_turnover_rate"],
        "away_last4_turnover_rate": ap["last4_turnover_rate"],
        "home_last4_orb_rate": hp["last4_orb_rate"],
        "away_last4_orb_rate": ap["last4_orb_rate"],
        "home_last4_possessions_1h": hp["last4_possessions_per_team_1h"],
        "away_last4_possessions_1h": ap["last4_possessions_per_team_1h"],
        "three_rate_gap": hp["last4_three_rate"] - ap["last4_three_rate"],
        "ft_rate_gap": hp["last4_ft_rate"] - ap["last4_ft_rate"],
        "turnover_rate_gap": hp["last4_turnover_rate"] - ap["last4_turnover_rate"],
        "orb_rate_gap": hp["last4_orb_rate"] - ap["last4_orb_rate"],
    }

    team_avgs = {
        "home_avg_scored": hs,
        "home_avg_allowed": ha,
        "away_avg_scored": as_,
        "away_avg_allowed": aa,
    }
    return features, exp, team_avgs


def classify_gap(abs_gap):
    if abs_gap >= 10:
        return "FULL SEND"
    if abs_gap >= 8:
        return "LEAN (gap 8-9)"
    if abs_gap >= 5:
        return "MONITOR (gap 5-7)"
    return "NO ACTION"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=5)
    parser.add_argument("--game", action="append", required=True,
                        help="home,away,line[,label[,tipoff]]; repeatable")
    parser.add_argument("--force-retrain", action="store_true")
    parser.add_argument("--show-cache-info", action="store_true")
    args = parser.parse_args()

    games = [parse_game_arg(x) for x in args.game]

    print("=" * 68)
    print(f"Pregame Total Predictor (cached RF) | window={args.window}")
    print("=" * 68)

    fp, fp_parts = fingerprint_for_window(args.window)
    cached = None if args.force_retrain else load_cached(args.window, fp)

    if cached is not None:
        model = cached["model"]
        feature_names = cached["feature_names"]
        train_rows = cached["meta"].get("train_rows")
        print("Cache status: HIT (reused existing trained model)")
        print(f"Cache fingerprint: {fp}")
        if args.show_cache_info:
            print(json.dumps(cached["meta"], indent=2))
    else:
        print("Cache status: MISS (training model now)")
        print("Expected training runtime: ~7-10 minutes depending on PBP prior loads")
        model, feature_names, train_rows, elapsed = train_model(args.window)
        save_cached(args.window, fp, fp_parts, model, feature_names, train_rows)
        print(f"Training complete in {elapsed / 60.0:.2f} minutes")
        print(f"Cache fingerprint saved: {fp}")

    print(f"Training rows available: {train_rows}")

    print("\nPredictions")
    print("-" * 68)
    for g in games:
        home = g["home"]
        away = g["away"]
        line = g["line"]
        label = g["label"]
        tipoff = g["tipoff"]

        home_date = latest_baseline_date_for_team(args.window, home)
        away_date = latest_baseline_date_for_team(args.window, away)

        if home_date is None or away_date is None:
            print(f"{label}")
            print("  ERROR: team baseline not found")
            print(f"  home={home} latest_date={home_date} | away={away} latest_date={away_date}")
            print("  Tip: use team SEO keys from workbook (e.g., michigan-st, iowa-st, uconn)")
            print("")
            continue

        features, baseline_total, team_avgs = build_single_game_features(
            args.window, home, away, home_date, away_date
        )
        x = [[features[n] for n in feature_names]]
        pred = float(model.predict(x)[0])

        raw_gap = pred - line
        abs_gap = abs(raw_gap)
        direction = "OVER" if raw_gap > 0 else "UNDER"
        signal = classify_gap(abs_gap)

        print(f"{label}" + (f" ({tipoff})" if tipoff else ""))
        print(f"  baseline_dates: home={home_date}, away={away_date}")
        print(
            "  team_avgs: "
            f"home_scored={team_avgs['home_avg_scored']:.1f}, "
            f"home_allowed={team_avgs['home_avg_allowed']:.1f}, "
            f"away_scored={team_avgs['away_avg_scored']:.1f}, "
            f"away_allowed={team_avgs['away_avg_allowed']:.1f}"
        )
        print(f"  baseline_expected_total: {baseline_total:.1f}")
        print(f"  model_pred_total: {pred:.1f}")
        print(f"  market_line: {line:.1f}")
        print(f"  signed_gap(pred-line): {raw_gap:+.1f} -> {direction}")
        print(f"  abs_gap: {abs_gap:.1f}")
        print(f"  trigger: {signal}")
        if abs_gap >= 8:
            print(f"  action: BET {direction} {line:.1f}")
        print("")


if __name__ == "__main__":
    main()
