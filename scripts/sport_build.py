"""
Data for the non-NHL sports' Matchups, Stats, Trends and team pages.

For each sport in scripts/sports.py: reads the games the loader saved
(data_seed/games/{sport}/{season}.json), the odds saved in the admin
(data_admin/odds/{sport}.json), grades every game with grading.py, and
writes {slug}/data.json for the pages (assets/sport.js renders them):

  games    current season by ET date: teams, status, line scores, odds and
           the graded result per segment + market
  stats    current season: per team and league-wide, per segment
  trends   League Trends per date, NHL's rules (league_trends.py) adapted
           to SU / ATS / Totals / NRFI; each date freezes when its first
           game starts (trends_log/{sport}.json) and only results update

Odds-based numbers (ATS, Totals, favorites, units) only count games that
have odds; records say how many ("based on N games with odds"). Games
without odds still grade SU and NRFI/YRFI.
"""
import glob
import json
import math
import os
from datetime import date as Date, datetime, timezone
from zoneinfo import ZoneInfo

import grading
import icons
import sports
import trend_rules
import trends as trend_cards

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')

# Same thresholds as NHL League Trends (league_trends.CONFIG).
CONFIG = {
    'rate_diff_pts': 8,
    'units_threshold': 2.0,
    'min_games': 10,
    'min_streak': 5,
    'small_rate': 20,
    'streak_weight': 4,
    'shown': 6,
    'max_per_market': 2,
    'first_backfill_days': 30,   # a new trends log starts this many days back
    'team_streak_min': 4,        # team streaks shown on Trends / team pages
}

# "Coming off a big loss" by sport (full-game margin).
BIG_LOSS = {'nfl': 14, 'ncaaf': 17, 'nba': 10, 'wnba': 10, 'ncaab': 10, 'mlb': 4}
BIG_LOSS_WORD = {'mlb': 'runs'}

# Season labels: these leagues' seasons span two calendar years and ESPN
# numbers them by the year they end (2026 = 2025-26).
SPAN_YEARS = {'nba', 'ncaab'}


def season_label(sport, season):
    return f'{season - 1}–{str(season)[2:]}' if sport in SPAN_YEARS else str(season)


def read_json(path, default):
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'), ensure_ascii=False)


# ------------------------------------------------------------------ grading

def compact(seg_key, sport_type, g):
    """grading.py's result for one segment, trimmed for data.json:
    sc [away, home]; su / ats from the away side (W L T/P NA); tot O U P NA;
    rfi Y N NA; u units per side (only where odds were saved; ml3 is
    [away, home, tie])."""
    if g is None:
        return None
    out = {}
    if g.get('score'):
        out['sc'] = [g['score']['away'], g['score']['home']]
    if g.get('no_action'):
        out['na'] = 1
    if sport_type == 'baseball' and seg_key == '1i':
        m = g['nrfi_yrfi']
        out['rfi'] = {'W': 'Y', 'L': 'N'}.get(m['yrfi']['result'], 'NA')
        if m['yrfi']['units'] is not None and not g.get('no_action'):
            out['u'] = {'rfi': [m['yrfi']['units'], m['nrfi']['units']]}
        return out
    u = {}
    out['su'] = g['su']['away']['result']
    if g['su']['away']['units'] is not None and not g.get('no_action'):
        u['su'] = [g['su']['away']['units'], g['su']['home']['units']]
    if g.get('ml3') and not g.get('no_action'):   # the 3-way's result reads off su
        u['ml3'] = [g['ml3']['away']['units'], g['ml3']['home']['units'], g['ml3']['draw']['units']]
    if g.get('ats'):
        out['ats'] = g['ats']['away']['result']
        if not g.get('no_action'):
            u['ats'] = [g['ats']['away']['units'], g['ats']['home']['units']]
    if g.get('total'):
        out['tot'] = {'W': 'O', 'L': 'U', 'P': 'P'}.get(g['total']['over']['result'], 'NA')
        if not g.get('no_action'):
            u['tot'] = [g['total']['over']['units'], g['total']['under']['units']]
    if u:
        out['u'] = u
    return out


def load_games(sport):
    """{season: [games]} from data_seed/games/{sport}/*.json."""
    d = os.path.join(ROOT, 'data_seed', 'games', sport)
    out = {}
    if not os.path.isdir(d):
        return out
    for name in os.listdir(d):
        if not name[:4].isdigit() or not name.endswith('.json'):
            continue
        doc = read_json(os.path.join(d, name), {})
        games = [g for g in (doc.get('games') or {}).values() if g.get('season_type') in (2, 3)]
        if games:
            out[int(doc.get('season') or name[:4])] = sorted(games, key=lambda g: (g['start'] or '', g['id']))
    return out


# Source names when the feed's /sources lookup hasn't loaded (ids are the
# same across leagues).
BOOK_NAMES = {'1': 'DraftKings', '2': 'FanDuel', '4': 'BetMGM', '20': 'Caesars', '36': 'theScore',
              '60': 'theScore CA', '118': 'theScore', '86': 'Fanatics', '80': 'BetMGM', '89': 'Novig',
              '66': 'ProphetX', '105': 'Kalshi', '107': 'Polymarket', '111': 'Polymarket US',
              '121': 'Underdog', '73': 'Underdog Fantasy', '72': 'PrizePicks', '84': 'DK Pick6'}
# Exchanges, prediction markets and pick'em apps: shown after the
# sportsbooks, and they never set the best price
EXCHANGES = {'89', '66', '105', '107', '111', '121', '73', '72', '84'}
# The major sportsbooks, in column order; then the other sportsbooks and
# then the exchanges, each alphabetically
MAJOR_BOOKS = ['1', '2', '4', '80', '20']   # DraftKings, FanDuel, BetMGM (and BetMGM Direct), Caesars


def book_names():
    names = dict(BOOK_NAMES)
    for path in sorted(glob.glob(os.path.join(ROOT, 'data_feed', 'unabated', 'lookups', 'sources_*.json'))):
        for src in read_json(path, {}).get('data') or []:
            names[str(src.get('id'))] = src.get('name')
    return names


EXTRA_BOOKS = {'consensus': 'Consensus'}
# Every source shows on the Odds page; these never set the best price
NO_BEST = {'60'}   # theScore CA (RTYB is for US bettors)
# Logos: assets/books/{source id}.{ext}, downloaded from Unabated's /sources
# thumbnails by fetch_odds_unabated.py; else a hand-made assets/books/{key}.svg
# or .png. The page shows the source's name when there's neither.
BOOK_KEYS = {'1': 'draftkings', '2': 'fanduel', '4': 'betmgm', '80': 'betmgm', '20': 'caesars',
             '36': 'thescore', '118': 'thescore', '86': 'fanatics', '121': 'underdog'}
LOGO_EXTS = ('svg', 'png', 'webp', 'jpg')


def book_logo(book_id):
    for key in (book_id, BOOK_KEYS.get(book_id)):
        for ext in LOGO_EXTS:
            if key and os.path.exists(os.path.join(ROOT, 'assets', 'books', f'{key}.{ext}')):
                return f'assets/books/{key}.{ext}'
    return None


