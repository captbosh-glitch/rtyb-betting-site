"""
Schedules, scores and line scores for the non-NHL sports, from ESPN's
public scoreboard (one request per sport per date; no API key).

Games are saved per season in data_seed/games/{sport}/{season}.json, keyed
by ESPN's game id, so re-running any date just rewrites those games
(idempotent). Dates that fail are logged to data_seed/games/{sport}/
failures.json and retried on the next run that covers them.

  python3 scripts/fetch_sport_games.py daily                  # every sport: yesterday..+7 days
  python3 scripts/fetch_sport_games.py nfl 2026-09-01 2026-10-17
  python3 scripts/fetch_sport_games.py retry                  # dates in failures.json

Saved game:
  {"id", "date" (ET), "start" (UTC ISO), "state": pre | in | final |
   postponed | canceled | suspended, "detail" ("Final", "Top 5th", ...),
   "away", "home" (team slugs; "espn-<id>" for teams not in
   data_seed/teams), "away_name", "home_name", "away_score", "home_score",
   "away_ls", "home_ls" (points or runs per period / inning),
   "periods_done", "final", "season", "season_type" (2 regular, 3 post),
   "conf_game", "neutral", "note"}
"""
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date as Date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAMES_DIR = os.path.join(ROOT, 'data_seed', 'games')
TEAMS_DIR = os.path.join(ROOT, 'data_seed', 'teams')
ET = ZoneInfo('America/New_York')

# ESPN path and extra query per sport (college: FBS = group 80, D-I = 50).
SOURCES = {
    'nfl': ('football/nfl', ''),
    'nba': ('basketball/nba', ''),
    'wnba': ('basketball/wnba', ''),
    'mlb': ('baseball/mlb', ''),
    'ncaaf': ('football/college-football', '&groups=80'),
    'ncaab': ('basketball/mens-college-basketball', '&groups=50'),
}
PRO = {'nfl', 'nba', 'wnba', 'mlb'}

STATE = {
    'STATUS_FINAL': 'final', 'STATUS_FINAL_OT': 'final', 'STATUS_FULL_TIME': 'final',
    'STATUS_POSTPONED': 'postponed', 'STATUS_CANCELED': 'canceled', 'STATUS_SUSPENDED': 'suspended',
    'STATUS_DELAYED': 'in', 'STATUS_RAIN_DELAY': 'in', 'STATUS_FORFEIT': 'canceled',
}


def fetch_json(url, tries=3):
    last = None
    for attempt in range(tries):
        try:
            # Python's default User-Agent; ESPN's feed rejects some custom labels.
            with urllib.request.urlopen(url, timeout=30) as resp:
                return json.loads(resp.read().decode('utf-8')), None
        except Exception as e:  # noqa: BLE001 -- report and retry
            last = str(e)
            time.sleep(2 * (attempt + 1))
    return None, last


