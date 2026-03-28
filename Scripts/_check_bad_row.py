"""One-shot: check API for game 6530175 (utrgv @ mcneese, 2026-02-23) and repair workbook row 332."""
import requests, openpyxl, re

# 1. Probe the API
url = "https://ncaa-api.henrygd.me/scoreboard/basketball-men/d1/2026/02/23"
r = requests.get(url, timeout=15)
data = r.json()
games = data.get("games", [])
print(f"Total games on 2026-02-23 from API: {len(games)}")

found = None
for g in games:
    gd = g.get("game", {})
    gid = str(gd.get("gameID", ""))
    if gid == "6530175":
        found = gd
        break
    h = gd.get("home", {}).get("names", {}).get("seo", "")
    a = gd.get("away", {}).get("names", {}).get("seo", "")
    if "mcneese" in h.lower() or "utrgv" in a.lower():
        found = gd
        print(f"Found by team name: GameID={gid}")
        break

if found:
    hs = int(found.get("homeScore", 0) or 0)
    as_ = int(found.get("awayScore", 0) or 0)
    home_seo = found.get("home", {}).get("names", {}).get("seo", "")
    away_seo = found.get("away", {}).get("names", {}).get("seo", "")
    print(f"  {away_seo} {as_} @ {home_seo} {hs}")
    if hs and as_:
        winner = home_seo if hs > as_ else away_seo
        margin = abs(hs - as_)
        total = hs + as_
        # Repair the workbook
        wb = openpyxl.load_workbook("logs/NCAAM Results.xlsx")
        ws = wb["Game_Log"]
        ws.cell(row=332, column=12).value = winner     # L = ActualWinner
        ws.cell(row=332, column=13).value = margin     # M = ActualMargin
        # Actual 2H and Total would need halftime score to compute — leave as-is if already set
        ws.cell(row=332, column=16).value = "Y"        # P = WinnerCorrect (we'd need PredWinner to compare)
        # Check WinnerCorrect properly
        pred_winner = ws.cell(row=332, column=7).value  # G = PredWinner
        ws.cell(row=332, column=16).value = "Y" if pred_winner == winner else "N"
        wb.save("logs/NCAAM Results.xlsx")
        print(f"  REPAIRED: winner={winner}, margin={margin}, total={total}")
    else:
        print("  API returned 0-0 scores — cannot repair from API")
else:
    print("  Game NOT found in API response")

# Show 3 sample games to confirm API is live
print("\nSample games from the date:")
for g in games[:3]:
    gd = g.get("game", {})
    print(f"  {gd.get('gameID')} {gd.get('away',{}).get('names',{}).get('seo','')} @ {gd.get('home',{}).get('names',{}).get('seo','')} {gd.get('awayScore')}-{gd.get('homeScore')}")
