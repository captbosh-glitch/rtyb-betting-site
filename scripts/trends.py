"""
League Trends cards for every sport's Trends page (Chris's Trends spec, the
sport-families rule in CLAUDE.md). Written to {slug}/trends.json and drawn
by assets/sport.js; Matchup Trends and Streak Trends are counted in the
browser from the games themselves.

Works on games in the shared sport shape (data.json's games, or NHL's
nhl/sport.json from nhl_sport.py): res[k] from the away side with u[market]
units, odds[k] the closing prices.

A trend is an angle (content/trend_tooltips.json: side angles like "teams
off a loss", game angles like "divisional games") plus one bet in one
segment. It gets a card on a date when:
  - its sample (graded games before the date) has at least
    RULES['min_games'] decisions (ties and pushes don't count),
  - its hit rate is at least RULES['min_edge'] above the league rate for the
    same bet (50% for a side's moneyline or spread; the league's own rate
    for totals, BTTS, the 3-way and NRFI/YRFI),
  - its units are positive, and
  - at least one game on the date fits it.
Cards are ordered by edge over the league rate, biggest first.

Side angles have two bets: Back (the team in the spot) and Fade (its
opponent). A game only counts for a side angle when exactly one team fits.

Each slate (a date, or an NFL / NCAAF week) is generated from games before
it and frozen in trends_log/cards/{sport}.json once its first game starts,
so past dates show the cards that were up that day; the page grades them
from the games.
"""
import json
import os
from datetime import date as Date, datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
LOG_DIR = os.path.join(ROOT, 'trends_log', 'cards')
TIPS_FILE = os.path.join(ROOT, 'content', 'trend_tooltips.json')

# Tune here.
RULES = {
    'min_games': 20,      # decisions in the sample
    'min_edge': 0.05,     # hit rate over the league rate for the same bet
    'shown': 8,           # cards before "Show more trends" (the page reads this)
    'backfill_days': 21,  # past slates generated on a first run, counted back from the latest game
}
LOG_VERSION = 1

# A loss by this much or more is a "blowout" (the tooltips say 3+ goals for NHL)
BIG_LOSS = {'nhl': 3, 'nfl': 14, 'ncaaf': 17, 'nba': 10, 'wnba': 10, 'ncaab': 10, 'mlb': 4}
SCORE_WORD = {'nhl': 'goals', 'mlb': 'runs'}
MARKET_TAG = {'ml': 'ML', 'ats': 'ATS', 'total': 'O/U', 'btts': 'BTTS', 'ml3': '3-way', 'rfi': ''}
SPREAD_WORD = {'mlb': 'run line', 'nhl': 'puck line'}
DOW = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def tips():
    with open(TIPS_FILE, encoding='utf-8') as f:
        return json.load(f)


def et_date(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET).date().isoformat()


def short_day(d):
    x = Date.fromisoformat(d)
    return f"{x.strftime('%b')} {x.day}"


def fmt_units(u):
    return f"{'+' if u > 0 else ''}{u:.2f}u"


def fmt_price(p):
    return f"{'+' if p > 0 else ''}{int(p) if float(p).is_integer() else p}"


def implied(p):
    return -p / (-p + 100) if p < 0 else 100 / (p + 100)


def favorite(o):
    """'away' / 'home' by a segment's shorter moneyline, else its spread line."""
    ml = (o or {}).get('ml') or {}
    a, h = ml.get('away'), ml.get('home')
    if isinstance(a, (int, float)) and isinstance(h, (int, float)) and implied(a) != implied(h):
        return 'away' if implied(a) > implied(h) else 'home'
    line = (((o or {}).get('ats') or {}).get('away') or {}).get('line')
    if isinstance(line, (int, float)) and line != 0:
        return 'away' if line < 0 else 'home'
    return None


def flip(r):
    return {'W': 'L', 'L': 'W'}.get(r, r)


def fbu(r):
    return 0.9091 if r == 'W' else -1.0 if r == 'L' else 0.0


def other(side):
    return 'home' if side == 'away' else 'away'


