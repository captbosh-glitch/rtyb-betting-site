"""
Team logos for the non-NHL sports, from ESPN's public team feed (the same
source as data_seed/teams/), cached in assets/logos/{sport}/:

  {slug}.png        the standard logo (for light backgrounds)
  {slug}-dark.png   ESPN's version for dark backgrounds, only when it
                    differs from the standard one
  index.json        {slug: {"dark": true|false}} -- what the pages read

Logos are 96px PNGs (ESPN's image resizer), small enough for ~600 teams.
Idempotent like fetch_team_logos.py (NHL): a logo already on disk is never
requested again, so this is safe on every refresh. A team whose logo can't
be fetched keeps the colored circle badge until a later run gets it.

  python3 scripts/fetch_sport_logos.py           # every sport
  python3 scripts/fetch_sport_logos.py ncaab     # one sport
"""
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEAMS_DIR = os.path.join(ROOT, 'data_seed', 'teams')
LOGOS_DIR = os.path.join(ROOT, 'assets', 'logos')

# ESPN team-list path per sport, and the logo folder its CDN uses (college
# logos are filed by ESPN team id under "ncaa").
SOURCES = {
    'nfl': ('football/nfl', 'nfl'),
    'nba': ('basketball/nba', 'nba'),
    'wnba': ('basketball/wnba', 'wnba'),
    'mlb': ('baseball/mlb', 'mlb'),
    'ncaaf': ('football/college-football', 'ncaa'),
    'ncaab': ('basketball/mens-college-basketball', 'ncaa'),
}
SIZE = 96
RESIZE = 'https://a.espncdn.com/combiner/i?img={path}&h={size}&w={size}'


def get(url, tries=3):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except Exception as e:  # noqa: BLE001 -- report and retry
            last = e
            time.sleep(1.5 * (attempt + 1))
    print(f'WARN: {url}: {last}', file=sys.stderr)
    return None


def espn_logos(path):
    """{espn_id: {'default': url, 'dark': url}} from the team list."""
    raw = get(f'https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=1000')
    out = {}
    if not raw:
        return out
    for lg in (json.loads(raw).get('sports') or [{}])[0].get('leagues', []):
        for entry in lg.get('teams', []):
            t = entry['team']
            urls = {}
            for logo in t.get('logos') or []:
                rel = logo.get('rel') or []
                if 'full' in rel and 'default' in rel:
                    urls['default'] = logo['href']
                elif 'full' in rel and 'dark' in rel:
                    urls['dark'] = logo['href']
            out[t['id']] = urls
    return out


def resized(url):
    """ESPN's resizer takes the CDN path; anything else is fetched as-is."""
    prefix = 'https://a.espncdn.com'
    if url.startswith(prefix):
        return RESIZE.format(path=urllib.parse.quote(url[len(prefix):]), size=SIZE)
    return url


def fetch_sport(key):
    path, folder = SOURCES[key]
    teams = json.load(open(os.path.join(TEAMS_DIR, f'{key}.json'), encoding='utf-8'))['teams']
    out_dir = os.path.join(LOGOS_DIR, key)
    os.makedirs(out_dir, exist_ok=True)
    index_path = os.path.join(out_dir, 'index.json')
    index = json.load(open(index_path, encoding='utf-8')) if os.path.exists(index_path) else {}
    todo = [t for t in teams if not os.path.exists(os.path.join(out_dir, f"{t['slug']}.png"))]
    listed = espn_logos(path) if todo else {}

    def one(t):
        urls = listed.get(t['espn_id']) or {}
        ident = t['espn_id'] if folder == 'ncaa' else (t['code'] or '').lower()
        default = urls.get('default') or f'https://a.espncdn.com/i/teamlogos/{folder}/500/{ident}.png'
        dark = urls.get('dark') or f'https://a.espncdn.com/i/teamlogos/{folder}/500-dark/{ident}.png'
        light_png = get(resized(default))
        if not light_png:
            return t['slug'], None
        dark_png = get(resized(dark))
        same = not dark_png or hashlib.sha1(dark_png).digest() == hashlib.sha1(light_png).digest()
        with open(os.path.join(out_dir, f"{t['slug']}.png"), 'wb') as f:
            f.write(light_png)
        if not same:
            with open(os.path.join(out_dir, f"{t['slug']}-dark.png"), 'wb') as f:
                f.write(dark_png)
        return t['slug'], {'dark': not same}

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(one, todo))
    missing = [slug for slug, info in results if info is None]
    for slug, info in results:
        if info is not None:
            index[slug] = info
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(index.items())), f, indent=0)
    print(f'{key}: {len(index)} of {len(teams)} logos'
          + (f' ({len(results) - len(missing)} new)' if results else '')
          + (f'; missing: {", ".join(missing[:8])}' if missing else ''))


if __name__ == '__main__':
    for key in sys.argv[1:] or list(SOURCES):
        fetch_sport(key)
