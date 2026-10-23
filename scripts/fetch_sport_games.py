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
  python3 scripts/fetch_sport_games.py coverage               # games / line scores per season
  python3 scripts/fetch_sport_games.py ncaab 2026-03-17 2026-04-06 --ncaa-tournament
                                    # only NCAA Tournament games (ESPN's game note
                                    # "NCAA Men's Basketball Championship"; not NIT etc.)

Saved game:
  {"id", "date" (ET), "start" (UTC ISO), "state": pre | in | final |
   postponed | canceled | suspended, "detail" ("Final", "Top 5th", ...),
   "away", "home" (team slugs; "espn-<id>" for teams not in
   data_seed/teams), "away_name", "home_name", "away_score", "home_score",
   "away_ls", "home_ls" (points or runs per period / inning),
   "periods_done", "final", "season", "season_type" (2 regular, 3 post),
   "week", "week_label" (football: ESPN's week number and its calendar
   label, e.g. 6 / "Week 6", or 1 / "Wild Card" in the postseason),
   "conf_game", "neutral", "note", "country" (venue country, e.g. "USA" /
   "England"), "away_rank", "home_rank" (college: the AP / CFP rank ESPN
   shows for the game, i.e. at kickoff; None when unranked)}

Football finals also get "fg_spread" (the home team's closing full-game
spread; negative = home favored) and "fg_total" from ESPN's game summary
(DraftKings close), fetched once per game, LINES_PER_RUN per sport per
run; None when ESPN has no line.

Games saved before a field existed are refetched by date in daily runs
(backfill_fields: up to BACKFILL_DATES dates per sport per run), so new
fields fill in across the season without a manual reload.
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


def week_labels(data):
    """{(season type, week number): label} from a scoreboard's calendar."""
    out = {}
    for lg in data.get('leagues') or []:
        for part in lg.get('calendar') or []:
            if not isinstance(part, dict):
                continue  # non-football calendars are plain date lists
            for entry in part.get('entries') or []:
                try:
                    out[(int(part.get('value')), int(entry.get('value')))] = entry.get('label')
                except (TypeError, ValueError):
                    pass
    return out


def parse_event(sport, ev, team_slugs, labels=None):
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
    week = (ev.get('week') or {}).get('number')
    ranks = {}
    for c in comp['competitors']:
        r = (c.get('curatedRank') or {}).get('current')
        ranks[c['homeAway']] = r if isinstance(r, int) and 1 <= r <= 25 else None
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
        'week': week,
        'week_label': (labels or {}).get((season.get('type'), week)) if week else None,
        'country': ((comp.get('venue') or {}).get('address') or {}).get('country'),
        'away_rank': ranks.get('away'), 'home_rank': ranks.get('home'),
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
    by_season, failed, seen_dates, skipped = {}, {}, set(), []

    def get(d):
        # limit=300: ESPN quietly caps some recent college days at 25 games
        # when asked for more (limit=1000), but returns the full day here.
        url = f'https://site.api.espn.com/apis/site/v2/sports/{path}/scoreboard?dates={d.replace("-", "")}&limit=300{extra}'
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
        labels = week_labels(data)
        for ev in data.get('events') or []:
            try:
                g = parse_event(sport, ev, team_slugs, labels)
            except (KeyError, IndexError, TypeError) as e:
                # A malformed entry (e.g. a game listed with no details) is
                # skipped and logged, not allowed to stop the whole load.
                skipped.append(f"{d} {ev.get('id')}: {e!r}")
                continue
            if g and (keep is None or keep(g)):
                by_season.setdefault(g['season'], {})[g['id']] = g
    if skipped and verbose:
        print(f'  {sport}: skipped {len(skipped)} malformed entries: {"; ".join(skipped[:5])}', file=sys.stderr)
    saved = 0
    for season, games in by_season.items():
        p = season_path(sport, season)
        doc = read_json(p, {'sport': sport, 'season': season, 'games': {}})
        for gid, g in games.items():
            old = doc['games'].get(gid) or {}
            for f in ('fg_spread', 'fg_total'):
                if f in old:
                    g[f] = old[f]
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


# Saved-game fields added after games were first loaded; a game without
# one has its date refetched (BACKFILL_DATES per sport per run).
NEW_FIELDS = ('country', 'away_rank')
BACKFILL_DATES = 20


def backfill_dates(sport):
    """Dates in the sport's latest season with a game missing a NEW_FIELDS
    key, oldest first, capped."""
    d = os.path.join(GAMES_DIR, sport)
    seasons = sorted(n for n in os.listdir(d) if n[:4].isdigit()) if os.path.isdir(d) else []
    if not seasons:
        return []
    games = read_json(os.path.join(d, seasons[-1]), {}).get('games', {}).values()
    return sorted({g['date'] for g in games if any(f not in g for f in NEW_FIELDS)})[:BACKFILL_DATES]