def source_order(ids, names):
    """Major sportsbooks first, then the other sportsbooks, then exchanges
    and prediction markets, each group alphabetically."""
    def key(b):
        if b in EXCHANGES:
            return (2, 0, (names.get(b) or b).lower())
        if b in MAJOR_BOOKS:
            return (0, MAJOR_BOOKS.index(b), '')
        return (1, 0, (names.get(b) or b).lower())
    return sorted(ids, key=key)


def _unlinked(row):
    if isinstance(row, dict):
        return {k: _unlinked(v) for k, v in row.items() if k != 'link'}
    return row


def best_price(market, books):
    """The best price per side, by the same rule the feed uses (sportsbooks
    only; spreads and totals at the line most books post). BTTS rows (the
    admin's consensus) are already one price per side."""
    import fetch_odds_unabated as feed
    if not books:
        return None
    if market == 'btts':
        row = next(iter(books.values()))
        return {s: (row.get(s) or {}).get('price') for s in ('yes', 'no')}
    sharp = {b for b in books if b not in EXCHANGES and b not in EXTRA_BOOKS and b not in NO_BEST}
    try:
        return feed.best_of(market, books, sharp)
    except (KeyError, TypeError, ValueError):
        return None


def write_odds_page(sp, slug_dir, now_utc, schedule, meta=None, extra=None, weeks=None):
    """The Odds page's data (assets/sport.js), for every scheduled game:

      {slug}/odds.json          index: sources (name, logo, exchange), source
                                order, markets with data, game counts per date
                                (the calendar), weeks (weekly sports) and meta
      {slug}/odds/{date}.json   that date's games: {away, home, start, state,
                                books, best, open, opens?}

    Games that haven't started carry every source's live price (links have the
    partner code, fetch_odds_unabated.tag_link); started and finished games
    carry each source's closing line (`books`) and opening line (`opens`) from
    data_feed/unabated/history/, without links. `best` is the best price per
    side (the green outline), `open` the best opening price (the Open column).

    schedule: {date: [{away, home, start, state, score?, detail?, res?}]}, state
    'pre' | 'live' | 'final', score {segment: [away, home]} once the game
    starts, detail the live clock, res the graded result once it's final. `meta` (NHL, whose data.json has another shape) carries label,
    segments and teams. `extra` (NHL's admin-entered BTTS) adds markets the
    feed doesn't carry: [{date, away, home, start, books: {seg: {m: {book: row}}}}]
    under the book ids EXTRA_BOOKS names."""
    feed = read_json(os.path.join(ROOT, 'data_feed', 'unabated', f"{sp['key']}.json"), {})
    hist_dir = os.path.join(ROOT, 'data_feed', 'unabated', 'history', sp['key'])
    out_dir = os.path.join(slug_dir, 'odds')
    index_path = os.path.join(slug_dir, 'odds.json')
    live = {(g['date'], g['away'], g['home']): g for g in (feed.get('games') or {}).values()}
    extras = {}
    for x in extra or []:
        for seg, mk in x['books'].items():
            extras.setdefault((x['date'], x['away'], x['home']), {}).setdefault(seg, {}).update(mk)

    shown = {(x[0], x[1]) for x in sp['family_markets']}

    def clean(books):
        """Every source, in the markets this sport's pages show (3-way: NHL only)."""
        return {seg: {m: dict(by) for m, by in mk.items() if (seg, m) in shown}
                for seg, mk in (books or {}).items()}

    def merge(a, b):
        out = {seg: dict(mk) for seg, mk in (a or {}).items()}
        for seg, mk in (b or {}).items():
            out.setdefault(seg, {}).update(mk)
        return out

    def bests(books):
        return {seg: {m: v for m, v in ((m, best_price(m, by)) for m, by in mk.items()) if v}
                for seg, mk in books.items()}

    dates = set(schedule)
    days, line_days, used, have = {}, [], set(), set()
    os.makedirs(out_dir, exist_ok=True)
    for d in sorted(dates):
        hist = (read_json(os.path.join(hist_dir, f'{d}.json'), {}).get('games') or {})
        rows = []
        for sg in sorted(schedule[d], key=lambda x: (x.get('start') or '', x['away'])):
            key = (d, sg['away'], sg['home'])
            try:
                started = bool(sg.get('start')) and datetime.fromisoformat(sg['start'].replace('Z', '+00:00')) <= now_utc
            except ValueError:
                started = False
            state = sg.get('state') or ('pre' if not started else 'live')
            if state == 'pre' and started:
                state = 'live'
            h = hist.get(f"{sg['away']}|{sg['home']}") or {}
            lg = live.get(key) or {}
            plain_extra = {seg: {m: _unlinked(v) for m, v in mk.items()} for seg, mk in (extras.get(key) or {}).items()}
            if state == 'pre':
                books = merge(clean(lg.get('books')), extras.get(key))
            else:
                books = merge(clean(h.get('close') or _unlinked(lg.get('books'))), plain_extra)
            # the Open column keeps the opening line before, during and after the game
            opens = merge(clean(h.get('open') or lg.get('opens')), plain_extra)
            game = {'books': books, 'away': sg['away'], 'home': sg['home'], 'start': sg.get('start'), 'state': state,
                    'best': bests(books), 'open': bests(opens) if opens else {}}
            if state != 'pre' and sg.get('score'):
                game['score'] = sg['score']   # {segment: [away, home]} so far
            if state == 'final' and sg.get('res'):
                # each segment's result, from the away side (su / ats / tot /
                # btts / rfi): past dates show which side won each market
                game['res'] = {seg: {m: v for m, v in r.items() if m != 'u'} for seg, r in sg['res'].items() if r}
            if state == 'live' and sg.get('detail'):
                game['detail'] = sg['detail']   # the live clock: "4:58 - 3rd", "End 1st"
            for seg, mk in books.items():
                for m, by in mk.items():
                    if by:
                        have.add((seg, m))
                        used.update(by)
            rows.append(game)
        days[d] = len(rows)
        if any(g['books'] for g in rows):
            line_days.append(d)
        write_json(os.path.join(out_dir, f'{d}.json'), {'date': d, 'games': rows})
    for name in os.listdir(out_dir):
        if name.endswith('.json') and name[:-5] not in dates:
            os.remove(os.path.join(out_dir, name))
    names = dict(book_names(), **EXTRA_BOOKS)
    markets = [list(x) for x in sp['family_markets'] if not have or (x[0], x[1]) in have]
    write_json(index_path, dict(meta or {}, updated=feed.get('updated'), calendar=sp['calendar'],
                                weeks=weeks or None, markets=markets, days=days, lineDays=line_days,
                                order=source_order(used, names),
                                sources={b: dict({'name': names.get(b, f'Source {b}')},
                                                 **({'logo': book_logo(b)} if book_logo(b) else {}),
                                                 **({'x': 1} if b in EXCHANGES else {})) for b in used}))


def seg_scores(sp, g):
    """{segment: [away, home]} over the periods played so far (a data.json game; live games
    show the score in progress), or None before the first one."""
    out = {}
    for s in sp['segments']:
        n = {'1i': 1, 'f5': 5}.get(s['key']) or grading.SEGMENT_PERIODS.get(sp['key'], grading.SEGMENT_PERIODS['default']).get(s['key'])
        a = [x for x in (g.get('als') or [])[:n or 0] if grading.num(x) is not None]
        h = [x for x in (g.get('hls') or [])[:n or 0] if grading.num(x) is not None]
        if a and h:
            out[s['key']] = [sum(a), sum(h)]
    return out or None


