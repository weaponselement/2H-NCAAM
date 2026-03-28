import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from zoneinfo import ZoneInfo

from paths import DATA_DIR


SELECTED_GAMES_DIR = DATA_DIR / "processed" / "selected_games"
OUTPUT_DIR = DATA_DIR / "processed" / "market_lines"

ODD_IDS = {
    "spread_home": "points-home-game-sp-home",
    "spread_away": "points-away-game-sp-away",
    "ml_home": "points-home-game-ml-home",
    "ml_away": "points-away-game-ml-away",
    "total_over": "points-all-game-ou-over",
    "total_under": "points-all-game-ou-under",
    "total_2h_over": "points-all-2h-ou-over",
    "total_2h_under": "points-all-2h-ou-under",
}

SGO_TO_SDIO = {
    "brigham-young": "byu",
    "florida-international": "fiu",
    "uic": "ill-chicago",
    "usc": "southern-california",
    "bryant-university": "bryant",
    "tennessee-martin": "ut-martin",
    "louisiana-state": "lsu",
    "north-carolina-state": "nc-state",
    "texas-christian": "tcu",
    "southern-methodist": "smu",
    "central-florida": "ucf",
    "florida-gulf-coast": "fgcu",
    "mississippi": "ole-miss",
    "louisiana-monroe": "la-monroe",
    "omaha": "neb-omaha",
    "florida-atlantic": "fla-atlantic",
    "east-tennessee": "east-tenn-st",
    "southeast-missouri-state": "se-missouri-st",
    "southern-illinois": "southern-ill",
    "middle-tennessee-state": "middle-tenn",
    "miami": "miami-oh",
}

