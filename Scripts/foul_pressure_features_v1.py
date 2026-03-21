import json


def extract_foul_pressure(pbp_data):
    away_fouls = 0
    home_fouls = 0

    plays = pbp_data.get("plays", [])

    for play in plays:
        text = str(play.get("text", "")).lower()

        if "foul" in text:
            if play.get("team") == "away":
                away_fouls += 1
            elif play.get("team") == "home":
                home_fouls += 1

    # Assume 20-minute half
    minutes = 20

    away_fpm = away_fouls / minutes
    home_fpm = home_fouls / minutes

    away_in_bonus = away_fouls >= 7
    home_in_bonus = home_fouls >= 7

    # Edge logic
    if away_fouls - home_fouls >= 3:
        edge = "home"
    elif home_fouls - away_fouls >= 3:
        edge = "away"
    else:
        edge = "neutral"

    return {
        "away_team_fouls": away_fouls,
        "home_team_fouls": home_fouls,
        "away_fouls_per_min": round(away_fpm, 2),
        "home_fouls_per_min": round(home_fpm, 2),
        "away_in_bonus": away_in_bonus,
        "home_in_bonus": home_in_bonus,
        "foul_pressure_edge": edge
    }