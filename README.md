# India cricket history data

Every men's international India have played: Tests, ODIs and T20 Internationals
since 25 June 1932. No franchise cricket.

Feeds [indian-cricket-today.bhaumikmistry.com](https://indian-cricket-today.bhaumikmistry.com).

## The file

`api.json`, rebuilt daily by an Action. Fetch it directly:

```
https://raw.githubusercontent.com/bhaumikmistry/india-cricket-history-data/main/api.json
```

```json
{
  "generated": "2026-09-08",
  "counts": { "test": 603, "odi": 1120, "t20i": 296 },
  "summary": { "played": 2019, "won": 952, "lost": 721, "drawn": 225, "tied": 18 },
  "landmarks": [ { "date": "1983-06-25", "format": "odi", "title": "The World Cup", "note": "..." } ],
  "matches": [
    {
      "format": "test",
      "date": "2021-09-02",
      "endDate": "2021-09-06",
      "days": 5,
      "opponent": "England",
      "ground": "The Oval",
      "result": "won",
      "margin": "157 runs",
      "id": "1263468",
      "india": { "runs": 657, "wkts": 20, "innings": [ { "score": "191", "overs": "61.3" } ] },
      "them":  { "runs": 500, "wkts": 20, "innings": [ { "score": "290", "overs": "91.4" } ] }
    }
  ]
}
```

A match carries every day it occupied, so the final day of a Test can be found
under that date and not only under the day it started.

`result` is one of `won`, `lost`, `draw`, `tied`, `n/r`, `abandoned`,
`cancelled`. The last two have no scores, because no ball was bowled.

## Rebuilding it

```
python3 scripts/fetch.py     # results and totals, both sides
python3 scripts/enrich.py    # margins, ids, date ranges, abandoned fixtures
python3 scripts/innings.py   # innings by innings scores
python3 scripts/build.py     # summary, landmarks, and the size guard
```

Around fifty requests to Statsguru with a pause between each. `build.py` refuses
to publish a dataset smaller than the one already committed, because a
half finished scrape overwriting a good file is the failure that matters.

## Where it comes from

ESPNcricinfo Statsguru, three views: per match team totals, the records match
results page for margins, and the innings view. Cricsheet only reaches back to
2001 and this needs 1932. Wikidata has no per match cricket. Howstat and the
ESPNcricinfo consumer API both refuse automated requests.

`landmarks.json` is written by hand. Every entry was checked against the data
before being added, so a landmark can only attach to a match that exists.
