"""Quick SGO quota check."""
import os, json, requests, sys

key = os.environ.get("SPORTS_API_KEY", "").strip()
if not key:
    print("ERROR: SPORTS_API_KEY not set")
    sys.exit(1)

print(f"Key present, length={len(key)}")
try:
    r = requests.get(
        "https://api.sportsgameodds.com/v2/account/usage",
        params={"apiKey": key},
        timeout=15,
    )
    print(f"Status: {r.status_code}")
    d = r.json()
    # Try to find per-month entities
    def find_key(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                find_key(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                find_key(v, f"{path}[{i}]")
        else:
            if "entit" in path.lower() or "request" in path.lower() or "tier" in path.lower():
                print(f"  {path} = {obj}")
    find_key(d)
    print("\nFull response:")
    print(json.dumps(d, indent=2))
except Exception as e:
    print(f"Error: {e}")