# ---------------------------------------------------------------- games

def prepare(sp, doc):
    """Every game in start order with each side's rest days and previous game:
    G = {g, date, k-independent context}."""
    teams = doc.get('teams') or {}
    big = BIG_LOSS.get(sp['key'], 10)
    college = sp['key'] in ('ncaaf', 'ncaab')
    games = sorted((g for gs in (doc.get('games') or {}).values() for g in gs
                    if g.get('state') not in ('postponed', 'canceled') and g.get('start')),
                   key=lambda g: (g['start'], str(g['id'])))
    last, out = {}, []
    for g in games:
        d = et_date(g['start'])
        G = {'g': g, 'date': d, 'sides': {}}
        for side in ('away', 'home'):
            prev = last.get(g[side])
            rest = (Date.fromisoformat(d) - Date.fromisoformat(prev['date'])).days - 1 if prev else None
            G['sides'][side] = {'side': side, 'slug': g[side], 'rest': rest, 'prev': prev}
        ta, th = teams.get(g['away']) or {}, teams.get(g['home']) or {}
        if not college and sp['key'] != 'wnba' and ta.get('division') and ta.get('division') == th.get('division'):
            G['type'] = 'div'
        elif ta.get('conference') and ta.get('conference') == th.get('conference'):
            G['type'] = 'conf'
        else:
            G['type'] = 'nonconf'
        if g.get('state') == 'final' and isinstance(g.get('as'), (int, float)) and isinstance(g.get('hs'), (int, float)):
            for side, mine, theirs in (('away', g['as'], g['hs']), ('home', g['hs'], g['as'])):
                last[g[side]] = {'date': d, 'mine': mine, 'theirs': theirs, 'opp': g[other(side)],
                                 'lost': mine < theirs, 'big': theirs - mine >= big, 'shutout': mine == 0 and theirs > 0}
        out.append(G)
    return out


def code(doc, slug):
    t = (doc.get('teams') or {}).get(slug) or {}
    return t.get('code') or (t.get('short') or slug).upper()[:4]


# ----------------------------------------------------------------- bets

def bets_for(sp, k):
    """The bets one segment's trends can make: [(market, kind, bet)], kind
    'side' (back / fade a team) or 'game' (over / under / yes / no / tie)."""
    period = sp['family'] == 'period'
    out = []
    for seg, m, _, _ in sp['family_markets']:
        if seg != k:
            continue
        if m in ('ml', 'ats'):
            out.append((m, 'side', None))
        elif m == 'ml3' and period:
            out += [('ml3', 'side', None), ('ml3', 'game', 'tie')]
        elif m == 'total':
            out += [('total', 'game', 'over'), ('total', 'game', 'under')]
        elif m == 'btts':
            out += [('btts', 'game', 'yes'), ('btts', 'game', 'no')]
        elif m == 'rfi':
            out += [('rfi', 'game', 'yes'), ('rfi', 'game', 'no')]
    return out


def side_result(g, k, market, side):
    """(W / L / P, units or None) for a bet on one side, or None (no grade)."""
    r = (g.get('res') or {}).get(k)
    if not r or not r.get('sc') or r.get('na'):
        return None
    u = r.get('u') or {}
    i = 0 if side == 'away' else 1
    if market == 'ml3':
        su = r.get('su')
        if su in (None, 'NA') or not u.get('ml3'):
            return None   # graded at 3-way prices only
        mine = su if side == 'away' else flip(su)
        return ('W' if mine == 'W' else 'L'), u['ml3'][i]
    key = 'su' if market == 'ml' else 'ats'
    x = r.get(key)
    if x in (None, 'NA'):
        return None
    x = x if side == 'away' else flip(x)
    x = 'P' if x in ('T', 'P') else x
    units = u[key][i] if u.get(key) else (fbu(x) if key == 'ats' else None)
    return x, units


