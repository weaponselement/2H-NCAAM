import json
import os
from collections import Counter

RAW_PATH = r"C:\NCAA Model\data\processed\schema_inspection\pbp_raw_6503596.json"

# Keys that commonly appear in play/event items
PLAY_SMELL_KEYS = {
    "clock", "time", "description", "text", "period", "half",
    "team", "teamid", "teamseo", "player", "playername",
    "homescore", "awayscore", "score"
}

def norm_key(k: str) -> str:
    return (k or "").strip().lower().replace("_", "")

def score_playish(item: dict) -> int:
    """Heuristic score: higher = more likely this dict is a PBP event."""
    keys = {norm_key(k) for k in item.keys()}
    hits = sum(1 for k in keys if k in PLAY_SMELL_KEYS)
    # bonus if it has obvious text/description fields
    if "description" in keys or "text" in keys:
        hits += 2
    # bonus if it has a clock/time + period/half
    if ("clock" in keys or "time" in keys) and ("period" in keys or "half" in keys):
        hits += 2
    return hits

def walk(obj, path="$", results=None, max_examples=30):
    """
    Recursively walk JSON and find candidate arrays that look like play lists.
    Record:
      - json path
      - length
      - sample keys
      - playish score
    """
    if results is None:
        results = []

    if isinstance(obj, dict):
        for k, v in obj.items():
            walk(v, f"{path}.{k}", results, max_examples)
    elif isinstance(obj, list):
        if obj and all(isinstance(x, dict) for x in obj[:10]):  # check first few
            # score based on first dict
            s = score_playish(obj[0])
            # also compute key frequency from first N items
            key_counter = Counter()
            for x in obj[: min(len(obj), 50)]:
                key_counter.update([norm_key(kk) for kk in x.keys()])
            common_keys = [k for k, _ in key_counter.most_common(20)]

            results.append({
                "path": path,
                "length": len(obj),
                "score": s,
                "common_keys_top20": common_keys,
            })

        # keep walking into list items too (sometimes plays are nested further)
        for i, v in enumerate(obj[:50]):  # cap recursion for huge lists
            walk(v, f"{path}[{i}]", results, max_examples)

    return results

def main():
    if not os.path.exists(RAW_PATH):
        print(f"Raw file not found at: {RAW_PATH}")
        return

    with open(RAW_PATH, "r", encoding="utf-8") as f:
        payload = json.load(f)

    print(f"\nLoaded raw JSON: {RAW_PATH}")
    print(f"Top-level type: {type(payload).__name__}")

    if isinstance(payload, dict):
        print(f"Top-level keys (first 40): {list(payload.keys())[:40]}")
    elif isinstance(payload, list):
        print(f"Top-level list length: {len(payload)}")

    candidates = walk(payload)

    # Sort by "playish score" (desc), then by length (desc)
    candidates_sorted = sorted(candidates, key=lambda x: (x["score"], x["length"]), reverse=True)

    print(f"\nFound {len(candidates_sorted)} candidate list-of-dict arrays.\n")

    # Print top 15 candidates
    for c in candidates_sorted[:15]:
        print(f"PATH: {c['path']}")
        print(f"  length: {c['length']}")
        print(f"  playish_score: {c['score']}")
        print(f"  common_keys_top20: {c['common_keys_top20']}\n")

    print("Next: pick the candidate with the highest playish_score and keys like clock/period/description.")
    print("Paste the TOP 3 candidates here and I’ll tell you which one is the real play list.\n")

if __name__ == "__main__":
    main()