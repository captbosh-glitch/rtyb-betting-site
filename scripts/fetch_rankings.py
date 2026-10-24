"""
Weekly AP Top 25 polls for college football and men's college basketball,
from ESPN (no key), saved per
season so every game can use the poll that was current at kickoff (the
latest poll released before it), not today's.

  data_seed/rankings/{ncaaf|ncaab}/{season}.json
    {"season": 2026, "updated": ..., "polls": [
       {"week": 4, "label": "Week 4", "date": "2026-09-20T07:00Z",
        "ranks": {"texas-longhorns": 1, ...}}, ...]}

Idempotent: each run refetches the latest saved week (polls can be
corrected) and any later weeks ESPN has published. Run by refresh.yml.

  python3 scripts/fetch_rankings.py [season]          # college football
  python3 scripts/fetch_rankings.py ncaab [season]    # men's college basketball (season = the spring year)
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_sport_games import fetch_json, load_teams, read_json, write_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = 'https://site.api.espn.com/apis/site/v2/sports/football/college-football/rankings?seasons={season}&weeks={week}&types=2'
# The preseason AP poll is only on ESPN's core API (saved as week 1).
PRESEASON = 'https://sports.core.api.espn.com/v2/sports/football/leagues/college-football/seasons/{season}/types/1/weeks/1/rankings/1'
MAX_WEEK = 17   # regular-season weeks ESPN numbers (the last poll before bowls)


# Men's college basketball: every week (preseason = week 1) from the core API.
NCAAB_WEEK = 'https://sports.core.api.espn.com/v2/sports/basketball/leagues/mens-college-basketball/seasons/{season}/types/2/weeks/{week}/rankings/1'
NCAAB_MAX_WEEK = 22


def path(season, sport='ncaaf'):
    return os.path.join(ROOT, 'data_seed', 'rankings', sport, f'{season}.json')


def ncaab(season):
    """All of a season's AP polls (idempotent: weeks already saved are kept,
    the latest one is refetched). A poll whose date is out of order with its
    neighbours (ESPN sometimes stamps a week with the final poll's date) is
    skipped, so a game never picks up a poll from later in the season."""
    slugs = load_teams('ncaab')
    doc = read_json(path(season, 'ncaab'), {'season': season, 'polls': []})
    polls = {p['week']: p for p in doc['polls']}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    start = max(polls) if polls else 1
    for week in range(start, NCAAB_MAX_WEEK + 1):
        data, err = fetch_json(NCAAB_WEEK.format(season=season, week=week))
        if not data or not data.get('ranks'):
            continue
        ranks = {}
        for r in data['ranks']:
            tid = ((r.get('team') or {}).get('$ref') or '').split('/teams/')[-1].split('?')[0]
            if slugs.get(tid) and isinstance(r.get('current'), int):
                ranks[slugs[tid]] = r['current']
        if (data.get('date') or '') > now:
            break
        label = 'Preseason' if week == 1 else f'Week {week}'
        polls[week] = {'week': week, 'label': label, 'date': data.get('date'), 'ranks': ranks}
    weeks = sorted(polls)
    keep = [w for i, w in enumerate(weeks)
            if (i == 0 or polls[w]['date'] >= polls[weeks[i - 1]]['date'])
            and (i == len(weeks) - 1 or polls[w]['date'] <= polls[weeks[i + 1]]['date'])]
    doc['polls'] = [polls[w] for w in keep]
    doc['updated'] = now
    os.makedirs(os.path.dirname(path(season, 'ncaab')), exist_ok=True)
    write_json(path(season, 'ncaab'), doc)
    print(f'ncaab AP polls {season}: {len(doc["polls"])} weeks saved')


def fetch_poll(season, week, slugs):
    data, err = fetch_json(URL.format(season=season, week=week))
    if data is None:
        print(f'  week {week}: FAILED ({err})', file=sys.stderr)
        return None
    ap = next((r for r in data.get('rankings') or [] if r.get('type') == 'ap'), None)
    if not ap or (ap.get('occurrence') or {}).get('number') != week or ap.get('season', {}).get('year', season) != season:
        return None
    ranks = {}
    for r in ap.get('ranks') or []:
        slug = slugs.get(str((r.get('team') or {}).get('id')))
        if slug and isinstance(r.get('current'), int):
            ranks[slug] = r['current']
    return {'week': week, 'label': (ap.get('occurrence') or {}).get('displayValue') or f'Week {week}',
            'date': ap.get('date'), 'ranks': ranks}


def fetch_preseason(season, slugs):
    data, err = fetch_json(PRESEASON.format(season=season))
    if not data or 'AP' not in (data.get('name') or ''):
        return None
    ranks = {}
    for r in data.get('ranks') or []:
        tid = ((r.get('team') or {}).get('$ref') or '').split('/teams/')[-1].split('?')[0]
        if slugs.get(tid) and isinstance(r.get('current'), int):
            ranks[slugs[tid]] = r['current']
    return {'week': 1, 'label': 'Preseason', 'date': data.get('date'), 'ranks': ranks}


def main(argv):
    if argv and argv[0] == 'ncaab':
        now = datetime.now(timezone.utc)
        return ncaab(int(argv[1]) if len(argv) > 1 else now.year + (1 if now.month >= 10 else 0))
    season = int(argv[0]) if argv else datetime.now(timezone.utc).year
    slugs = load_teams('ncaaf')
    doc = read_json(path(season), {'season': season, 'polls': []})
    polls = {p['week']: p for p in doc['polls']}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
    got = 0
    if 1 not in polls:
        p = fetch_preseason(season, slugs)
        if p and p['ranks']:
            polls[1] = p
            got += 1
    # ESPN has no AP poll for some week numbers (e.g. week 1 = preseason);
    # skip those, and stop at the first future poll or a gap past the last one.
    last = max([w for w in polls if w > 1] or [1])
    for week in range(max(2, last), MAX_WEEK + 1):
        p = fetch_poll(season, week, slugs)
        if p is None or not p['ranks']:
            if week > last + 1:
                break
            continue
        if (p['date'] or '') > now:
            break
        polls[week] = p
        last = max(last, week)
        got += 1
    doc['polls'] = [polls[w] for w in sorted(polls)]
    doc['updated'] = now
    os.makedirs(os.path.dirname(path(season)), exist_ok=True)
    write_json(path(season), doc)
    print(f'ncaaf AP polls {season}: {len(doc["polls"])} weeks saved ({got} fetched this run)')


if __name__ == '__main__':
    main(sys.argv[1:])