def merge_odds(admin, feed):
    """Odds the pages grade against: the Unabated feed (fetch_odds_unabated.py,
    auto-published) with the admin's saved odds on top. A market Chris saved
    always wins; one he left blank, or never saved, comes from the feed."""
    out = {}
    for key in set(admin) | set(feed):
        a, f = admin.get(key) or {}, feed.get(key) or {}
        segs = {}
        for seg in set(a.get('segments') or {}) | set(f.get('segments') or {}):
            mine = (a.get('segments') or {}).get(seg) or {}
            auto = (f.get('segments') or {}).get(seg) or {}
            # 3-way ML is NHL only (nhl_sport.py); this builds the other sports
            merged = {m: v for m, v in auto.items() if v is not None and m != 'ml3'}
            merged.update({m: v for m, v in mine.items() if v is not None and m != 'ml3'})
            if merged:
                segs[seg] = merged
        base = a or f
        out[key] = {'date': base.get('date'), 'away': base.get('away'), 'home': base.get('home'), 'segments': segs}
    return out


def grade_all(sp, games, odds):
    segs = [s['key'] for s in sp['segments']]
    for g in games:
        o = odds.get(f"{g['date']}|{g['away']}|{g['home']}")
        g['_odds'] = (o or {}).get('segments') or {}
        full = grading.grade_game(sp['key'], sp['sport_type'], segs, g, o)
        g['_res'] = {k: compact(k, sp['sport_type'], v) for k, v in full.items()}


# -------------------------------------------------------------------- stats

class Rec:
    """W-L-T(P) plus units over the games that had odds."""
    __slots__ = ('w', 'l', 't', 'units', 'priced')

    def __init__(self):
        self.w = self.l = self.t = self.priced = 0
        self.units = 0.0

    def add(self, res, units):
        if res in ('NA', None):
            return
        if res == 'W':
            self.w += 1
        elif res == 'L':
            self.l += 1
        else:
            self.t += 1
        if units is not None:
            self.units += units
            self.priced += 1

    @property
    def n(self):
        return self.w + self.l + self.t

    @property
    def decisions(self):
        """W + L: ties and pushes aren't decisions (they're 0u and left
        out of rates, and minimum samples count decisions, not games)."""
        return self.w + self.l

    @property
    def rate(self):
        return self.w / (self.w + self.l) if (self.w + self.l) else None

    def out(self):
        """[w, l, t, units, games with odds]"""
        return [self.w, self.l, self.t, round(self.units, 2), self.priced]


def flip(r):
    return {'W': 'L', 'L': 'W'}.get(r, r)


def side_res(res, market, side):
    """Result for one side: away results are stored; home is the flip."""
    r = res.get(market)
    return r if side == 'away' else flip(r)


def side_units(res, market, side):
    u = (res.get('u') or {}).get(market)
    return None if u is None else u[0 if side == 'away' else 1]


def favorite(odds_seg):
    """'away' / 'home' by the shorter moneyline, else by the ATS line."""
    ml = (odds_seg or {}).get('ml') or {}
    a, h = ml.get('away'), ml.get('home')
    if isinstance(a, (int, float)) and isinstance(h, (int, float)):
        ia = -a / (-a + 100) if a < 0 else 100 / (a + 100)
        ih = -h / (-h + 100) if h < 0 else 100 / (h + 100)
        if ia != ih:
            return 'away' if ia > ih else 'home'
    ats = (odds_seg or {}).get('ats') or {}
    line = (ats.get('away') or {}).get('line')
    if isinstance(line, (int, float)) and line != 0:
        return 'away' if line < 0 else 'home'
    return None


def season_stats(sp, games):
    """Team and league stats per segment for one season's graded games."""
    rfi_seg = sp['sport_type'] == 'baseball'
    out = {'teams': {}, 'league': {}}
    for seg in sp['segments']:
        k = seg['key']
        teams, lg = {}, None
        if rfi_seg and k == '1i':
            lg = {'gp': 0, 'yrfi': Rec(), 'nrfi': Rec(), 'dist': {}}
        else:
            # Both sides of each market, so the Stats page's Season Results
            # can show each side's record and units (ties / pushes kept).
            lg = {'gp': 0, 'home': Rec(), 'away': Rec(), 'fav_su': Rec(), 'dog_su': Rec(),
                  'fav_ats': Rec(), 'dog_ats': Rec(), 'home_ats': Rec(), 'away_ats': Rec(),
                  'over': Rec(), 'under': Rec(), 'pts': 0, 'scored': 0, 'dist': {}, 'na': 0}
        for g in games:
            res = (g.get('_res') or {}).get(k)
            if not res:
                continue
            if res.get('na'):
                if 'na' in lg:
                    lg['na'] += 1
                continue
            sc = res.get('sc')
            lg['gp'] += 1
            total_pts = sc[0] + sc[1]
            key = str(int(total_pts)) if float(total_pts).is_integer() else str(total_pts)
            lg['dist'][key] = lg['dist'].get(key, 0) + 1
            for side in ('away', 'home'):
                slug = g[side]
                t = teams.get(slug)
                if t is None:
                    if rfi_seg and k == '1i':
                        t = teams[slug] = {'gp': 0, 'yrfi': Rec(), 'scored': 0, 'allowed': 0,
                                           'home': Rec(), 'away': Rec()}
                    else:
                        t = teams[slug] = {'gp': 0, 'su': Rec(), 'home': Rec(), 'away': Rec(), 'ats': Rec(),
                                           'over': Rec(), 'pf': 0, 'pa': 0}
                t['gp'] += 1
                mine, theirs = (sc[0], sc[1]) if side == 'away' else (sc[1], sc[0])
                if rfi_seg and k == '1i':
                    y = res['rfi']
                    yu = (res.get('u') or {}).get('rfi')
                    t['yrfi'].add('W' if y == 'Y' else 'L', None if yu is None else yu[0])
                    t[side].add('W' if y == 'Y' else 'L', None)   # YRFI rate home / away
                    t['scored'] += mine > 0
                    t['allowed'] += theirs > 0
                else:
                    t['su'].add(side_res(res, 'su', side), side_units(res, 'su', side))
                    t[side].add(side_res(res, 'su', side), side_units(res, 'su', side))
                    if 'ats' in res:
                        t['ats'].add(side_res(res, 'ats', side), side_units(res, 'ats', side))
                    if 'tot' in res:
                        t['over'].add({'O': 'W', 'U': 'L', 'P': 'P'}.get(res['tot']), (res.get('u') or {}).get('tot', [None])[0])
                    t['pf'] += mine
                    t['pa'] += theirs
            if rfi_seg and k == '1i':
                yu = (res.get('u') or {}).get('rfi')
                lg['yrfi'].add('W' if res['rfi'] == 'Y' else 'L', None if yu is None else yu[0])
                lg['nrfi'].add('W' if res['rfi'] == 'N' else 'L', None if yu is None else yu[1])
            else:
                lg['home'].add(flip(res['su']), side_units(res, 'su', 'home'))
                lg['away'].add(res['su'], side_units(res, 'su', 'away'))
                fav = favorite(g['_odds'].get(k))
                if fav:
                    dog = 'home' if fav == 'away' else 'away'
                    lg['fav_su'].add(side_res(res, 'su', fav), side_units(res, 'su', fav))
                    lg['dog_su'].add(side_res(res, 'su', dog), side_units(res, 'su', dog))
                    if 'ats' in res:
                        lg['fav_ats'].add(side_res(res, 'ats', fav), side_units(res, 'ats', fav))
                        lg['dog_ats'].add(side_res(res, 'ats', dog), side_units(res, 'ats', dog))
                if 'ats' in res:
                    lg['home_ats'].add(flip(res['ats']), side_units(res, 'ats', 'home'))
                    lg['away_ats'].add(res['ats'], side_units(res, 'ats', 'away'))
                if 'tot' in res:
                    tu = (res.get('u') or {}).get('tot', [None, None])
                    lg['over'].add({'O': 'W', 'U': 'L', 'P': 'P'}.get(res['tot']), tu[0])
                    lg['under'].add({'O': 'L', 'U': 'W', 'P': 'P'}.get(res['tot']), tu[1])
                lg['pts'] += total_pts
        # serialize
        seg_teams = {}
        for slug, t in teams.items():
            row = {}
            for f, v in t.items():
                row[f] = v.out() if isinstance(v, Rec) else (round(v, 2) if isinstance(v, float) else v)
            seg_teams[slug] = row
        league = {}
        for f, v in lg.items():
            league[f] = v.out() if isinstance(v, Rec) else v
        if 'pts' in league:
            league['avg'] = round(league['pts'] / league['gp'], 2) if league['gp'] else None
            del league['pts']
            league.pop('scored', None)
        out['league'][k] = league
        for slug, row in seg_teams.items():
            out['teams'].setdefault(slug, {})[k] = row
    return out