def game_result(g, k, market, bet):
    r = (g.get('res') or {}).get(k)
    if not r or not r.get('sc') or r.get('na'):
        return None
    u = r.get('u') or {}
    if market == 'ml3':
        su = r.get('su')
        if su in (None, 'NA') or not u.get('ml3'):
            return None
        return ('W' if su in ('T', 'P') else 'L'), u['ml3'][2]
    if market == 'total':
        t = r.get('tot')
        if t in (None, 'NA'):
            return None
        x = {'O': 'W', 'U': 'L'}.get(t, 'P') if bet == 'over' else {'O': 'L', 'U': 'W'}.get(t, 'P')
        i = 0 if bet == 'over' else 1
        return x, (u['tot'][i] if u.get('tot') else fbu(x))
    if market == 'btts':
        b = r.get('btts')
        if b not in ('Y', 'N'):
            return None
        x = 'W' if (b == 'Y') == (bet == 'yes') else 'L'
        return x, (u['btts'][0 if bet == 'yes' else 1] if u.get('btts') else None)
    if market == 'rfi':
        b = r.get('rfi')
        if b not in ('Y', 'N'):
            return None
        x = 'W' if (b == 'Y') == (bet == 'yes') else 'L'
        return x, (u['rfi'][0 if bet == 'yes' else 1] if u.get('rfi') else None)
    return None


class Rec:
    __slots__ = ('w', 'l', 't', 'units', 'priced', 'last')

    def __init__(self):
        self.w = self.l = self.t = self.priced = 0
        self.units = 0.0
        self.last = None

    def add(self, res, units):
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
        return self.w + self.l

    @property
    def rate(self):
        return self.w / self.n if self.n else None


# --------------------------------------------------------------- angles

def side_angles(sp):
    """[(id, test(G, c, fav, price))] -- c is one side's context."""
    def rest_edge(G):
        a, h = G['sides']['away']['rest'], G['sides']['home']['rest']
        return a is not None and h is not None and a != h
    A = [
        ('home_fav', lambda G, c, f, p: c['side'] == 'home' and f == 'home'),
        ('road_dog', lambda G, c, f, p: c['side'] == 'away' and f == 'home'),
        ('home_dog', lambda G, c, f, p: c['side'] == 'home' and f == 'away'),
        ('road_fav', lambda G, c, f, p: c['side'] == 'away' and f == 'away'),
        ('tier1', lambda G, c, f, p: p is not None and p <= -150),
        ('tier2', lambda G, c, f, p: p is not None and -150 < p <= -101),
        ('tier3', lambda G, c, f, p: p is not None and (100 <= p <= 149 or p == -100)),
        ('tier4', lambda G, c, f, p: p is not None and p >= 150),
        ('off_loss', lambda G, c, f, p: bool(c['prev'] and c['prev']['lost'])),
        ('off_loss3', lambda G, c, f, p: bool(c['prev'] and c['prev']['big'])),
        ('off_shutout', lambda G, c, f, p: bool(c['prev'] and c['prev']['shutout'])),
    ]
    if sp['key'] not in ('mlb', 'nfl', 'ncaaf'):
        A += [
            ('b2b', lambda G, c, f, p: c['rest'] == 0 and G['sides'][other(c['side'])]['rest'] != 0),
            ('b2b_opp', lambda G, c, f, p: c['rest'] != 0 and G['sides'][other(c['side'])]['rest'] == 0),
        ]
    if sp['key'] != 'mlb':
        A += [
            ('rested', lambda G, c, f, p: rest_edge(G) and c['rest'] > G['sides'][other(c['side'])]['rest']),
            ('tired', lambda G, c, f, p: rest_edge(G) and c['rest'] < G['sides'][other(c['side'])]['rest']),
        ]
    return A


