#!/usr/bin/env python3
"""Add margins, match ids and true date ranges to data/matches.json.

The per match team view used by fetch.py gives totals but not how a match was
won. Statsguru's records section does: Team 1, Team 2, Winner, Margin, Ground,
Match Date, and the scorecard id. The date there is a range, so a Test that ran
from 6 to 10 September is finally known to have occupied all five days rather
than only its first.

Joined on date plus ground, the same key fetch.py uses.

Usage:
    python3 scripts/enrich.py
"""

import json
import re
import time
import urllib.request
from pathlib import Path

FORMATS = {"test": 1, "odi": 2, "t20i": 3}
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
ROOT = Path(__file__).resolve().parent.parent
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
)}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read().decode("utf-8", errors="ignore")


def strip(html):
    return re.sub(r"<[^>]+>", "", html).replace("&nbsp;", " ").strip()


def parse_dates(text):
    """'Jun 25-28, 1932' or 'Sep 6, 2017' or 'Dec 31, 1998 - Jan 1, 1999'."""
    text = text.replace("–", "-").strip()
    year = re.findall(r"(\d{4})", text)
    if not year:
        return None, None
    end_year = int(year[-1])

    # Straddles a new year: two full dates either side of the dash.
    cross = re.match(r"([A-Za-z]{3}) (\d{1,2}), (\d{4})\s*-\s*([A-Za-z]{3}) (\d{1,2}), (\d{4})", text)
    if cross:
        m1, d1, y1, m2, d2, y2 = cross.groups()
        return f"{y1}-{MONTHS[m1]:02d}-{int(d1):02d}", f"{y2}-{MONTHS[m2]:02d}-{int(d2):02d}"

    # Same month: 'Jun 25-28, 1932'. Or a single day: 'Sep 6, 2017'.
    m = re.match(r"([A-Za-z]{3}) (\d{1,2})(?:\s*-\s*(?:([A-Za-z]{3}) )?(\d{1,2}))?", text)
    if not m:
        return None, None
    mon, d1, mon2, d2 = m.groups()
    start = f"{end_year}-{MONTHS[mon]:02d}-{int(d1):02d}"
    if not d2:
        return start, start
    end_month = MONTHS[mon2] if mon2 else MONTHS[mon]
    return start, f"{end_year}-{end_month:02d}-{int(d2):02d}"


def fetch_results(fmt):
    url = (
        "https://stats.espncricinfo.com/ci/engine/records/team/match_results.html"
        f"?class={FORMATS[fmt]};id=6;type=team"
    )
    html = get(url)
    out = []
    for block in re.findall(r'<tr[^>]*class="data\d?"[^>]*>(.*?)</tr>', html, re.S):
        cells = [strip(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)]
        if len(cells) < 6:
            continue
        mid = re.search(r"engine/match/(\d+)\.html", block)

        # A decided match has a margin cell, a draw or abandonment does not,
        # which shifts every column after the winner.
        if len(cells) >= 7:
            team1, team2, winner, margin, ground, dates, card = cells[:7]
        else:
            team1, team2, winner, ground, dates, card = cells[:6]
            margin = ""

        start, end = parse_dates(dates)
        out.append({
            "id": mid.group(1) if mid else None,
            "winner": winner,
            "margin": margin,
            "ground": ground,
            "start": start,
            "end": end,
            "card": card,
            "teams": [team1, team2],
        })
    return out



def add_unplayed(matches, index, have):
    """Abandoned and cancelled fixtures never reach the team aggregate view,
    because no ball was bowled and so no team has a total. India still turned
    up, so they belong in a history organised by date."""
    added = 0
    for (fmt, start, ground), r in index.items():
        if (fmt, start, ground) in have:
            continue
        opponent = [t for t in r["teams"] if t != "India"]
        matches.append({
            "format": fmt,
            "date": start,
            "opponent": opponent[0] if opponent else "",
            "ground": ground,
            "result": r["winner"] if r["winner"] in ("abandoned", "cancelled") else "n/r",
            "india": {"runs": None, "wkts": None, "balls": None},
            "them": {"runs": None, "wkts": None, "balls": None},
            "id": r["id"],
            "margin": "",
            "endDate": r["end"],
            "days": days_between(start, r["end"]),
            "card": r["card"],
        })
        added += 1
    return added


def main():
    path = ROOT / "data" / "matches.json"
    payload = json.loads(path.read_text())
    matches = payload["matches"]

    index = {}
    for fmt in FORMATS:
        print(f"{fmt}...", flush=True)
        rows = fetch_results(fmt)
        print(f"  {len(rows)} rows from the records page")
        for r in rows:
            if r["start"]:
                index[(fmt, r["start"], r["ground"])] = r
        time.sleep(1.5)

    hit = 0
    for m in matches:
        r = index.get((m["format"], m["date"], m["ground"]))
        if not r:
            continue
        hit += 1
        m["id"] = r["id"]
        m["margin"] = r["margin"]
        m["endDate"] = r["end"]
        m["days"] = days_between(m["date"], r["end"])
        m["card"] = r["card"]

    have = {(m["format"], m["date"], m["ground"]) for m in matches}
    added = add_unplayed(matches, index, have)
    print(f"added {added} abandoned or cancelled fixtures")

    matches.sort(key=lambda m: (m["date"] or "", m["format"]))
    payload["matches"] = matches
    payload["counts"] = {f: sum(1 for m in matches if m["format"] == f) for f in FORMATS}
    payload["enriched"] = time.strftime("%Y-%m-%d")
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"enriched {hit} of {len(matches)} matches")

    missing = [m for m in matches if "margin" not in m]
    if missing:
        print(f"no records row for {len(missing)}, first few:")
        for m in missing[:5]:
            print("  ", m["date"], m["format"], m["ground"])


def days_between(a, b):
    if not a or not b:
        return 1
    from datetime import date
    ya, ma, da = map(int, a.split("-"))
    yb, mb, db = map(int, b.split("-"))
    return (date(yb, mb, db) - date(ya, ma, da)).days + 1


if __name__ == "__main__":
    main()
