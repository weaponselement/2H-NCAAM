#!/usr/bin/env python3
"""
Audit Covers -> workbook match quality over recent workbook dates.

Purpose:
- Quantify coverage and match methods without writing canonical lines.
- Rank unmatched pairs and surface likely slug-mapping gaps.
- Provide a reproducible report for maintenance (next-season restart safety).

Usage:
  python Scripts/audit_covers_matching_v1.py --recent-dates 21
  python Scripts/audit_covers_matching_v1.py --recent-dates 30 --out data/logs/covers_slug_audit_recent30.json
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import importlib.util as _ilu

PROJECT_ROOT = Path(__file__).resolve().parent.parent
COVERS_SCRIPT = PROJECT_ROOT / "Scripts" / "ncaab_historical_lines_covers_v1.py"


def _slug_similarity(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    ap, bp = set(a.split("-")), set(b.split("-"))
    union = len(ap | bp)
    return (len(ap & bp) / union) if union else 0.0


def load_covers_module():
    spec = _ilu.spec_from_file_location("covers", COVERS_SCRIPT)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def classify_root_cause(mod, date, away_raw, home_raw, team_lookup, all_team_pairs, all_team_seos):
    away = mod.slug_from_covers(away_raw)
    home = mod.slug_from_covers(home_raw)

    if (date, away, home) in team_lookup:
        return "unmatched-despite-exact-key"
    if (date, home, away) in team_lookup:
        return "home-away-reversed-on-date"

    if (away, home) in all_team_pairs:
        return "pair-exists-other-date"
    if (home, away) in all_team_pairs:
        return "pair-exists-other-date-reversed"

    away_exists = away in all_team_seos
    home_exists = home in all_team_seos
    if away_exists and home_exists:
        return "both-teams-exist-no-pair"
    if away_exists or home_exists:
        return "one-team-missing-or-remapped"
    return "both-teams-missing"


def main():
    parser = argparse.ArgumentParser(description="Audit Covers->workbook match quality")
    parser.add_argument("--recent-dates", type=int, default=21, help="Number of latest workbook dates to audit")
    parser.add_argument(
        "--out",
        default="data/logs/covers_slug_audit_recent.json",
        help="Output JSON path relative to repo root",
    )
    args = parser.parse_args()

    mod = load_covers_module()

    wb_games = mod.load_workbook_games()
    score_lookup = mod.build_score_lookup(wb_games)
    team_lookup = mod.build_team_lookup(wb_games)

    wb_games_by_date = {}
    for g in wb_games:
        wb_games_by_date.setdefault(g["date"], []).append(g)

    all_dates = sorted(wb_games_by_date.keys())
    recent_dates = all_dates[-args.recent_dates :] if len(all_dates) > args.recent_dates else all_dates

    all_team_pairs = {(g["away_seo"], g["home_seo"]) for g in wb_games}
    all_team_seos = sorted({g["away_seo"] for g in wb_games} | {g["home_seo"] for g in wb_games})

    method_counts = Counter()
    root_cause_counts = Counter()
    unmatched_pairs = Counter()
    missing_mapped_slug_counts = Counter()
    raw_by_missing_mapped_slug = defaultdict(Counter)
    per_date = []

    for date in recent_dates:
        games = mod.scrape_date(date)
        matched = 0

        for cg in games:
            gid, method = mod.match_game(cg, date, score_lookup, team_lookup, wb_games_by_date)
            if gid:
                matched += 1
                method_counts[method] += 1
                continue

            away_raw = cg.get("away_slug", "")
            home_raw = cg.get("home_slug", "")
            unmatched_pairs[(away_raw, home_raw)] += 1

            cause = classify_root_cause(
                mod,
                date,
                away_raw,
                home_raw,
                team_lookup,
                all_team_pairs,
                set(all_team_seos),
            )
            root_cause_counts[cause] += 1

            for raw in (away_raw, home_raw):
                mapped = mod.slug_from_covers(raw)
                if mapped not in all_team_seos:
                    missing_mapped_slug_counts[mapped] += 1
                    raw_by_missing_mapped_slug[mapped][raw] += 1

        per_date.append(
            {
                "date": date,
                "scraped": len(games),
                "matched": matched,
                "unmatched": len(games) - matched,
            }
        )

    def top_candidates(mapped_slug: str, n: int = 5):
        scored = [(_slug_similarity(mapped_slug, t), t) for t in all_team_seos]
        scored.sort(reverse=True)
        return scored[:n]

    top_unmatched = []
    for (away_raw, home_raw), count in unmatched_pairs.most_common(80):
        away_mapped = mod.slug_from_covers(away_raw)
        home_mapped = mod.slug_from_covers(home_raw)
        top_unmatched.append(
            {
                "count": count,
                "away_raw": away_raw,
                "home_raw": home_raw,
                "away_mapped": away_mapped,
                "home_mapped": home_mapped,
                "away_best": top_candidates(away_mapped, 5),
                "home_best": top_candidates(home_mapped, 5),
            }
        )

    top_missing_slugs = []
    for mapped, count in missing_mapped_slug_counts.most_common(80):
        top_missing_slugs.append(
            {
                "count": count,
                "mapped_slug": mapped,
                "raw_examples": raw_by_missing_mapped_slug[mapped].most_common(5),
                "best_candidates": top_candidates(mapped, 5),
            }
        )

    total_scraped = sum(x["scraped"] for x in per_date)
    total_matched = sum(x["matched"] for x in per_date)
    coverage_pct = (100.0 * total_matched / total_scraped) if total_scraped else 0.0

    out = {
        "recent_dates": recent_dates,
        "summary": {
            "total_scraped": total_scraped,
            "total_matched": total_matched,
            "coverage_pct": round(coverage_pct, 2),
        },
        "per_date": per_date,
        "method_counts": dict(method_counts),
        "root_cause_counts": dict(root_cause_counts),
        "top_unmatched": top_unmatched,
        "top_missing_mapped_slugs": top_missing_slugs,
    }

    out_path = PROJECT_ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(
        f"dates={len(recent_dates)} scraped={total_scraped} "
        f"matched={total_matched} coverage={coverage_pct:.1f}%"
    )
    print(f"report={out_path}")
    print("root_causes:")
    for k, v in Counter(root_cause_counts).most_common():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
