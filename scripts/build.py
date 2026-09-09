#!/usr/bin/env python3
"""Fold data/matches.json and landmarks.json into the published api.json.

The three fetch scripts write data/matches.json between them. This is the last
step: it adds a summary block so a page can show headline numbers without
walking two thousand records, folds in the landmarks, and refuses to publish a
file that is smaller than the one already committed.

That last part is the important one. Statsguru has answered 503 in the middle
of a run before, and a truncated scrape quietly overwriting a good dataset is
the failure worth designing against.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "matches.json"
OUT = ROOT / "api.json"
MARKS = ROOT / "landmarks.json"


def main():
    payload = json.loads(SRC.read_text())
    matches = payload["matches"]

    if not matches:
        sys.exit("refusing to publish an empty dataset")

    # Never publish fewer matches than are already public. India can only ever
    # have played more.
    if OUT.exists():
        try:
            before = len(json.loads(OUT.read_text()).get("matches", []))
        except Exception:
            before = 0
        if len(matches) < before:
            sys.exit(f"refusing to shrink api.json: have {before}, built {len(matches)}")

    results = {}
    for m in matches:
        results[m["result"]] = results.get(m["result"], 0) + 1

    landmarks = json.loads(MARKS.read_text())["landmarks"] if MARKS.exists() else []

    api = {
        "team": "India men",
        "source": "ESPNcricinfo Statsguru",
        "generated": time.strftime("%Y-%m-%d"),
        "counts": {f: sum(1 for m in matches if m["format"] == f) for f in ("test", "odi", "t20i")},
        "summary": {
            "played": len(matches),
            "won": results.get("won", 0),
            "lost": results.get("lost", 0),
            "drawn": results.get("draw", 0),
            "tied": results.get("tied", 0),
            "noResult": results.get("n/r", 0),
            "abandoned": results.get("abandoned", 0) + results.get("cancelled", 0),
            "first": min(m["date"] for m in matches),
            "last": max(m["date"] for m in matches),
        },
        "landmarks": landmarks,
        "matches": matches,
    }

    OUT.write_text(json.dumps(api, separators=(",", ":")))
    kb = OUT.stat().st_size / 1024
    print(f"api.json: {len(matches)} matches, {len(landmarks)} landmarks, {kb:.0f} KB")


if __name__ == "__main__":
    main()