def team_streaks(sp, games):
    """Current streaks per team per segment + market, newest game first.
    A push / tie ends a streak."""
    by_team = {}
    for g in games:
        if not g.get('_res'):
            continue
        for side in ('away', 'home'):
            by_team.setdefault(g[side], []).append((g, side))
    out = {}
    for slug, lst in by_team.items():
        found = []
        for seg in sp['segments']:
            k = seg['key']
            no_ml = not sports.has_ml(seg)
            seq = [(g['_res'].get(k), side) for g, side in reversed(lst) if g['_res'].get(k) and not g['_res'][k].get('na')]
            markets = [('rfi', lambda r, s: {'Y': 'YRFI', 'N': 'NRFI'}.get(r['rfi']))] if k == '1i' and sp['sport_type'] == 'baseball' else [
                ('su', lambda r, s: {'W': 'W', 'L': 'L'}.get(side_res(r, 'su', s))),
                ('ats', lambda r, s: {'W': 'W', 'L': 'L'}.get(side_res(r, 'ats', s)) if 'ats' in r else None),
                ('tot', lambda r, s: {'O': 'Over', 'U': 'Under'}.get(r.get('tot')) if 'tot' in r else None),
            ]
            for market, fn in markets:
                if market == 'su' and no_ml:
                    continue
                vals = [fn(r, s) for r, s in seq if market != 'ats' and market != 'tot' or market in r]
                if not vals or vals[0] is None:
                    continue
                n = 0
                for v in vals:
                    if v != vals[0]:
                        break
                    n += 1
                if n >= CONFIG['team_streak_min']:
                    found.append({'seg': k, 'market': market, 'kind': vals[0], 'n': n})
        if found:
            out[slug] = sorted(found, key=lambda x: -x['n'])
    return out


# ------------------------------------------------------------------- trends

def seg_tag(sp, k, market):
    seg = next(s for s in sp['segments'] if s['key'] == k)
    if market == 'rfi':
        return 'NRFI/YRFI'
    word = {'su': 'SU', 'ats': 'ATS', 'tot': 'O/U'}[market]
    return f"{seg['tag']} {word}"


def seg_label(sp, k):
    seg = next(s for s in sp['segments'] if s['key'] == k)
    return 'the 1st inning' if k == '1i' else ('the First Five' if k == 'f5' else f"the {seg['label']}")


def prepare(sp, teams, games):
    """Per game: rest days, previous result and game type for each side."""
    last = {}
    big = BIG_LOSS.get(sp['key'], 10)
    college = sp['key'] in ('ncaaf', 'ncaab')
    out = []
    for g in games:
        G = {'g': g, 'date': g['date'], 'key': g['id'], 'graded': bool(g.get('final')), 'sides': {}}
        for side in ('away', 'home'):
            slug = g[side]
            prev = last.get(slug)
            rest = None
            if prev:
                rest = (Date.fromisoformat(g['date']) - Date.fromisoformat(prev['date'])).days - 1
            G['sides'][side] = {'side': side, 'slug': slug, 'rest': rest, 'prev': prev and prev['res']}
        ta, th = teams.get(g['away']) or {}, teams.get(g['home']) or {}
        if college:
            G['type'] = 'conf' if g.get('conf_game') else 'nonconf'
        elif ta.get('division') and ta.get('division') == th.get('division'):
            G['type'] = 'div'
        elif ta.get('conference') and ta.get('conference') == th.get('conference'):
            G['type'] = 'conf'
        else:
            G['type'] = 'nonconf'
        G['neutral'] = bool(g.get('neutral'))
        G['post'] = g.get('season_type') == 3
        if g.get('final') and isinstance(g.get('away_score'), (int, float)) and isinstance(g.get('home_score'), (int, float)):
            a, h = g['away_score'], g['home_score']
            for side, mine, theirs in (('away', a, h), ('home', h, a)):
                last[g[side]] = {'date': g['date'], 'res': {
                    'lost': mine < theirs, 'big': theirs - mine >= big, 'shutout': mine == 0 and theirs > 0}}
        out.append(G)
    return out


def type_words(sp):
    if sp['key'] in ('ncaaf', 'ncaab'):
        return {'conf': 'Conference games', 'nonconf': 'Non-Conference games'}
    if sp['key'] == 'mlb':
        return {'div': 'Divisional games', 'conf': 'League games', 'nonconf': 'Interleague games'}
    if sp['key'] == 'wnba':
        return {'conf': 'Conference games', 'nonconf': 'Non-Conference games'}
    return {'div': 'Divisional games', 'conf': 'Conference games', 'nonconf': 'Non-Conference games'}


def _other(G, c):
    return G['sides']['home' if c['side'] == 'away' else 'away']


def _rest_edge(G):
    a, h = G['sides']['away']['rest'], G['sides']['home']['rest']
    return a is not None and h is not None and a != h


