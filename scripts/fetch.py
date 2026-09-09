#!/usr/bin/env python3
"""Build data/matches.json: every men's international India have played.

Source is ESPNcricinfo Statsguru, in the per-match team view. Two passes per
format: one for India's own totals, one for the opponent's, joined on date and
ground because that pair is unique for an international.

Statsguru is fetched politely and only when the data is rebuilt, which is at
most once a day. See docs/data.md for what that means for publishing the
result.

Usage:
    python3 scripts/fetch.py            # all three formats
    python3 scripts/fetch.py test       # just one
"""

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

INDIA = 6
FORMATS = {"test": 1, "odi": 2, "t20i": 3}
PAGE_SIZE = 200
BASE = "https://stats.espncricinfo.com/ci/engine/stats/index.html"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
ROOT = Path(__file__).resolve().parent.parent

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def get(url, tries=4):
    """Statsguru answers 503 when leaned on, so back off rather than give up
    halfway and leave a half written dataset."""
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode("utf-8", errors="ignore")
        except Exception as e:
            if attempt == tries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"    {e}, retrying in {wait}s", flush=True)
            time.sleep(wait)


def strip(html):
    return re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").strip()


def parse_rows(html):
    """Statsguru per-match rows: team, runs, wkts, balls, ave, rpo, result, _, opp, ground, date."""
    out = []
    for block in re.findall(r'<tr class="data1">(.*?)</tr>', html, re.S):
        cells = [strip(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)]
        if len(cells) < 11:
            continue
        team, runs, wkts, balls, _ave, _rpo, result, _blank, opp, ground, date = cells[:11]
        if not date:
            continue
        out.append({
            "team": team,
            "runs": int(runs) if runs.isdigit() else None,
            "wkts": int(wkts) if wkts.isdigit() else None,
            "balls": int(balls) if balls.isdigit() else None,
            "result": result.lower(),
            "opponent": opp.replace("v ", "").strip(),
            "ground": ground,
            "date": iso_date(date),
            "raw_date": date,
        })
    return out


def iso_date(text):
    """'25 Jun 1932' to '1932-06-25'. Multi day Tests give the first day."""
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text.strip())
    if not m:
        return None
    d, mon, y = m.groups()
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}"


def fetch_side(class_id, key, value):
    """key is 'team' for India's rows, 'opposition' for the other side's."""
    rows, page = [], 1
    while True:
        url = (
            f"{BASE}?class={class_id};{key}={value};template=results;"
            f"type=team;view=match;size={PAGE_SIZE};page={page}"
        )
        got = parse_rows(get(url))
        rows.extend(got)
        if len(got) < PAGE_SIZE:
            break
        page += 1
        time.sleep(1.5)  # be a guest, not a load test
    return rows


def build(fmt):
    class_id = FORMATS[fmt]
    print(f"  {fmt}: India's rows", flush=True)
    ours = fetch_side(class_id, "team", INDIA)
    time.sleep(1.5)
    print(f"  {fmt}: opponents' rows", flush=True)
    theirs = fetch_side(class_id, "opposition", INDIA)

    # Date plus ground identifies an international. Two matches have never
    # started at the same ground on the same day.
    other = {(r["date"], r["ground"]): r for r in theirs}

    matches = []
    for r in ours:
        o = other.get((r["date"], r["ground"]))
        matches.append({
            "format": fmt,
            "date": r["date"],
            "opponent": r["opponent"],
            "ground": r["ground"],
            "result": r["result"],          # won, lost, draw, tied, n/r
            "india": {"runs": r["runs"], "wkts": r["wkts"], "balls": r["balls"]},
            "them": {
                "runs": o["runs"] if o else None,
                "wkts": o["wkts"] if o else None,
                "balls": o["balls"] if o else None,
            },
        })

    unmatched = sum(1 for m in matches if m["them"]["runs"] is None)
    print(f"  {fmt}: {len(matches)} matches, {unmatched} without an opponent row")
    return matches


def main():
    which = sys.argv[1:] or list(FORMATS)
    all_matches = []
    for fmt in which:
        if fmt not in FORMATS:
            sys.exit(f"unknown format: {fmt}")
        print(f"{fmt}...", flush=True)
        all_matches.extend(build(fmt))
        time.sleep(1.5)

    all_matches.sort(key=lambda m: (m["date"] or "", m["format"]))

    out = ROOT / "data" / "matches.json"
    out.parent.mkdir(exist_ok=True)
    payload = {
        "team": "India men",
        "source": "ESPNcricinfo Statsguru, per match team view",
        "generated": time.strftime("%Y-%m-%d"),
        "counts": {f: sum(1 for m in all_matches if m["format"] == f) for f in FORMATS},
        "matches": all_matches,
    }
    out.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"wrote {out} with {len(all_matches)} matches")


if __name__ == "__main__":
    main()