LINE_SPORTS = {'nfl': 'football/nfl', 'ncaaf': 'football/college-football'}
LINES_PER_RUN = 60


def fetch_lines(sport, cap=LINES_PER_RUN):
    """Closing full-game spread / total for finals that don't have them yet."""
    d = os.path.join(GAMES_DIR, sport)
    seasons = sorted(n for n in os.listdir(d) if n[:4].isdigit()) if os.path.isdir(d) else []
    if sport not in LINE_SPORTS or not seasons:
        return 0
    p = os.path.join(d, seasons[-1])
    doc = read_json(p, {})
    todo = [g for g in doc.get('games', {}).values() if g.get('final') and 'fg_spread' not in g][:cap]

    def get(g):
        url = f'https://site.api.espn.com/apis/site/v2/sports/{LINE_SPORTS[sport]}/summary?event={g["id"]}'
        return g, fetch_json(url)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(get, todo))
    done = 0
    for g, (data, err) in results:
        if data is None:
            continue
        pc = next(iter(data.get('pickcenter') or []), {}) or {}
        g['fg_spread'] = pc.get('spread') if isinstance(pc.get('spread'), (int, float)) else None
        g['fg_total'] = pc.get('overUnder') if isinstance(pc.get('overUnder'), (int, float)) else None
        done += 1
    if done:
        write_json(p, doc)
    return done


def daily():
    today = datetime.now(ET).date()
    dates = date_range((today - timedelta(days=1)).isoformat(), (today + timedelta(days=7)).isoformat())
    for sport in SOURCES:
        fails = sorted(read_json(os.path.join(GAMES_DIR, sport, 'failures.json'), {}))
        back = backfill_dates(sport)
        saved, failed = fetch_dates(sport, sorted(set(dates) | set(fails[-14:]) | set(back)), verbose=False)
        lines = fetch_lines(sport)
        print(f'{sport}: {saved} games' + (f' ({len(back)} older dates refetched for new fields)' if back else '')
              + (f', closing lines for {lines}' if lines else '') + (f', {len(failed)} dates failed' if failed else ''))


# Periods a final needs for every segment to grade (MLB: 5 innings for F5).
FULL_PERIODS = {'nfl': 2, 'ncaaf': 2, 'nba': 2, 'wnba': 2, 'ncaab': 1, 'mlb': 5}


def coverage():
    """Per sport and season: games, finals, finals with the line scores the
    segments need, and seasons where that's incomplete (flagged)."""
    for sport in SOURCES:
        d = os.path.join(GAMES_DIR, sport)
        if not os.path.isdir(d):
            print(f'{sport}: no games loaded')
            continue
        for name in sorted(os.listdir(d)):
            if not name[:4].isdigit():
                continue
            games = list(read_json(os.path.join(d, name), {}).get('games', {}).values())
            finals = [g for g in games if g['final']]
            need = FULL_PERIODS[sport]
            full = sum(1 for g in finals if min(len(g['away_ls']), len(g['home_ls'])) >= need)
            pct = 100 * full / len(finals) if finals else 0
            flag = '' if not finals or pct >= 99 else '  <-- missing line scores'
            dates = sorted(g['date'] for g in games)
            print(f'{sport} {name[:-5]}: {len(games)} games ({dates[0]} to {dates[-1]}), {len(finals)} final, '
                  f'{full} with line scores ({pct:.1f}%){flag}')
        fails = read_json(os.path.join(d, 'failures.json'), {})
        if fails:
            print(f'{sport}: {len(fails)} failed dates: {", ".join(sorted(fails)[:10])}')


def main(argv):
    if argv and argv[0] == 'coverage':
        coverage()
    elif not argv or argv[0] == 'daily':
        daily()
    elif argv[0] == 'lines':   # e.g. lines ncaaf 1000
        print(argv[1], fetch_lines(argv[1], int(argv[2]) if len(argv) > 2 else LINES_PER_RUN))
    elif argv[0] == 'retry':
        for sport in SOURCES:
            fails = sorted(read_json(os.path.join(GAMES_DIR, sport, 'failures.json'), {}))
            if fails:
                print(sport, fetch_dates(sport, fails))
    else:
        sport, start, end = argv[0], argv[1], argv[2]
        keep = None
        if '--ncaa-tournament' in argv[3:]:
            keep = lambda g: (g.get('note') or '').startswith("NCAA Men's Basketball Championship")
        saved, failed = fetch_dates(sport, date_range(start, end), keep=keep)
        print(f'{sport} {start}..{end}: {saved} games, {len(failed)} failed dates')


if __name__ == '__main__':
    main(sys.argv[1:])
