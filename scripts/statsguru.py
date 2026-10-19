"""The one place that talks to Statsguru, shared by fetch, enrich and innings.

Statsguru started answering 503 and then 429 to GitHub's runners in October
2026, a few seconds into a run. So every request goes through get(), which:

- waits at least GAP seconds since the previous request, plus some jitter, so
  a run is a slow trickle rather than a burst
- writes the query in the order Statsguru wants (keys sorted). Any other
  order gets a 301 to the sorted one, which doubled every request
- on 429 or 503 backs off 30s, 60s, 120s, 240s. Statsguru sends
  Retry-After: 5, which is how the old 5s retries kept hitting the wall, so
  that header only ever lengthens the wait
- if Statsguru is still refusing after that, exits with code 75 (EX_TEMPFAIL)
  so the workflow can keep yesterday's data instead of failing the job

The host is stats.cricinfo.com. stats.espncricinfo.com still works but 301s
there first, which doubled every request.
"""

import random
import sys
import time
import urllib.error
import urllib.request

HOST = "https://stats.cricinfo.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
GAP = 10         # seconds between requests, minimum
JITTER = 4       # plus up to this much, at random
BACKOFF = [30, 60, 120, 240]
TEMPFAIL = 75

_last = 0.0


class Unavailable(SystemExit):
    """Statsguru is throttling or down. Not a bug, try again tomorrow."""

    def __init__(self, url, reason):
        print(f"::warning::Statsguru unavailable ({reason}) at {url}", flush=True)
        super().__init__(TEMPFAIL)


def _pace():
    global _last
    wait = _last + GAP + random.uniform(0, JITTER) - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last = time.monotonic()


def _retry_after(err):
    value = err.headers.get("Retry-After") if err.headers else None
    if value and value.strip().isdigit():
        return min(int(value), 600)
    return None


def canonical(url):
    """'?class=1;team=6;page=2' to '?class=1;page=2;team=6'."""
    if "?" not in url:
        return url
    path, query = url.split("?", 1)
    return path + "?" + ";".join(sorted(query.split(";")))


def get(url):
    url = canonical(url)
    for backoff in BACKOFF + [None]:
        _pace()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read().decode("utf-8", errors="ignore")
        except urllib.error.HTTPError as e:
            # Anything other than "slow down" or "busy" is a real problem.
            if e.code not in (429, 502, 503, 504):
                raise
            reason, wait = f"HTTP {e.code}", max(_retry_after(e) or 0, backoff or 0)
        except (urllib.error.URLError, TimeoutError) as e:
            reason, wait = str(getattr(e, "reason", e)), backoff
        if backoff is None:
            raise Unavailable(url, reason)
        print(f"    {reason}, retrying in {wait}s", flush=True)
        time.sleep(wait)