def game_angles(sp):
    """[(id, test(G, fav))]"""
    def rest(G, s):
        return G['sides'][s]['rest']
    types = ['conf', 'nonconf'] if sp['key'] in ('ncaaf', 'ncaab', 'wnba') else ['div', 'conf', 'nonconf']
    A = [(t, (lambda t: lambda G, f: G['type'] == t)(t)) for t in types]
    A += [
        ('off_loss_game', lambda G, f: any(c['prev'] and c['prev']['lost'] for c in G['sides'].values())),
        ('off_loss3_game', lambda G, f: any(c['prev'] and c['prev']['big'] for c in G['sides'].values())),
        ('off_shutout_game', lambda G, f: any(c['prev'] and c['prev']['shutout'] for c in G['sides'].values())),
        ('home_fav_game', lambda G, f: f == 'home'),
        ('home_dog_game', lambda G, f: f == 'away'),
    ]
    if sp['key'] != 'mlb':
        A += [
            ('rest_edge', lambda G, f: None not in (rest(G, 'away'), rest(G, 'home')) and rest(G, 'away') != rest(G, 'home')),
            ('even_rest', lambda G, f: None not in (rest(G, 'away'), rest(G, 'home')) and rest(G, 'away') == rest(G, 'home')),
        ]
        if sp['key'] not in ('nfl', 'ncaaf'):
            A.append(('b2b_game', lambda G, f: rest(G, 'away') == 0 or rest(G, 'home') == 0))
    return A


# ------------------------------------------------------------- the words

def angle_text(sp, T, group, aid):
    """(title, meaning, counted) from the tooltips file, with this sport's
    blowout size and game types."""
    t = dict(T[group][aid])
    big, word = BIG_LOSS.get(sp['key'], 10), SCORE_WORD.get(sp['key'], 'points')
    for f in ('title', 'meaning', 'counted'):
        t[f] = t[f].replace('3+ goals', f'{big}+ {word}').replace('Final-score margin of 3 or more', f'Final-score margin of {big} or more')
        if sp['key'] != 'nhl':
            t[f] = t[f].replace('zero goals', f'zero {word}').replace('including overtime', 'including overtime' if sp['key'] != 'mlb' else 'including extra innings')
    if sp['key'] == 'mlb':
        t['title'] = {'conf': 'League games', 'nonconf': 'Interleague games'}.get(aid, t['title'])
    return t['title'], t['meaning'], t['counted']


def tag(sp, k, market):
    seg = next(s for s in sp['segments'] if s['key'] == k)
    if market == 'rfi':
        return 'NRFI'
    if market == 'total' and sp['key'] == 'nhl':
        return f"{seg['tag']} O/U"
    return f"{seg['tag']} {MARKET_TAG[market]}"


def game_bet_word(sp, k, market, bet, line=None):
    if market == 'total':
        w = 'Over' if bet == 'over' else 'Under'
        if sp['key'] == 'nhl':
            return f'{w} 1.5'
        return f'{w} {line:g}' if isinstance(line, (int, float)) else w
    if market == 'btts':
        return 'BTTS Yes' if bet == 'yes' else 'BTTS No'
    if market == 'rfi':
        return 'YRFI' if bet == 'yes' else 'NRFI'
    return 'Tie'


def seg_words(sp, k):
    return next(s for s in sp['segments'] if s['key'] == k)['label'].lower().replace('first five innings', 'first five')


def prev_fact(doc, c):
    p = c['prev']
    day = DOW[Date.fromisoformat(p['date']).weekday()]
    verb = 'lost' if p['mine'] < p['theirs'] else 'won' if p['mine'] > p['theirs'] else 'tied'
    hi, lo = max(p['mine'], p['theirs']), min(p['mine'], p['theirs'])
    return f"{code(doc, c['slug'])} {verb} {hi}–{lo} {'to' if verb == 'lost' else 'vs'} {code(doc, p['opp'])} on {day}"


