"""
Data for the non-NHL sports' Games, Stats, Trends and team pages.

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
import json
import math
import os
from datetime import date as Date, datetime, timezone
from zoneinfo import ZoneInfo

import grading
import icons
import trend_rules

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
    rfi Y N NA; u units per side (only where odds were saved)."""
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
            seq = [(g['_res'].get(k), side) for g, side in reversed(lst) if g['_res'].get(k) and not g['_res'][k].get('na')]
            markets = [('rfi', lambda r, s: {'Y': 'YRFI', 'N': 'NRFI'}.get(r['rfi']))] if k == '1i' and sp['sport_type'] == 'baseball' else [
                ('su', lambda r, s: {'W': 'W', 'L': 'L'}.get(side_res(r, 'su', s))),
                ('ats', lambda r, s: {'W': 'W', 'L': 'L'}.get(side_res(r, 'ats', s)) if 'ats' in r else None),
                ('tot', lambda r, s: {'O': 'Over', 'U': 'Under'}.get(r.get('tot')) if 'tot' in r else None),
            ]
            for market, fn in markets:
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
        side_markets = [] if (baseball and k == '1i') else ['su', 'ats']
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
                              'z': round(z, 2), 'strength': trend_rules.label(z), 'score': abs(z),
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
                              'z': round(z, 2), 'strength': trend_rules.label(z), 'score': abs(z),
                              'slate_n': len(tonight), 'games': picks})
    # ---- rank by strength: one per angle family, a few per market, and
    # never two trends on opposite sides of the same game
    cands.sort(key=lambda c: (-c['score'], -len(c['games'])))
    picked, families, per_market, taken = [], set(), {}, {}
    for c in cands:
        if c['family'] in families or per_market.get(c['market'], 0) >= CONFIG['max_per_market']:
            continue
        sigs = [(f"{g['key']}:{g['seg']}:{'side-' + g['market'] if g['kind'] == 'side' else GAME_MARKETS[g['market']][0]}",
                 g.get('side') or g['market']) for g in c['games']]
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


def grade_trends(entry, by_key):
    w = l = 0
    for t in entry['trends']:
        for p in t['games']:
            G = by_key.get(p['key'])
            res = G and (G['g']['_res'].get(p['seg']) or None)
            if not res or not G['graded'] or res.get('na'):
                p['status'] = 'NA' if res and res.get('na') else 'PENDING'
                continue
            if p['kind'] == 'side':
                r = side_res(res, p['market'], p['side'])
            else:
                r = GAME_MARKETS[p['market']][1](res)
            p['status'] = 'P' if r in ('T', 'P') else (r or 'PENDING')
            w += r == 'W'
            l += r == 'L'
    entry['record'] = {'w': w, 'l': l}


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
        grade_trends(entry, by_key)
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
    }


def week_key(g):
    """'2-7' = regular season week 7, '3-1' = postseason week 1; None if
    the game has no ESPN week (non-football)."""
    return f"{g.get('season_type')}-{g['week']}" if g.get('week') else None


def week_list(games):
    """Weeks in order: [{key, label, start, end, games}] for the Games page
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


def build(sp, teams_list, now_utc=None):
    """Writes {slug}/data.json for the current season (the latest one
    loaded; earlier seasons stay in data_seed/games but aren't published).
    Returns a summary for the build log and the home page:
    {season, games, graded, today}."""
    now_utc = now_utc or datetime.now(timezone.utc)
    seasons = load_games(sp['key'])
    odds = read_json(os.path.join(ROOT, 'data_admin', 'odds', f"{sp['key']}.json"), {})
    teams = {t['slug']: t for t in teams_list}
    slug_dir = os.path.join(ROOT, sp['slug'])
    current = max(seasons) if seasons else None
    games = seasons.get(current, [])
    grade_all(sp, games, odds)
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
        'schedule': sp.get('schedule', 'day'),
        'weeks': week_list(games) if sp.get('schedule') == 'week' else None,
        'season': current, 'seasonLabel': season_label(sp['key'], current) if current else None,
        'generated': now_utc.strftime('%Y-%m-%dT%H:%M:%SZ'),
        'teams': {t['slug']: dict({k: t.get(k) for k in ('name', 'short', 'code', 'color', 'conference', 'division')},
                                  logo=logo_flag(sp['key'], t['slug'])) for t in teams_list},
        'otherTeams': extra,
        'games': by_date,
        'stats': stats,
        'streaks': team_streaks(sp, games),
        'trendRules': trend_rules.for_page(),
        'trends': {d: e for d, e in trends.items()},
    }
    write_json(os.path.join(slug_dir, 'data.json'), doc)
    today = now_utc.astimezone(ET).date().isoformat()
    return {'season': current, 'games': len(games), 'graded': sum(1 for g in games if g.get('final')),
            'today': len(by_date.get(today, []))}