def side_angles(sp):
    big = BIG_LOSS.get(sp['key'], 10)
    unit = BIG_LOSS_WORD.get(sp['key'], 'points' if sp['key'] not in ('nfl', 'ncaaf') else 'points')
    A = [
        ('home_fav', 'Home Favorites', lambda G, c, f, p: c['side'] == 'home' and f == 'home', 'ha_fav', True),
        ('road_dog', 'Road Underdogs', lambda G, c, f, p: c['side'] == 'away' and f == 'home', 'ha_fav', True),
        ('home_dog', 'Home Underdogs', lambda G, c, f, p: c['side'] == 'home' and f == 'away', 'ha_dog', True),
        ('road_fav', 'Road Favorites', lambda G, c, f, p: c['side'] == 'away' and f == 'away', 'ha_dog', True),
        ('tier1', 'Sides at -150 or shorter', lambda G, c, f, p: p is not None and p <= -150, None, True),
        ('tier2', 'Sides priced -149 to -101', lambda G, c, f, p: p is not None and -150 < p <= -101, None, True),
        ('tier3', 'Sides priced +100 to +149', lambda G, c, f, p: p is not None and (100 <= p <= 149 or p == -100), None, True),
        ('tier4', 'Sides at +150 or longer', lambda G, c, f, p: p is not None and p >= 150, None, True),
        ('home', 'Home teams', lambda G, c, f, p: c['side'] == 'home' and not G['neutral'], 'home_road', False),
        ('road', 'Road teams', lambda G, c, f, p: c['side'] == 'away' and not G['neutral'], 'home_road', False),
        ('off_loss', 'Teams coming off a loss', lambda G, c, f, p: bool(c['prev'] and c['prev']['lost']), None, False),
        ('off_big', f'Teams coming off a loss by {big}+ {unit}', lambda G, c, f, p: bool(c['prev'] and c['prev']['big']), None, False),
    ]
    if sp['key'] == 'mlb':
        A.append(('off_shutout', 'Teams coming off a shutout loss', lambda G, c, f, p: bool(c['prev'] and c['prev']['shutout']), None, False))
    else:
        A += [
            ('b2b', 'Teams on a back-to-back', lambda G, c, f, p: c['rest'] == 0 and _other(G, c)['rest'] != 0, 'b2b', False),
            ('b2b_opp', 'Opponents of a back-to-back team', lambda G, c, f, p: c['rest'] != 0 and _other(G, c)['rest'] == 0, 'b2b', False),
            ('rested', 'Rested teams (rest edge)', lambda G, c, f, p: _rest_edge(G) and c['rest'] > _other(G, c)['rest'], 'rest', False),
            ('tired', 'Tired teams (rest edge)', lambda G, c, f, p: _rest_edge(G) and c['rest'] < _other(G, c)['rest'], 'rest', False),
        ]
    return A


def game_angles(sp):
    words = type_words(sp)
    A = [(t, w, (lambda t: lambda G, f: G['type'] == t)(t), False) for t, w in words.items()]
    A += [
        ('neutral', 'neutral-site games', lambda G, f: G['neutral'], False),
        ('post', 'postseason games', lambda G, f: G['post'], False),
        ('off_loss_game', 'games with a team coming off a loss',
         lambda G, f: any(c['prev'] and c['prev']['lost'] for c in G['sides'].values()), False),
        ('home_fav_game', 'games with a Home Favorite', lambda G, f: f == 'home', True),
        ('home_dog_game', 'games with a Home Underdog', lambda G, f: f == 'away', True),
    ]
    if sp['key'] != 'mlb':
        A += [
            ('rest_edge', 'games with a rest edge', lambda G, f: _rest_edge(G), False),
            ('b2b_game', 'games with a team on a back-to-back',
             lambda G, f: G['sides']['away']['rest'] == 0 or G['sides']['home']['rest'] == 0, False),
        ]
    return A


def fmt_units(u):
    return f"{'+' if u > 0 else ''}{u:.2f}u"


def fmt_price(p):
    if not isinstance(p, (int, float)):
        return ''
    return f"{'+' if p > 0 else ''}{int(p) if float(p).is_integer() else p}"


def side_market_info(G, k, market, side):
    """(result W/L/T/P, units, price for tiers, pick label) for one side."""
    res = G['g']['_res'].get(k) or {}
    o = G['g']['_odds'].get(k) or {}
    if market == 'su':
        price = ((o.get('ml') or {}).get(side))
        return side_res(res, 'su', side), side_units(res, 'su', side), price, fmt_price(price)
    ats = (o.get('ats') or {}).get(side) or {}
    return side_res(res, 'ats', side), side_units(res, 'ats', side), ats.get('price'), fmt_price(ats.get('line'))


GAME_MARKETS = {
    'over': ('tot', lambda r: {'O': 'W', 'U': 'L', 'P': 'P'}.get(r.get('tot')), 0, 'The Over', 'O'),
    'under': ('tot', lambda r: {'O': 'L', 'U': 'W', 'P': 'P'}.get(r.get('tot')), 1, 'The Under', 'U'),
    'yrfi': ('rfi', lambda r: {'Y': 'W', 'N': 'L'}.get(r.get('rfi')), 0, 'YRFI', 'YRFI'),
    'nrfi': ('rfi', lambda r: {'Y': 'L', 'N': 'W'}.get(r.get('rfi')), 1, 'NRFI', 'NRFI'),
}


# Plain words per side angle: what a team in the spot "is", and the
# group's name. A bettor-side record names the opposite group when the angle
# comes in a pair (road favorites <-> home underdogs), else "Their opponents".
def angle_words(sp):
    big = BIG_LOSS.get(sp['key'], 10)
    unit = BIG_LOSS_WORD.get(sp['key'], 'points')
    return {
        'home_fav': ('is a home favorite', 'Home favorites'),
        'road_dog': ('is a road underdog', 'Road underdogs'),
        'home_dog': ('is a home underdog', 'Home underdogs'),
        'road_fav': ('is a road favorite', 'Road favorites'),
        'tier1': ('is priced -150 or shorter', 'Sides at -150 or shorter'),
        'tier2': ('is priced -149 to -101', 'Sides priced -149 to -101'),
        'tier3': ('is priced +100 to +149', 'Sides priced +100 to +149'),
        'tier4': ('is priced +150 or longer', 'Sides at +150 or longer'),
        'home': ('is at home', 'Home teams'),
        'road': ('is on the road', 'Road teams'),
        'off_loss': ('is coming off a loss', 'Teams off a loss'),
        'off_big': (f'lost by {big}+ {unit} last game', f'Teams off a {big}+ {unit} loss'),
        'off_shutout': ('was shut out last game', 'Teams off a shutout loss'),
        'b2b': ('is on a back-to-back', 'Teams on a back-to-back'),
        'b2b_opp': ('is facing a team on a back-to-back', 'Opponents of a back-to-back team'),
        'rested': ('has the rest edge', 'Rested teams'),
        'tired': ('is on less rest', 'Tired teams'),
    }


OPPOSITE = {'home_fav': 'road_dog', 'road_dog': 'home_fav', 'home_dog': 'road_fav', 'road_fav': 'home_dog',
            'home': 'road', 'road': 'home', 'b2b': 'b2b_opp', 'b2b_opp': 'b2b', 'rested': 'tired', 'tired': 'rested'}
GAME_WORD = {'over': 'Over', 'under': 'Under', 'yrfi': 'YRFI', 'nrfi': 'NRFI'}


def _code(teams, G, side):
    return (teams.get(G['g'][side]) or {}).get('code') or G['g'][side + '_name']


def _matchup(teams, G):
    return f"{_code(teams, G, 'away')} @ {_code(teams, G, 'home')}"