def fact(sp, doc, G, aid, c, k):
    """One specific fact about a game that fits an angle (c = the side that
    fits, for side angles)."""
    g = G['g']
    o = (g.get('odds') or {}).get(k) or {}
    ml = o.get('ml') or {}
    seg = next(s for s in sp['segments'] if s['key'] == k)
    A, H = code(doc, g['away']), code(doc, g['home'])

    def priced(side):
        p = ml.get(side)
        return f" at {fmt_price(p)}" if isinstance(p, (int, float)) else ''
    if c is None and aid.endswith('_game') and aid not in ('home_fav_game', 'home_dog_game', 'b2b_game'):
        test = {'off_loss_game': 'lost', 'off_loss3_game': 'big', 'off_shutout_game': 'shutout'}[aid]
        c = next((x for x in G['sides'].values() if x['prev'] and x['prev'][test]), None)
    if aid in ('off_loss', 'off_loss3', 'off_shutout', 'off_loss_game', 'off_loss3_game', 'off_shutout_game') and c and c['prev']:
        return prev_fact(doc, c)
    if aid in ('home_fav', 'road_dog', 'home_fav_game'):
        return f"{H} is the {seg['tag']} favorite at home{priced('home')}"
    if aid in ('home_dog', 'road_fav', 'home_dog_game'):
        return f"{A} is the {seg['tag']} favorite on the road{priced('away')}"
    if aid.startswith('tier') and c:
        return f"{code(doc, c['slug'])} is priced{priced(c['side'])} for the {seg['tag']}"
    a, h = G['sides']['away'], G['sides']['home']
    if aid in ('b2b', 'b2b_opp', 'b2b_game'):
        tired = a if a['rest'] == 0 else h
        return f"{code(doc, tired['slug'])} played yesterday"
    if aid in ('rested', 'tired', 'rest_edge', 'even_rest') and a['rest'] is not None and h['rest'] is not None:
        if a['rest'] == h['rest']:
            return f"Both teams have {a['rest']} day{'' if a['rest'] == 1 else 's'} off"
        return f"{A} has {a['rest']} day{'' if a['rest'] == 1 else 's'} off, {H} {h['rest']}"
    teams = doc.get('teams') or {}
    if aid == 'div':
        return f"{A} and {H} are both in the {(teams.get(g['home']) or {}).get('division') or 'same'} division"
    if aid == 'conf':
        return f"{A} and {H} are both in the {(teams.get(g['home']) or {}).get('conference') or 'same'} conference"
    if aid == 'nonconf':
        return f"{A} and {H} are in different conferences" if sp['key'] != 'mlb' else f"{A} and {H} are in different leagues"
    return ''


def outcome(sp, doc, G, k, market, kind, bet, side):
    """'COL won the 1st period 1-0 ✓' for the example line."""
    g = G['g']
    r = g['res'][k]
    a, h = r['sc']
    sw = seg_words(sp, k)
    if kind == 'side':
        res, _ = side_result(g, k, market, side)
        mine, theirs = (a, h) if side == 'away' else (h, a)
        c = code(doc, g[side])
        if market == 'ats':
            line = ((((g.get('odds') or {}).get(k) or {}).get('ats') or {}).get(side) or {}).get('line')
            lt = f" {fmt_price(line)}" if isinstance(line, (int, float)) else ''
            text = f"{c}{lt} {'covered' if res == 'W' else 'pushed' if res == 'P' else 'failed to cover'} ({mine}–{theirs})"
        else:
            verb = 'won' if mine > theirs else 'lost' if mine < theirs else 'tied'
            text = f"{c} {verb} the {sw} {max(mine, theirs)}–{min(mine, theirs)}"
    else:
        res, _ = game_result(g, k, market, bet)
        if market == 'total':
            line = (((g.get('odds') or {}).get(k) or {}).get('total') or {}).get('line')
            tot = a + h
            went = {'O': 'went Over', 'U': 'went Under'}.get(r.get('tot'), 'landed on')
            text = f"the {sw} {went}" + (f" {line:g}" if isinstance(line, (int, float)) else '') + f" ({tot})"
        elif market == 'btts':
            text = 'both teams scored' if r.get('btts') == 'Y' else 'at least one team was held scoreless'
            text += f" in the {sw} ({a}–{h})"
        elif market == 'rfi':
            text = 'a run scored in the 1st inning' if r.get('rfi') == 'Y' else 'no run scored in the 1st inning'
        else:
            text = f"the {sw} ended {a}–{h}" + (' (a tie)' if a == h else '')
    mark = {'W': '✓', 'L': '✗'}.get(res, '–')
    return f"{text} {mark}"


# ------------------------------------------------------------- the cards