STAGED_FIELDS = [
    "source_file",
    "sgo_event_id",
    "starts_at_utc",
    "local_date",
    "sgo_away_raw",
    "sgo_home_raw",
    "away_seo_candidate",
    "home_seo_candidate",
    "match_status",
    "match_reason",
    "matched_game_id",
    "matched_date",
    "matched_away",
    "matched_home",
    "candidate_count",
    "candidate_game_ids",
    "suggested_game_ids",
    "suggested_away",
    "suggested_home",
    "spread_home",
    "spread_away",
    "ml_home",
    "ml_away",
    "total_game",
    "total_2h",
]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def save_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=STAGED_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = text.replace("'", "")
    text = re.sub(r"_ncaab$", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text


def normalize_sgo_team(raw_name: str) -> str:
    base = slugify(raw_name)
    if base.endswith("-state"):
        base = f"{base[:-6]}-st"
    return SGO_TO_SDIO.get(base, base)


def parse_iso_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def event_local_date(event: dict, timezone_name: str):
    starts_at = extract_start_time(event)
    parsed = parse_iso_datetime(starts_at)
    if parsed is None:
        return ""
    return parsed.astimezone(ZoneInfo(timezone_name)).date().isoformat()


def extract_start_time(event: dict) -> str:
    for key in ["startsAt", "startTime", "commenceTime", "scheduled", "date"]:
        value = event.get(key)
        if value:
            return str(value)
    return ""


def extract_event_id(event: dict) -> str:
    for key in ["eventID", "eventId", "id"]:
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def extract_name_from_object(obj):
    if isinstance(obj, str):
        return obj
    if not isinstance(obj, dict):
        return ""
    for key in ["name", "displayName", "fullName", "shortName", "team", "key"]:
        value = obj.get(key)
        if value:
            return str(value)
    return ""


def extract_team_name(event: dict, side: str) -> str:
    direct = event.get(side)
    name = extract_name_from_object(direct)
    if name:
        return name

    nested = event.get("teams")
    if isinstance(nested, dict):
        name = extract_name_from_object(nested.get(side))
        if name:
            return name

    side_key = f"{side}Team"
    name = extract_name_from_object(event.get(side_key))
    if name:
        return name

    participants = event.get("participants")
    if isinstance(participants, list):
        for participant in participants:
            if not isinstance(participant, dict):
                continue
            role = str(participant.get("side") or participant.get("designation") or "").lower()
            if role == side:
                name = extract_name_from_object(participant)
                if name:
                    return name
            if side == "home" and participant.get("isHome") is True:
                name = extract_name_from_object(participant)
                if name:
                    return name
            if side == "away" and participant.get("isHome") is False:
                name = extract_name_from_object(participant)
                if name:
                    return name
    return ""


def extract_market_value(odds_obj: dict, odd_id: str, primary_field: str):
    market = (odds_obj or {}).get(odd_id) or {}
    if not isinstance(market, dict):
        return None
    fallback_fields = {
        "bookSpread": ["fairSpread"],
        "bookOdds": ["fairOdds"],
        "bookOverUnder": ["fairOverUnder"],
    }
    for field in [primary_field] + fallback_fields.get(primary_field, []):
        value = market.get(field)
        if value is not None:
            return value
    return None


def extract_line_values(event: dict) -> dict:
    odds_obj = event.get("odds") or {}
    return {
        "spread_home": extract_market_value(odds_obj, ODD_IDS["spread_home"], "bookSpread"),
        "spread_away": extract_market_value(odds_obj, ODD_IDS["spread_away"], "bookSpread"),
        "ml_home": extract_market_value(odds_obj, ODD_IDS["ml_home"], "bookOdds"),
        "ml_away": extract_market_value(odds_obj, ODD_IDS["ml_away"], "bookOdds"),
        "total_game": extract_market_value(odds_obj, ODD_IDS["total_over"], "bookOverUnder"),
        "total_2h": extract_market_value(odds_obj, ODD_IDS["total_2h_over"], "bookOverUnder"),
    }


def extract_sgo_events(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ["events", "data", "items", "results"]:
        events = payload.get(key)
        if isinstance(events, list):
            return events
    return []


def load_selected_games(date_filter: str | None):
    rows = []
    if date_filter:
        paths = [SELECTED_GAMES_DIR / f"selected_games_{date_filter}.json"]
    else:
        paths = sorted(SELECTED_GAMES_DIR.glob("selected_games_*.json"))

    for path in paths:
        if not path.exists():
            continue
        payload = load_json(path)
        if not isinstance(payload, list):
            continue
        for row in payload:
            if not isinstance(row, dict):
                continue
            rows.append({
                "date": str(row.get("date") or "").strip(),
                "gameID": str(row.get("gameID") or "").strip(),
                "away_seo": str(row.get("away_seo") or "").strip(),
                "home_seo": str(row.get("home_seo") or "").strip(),
                "away_short": str(row.get("away_short") or "").strip(),
                "home_short": str(row.get("home_short") or "").strip(),
            })
    return rows


def build_selected_index(rows):
    by_exact = defaultdict(list)
    by_pair = defaultdict(list)
    by_date = defaultdict(list)
    for row in rows:
        exact_key = (row["date"], row["away_seo"], row["home_seo"])
        pair_key = (row["away_seo"], row["home_seo"])
        by_exact[exact_key].append(row)
        by_pair[pair_key].append(row)
        by_date[row["date"]].append(row)
    return by_exact, by_pair, by_date


def similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def build_suggestions(local_date: str, away_candidate: str, home_candidate: str, by_date: dict, limit: int = 3):
    scored = []
    for candidate in by_date.get(local_date, []):
        away_score = similarity(away_candidate, candidate["away_seo"])
        home_score = similarity(home_candidate, candidate["home_seo"])
        score = (away_score + home_score) / 2.0
        if score <= 0.65:
            continue
        scored.append((score, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in scored[:limit]]


def match_event(event: dict, source_file: str, by_exact: dict, by_pair: dict, by_date: dict, timezone_name: str):
    starts_at = extract_start_time(event)
    local_date = event_local_date(event, timezone_name)
    away_raw = extract_team_name(event, "away")
    home_raw = extract_team_name(event, "home")
    away_candidate = normalize_sgo_team(away_raw)
    home_candidate = normalize_sgo_team(home_raw)

    lines = extract_line_values(event)
    exact_candidates = by_exact.get((local_date, away_candidate, home_candidate), [])
    pair_candidates = by_pair.get((away_candidate, home_candidate), [])
    reverse_pair_candidates = by_pair.get((home_candidate, away_candidate), [])
    suggestions = build_suggestions(local_date, away_candidate, home_candidate, by_date)

    match_status = "UNMATCHED"
    match_reason = "no_exact_match"
    matched = {}
    candidate_rows = []

    if len(exact_candidates) == 1:
        match_status = "EXACT"
        match_reason = "date_away_home_exact"
        matched = exact_candidates[0]
        candidate_rows = exact_candidates
    elif len(exact_candidates) > 1:
        match_status = "AMBIGUOUS"
        match_reason = "multiple_exact_candidates"
        candidate_rows = exact_candidates
    elif reverse_pair_candidates:
        match_status = "UNMATCHED"
        match_reason = "home_away_reversed_candidate_exists"
        candidate_rows = reverse_pair_candidates
    elif pair_candidates:
        match_status = "UNMATCHED"
        match_reason = "team_pair_found_on_other_date"
        candidate_rows = pair_candidates

    return {
        "source_file": source_file,
        "sgo_event_id": extract_event_id(event),
        "starts_at_utc": starts_at,
        "local_date": local_date,
        "sgo_away_raw": away_raw,
        "sgo_home_raw": home_raw,
        "away_seo_candidate": away_candidate,
        "home_seo_candidate": home_candidate,
        "match_status": match_status,
        "match_reason": match_reason,
        "matched_game_id": matched.get("gameID", ""),
        "matched_date": matched.get("date", ""),
        "matched_away": matched.get("away_seo", ""),
        "matched_home": matched.get("home_seo", ""),
        "candidate_count": len(candidate_rows),
        "candidate_game_ids": "|".join(row.get("gameID", "") for row in candidate_rows),
        "suggested_game_ids": "|".join(row.get("gameID", "") for row in suggestions),
        "suggested_away": "|".join(row.get("away_seo", "") for row in suggestions),
        "suggested_home": "|".join(row.get("home_seo", "") for row in suggestions),
        "spread_home": lines["spread_home"],
        "spread_away": lines["spread_away"],
        "ml_home": lines["ml_home"],
        "ml_away": lines["ml_away"],
        "total_game": lines["total_game"],
        "total_2h": lines["total_2h"],
    }


def build_summary(rows):
    counts = defaultdict(int)
    for row in rows:
        counts[row["match_status"]] += 1
    return {
        "total_rows": len(rows),
        "exact": counts.get("EXACT", 0),
        "unmatched": counts.get("UNMATCHED", 0),
        "ambiguous": counts.get("AMBIGUOUS", 0),
    }


def main():
    parser = argparse.ArgumentParser(description="Stage SGO market lines against SDIO selected games without touching Excel.")
    parser.add_argument("--input", required=True, help="Path to raw SGO JSON payload.")
    parser.add_argument("--date", default=None, help="Limit SDIO lookup to selected_games_YYYY-MM-DD.json.")
    parser.add_argument("--timezone", default="America/Chicago", help="Timezone used to derive local game date from UTC startsAt.")
    parser.add_argument("--label", default=None, help="Optional label for output file names.")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    payload = load_json(input_path)
    events = extract_sgo_events(payload)
    selected_rows = load_selected_games(args.date)
    if not selected_rows:
        raise RuntimeError("No selected_games rows found for the requested scope.")

    by_exact, by_pair, by_date = build_selected_index(selected_rows)

    staged_rows = [
        match_event(event, input_path.name, by_exact, by_pair, by_date, args.timezone)
        for event in events
    ]

    label = args.label or input_path.stem
    summary = build_summary(staged_rows)
    output_json = OUTPUT_DIR / f"sgo_stage_{label}.json"
    output_csv = OUTPUT_DIR / f"sgo_stage_{label}.csv"

    save_json(output_json, {
        "input": str(input_path),
        "date_filter": args.date,
        "timezone": args.timezone,
        "summary": summary,
        "rows": staged_rows,
    })
    save_csv(output_csv, staged_rows)

    print(f"Input file   : {input_path}")
    print(f"Selected rows: {len(selected_rows)}")
    print(f"Events found : {len(events)}")
    print(f"Exact        : {summary['exact']}")
    print(f"Unmatched    : {summary['unmatched']}")
    print(f"Ambiguous    : {summary['ambiguous']}")
    print(f"Saved JSON   : {output_json}")
    print(f"Saved CSV    : {output_csv}")


if __name__ == "__main__":
    main()