def side_chip(teams, G, k, tag, market, side):
    """'Bet BAL 1H ML', 'Bet NE +1.5 1H', or 'Bet NE 1H · line TBD'."""
    code = _code(teams, G, side)
    o = G['g']['_odds'].get(k) or {}
    if market == 'su':
        return f'Bet {code} {tag} ML'
    line = ((o.get('ats') or {}).get(side) or {}).get('line')
    return f'Bet {code} {fmt_price(line)} {tag}' if line is not None else f'Bet {code} {tag} · line TBD'


def game_chip(G, k, tag, which):
    """'Under 3.5 1Q', 'Under 1Q · line TBD', 'NRFI -130'."""
    o = G['g']['_odds'].get(k) or {}
    if which in ('over', 'under'):
        line = (o.get('total') or {}).get('line')
        word = GAME_WORD[which]
        return f'{word} {line} {tag}' if line is not None else f'{word} {tag} · line TBD'
    price = fmt_price((o.get('nrfi_yrfi') or {}).get(which))
    return GAME_WORD[which] + (f' {price}' if price else '')


def generate_for_date(sp, teams, games, d, slate=None):
    """League trends for the games on date d -- or, for week-scheduled
    sports, for `slate` (the week's games), using only games before d.
    Every trend is the side to bet: records, units and rates are from that
    side (ties and pushes left out), strength and minimum samples come from
    trend_rules, and a game only counts when exactly one team fits."""
    R = trend_rules.RULES
    before = [G for G in games if G['date'] < d and G['graded']]
    tonight = slate if slate is not None else [G for G in games if G['date'] == d]
    if not tonight:
        return []
    cands = []
    baseball = sp['sport_type'] == 'baseball'
    words = angle_words(sp)
    for seg in sp['segments']:
        k, tag = seg['key'], seg['tag']
        side_markets = [] if (baseball and k == '1i') else ['su', 'ats'] if sports.has_ml(seg) else ['ats']
        game_fams = [('rfi', 'yrfi', 'nrfi')] if (baseball and k == '1i') else [('tot', 'over', 'under')]
        pool_k = [G for G in before if (G['g']['_res'].get(k) or {}) and not G['g']['_res'][k].get('na')]
        # ---- side angles (SU / ATS)
        for key, noun, test, pair, priced_only in side_angles(sp):
            for market in side_markets:
                def fits(G, c):
                    fav = favorite(G['g']['_odds'].get(k))
                    price = ((G['g']['_odds'].get(k) or {}).get('ml') or {}).get(c['side'])
                    return test(G, c, fav, price)

                def one_side(G):
                    fit = [c for c in G['sides'].values() if fits(G, c)]
                    return fit[0] if len(fit) == 1 else None
                sides_tonight = [(G, one_side(G)) for G in tonight if one_side(G)]
                if not sides_tonight:
                    continue
                mine, theirs = Rec(), Rec()
                for G in pool_k:
                    if market == 'ats' and 'ats' not in G['g']['_res'][k]:
                        continue
                    c = one_side(G)
                    if not c:
                        continue
                    for rec, cc in ((mine, c), (theirs, _other(G, c))):
                        res, u, _, _ = side_market_info(G, k, market, cc['side'])
                        rec.add(res, u)
                if mine.rate is None:
                    continue
                bet_self = mine.rate >= 0.5
                rec = mine if bet_self else theirs
                n = rec.decisions
                units = rec.units if rec.priced else None
                if n < R['league_min'] or (units is not None and units < R['min_units']):
                    continue
                z = trend_rules.strength(rec.rate, 0.5, n)
                phrase, group = words.get(key, ('fits this spot', noun))
                lower = group[0].lower() + group[1:]
                title = f'Bet {lower}' if bet_self else f'Bet against {lower}'
                rec_group = group if bet_self else (words[OPPOSITE[key]][1] if key in OPPOSITE else 'Their opponents')
                picks = []
                for G, c in sides_tonight:
                    bet = c if bet_self else _other(G, c)
                    picks.append({'key': G['key'], 'kind': 'side', 'seg': k, 'market': market, 'side': bet['side'],
                                  'team': _code(teams, G, bet['side']),
                                  'chip': side_chip(teams, G, k, tag, market, bet['side']),
                                  'label': side_chip(teams, G, k, tag, market, bet['side']),
                                  'why': f"{_code(teams, G, c['side'])} {phrase}", 'matchup': _matchup(teams, G)})
                cands.append({'id': f'side:{key}:{k}:{market}', 'family': f'{pair or key}:{market}', 'kind': 'side',
                              'market': seg_tag(sp, k, market), 'seg': k, 'mk': market,
                              'title': title, 'sentence': title, 'group': rec_group,
                              'w': rec.w, 'l': rec.l, 't': rec.t, 'record': trend_rules.record_text(rec.w, rec.l, rec.t),
                              'rate': round(rec.rate, 4), 'base': 0.5, 'n': n,
                              'units': round(units, 2) if units is not None else None, 'priced': rec.priced,
                              'z': round(z, 2), 'strength': trend_rules.label(z, units, rec.priced), 'score': abs(z),
                              'slate_n': len(tonight), 'games': picks})
        # ---- game angles (totals / NRFI)
        for key, phrase, test, priced_only in game_angles(sp):
            def gfits(G):
                return test(G, favorite(G['g']['_odds'].get(k)))
            games_tonight = [G for G in tonight if gfits(G)]
            if not games_tonight:
                continue
            for fam, hit, miss in game_fams:
                fam_pool = [G for G in pool_k if fam in G['g']['_res'][k]]
                pool = [G for G in fam_pool if gfits(G)]
                hit_fn = GAME_MARKETS[hit][1]
                r_hit, lg = Rec(), Rec()
                for G in pool:
                    r_hit.add(hit_fn(G['g']['_res'][k]), None)
                for G in fam_pool:
                    lg.add(hit_fn(G['g']['_res'][k]), None)
                if r_hit.rate is None or lg.rate is None:
                    continue
                which = hit if r_hit.rate >= lg.rate else miss
                _, fn, ui, word, _ = GAME_MARKETS[which]
                r = Rec()
                for G in pool:
                    res = G['g']['_res'][k]
                    u = (res.get('u') or {}).get(fam)
                    r.add(fn(res), None if u is None else u[ui])
                base = lg.rate if which == hit else 1 - lg.rate
                n = r.decisions
                units = r.units if r.priced else None
                if n < R['league_min'] or (units is not None and units < R['min_units']):
                    continue
                z = trend_rules.strength(r.rate, base, n)
                where = f'in {phrase}'
                title = f"{GAME_WORD[which]} {where}"
                picks = [{'key': G['key'], 'kind': 'game', 'seg': k, 'market': which,
                          'chip': game_chip(G, k, tag, which), 'label': game_chip(G, k, tag, which),
                          'matchup': _matchup(teams, G)} for G in games_tonight]
                cands.append({'id': f'game:{key}:{k}:{which}', 'family': f'{key}:{fam}', 'kind': 'game',
                              'market': 'NRFI/YRFI' if fam == 'rfi' else seg_tag(sp, k, 'tot'), 'seg': k, 'mk': fam,
                              'title': title, 'sentence': title, 'hits': r.w, 'n': n,
                              'w': r.w, 'l': r.l, 't': r.t, 'record': trend_rules.record_text(r.w, r.l, r.t),
                              'rate': round(r.rate, 4), 'base': round(base, 4),
                              'units': round(units, 2) if units is not None else None, 'priced': r.priced,
                              'z': round(z, 2), 'strength': trend_rules.label(z, units, r.priced), 'score': abs(z),
                              'slate_n': len(tonight), 'games': picks})
    # ---- rank by strength: one per angle family, a few per market, and
    # never two trends on opposite sides of the same game
    cands.sort(key=lambda c: (-c['score'], -len(c['games'])))
    picked, families, per_market, taken = [], set(), {}, {}
    for c in cands:
        if c['family'] in families or per_market.get(c['market'], 0) >= CONFIG['max_per_market']:
            continue
        sigs = [_pick_sig(g) for g in c['games']]
        if any(taken.get(s, v) != v for s, v in sigs):
            continue
        for s, v in sigs:
            taken[s] = v
        picked.append(c)
        families.add(c['family'])
        per_market[c['market']] = per_market.get(c['market'], 0) + 1
        if len(picked) >= R['shown']:
            break
    for c in picked:
        c.pop('family', None)
        c['score'] = round(c['score'], 2)
    return picked


