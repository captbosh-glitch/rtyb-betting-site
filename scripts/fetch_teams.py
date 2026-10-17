"""
Team lists for the non-NHL sports, with conference / division, from ESPN's
public standings feed (one request per sport).

Writes data_seed/teams/{sport}.json:
  {"sport", "source", "fetched", "teams": [
     {"code", "name", "short", "location", "nickname", "slug", "color",
      "conference", "division", "espn_id"}, ...]}

Team -> conference lives in these files, not in code: when conferences
realign, re-run this script (or edit the JSON) and rebuild.

  python3 scripts/fetch_teams.py            # every sport
  python3 scripts/fetch_teams.py ncaaf      # one sport
"""
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'data_seed', 'teams')

# ESPN standings feed per sport. Pro leagues: level=3 gives conference >
# division. College: group=80 is FBS, group=50 is Division I men's basketball.
SOURCES = {
    'nfl':   ('football/nfl', 'level=3', 'pro'),
    'nba':   ('basketball/nba', 'level=3', 'pro'),
    'wnba':  ('basketball/wnba', 'level=3', 'pro'),
    'mlb':   ('baseball/mlb', 'level=3', 'pro'),
    'ncaaf': ('football/college-football', 'group=80', 'college'),
    'ncaab': ('basketball/mens-college-basketball', 'group=50', 'college'),
}

# ESPN splits some conferences into divisions in standings; teams belong to
# the conference.
CONFERENCE_ALIASES = {
    'Sun Belt - East': 'Sun Belt Conference',
    'Sun Belt - West': 'Sun Belt Conference',
}


def fetch_json(url, tries=3):
    for attempt in range(tries):
        try:
            # Python's default User-Agent; ESPN's feed rejects some custom labels.
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:  # noqa: BLE001 -- report and retry
            print(f'WARN: {url}: {e}', file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return None


def name_slug(name):
    return re.sub(r'[^a-z0-9]+', '-', name.lower().replace('&', 'and').replace("'", '')).strip('-')


def collect(node, path, out):
    name = node.get('name') or node.get('abbreviation') or ''
    for e in (node.get('standings') or {}).get('entries') or []:
        out.append((path + [name], e['team']))
    for child in node.get('children', []):
        collect(child, path + ([name] if name else []), out)


def fetch_sport(key):
    path, query, kind = SOURCES[key]
    data = fetch_json(f'https://site.api.espn.com/apis/v2/sports/{path}/standings?{query}')
    if not data:
        raise SystemExit(f'{key}: standings fetch failed')
    rows = []
    collect(data, [], rows)
    teams = {}
    for groups, t in rows:
        groups = [g for g in groups if g]
        if kind == 'pro':
            # [league, conference, division] or [league, conference]
            conference = groups[1] if len(groups) > 1 else None
            division = groups[2] if len(groups) > 2 else None
        else:
            conference = CONFERENCE_ALIASES.get(groups[-1], groups[-1])
            division = None
        code = t.get('abbreviation')
        teams[t['id']] = {
            'code': code,
            'name': t.get('displayName'),
            'short': t.get('shortDisplayName'),
            'location': t.get('location'),
            'nickname': t.get('name'),
            # Pro URLs use the abbreviation like NHL (/nfl/teams/ari/);
            # college uses the full name since 300+ abbreviations can collide
            # (e.g. /college-football/teams/alabama-crimson-tide/).
            'slug': code.lower() if kind == 'pro' else name_slug(t.get('displayName')),
            'color': t.get('color'),
            'conference': conference,
            'division': division,
            'espn_id': t['id'],
        }
    # Team colors aren't in the standings feed; take them from the team list.
    listing = fetch_json(f'https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=1000') or {}
    for lg in (listing.get('sports') or [{}])[0].get('leagues', []):
        for entry in lg.get('teams', []):
            t = entry['team']
            if t['id'] in teams and t.get('color'):
                teams[t['id']]['color'] = t['color']
    out = sorted(teams.values(), key=lambda x: x['name'])
    slugs = [t['slug'] for t in out]
    if len(set(slugs)) != len(slugs):
        raise SystemExit(f'{key}: duplicate team slugs')
    return out


def main(keys):
    os.makedirs(OUT_DIR, exist_ok=True)
    for key in keys:
        teams = fetch_sport(key)
        doc = {'sport': key, 'source': 'ESPN standings', 'fetched': date.today().isoformat(), 'teams': teams}
        with open(os.path.join(OUT_DIR, f'{key}.json'), 'w', encoding='utf-8') as f:
            json.dump(doc, f, indent=1, ensure_ascii=False)
        confs = sorted({t['conference'] for t in teams if t['conference']})
        print(f'{key}: {len(teams)} teams, {len(confs)} conferences')


if __name__ == '__main__':
    main(sys.argv[1:] or list(SOURCES))