def generate(sp, doc, G_all, slate, before_date, T):
    """Cards for one slate (its games), from graded games before before_date."""
    pool = [G for G in G_all if G['date'] < before_date]
    cards = []
    for seg in sp['segments']:
        k = seg['key']
        graded = [G for G in pool if ((G['g'].get('res') or {}).get(k) or {}).get('sc')]
        if not graded:
            continue
        for market, kind, bet in bets_for(sp, k):
            # the league rate for the same bet
            lg = Rec()
            for G in graded:
                if kind == 'side':
                    for s in ('away', 'home'):
                        x = side_result(G['g'], k, market, s)
                        if x:
                            lg.add(*x)
                else:
                    x = game_result(G['g'], k, market, bet)
                    if x:
                        lg.add(*x)
            if lg.rate is None:
                continue
            base = lg.rate
            if kind == 'side':
                if market != 'ml3':
                    base = 0.5   # every game has a winner and a loser
                for aid, test in side_angles(sp):
                    def one(G):
                        o = (G['g'].get('odds') or {}).get(k) or {}
                        f = favorite(o)
                        fits = [c for c in G['sides'].values()
                                if test(G, c, f, ((o.get('ml') or {}).get(c['side'])))]
                        return fits[0] if len(fits) == 1 else None
                    tonight = [(G, one(G)) for G in slate]
                    tonight = [x for x in tonight if x[1]]
                    if not tonight:
                        continue
                    back, fade = Rec(), Rec()
                    for G in graded:
                        c = one(G)
                        if not c:
                            continue
                        for rec, s in ((back, c['side']), (fade, other(c['side']))):
                            x = side_result(G['g'], k, market, s)
                            if x:
                                rec.add(*x)
                                rec.last = (G, c, s)
                    for direction, rec in (('Back', back), ('Fade', fade)):
                        card = qualify(rec, base)
                        if not card:
                            continue
                        title, meaning, counted = angle_text(sp, T, 'side_angles', aid)
                        G0, c0, s0 = rec.last
                        card.update({
                            'id': f'{aid}:{k}:{market}:{direction.lower()}', 'angle': aid, 'seg': k, 'mk': market,
                            'tag': tag(sp, k, market), 'dir': direction,
                            'title': f'{direction} {title[0].lower()}{title[1:]}', 'meaning': meaning, 'counted': counted,
                            'note': 'ml3' if market == 'ml3' else 'side',
                            'example': f"Example: {short_day(G0['date'])}, {fact(sp, doc, G0, aid, c0, k)}, then "
                                       f"{outcome(sp, doc, G0, k, market, 'side', None, s0)}",
                            'games': [{'id': G['g']['id'], 'side': c['side'] if direction == 'Back' else other(c['side']),
                                       'fact': fact(sp, doc, G, aid, c, k)} for G, c in tonight]})
                        cards.append(card)
            else:
                for aid, test in game_angles(sp):
                    def fits(G):
                        return test(G, favorite((G['g'].get('odds') or {}).get(k)))
                    tonight = [G for G in slate if fits(G)]
                    if not tonight:
                        continue
                    rec = Rec()
                    for G in graded:
                        if fits(G):
                            x = game_result(G['g'], k, market, bet)
                            if x:
                                rec.add(*x)
                                rec.last = G
                    card = qualify(rec, base)
                    if not card:
                        continue
                    title, meaning, counted = angle_text(sp, T, 'game_angles', aid)
                    word = game_bet_word(sp, k, market, bet)
                    G0 = rec.last
                    card.update({
                        'id': f'{aid}:{k}:{market}:{bet}', 'angle': aid, 'seg': k, 'mk': market,
                        'tag': tag(sp, k, market), 'dir': None,
                        'title': f'{word}: {title[0].lower()}{title[1:]}', 'meaning': meaning, 'counted': counted,
                        'note': 'ml3' if market == 'ml3' else 'game',
                        'example': f"Example: {short_day(G0['date'])}, {fact(sp, doc, G0, aid, None, k)}, then "
                                   f"{outcome(sp, doc, G0, k, market, 'game', bet, None)}",
                        'games': [{'id': G['g']['id'], 'bet': bet,
                                   'label': game_bet_word(sp, k, market, bet, (((G['g'].get('odds') or {}).get(k) or {}).get('total') or {}).get('line')),
                                   'fact': fact(sp, doc, G, aid, None, k)} for G in tonight]})
                    cards.append(card)
    # Mirror angles make the same bet on the same games ("Back home
    # favorites" = "Fade road underdogs"): keep one, worded as Back
    cards.sort(key=lambda c: (-(c['rate'] - c['base']), -c['units'], c['dir'] != 'Back', c['id']))
    seen, out = set(), []
    for c in cards:
        sig = (c['seg'], c['mk'], c['w'], c['l'], c['t'], c['units'],
               tuple(sorted((str(x['id']), x.get('side') or x.get('bet')) for x in c['games'])))
        if sig not in seen:
            seen.add(sig)
            out.append(c)
    return out