def _pick_sig(g):
    """(game + segment + market family, which side of it) for one pick."""
    fam = 'side-' + g['market'] if g['kind'] == 'side' else GAME_MARKETS[g['market']][0]
    return (f"{g['key']}:{g['seg']}:{fam}", g.get('side') or g['market'])


def _started(G, now_utc):
    g = G['g']
    if g.get('state') in ('in', 'final'):
        return True
    return bool(now_utc and g.get('start') and now_utc >= datetime.fromisoformat(g['start'].replace('Z', '+00:00')))


def grade_trends(entry, by_key, now_utc=None):
    """Each pick's status: PENDING, LIVE once its game starts (no longer a
    bet), NA, or W / L / P once graded; then the slate's labels, agreement
    and record (trend_rules.finish_slate)."""
    for t in entry['trends']:
        for p in t['games']:
            G = by_key.get(p['key'])
            res = G and (G['g']['_res'].get(p['seg']) or None)
            if not res or not G['graded'] or res.get('na'):
                p['status'] = ('NA' if res and res.get('na') else
                               'LIVE' if G and _started(G, now_utc) else 'PENDING')
                continue
            if p['kind'] == 'side':
                r = side_res(res, p['market'], p['side'])
            else:
                r = GAME_MARKETS[p['market']][1](res)
            p['status'] = 'P' if r in ('T', 'P') else (r or 'PENDING')
    trend_rules.finish_slate(entry, _pick_sig)


LOG_VERSION = 2   # trend log format; older entries are rebuilt once


def slates(sp, prepared):
    """[(log key, first date, games)]: one slate per date, or per ESPN week
    for week-scheduled sports (NFL, NCAAF), keyed by the week ('2-7')."""
    groups = {}
    if sp.get('schedule') == 'week':
        for G in prepared:
            k = week_key(G['g'])
            if k:
                groups.setdefault(k, []).append(G)
    else:
        for G in prepared:
            groups.setdefault(G['date'], []).append(G)
    out = [(k, min(G['date'] for G in gs), gs) for k, gs in groups.items()]
    return sorted(out, key=lambda x: (x[1], x[0]))


def update_trends_log(sp, teams, games, log_path, now_utc):
    log = read_json(log_path, {})
    today = now_utc.astimezone(ET).date().isoformat()
    prepared = prepare(sp, teams, games)
    by_key = {G['key']: G for G in prepared}
    groups = slates(sp, prepared)
    # A sport that moved from daily to weekly slates drops its old date keys.
    keys = {k for k, _, _ in groups}
    for k in list(log):
        if k not in keys:
            del log[k]
    floor = None
    if not log:
        floor = (datetime.fromisoformat(today).date().toordinal() - CONFIG['first_backfill_days'])
    for k, d, slate in groups:
        if floor is not None and sp.get('schedule') != 'week' and Date.fromisoformat(d).toordinal() < floor:
            continue
        # Locked once the slate's first game starts.
        starts = [G['g']['start'] for G in slate if G['g'].get('start')]
        first = min(starts) if starts else None
        started = d < today or (first is not None and now_utc >= datetime.fromisoformat(first.replace('Z', '+00:00')))
        entry = log.get(k)
        # Open slates regenerate; an entry from an older format is rebuilt
        # once (from games before its slate only, so its picks are the ones
        # it would have shown).
        if entry is None or not entry.get('frozen') or entry.get('v') != LOG_VERSION:
            entry = {'trends': generate_for_date(sp, teams, prepared, d,
                                                 slate if sp.get('schedule') == 'week' else None),
                     'frozen': started, 'v': LOG_VERSION}
            log[k] = entry
        elif started:
            entry['frozen'] = True
        grade_trends(entry, by_key, now_utc)
    write_json(log_path, log)
    return log


# --------------------------------------------------------------------- page

def game_out(g):
    return {
        'id': g['id'], 'start': g['start'], 'state': g['state'], 'detail': g['detail'],
        'away': g['away'], 'home': g['home'], 'awayName': g['away_name'], 'homeName': g['home_name'],
        'as': g['away_score'], 'hs': g['home_score'], 'als': g['away_ls'], 'hls': g['home_ls'],
        'note': g.get('note'), 'post': g.get('season_type') == 3, 'neutral': g.get('neutral') or False,
        'odds': g['_odds'] or None, 'res': {k: v for k, v in g['_res'].items() if v} or None,
        'wk': week_key(g),
        # outside the US (International games); None = not known yet
        'intl': None if g.get('country') is None else g['country'] not in ('USA', 'United States'),
        'ar': g.get('away_rank'), 'hr': g.get('home_rank'),
        # closing full-game line (home team's spread; negative = home favored)
        'fs': g.get('fg_spread'), 'ft': g.get('fg_total'), 'fml': g.get('fg_ml'),
        'tvn': g.get('national_tv'),
    }


def season_file(kind, sport, season):
    """data_seed/{kind}/{sport}/{season}.json, else the latest earlier
    season's file (membership carries over until a new file is added)."""
    d = os.path.join(ROOT, 'data_seed', kind, sport)
    if not os.path.isdir(d) or season is None:
        return None
    names = sorted((n for n in os.listdir(d) if n[:4].isdigit() and int(n[:4]) <= season), reverse=True)
    return read_json(os.path.join(d, names[0]), None) if names else None


def apply_ap_ranks(sport, season, games):
    """College football: each team's AP rank from the poll current at
    kickoff (the latest poll released before it), when the season's polls
    are saved (fetch_rankings.py); otherwise ESPN's rank on the game stays."""
    doc = season_file('rankings', sport, season)
    polls = sorted((doc or {}).get('polls') or [], key=lambda p: p.get('date') or '')
    if not polls or (doc or {}).get('season') != season:
        return
    for g in games:
        poll = None
        for p in polls:
            if (p.get('date') or '') <= (g.get('start') or ''):
                poll = p
        ranks = (poll or {}).get('ranks') or {}
        g['away_rank'], g['home_rank'] = ranks.get(g['away']), ranks.get(g['home'])


def week_key(g):
    """'2-7' = regular season week 7, '3-1' = postseason week 1; None if
    the game has no ESPN week (non-football)."""
    return f"{g.get('season_type')}-{g['week']}" if g.get('week') else None


