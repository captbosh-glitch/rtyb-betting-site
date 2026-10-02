"""
Download and cache official NHL team logo SVGs (light + dark variants) into
assets/logos/ at the repo root, keyed by RTYB's own site team codes (see
ABBREV_MAP in fetch_schedule.py) so the front end can always reference
/assets/logos/{CODE}_{light|dark}.svg regardless of what NHL's actual
abbreviation is for that team.

Idempotent by design: a team's light/dark file that already exists on disk
(and is non-empty) is skipped entirely -- no request made for it. That makes
this safe to run on every scheduled refresh (every 10 min, per
.github/workflows/refresh.yml): the first real run -- in GitHub Actions,
the only environment that can actually reach assets.nhle.com from this
project (this sandbox's egress proxy blocks it outright) -- seeds every
file once, and every run after that is a no-op unless a file goes missing
or was never fetched.

Logo source: always NHL's public SVG asset host,
  https://assets.nhle.com/logos/nhl/svg/{ABBREV}_{variant}.svg
using each team's REAL NHL abbreviation (NHL_ABBREV below), not RTYB's own
site code where the two differ.

On the product spec's suggestion to prefer a logo URL from "our existing
NHL data source" (api-web.nhle.com) if it returns one: fetch_schedule.py's
own docstring and parsing code are the only evidence available for what
that API actually returns, and its parsing there only ever reads
awayTeam/homeTeam .abbrev and .score, plus (for finished games)
goals/periodDescriptor fields for the 1P score backfill -- there is no
logo field read or mentioned anywhere in it. Rather than guess a field name
(e.g. "logo" or "darkLogo") that might not exist and silently produce
nothing in production, this script skips that path entirely and goes
straight to the NHL SVG asset URLs above as the sole source. If someone
later confirms api-web.nhle.com does include a usable per-team logo URL,
that can be wired in deliberately with a real field name in hand.

A single team's missing/failed logo never fails the whole script: it's
logged as a WARN to stderr and that team is simply left on the client-side
circle fallback until a later run (in an environment that can reach NHL)
fills it in.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGOS_DIR = os.path.join(ROOT, 'assets', 'logos')

# RTYB site code -> NHL's real abbreviation, for the handful fetch_schedule.py
# remaps to join against the archived season dataset (see its ABBREV_MAP).
# Every other team's site code already matches NHL's own abbreviation.
NHL_ABBREV = {'TB': 'TBL', 'MON': 'MTL', 'NJ': 'NJD', 'SJ': 'SJS', 'LA': 'LAK', 'ANH': 'ANA'}

LOGO_URL = 'https://assets.nhle.com/logos/nhl/svg/{abbrev}_{variant}.svg'
VARIANTS = ('light', 'dark')


def nhl_abbrev(site_code):
    return NHL_ABBREV.get(site_code, site_code)


def fetch_bytes(url, tries=3, timeout=15):
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'rtyb-fetch/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"WARN: failed to fetch {url}: {last_err}", file=sys.stderr)
    return None


def team_codes():
    """Every team code base_data.json's summary has a season stat line for --
    the authoritative "teams this site actually has pages for" list (matches
    TEAM_TRUE_COLOR's keys in template.html 1:1 in practice)."""
    base_path = os.path.join(ROOT, 'base_data.json')
    if not os.path.exists(base_path):
        return []
    with open(base_path, encoding='utf-8') as f:
        base = json.load(f)
    return sorted(base.get('summary', {}).keys())


def main():
    codes = team_codes()
    if not codes:
        print("WARN: no team codes found in base_data.json -- nothing to do", file=sys.stderr)
        return
    os.makedirs(LOGOS_DIR, exist_ok=True)

    cached = 0
    downloaded = 0
    failed = 0

    for code in codes:
        abbrev = nhl_abbrev(code)
        for variant in VARIANTS:
            dest = os.path.join(LOGOS_DIR, f'{code}_{variant}.svg')
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                cached += 1
                continue
            url = LOGO_URL.format(abbrev=abbrev, variant=variant)
            data = fetch_bytes(url)
            if data is None:
                failed += 1
                print(f"WARN: no {variant} logo for {code} ({abbrev}) -- left on fallback for now", file=sys.stderr)
                continue
            # Write via a temp file + rename so a run interrupted mid-write
            # never leaves a truncated file behind that a later run's
            # os.path.getsize() check would treat as already-cached.
            tmp = dest + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, dest)
            downloaded += 1

    print(f"team logos: {cached} already cached, {downloaded} newly downloaded, {failed} failed (left on fallback)")


if __name__ == '__main__':
    main()
