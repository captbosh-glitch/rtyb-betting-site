"""
Odds for the non-NHL sports from the Unabated free API, auto-published.

Writes data_feed/unabated/{sport}.json, which sport_build.py merges under
the admin's saved odds (data_admin/odds/{sport}.json): a market Chris saved
always wins, the feed fills everything else. The admin page reads the same
file to show what's still missing.

  {"updated": iso,                                              last time anything here changed
   "status": {"1": "ok", "2": "failed", ...},                   last run, per bet type
   "unmatched": ["Team A @ Team B", ...],                        events no RTYB game matched
   "games": {"date|away|home": {
      date, away, home, start,
      segments: {seg: {ml: {away, home},                        best price per side
                       ats: {away: {line, price}, home: {line, price}},
                       total: {line, over, under}}},            consensus line, best price at it
      books: {seg: {ml:    {bookId: {away: {price, link}, home: {...}}},
                    ats:   {bookId: {away: {line, price, link}, home: {...}}},
                    total: {bookId: {line, over: {price, link}, under: {...}}}}}}}}

Best odds: moneyline = the best price on each side across the sportsbooks.
Spread / total = the line the most books post, then the best price on each
side at that line (prices on different lines can't be compared). Exchanges
and pick'em apps are kept in "books" for the comparison page but don't set
the best price.

Rules that keep it honest:
  - a game's odds freeze at its start time (the last pull before it is the
    closing line the site grades against)
  - a failed request never wipes what an earlier run found
  - every Gambly link gets the partner code (?utm_campaign=rtyb) before it
    is saved -- Unabated's free tier requires it; tests/test_unabated.py
    fails the build if one is missing

Free tier: one odds request every 5 seconds per key, and the API returns
"Unexpected error" at random, so each bet type is asked for on its own and
retried. Requires UNABATED_API_KEY (a GitHub Actions secret, never in code).
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = 'https://data.unabated.com'
KEY = os.environ.get('UNABATED_API_KEY', '').strip()
ET = ZoneInfo('America/New_York')
OUT_DIR = os.path.join(ROOT, 'data_feed', 'unabated')

PARTNER_CODE = 'rtyb'
GAP = 5.5            # seconds between requests (limit is one per 5s)
TRIES = 3            # per bet type per run
LOOKAHEAD_DAYS = 7   # games this far out get odds
TEAMS_MAX_AGE = timedelta(days=7)
SOURCES_MAX_AGE = timedelta(days=1)

# RTYB sport -> Unabated league route
LEAGUE = {'nhl': 'nhl', 'nfl': 'nfl', 'nba': 'nba', 'wnba': 'wnba', 'mlb': 'mlb', 'ncaaf': 'cfb', 'ncaab': 'cbb'}
# Unabated bet type ids (98: 3-way moneyline, home / away / tie)
BT_ML, BT_SPREAD, BT_TOTAL, BT_ML3 = 1, 2, 3, 98
# Unabated period type id -> RTYB segment, per sport type
PERIOD_SEG = {'period': {8: '1p'}, 'spread': {4: '1q', 2: '1h'}, 'baseball': {20: 'f5'}}
# NHL's 1st period: 2-way and 3-way moneyline and the total (no spread)
NHL_BETS = (BT_ML, BT_ML3, BT_TOTAL)
# Sportsbooks that set the best price (matched against /sources names)
SPORTSBOOKS = ('draftkings', 'fanduel', 'mgm', 'caesars', 'thescore', 'fanatics')
# Their ids, for when /sources fails (DraftKings, FanDuel, BetMGM, Caesars,
# theScore US / Fast, Fanatics, BetMGM Direct). RTYB is for US bettors, so
# Canadian books (theScore CA, id 60) never set the best price.
SPORTSBOOK_IDS = {'1', '2', '4', '20', '36', '118', '86', '80'}

# Unabated team name -> RTYB team location, where the names don't line up
ALIASES = {
    'miami ohio': 'miami oh', 'miami florida': 'miami', 'mississippi': 'ole miss',
    'st francis pa': 'st francis', 'nc greensboro': 'unc greensboro', 'umkc': 'kansas city',
    'oakland athletics': 'athletics', 'louisiana lafayette': 'louisiana', 'ul lafayette': 'louisiana',
    'middle tennessee state': 'middle tennessee', 'sam houston state': 'sam houston',
    'iupui': 'iu indianapolis', 'detroit': 'detroit mercy', 'wisconsin green bay': 'green bay',
    'wisconsin milwaukee': 'milwaukee', 'arkansas little rock': 'little rock', 'nebraska omaha': 'omaha',
    'ipfw': 'purdue fort wayne', 'fort wayne': 'purdue fort wayne', 'queens': 'queens university',
    'etsu': 'east tennessee state', 'semo': 'southeast missouri state', 'se missouri state': 'southeast missouri state',
    'md eastern shore': 'maryland eastern shore', 'ark pine bluff': 'arkansas pine bluff',
    'nicholls state': 'nicholls', 'cs fullerton': 'cal state fullerton', 'unc charlotte': 'charlotte',
    'new orleans': 'lsu new orleans', 'connecticut': 'uconn', 'central florida': 'ucf',
    'appalachian state': 'app state', 'albany ny': 'ualbany',
}


# ------------------------------------------------------------------ helpers

def read_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False, sort_keys=True)


def parse_time(s):
    if not s:
        return None
    s = s.replace('Z', '+00:00')
    if re.search(r'T\d\d:\d\d\+', s):           # ESPN's "2026-11-12T03:00Z"
        s = s.replace('+', ':00+', 1)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def tag_link(link):
    """The Gambly link with the partner code set (replacing any other)."""
    if not link:
        return None
    parts = urllib.parse.urlsplit(link)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if k != 'utm_campaign']
    query.append(('utm_campaign', PARTNER_CODE))
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def norm(s):
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode()
    s = s.lower().replace('&', ' and ').replace('(', ' ').replace(')', ' ')
    s = re.sub(r"[.'’]", '', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    s = re.sub(r'^saint ', 'st ', s)
    return re.sub(r' st$', ' state', s)


_last_call = [0.0]


def get(path):
    """GET with the 5-second spacing. Returns (data, error)."""
    wait = GAP - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    req = urllib.request.Request(BASE + path, headers={'X-Api-Key': KEY, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f'HTTP {e.code}'
    except (OSError, ValueError) as e:
        return None, f'no response ({e.__class__.__name__})'
    if body.get('success') is not True:
        return None, '; '.join(body.get('messages') or ['unsuccessful'])
    return body.get('data'), None


def get_retry(path):
    err = None
    for _ in range(TRIES):
        data, err = get(path)
        if err is None:
            return data, None
        if err == 'HTTP 401':
            break
    return None, err


def cached(name, path, max_age):
    """Slow-changing lookups (teams, sportsbooks), refreshed when stale."""
    file = os.path.join(OUT_DIR, 'lookups', name + '.json')
    doc = read_json(file, {})
    fetched = parse_time(doc.get('fetched'))
    if fetched and datetime.now(timezone.utc) - fetched < max_age and doc.get('data'):
        return doc['data']
    data, err = get_retry(path)
    if err:
        print(f'  {name}: {err}; using the saved copy' if doc.get('data') else f'  {name}: {err}', file=sys.stderr)
        return doc.get('data') or []
    write_json(file, {'fetched': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'data': data})
    return data


# ------------------------------------------------------------- RTYB games

def upcoming_nhl(now):
    """NHL games from the schedule files (build_site.py's, not data_seed):
    this run's fetch (schedule_fresh.json) over the last merged one."""
    seen = {}
    for name in ('schedule_data.json', 'schedule_fresh.json'):
        for date, games in (read_json(os.path.join(ROOT, name), {}).get('games') or {}).items():
            for g in games:
                start = parse_time(g.get('startTimeUTC'))
                if start and now < start <= now + timedelta(days=LOOKAHEAD_DAYS) and g.get('away') and g.get('home'):
                    seen[g.get('id') or f"{date}|{g['away']}|{g['home']}"] = {
                        'date': date, 'away': g['away'], 'home': g['home'], 'start': g['startTimeUTC'], '_start': start}
    return list(seen.values())


def upcoming_games(sport, now):
    """RTYB games that haven't started and start within the lookahead."""
    if sport == 'nhl':
        return upcoming_nhl(now)
    d = os.path.join(ROOT, 'data_seed', 'games', sport)
    out = []
    if not os.path.isdir(d):
        return out
    seasons = sorted(n for n in os.listdir(d) if n[:4].isdigit() and n.endswith('.json'))[-2:]
    for name in seasons:
        for g in (read_json(os.path.join(d, name), {}).get('games') or {}).values():
            start = parse_time(g.get('start'))
            if start and now < start <= now + timedelta(days=LOOKAHEAD_DAYS) and g.get('away') and g.get('home'):
                out.append(dict(g, _start=start))
    return out


def team_aliases(sport):
    """RTYB slug -> set of normalized names it goes by."""
    if sport == 'nhl':
        sys.path.insert(0, os.path.join(ROOT, 'scripts'))
        from fetch_odds_theoddsapi import TEAM_NAME_TO_ABBREV
        out = {}
        for name, code in TEAM_NAME_TO_ABBREV.items():
            out.setdefault(code, {norm(code)}).add(norm(name))
        return out
    doc = read_json(os.path.join(ROOT, 'data_seed', 'teams', sport + '.json'), {})
    out = {}
    for t in doc.get('teams') or []:
        names = {t.get('name'), t.get('location'), t.get('short'), t.get('code'),
                 f"{t.get('location', '')} {t.get('nickname', '')}"}
        out[t['slug']] = {norm(n) for n in names if n}
    return out


def similarity(name, aliases):
    """1.0 exact, else word overlap (0-1) between the Unabated name and the
    best of the RTYB team's names."""
    n = norm(name)
    n = ALIASES.get(n, n)
    if n in aliases:
        return 1.0
    words = set(n.split())
    best = 0.0
    for a in aliases:
        aw = set(a.split())
        if words and aw:
            best = max(best, len(words & aw) / len(words | aw))
    return best


def match_event(away_name, home_name, start, games, aliases):
    """The RTYB game for an Unabated event: starts within 4 hours, and both
    teams match (either way round -- neutral sites can flip home/away).
    Returns (game, flipped) or (None, False)."""
    best, best_score, flipped = None, 0.0, False
    for g in games:
        if abs((g['_start'] - start).total_seconds()) > 4 * 3600:
            continue
        aa, ha = aliases.get(g['away'], set()), aliases.get(g['home'], set())
        for flip, (x, y) in ((False, (aa, ha)), (True, (ha, aa))):
            s1, s2 = similarity(away_name, x), similarity(home_name, y)
            ok = min(s1, s2) >= 0.5 or (max(s1, s2) == 1.0 and min(s1, s2) >= 0.34)
            if ok and s1 + s2 > best_score:
                best, best_score, flipped = g, s1 + s2, flip
    return best, flipped


# ------------------------------------------------------------- odds board

def is_price(p):
    return isinstance(p, (int, float)) and abs(p) >= 100


def is_half(n):
    return isinstance(n, (int, float)) and abs(n * 2 - round(n * 2)) < 1e-9


def lines_of(side):
    """{bookId: line} for a side's open main lines."""
    out = {}
    for book, line in (side.get('marketSourceLines') or {}).items():
        if line.get('statusId') != 1 or line.get('disabled') or not is_price(line.get('price')):
            continue
        out[str(line.get('marketSourceId') or book)] = line
    return out


def read_board(data, sport_type):
    """Pregame groups -> [{eventId, start, teams: {0: id, 1: id}, seg, bet, sides: {idx: side}}]."""
    out = []
    seg_of = PERIOD_SEG.get(sport_type, {})
    for league in ((data or {}).get('odds') or {}).values():
        for period in (league.get('periodTypes') or {}).values():
            seg = seg_of.get(period.get('periodTypeId'))
            if not seg:
                continue
            for group in (period.get('pregame') or {}).values():
                teams = {int(t.get('sideIndex')): t.get('teamId') for t in (group.get('eventTeams') or {}).values()}
                sides = {}
                for s in (group.get('sides') or {}).values():
                    sides.setdefault(int(s.get('sideIndex', -1)), s)
                out.append({'eventId': group.get('eventId'), 'start': parse_time(group.get('eventStart')),
                            'teams': teams, 'seg': seg, 'bet': group.get('betTypeId'), 'sides': sides,
                            'name': group.get('eventName') or ''})
    return out


def is_over(side):
    name = str(side.get('sideName') or '').lower()
    if name.startswith('o'):
        return True
    if name.startswith('u'):
        return False
    return side.get('sideIndex') == 0


def books_for(bet, sides, flipped):
    """This group's per-book prices in RTYB terms (away/home or over/under)."""
    def link(l):
        return tag_link(l.get('deepLink'))
    out = {}
    if bet == BT_TOTAL:
        over = next((s for s in sides.values() if is_over(s)), None)
        under = next((s for s in sides.values() if s is not over), None)
        if not over or not under:
            return out
        lo, lu = lines_of(over), lines_of(under)
        for b in lo.keys() & lu.keys():
            pts = lo[b].get('points')
            if not is_half(pts) or pts <= 0 or lu[b].get('points') != pts:
                continue
            out[b] = {'line': pts, 'over': {'price': lo[b]['price'], 'link': link(lo[b])},
                      'under': {'price': lu[b]['price'], 'link': link(lu[b])}}
        return out
    a, h = sides.get(0), sides.get(1)
    if flipped:
        a, h = h, a
    if not a or not h:
        return out
    la, lh = lines_of(a), lines_of(h)
    if bet == BT_ML3:
        ld = lines_of(sides[2]) if sides.get(2) else {}
        for b in la.keys() & lh.keys() & ld.keys():
            out[b] = {'away': {'price': la[b]['price'], 'link': link(la[b])},
                      'draw': {'price': ld[b]['price'], 'link': link(ld[b])},
                      'home': {'price': lh[b]['price'], 'link': link(lh[b])}}
        return out
    for b in la.keys() & lh.keys():
        if bet == BT_ML:
            out[b] = {'away': {'price': la[b]['price'], 'link': link(la[b])},
                      'home': {'price': lh[b]['price'], 'link': link(lh[b])}}
        else:
            pa, ph = la[b].get('points'), lh[b].get('points')
            if not is_half(pa) or ph is None or abs(pa + ph) > 1e-9:
                continue
            out[b] = {'away': {'line': pa, 'price': la[b]['price'], 'link': link(la[b])},
                      'home': {'line': ph, 'price': lh[b]['price'], 'link': link(lh[b])}}
    return out


def best_of(market, books, sharp):
    """Best odds from the sportsbooks in `sharp` (all books if that's empty)."""
    use = {b: v for b, v in books.items() if not sharp or b in sharp}
    if not use and market == 'ml3':
        use = books   # the free tier's 3-way comes only from exchanges (Underdog)
    if not use:
        return None
    if market in ('ml', 'ml3'):
        return {side: max(v[side]['price'] for v in use.values()) for side in next(iter(use.values()))}
    key = (lambda v: v['away']['line']) if market == 'ats' else (lambda v: v['line'])
    counts = {}
    for v in use.values():
        counts[key(v)] = counts.get(key(v), 0) + 1
    # most books; ties go to the line nearest the median of all posted lines
    posted = sorted(key(v) for v in use.values())
    median = posted[len(posted) // 2]
    line = max(counts, key=lambda x: (counts[x], -abs(x - median)))
    at = [v for v in use.values() if key(v) == line]
    if market == 'ats':
        return {'away': {'line': line, 'price': max(v['away']['price'] for v in at)},
                'home': {'line': -line if line else 0, 'price': max(v['home']['price'] for v in at)}}
    return {'line': line, 'over': max(v['over']['price'] for v in at),
            'under': max(v['under']['price'] for v in at)}


MARKET = {BT_ML: 'ml', BT_SPREAD: 'ats', BT_TOTAL: 'total', BT_ML3: 'ml3'}


# ------------------------------------------------------------------ main

def run_sport(sport, sport_type, segments, has_ml, now, ml3=False):
    path = os.path.join(OUT_DIR, sport + '.json')
    doc = read_json(path, {})
    games_doc = doc.get('games') or {}
    upcoming = upcoming_games(sport, now)
    league = LEAGUE[sport]
    stamp = now.isoformat(timespec='seconds')

    # odds freeze at the start: drop per-book detail once a game is underway
    for g in games_doc.values():
        start = parse_time(g.get('start'))
        if start and start <= now:
            g.pop('books', None)

    if not upcoming:
        if doc and (doc.get('unmatched') or doc.get('games') != read_json(path, {}).get('games')):
            doc.update({'games': games_doc, 'unmatched': []})
            write_json(path, doc)
        print(f'{sport}: no upcoming games')
        return

    teams = {t.get('id'): t.get('name') for t in cached(f'teams_{league}', f'/team/{league}', TEAMS_MAX_AGE)}
    sources = cached(f'sources_{league}', f'/market/{league}/straight/sources', SOURCES_MAX_AGE)
    sharp = {str(s.get('id')) for s in sources if any(w in norm(s.get('name')).replace(' ', '') for w in SPORTSBOOKS)
             and not norm(s.get('name')).endswith(' ca')}
    sharp = sharp or SPORTSBOOK_IDS
    aliases = team_aliases(sport)
    last_start = max(g['_start'] for g in upcoming)

    status, unmatched, filled = {}, set(), 0
    bets = NHL_BETS if sport == 'nhl' else [b for b in (BT_ML, BT_SPREAD, BT_TOTAL) if b != BT_ML or has_ml]
    if ml3 and has_ml and BT_ML3 not in bets:   # 3-way (tie included), for the 3-way records' units
        bets = bets + [BT_ML3]
    for bet in bets:
        data, err = get_retry(f'/market/{league}/straight/odds?betTypeId={bet}')
        status[str(bet)] = 'ok' if err is None else f'failed: {err}'
        if err:
            continue
        market = MARKET[bet]
        for grp in read_board(data, sport_type):
            if grp['bet'] != bet or grp['seg'] not in segments or not grp['start']:
                continue
            an, hn = teams.get(grp['teams'].get(0)), teams.get(grp['teams'].get(1))
            g, flipped = match_event(an, hn, grp['start'], upcoming, aliases)
            if not g:
                # started games aren't looked for; later ones aren't on RTYB's schedule yet
                if now < grp['start'] <= last_start:
                    unmatched.add(f'{an} @ {hn}')
                continue
            books = books_for(bet, grp['sides'], flipped)
            if sport_type == 'baseball' and market == 'ats':   # RTYB's F5 run line is always 0.5
                books = {b: v for b, v in books.items() if abs(v['away']['line']) == 0.5}
            best = best_of(market, books, sharp)
            if not best:
                continue
            key = f"{g['date']}|{g['away']}|{g['home']}"
            rec = games_doc.setdefault(key, {'date': g['date'], 'away': g['away'], 'home': g['home'], 'segments': {}})
            rec['start'] = g.get('start')
            rec.setdefault('segments', {}).setdefault(grp['seg'], {})[market] = best
            rec.setdefault('books', {}).setdefault(grp['seg'], {})[market] = books
            filled += 1

    new = {'status': status, 'unmatched': sorted(unmatched), 'games': games_doc}
    old = read_json(path, {})
    # only rewrite (and so only commit) when something actually changed
    if any(old.get(k) != v for k, v in new.items()):
        write_json(path, dict(new, updated=stamp))
    print(f"{sport}: {len(upcoming)} upcoming games, {filled} markets filled, "
          f"bet types {status}, {len(unmatched)} unmatched events")


def main():
    if not KEY:
        print('WARN: UNABATED_API_KEY not set -- skipping the Unabated odds feed', file=sys.stderr)
        return
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    import sports
    now = datetime.now(timezone.utc)
    want = set(sys.argv[1:])
    for sp in sports.SPORTS:
        if sp['key'] not in LEAGUE or (want and sp['key'] not in want):
            continue
        segs = {s['key'] for s in sp['segments']}
        has_ml = any(sports.has_ml(s) for s in sp['segments'])
        try:
            # launched sports also get the 3-way moneyline (one more request each)
            run_sport(sp['key'], sp['sport_type'], segs, has_ml, now, ml3=bool(sp.get('launched')))
        except Exception as e:   # one sport's surprise shouldn't stop the others
            print(f"{sp['key']}: skipped -- {e.__class__.__name__}: {e}", file=sys.stderr)


if __name__ == '__main__':
    main()