def week_list(games):
    """Weeks in order: [{key, label, start, end, games}] for the Matchups page
    and Admin of week-scheduled sports."""
    weeks = {}
    for g in games:
        k = week_key(g)
        if not k:
            continue
        w = weeks.setdefault(k, {'key': k, 'label': g.get('week_label') or f"Week {g['week']}",
                                 'start': g['date'], 'end': g['date'], 'games': 0,
                                 '_order': (g.get('season_type') or 0, g['week'])})
        w['start'] = min(w['start'], g['date'])
        w['end'] = max(w['end'], g['date'])
        w['games'] += 1
    out = sorted(weeks.values(), key=lambda w: w['_order'])
    for w in out:
        del w['_order']
    return out


def logo_flag(sport_key, slug):
    """'d' = light + dark logos cached, 'l' = light only, None = no logo
    (assets/logos/{sport}/, scripts/fetch_sport_logos.py)."""
    info = icons.logo_index(sport_key).get(slug)
    return None if info is None else ('d' if info.get('dark') else 'l')


COLLEGE = ('ncaab', 'ncaaf')


def page_markets(sp):
    """[[segment, market, label, kind]] for the pages, in order."""
    return [list(m) for m in sp['family_markets']]


def build(sp, teams_list, now_utc=None):
    """Writes {slug}/data.json for the current season (the latest one
    loaded; earlier seasons stay in data_seed/games but aren't published).
    Returns a summary for the build log and the home page:
    {season, games, graded, today}."""
    now_utc = now_utc or datetime.now(timezone.utc)
    seasons = load_games(sp['key'])
    odds = merge_odds(read_json(os.path.join(ROOT, 'data_admin', 'odds', f"{sp['key']}.json"), {}),
                      read_json(os.path.join(ROOT, 'data_feed', 'unabated', f"{sp['key']}.json"), {}).get('games') or {})
    teams = {t['slug']: t for t in teams_list}
    slug_dir = os.path.join(ROOT, sp['slug'])
    current = max(seasons) if seasons else None
    games = seasons.get(current, [])
    grade_all(sp, games, odds)
    if sp['key'] in ('ncaaf', 'ncaab'):
        apply_ap_ranks(sp['key'], current, games)
    by_date = {}
    for g in games:
        by_date.setdefault(g['date'], []).append(game_out(g))
    extra = {}
    for g in games:
        for side in ('away', 'home'):
            if g[side] not in teams:
                extra[g[side]] = g[side + '_name']
    trends = {}
    if current is not None:
        trends = update_trends_log(sp, teams, games, os.path.join(ROOT, 'trends_log', f"{sp['key']}.json"), now_utc)
    stats = season_stats(sp, games) if games else {'teams': {}, 'league': {}}
    doc = {
        'sport': sp['key'], 'label': sp['label'], 'slug': sp['slug'], 'sportType': sp['sport_type'],
        'segments': sp['segments'],
        # the market pills every page uses (sports.py family markets); no 3-way for the spread family
        'markets': page_markets(sp),
        'schedule': sp.get('schedule', 'day'),
        'weeks': week_list(games) if sp.get('schedule') == 'week' else None,
        'season': current, 'seasonLabel': season_label(sp['key'], current) if current else None,
        'generated': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'teams': {t['slug']: dict({k: t.get(k) for k in ('name', 'short', 'code', 'color', 'conference', 'division')},
                                  # naming rule: college teams go by the school name, never the nickname
                                  **({'short': t.get('location') or t.get('short')} if sp['key'] in COLLEGE else {}),
                                  logo=logo_flag(sp['key'], t['slug'])) for t in teams_list},
        'otherTeams': extra,
        # logos for the opponents outside the league (non-Division I schools)
        'otherLogos': {slug: f for slug, f in ((slug, logo_flag(sp['key'], slug)) for slug in extra) if f},
        'games': by_date,
        'stats': stats,
        'streaks': team_streaks(sp, games),
        'trendRules': trend_rules.for_page(),
        'trends': {d: e for d, e in trends.items()},
    }
    if sp['key'] == 'ncaaf':
        # Situational Results: conference membership by season, rivalries
        doc['conf'] = season_file('conferences', 'ncaaf', current)
        doc['rivals'] = (read_json(os.path.join(ROOT, 'data_seed', 'rivalries', 'ncaaf.json'), {}) or {}).get('pairs') or []
    if sp['key'] == 'ncaab':
        doc['conf'] = season_file('conferences', 'ncaab', current)
    # Situational Results "total size" rows: thirds of this season's posted
    # segment totals (the cutoffs show in the row descriptions)
    cuts = {}
    for s in sp['segments']:
        lines = sorted(((g.get('_odds') or {}).get(s['key']) or {}).get('total', {}).get('line')
                       for g in games if isinstance((((g.get('_odds') or {}).get(s['key']) or {}).get('total') or {}).get('line'), (int, float)))
        if len(lines) >= 6:
            cuts[s['key']] = [lines[len(lines) // 3], lines[2 * len(lines) // 3]]
    doc['totalCuts'] = cuts
    # "Since last season": the previous season's games in their own file,
    # loaded only when that option is picked
    prev = max((y for y in seasons if current is not None and y < current), default=None)
    hist_path = os.path.join(slug_dir, 'history.json')
    if prev is not None:
        pgames = seasons[prev]
        grade_all(sp, pgames, odds)
        if sp['key'] in ('ncaaf', 'ncaab'):
            apply_ap_ranks(sp['key'], prev, pgames)
        hist = {}
        for g in pgames:
            hist.setdefault(g['date'], []).append(game_out(g))
        for g in pgames:
            for side in ('away', 'home'):
                if g[side] not in teams:
                    extra.setdefault(g[side], g[side + '_name'])
        write_json(hist_path, {'season': prev, 'seasonLabel': season_label(sp['key'], prev), 'games': hist})
        doc['history'] = {'season': prev, 'label': season_label(sp['key'], prev)}
    elif os.path.exists(hist_path):
        os.remove(hist_path)
    write_json(os.path.join(slug_dir, 'data.json'), doc)
    # the Trends page's League Trends cards (scripts/trends.py)
    trends_doc = trend_cards.page_doc(sp, doc, now_utc)
    write_json(os.path.join(slug_dir, 'trends.json'), trends_doc)
    odds_schedule = {d: [{'away': g['away'], 'home': g['home'], 'start': g.get('start'),
                          'state': {'in': 'live', 'final': 'final', 'post': 'final'}.get(g.get('state'), 'pre'),
                          'score': seg_scores(sp, g), 'detail': g.get('detail') or '',
                          'res': g.get('res') if g.get('state') in ('final', 'post') else None} for g in day]
                     for d, day in by_date.items()}
    write_odds_page(sp, slug_dir, now_utc, odds_schedule, weeks=doc.get('weeks'))
    import hub   # the Arena hub (/{slug}/): Matchup of the Day and The Daily, after the odds files it prices from
    hub.build(sp, doc, trends_doc, slug_dir, now_utc)
    today = now_utc.astimezone(ET).date().isoformat()
    return {'season': current, 'seasonLabel': doc['seasonLabel'], 'games': len(games), 'graded': sum(1 for g in games if g.get('final')),
            'today': len(by_date.get(today, []))}