def load_teams(sport):
    path = os.path.join(TEAMS_DIR, f'{sport}.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return {t['espn_id']: t['slug'] for t in json.load(f)['teams']}


def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else f


def periods_done(sport, state, status, n_played):
    if state == 'final':
        return n_played
    if state != 'in':
        return 0
    period = status.get('period') or 0
    detail = (status.get('type') or {}).get('shortDetail', '')
    # "End 5th" / "End of 1st Quarter" / "Halftime" mean that period is over.
    if detail.startswith('End') or detail.startswith('Halftime'):
        return period
    return max(period - 1, 0)


def parse_event(sport, ev, team_slugs):
    comp = ev['competitions'][0]
    status = comp.get('status') or ev.get('status') or {}
    stype = status.get('type') or {}
    name = stype.get('name', '')
    if name in STATE:
        state = STATE[name]
    else:
        state = {'pre': 'pre', 'in': 'in', 'post': 'final'}.get(stype.get('state'), 'pre')
    if state == 'final' and not stype.get('completed', True):
        state = 'postponed'
    side = {}
    for c in comp['competitors']:
        t = c['team']
        side[c['homeAway']] = {
            'slug': team_slugs.get(t['id'], f"espn-{t['id']}"),
            'name': t.get('displayName') or t.get('name'),
            'known': t['id'] in team_slugs,
            'score': num(c.get('score')) if state in ('in', 'final', 'suspended') else None,
            'ls': [num(x.get('value')) for x in c.get('linescores') or []],
        }
    if 'away' not in side or 'home' not in side:
        return None
    # Pro leagues: skip All-Star and exhibition games against non-league teams.
    if sport in PRO and not (side['away']['known'] and side['home']['known']):
        return None
    season = ev.get('season') or {}
    if season.get('type') not in (2, 3):  # regular season and postseason only
        return None
    start = ev.get('date') or comp.get('date')
    try:
        local = datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(ET).date().isoformat()
    except (AttributeError, ValueError):
        return None
    # Periods both teams finished. (MLB: the home team skips the bottom of
    # the 9th when ahead, so its line score can be one inning shorter.)
    n_played = min(len(side['away']['ls']), len(side['home']['ls']))
    notes = [n.get('headline') for n in comp.get('notes') or [] if n.get('headline')]
    return {
        'id': ev['id'],
        'date': local,
        'start': start,
        'state': state,
        'detail': stype.get('shortDetail') or stype.get('detail') or '',
        'away': side['away']['slug'], 'home': side['home']['slug'],
        'away_name': side['away']['name'], 'home_name': side['home']['name'],
        'away_score': side['away']['score'], 'home_score': side['home']['score'],
        'away_ls': side['away']['ls'], 'home_ls': side['home']['ls'],
        'periods_done': periods_done(sport, state, status, n_played),
        'final': state == 'final',
        'season': season.get('year'),
        'season_type': season.get('type'),
        'conf_game': bool(comp.get('conferenceCompetition')),
        'neutral': bool(comp.get('neutralSite')),
        'note': notes[0] if notes else None,
    }


def season_path(sport, season):
    return os.path.join(GAMES_DIR, sport, f'{season}.json')


def read_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False, sort_keys=True)
    os.replace(tmp, path)


def fetch_dates(sport, dates, keep=None, verbose=True):
    """Fetch each date; merge into the season files. keep(game) can filter
    (e.g. NCAA Tournament only). Returns (games saved, failed dates)."""
    path, extra = SOURCES[sport]
    team_slugs = load_teams(sport)
    by_season, failed, seen_dates = {}, {}, set()

    def get(d):
        url = f'https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d.replace("-", "")}&limit=1000{extra}'
        return d, fetch_json(url)

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(get, dates))
    for d, (data, err) in responses:
        if data is None:
            failed[d] = err or 'no response'
            if verbose:
                print(f'  {sport} {d}: FAILED ({failed[d]})', file=sys.stderr)
            continue
        seen_dates.add(d)
        for ev in data.get('events') or []:
            g = parse_event(sport, ev, team_slugs)
            if g and (keep is None or keep(g)):
                by_season.setdefault(g['season'], {})[g['id']] = g
    saved = 0
    for season, games in by_season.items():
        p = season_path(sport, season)
        doc = read_json(p, {'sport': sport, 'season': season, 'games': {}})
        doc['games'].update(games)
        doc['updated'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        write_json(p, doc)
        saved += len(games)
    # failures log: add new failures, clear dates that now worked
    fpath = os.path.join(GAMES_DIR, sport, 'failures.json')
    log = read_json(fpath, {})
    for d in seen_dates:
        log.pop(d, None)
    log.update(failed)
    if log or os.path.exists(fpath):
        write_json(fpath, dict(sorted(log.items())))
    return saved, sorted(failed)


def date_range(start, end):
    d, e = Date.fromisoformat(start), Date.fromisoformat(end)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def daily():
    today = datetime.now(ET).date()
    dates = date_range((today - timedelta(days=1)).isoformat(), (today + timedelta(days=7)).isoformat())
    for sport in SOURCES:
        fails = sorted(read_json(os.path.join(GAMES_DIR, sport, 'failures.json'), {}))
        saved, failed = fetch_dates(sport, sorted(set(dates) | set(fails[-14:])), verbose=False)
        print(f'{sport}: {saved} games' + (f', {len(failed)} dates failed' if failed else ''))


def main(argv):
    if not argv or argv[0] == 'daily':
        daily()
    elif argv[0] == 'retry':
        for sport in SOURCES:
            fails = sorted(read_json(os.path.join(GAMES_DIR, sport, 'failures.json'), {}))
            if fails:
                print(sport, fetch_dates(sport, fails))
    else:
        sport, start, end = argv[0], argv[1], argv[2]
        saved, failed = fetch_dates(sport, date_range(start, end))
        print(f'{sport} {start}..{end}: {saved} games, {len(failed)} failed dates')


if __name__ == '__main__':
    main(sys.argv[1:])
