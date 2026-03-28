import json
with open("data/logs/covers_slug_audit_pass1.json") as f:
    d = json.load(f)

print("=== one-team-missing-or-remapped ===")
for item in d.get("unmatched_ranked", []):
    if item.get("root_cause") == "one-team-missing-or-remapped":
        away = item.get("away", "")
        home = item.get("home", "")
        date = item.get("date", "")
        missing_side = item.get("missing_side", "")
        unmatched = item.get("unmatched_slug", "")
        print(f"  {away} @ {home} | {date} | missing={missing_side} | slug={unmatched}")

print()
print("=== both-teams-exist-no-pair ===")
for item in d.get("unmatched_ranked", []):
    if item.get("root_cause") == "both-teams-exist-no-pair":
        away = item.get("away", "")
        home = item.get("home", "")
        date = item.get("date", "")
        print(f"  {away} @ {home} | {date}")

print()
print("=== missing_slug_ranking (top missing from override dict) ===")
for entry in d.get("missing_slug_ranking", [])[:20]:
    print(f"  {entry}")