def qualify(rec, base):
    """The card's numbers when a record clears the bar, else None."""
    if rec.n < RULES['min_games'] or rec.rate is None or not rec.priced:
        return None
    if rec.rate < base + RULES['min_edge'] - 1e-9 or rec.units <= 0:
        return None
    return {'w': rec.w, 'l': rec.l, 't': rec.t, 'rate': round(rec.rate, 4), 'base': round(base, 4),
            'units': round(rec.units, 2), 'n': rec.n}


# ------------------------------------------------------------ the slates

def slates(sp, G_all):
    """[(key, first date, games)]: by date, or by week for NFL / NCAAF."""
    groups = {}
    for G in G_all:
        key = (G['g'].get('wk') or None) if sp.get('schedule') == 'week' else G['date']
        if key:
            groups.setdefault(key, []).append(G)
    out = [(key, min(G['date'] for G in gs), gs) for key, gs in groups.items()]
    return sorted(out, key=lambda x: (x[1], x[0]))


def update(sp, doc, now_utc, log_path=None):
    """{slate key: {cards, frozen}} for the page; open slates regenerate,
    and a slate freezes once its first game starts."""
    log_path = log_path or os.path.join(LOG_DIR, f"{sp['key']}.json")
    try:
        with open(log_path, encoding='utf-8') as f:
            log = json.load(f)
    except (OSError, ValueError):
        log = {}
    if log.get('v') != LOG_VERSION:
        log = {'v': LOG_VERSION, 'slates': {}}
    T = tips()
    G_all = prepare(sp, doc)
    groups = slates(sp, G_all)
    today = now_utc.astimezone(ET).date().isoformat()
    latest = max((d for _, d, _ in groups), default=today)
    floor = (Date.fromisoformat(min(latest, today)).toordinal() - RULES['backfill_days'])
    keep = {}
    for key, d, slate in groups:
        entry = log['slates'].get(key)
        if entry is None and Date.fromisoformat(d).toordinal() < floor:
            continue
        starts = [G['g']['start'] for G in slate]
        started = d < today or now_utc >= datetime.fromisoformat(min(starts).replace('Z', '+00:00'))
        if entry is not None and not entry.get('frozen') and started:
            entry = {'cards': entry['cards'], 'frozen': True}   # the cards that were up when it started
        elif entry is None or not entry.get('frozen'):
            entry = {'cards': generate(sp, doc, G_all, slate, d, T), 'frozen': started}
        keep[key] = entry
    log['slates'] = keep
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, separators=(',', ':'))
    return keep


def page_doc(sp, doc, now_utc, log_path=None):
    """{slug}/trends.json: the cards per slate, the rules and the tooltips."""
    T = tips()
    return {'sport': sp['key'], 'shown': RULES['shown'], 'slates': update(sp, doc, now_utc, log_path),
            'markets': [[seg, m, label] for seg, m, label, _ in sp['family_markets'] if m != 'ml3' or sp['family'] == 'period'],
            'tips': {k: T[k] for k in ('footer', 'direction', 'market_notes', 'matchup_labels', 'streaks', 'status_icons', 'record_line', 'todays_record')}}
