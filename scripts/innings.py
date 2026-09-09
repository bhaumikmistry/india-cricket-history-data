#!/usr/bin/env python3
"""Add innings by innings scores to data/matches.json.

A Test shown as 637 against 755 is nonsense: those are two innings added
together, and no scoreboard has ever displayed them that way. Statsguru's
innings view gives each one separately, with declarations intact.

Two passes per format again, India's innings and the opponent's, joined on
date and ground and then ordered by innings number.

Usage:
    python3 scripts/innings.py
"""

import json
import re
import time
import urllib.request
from collections import defaultdict
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


def iso_date(text):
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text.strip())
    if not m:
        return None
    d, mon, y = m.groups()
    return f"{y}-{MONTHS[mon]:02d}-{int(d):02d}"


def parse(html):
    """Tests carry a Lead column and limited overs do not, so the columns after
    it sit at different indices. Counting from the right is stable for both:
    ..., inns, result, blank, opposition, ground, date, blank."""
    out = []
    for block in re.findall(r'<tr class="data1">(.*?)</tr>', html, re.S):
        c = [strip(x) for x in re.findall(r"<td[^>]*>(.*?)</td>", block, re.S)]
        if len(c) < 11:
            continue
        score, overs = c[1], c[2]
        inns, ground, date = c[-7], c[-3], c[-2]
        if not date or not score or score in ("-", "DNB"):
            continue
        out.append({
            "score": score,          # "759/7d", "183", "82/4"
            "overs": overs,
            "inns": int(inns) if inns.isdigit() else 1,
            "ground": ground,
            "date": iso_date(date),
        })
    return out


def fetch_side(class_id, key, value):
    rows, page = [], 1
    while True:
        url = (
            f"{BASE}?class={class_id};{key}={value};template=results;"
            f"type=team;view=innings;size={PAGE_SIZE};page={page}"
        )
        got = parse(get(url))
        rows.extend(got)
        if len(got) < PAGE_SIZE:
            break
        page += 1
        time.sleep(1.5)
    return rows


def collect(fmt):
    class_id = FORMATS[fmt]
    print(f"  {fmt}: India's innings", flush=True)
    ours = fetch_side(class_id, "team", INDIA)
    time.sleep(1.5)
    print(f"  {fmt}: opponents' innings", flush=True)
    theirs = fetch_side(class_id, "opposition", INDIA)

    def group(rows):
        g = defaultdict(list)
        for r in rows:
            if r["date"]:
                g[(fmt, r["date"], r["ground"])].append(r)
        for k in g:
            g[k].sort(key=lambda r: r["inns"])
        return g

    return group(ours), group(theirs)


def main():
    path = ROOT / "data" / "matches.json"
    payload = json.loads(path.read_text())
    matches = payload["matches"]

    ours_all, theirs_all = {}, {}
    for fmt in FORMATS:
        print(f"{fmt}...", flush=True)
        a, b = collect(fmt)
        ours_all.update(a)
        theirs_all.update(b)
        time.sleep(1.5)

    hit = 0
    for m in matches:
        key = (m["format"], m["date"], m["ground"])
        ours = ours_all.get(key, [])
        theirs = theirs_all.get(key, [])
        if ours or theirs:
            hit += 1
        m["india"]["innings"] = [{"score": r["score"], "overs": r["overs"]} for r in ours]
        m["them"]["innings"] = [{"score": r["score"], "overs": r["overs"]} for r in theirs]

    payload["matches"] = matches
    payload["innings"] = time.strftime("%Y-%m-%d")
    path.write_text(json.dumps(payload, separators=(",", ":")))

    tests = [m for m in matches if m["format"] == "test"]
    two_plus = sum(1 for m in tests if len(m["india"]["innings"]) > 1)
    print(f"innings on {hit} of {len(matches)} matches")
    print(f"Tests with more than one India innings: {two_plus} of {len(tests)}")


if __name__ == "__main__":
    main()
