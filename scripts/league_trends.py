"""
League Trends for the daily slate: league-wide angles (a TYPE of bet or a
TYPE of game) that apply to games on a given date.

Runs at build time (build_site.py), not in the browser, because each date's
trends have to be stored: once a date's first game starts, its list is
frozen in league_trends_log.json and only the results get filled in, so
"League Trends went X-Y on this date" never changes when later games shift
the rankings. Dates before this feature existed are generated point-in-time
(only games before that date count).

Definitions match the Stats page's stats module (template.html, rtybStats):
rest days = days between games minus 1 (0 = back-to-back; a team's first
game of a season has none); loss = full-game loss incl. OT/SO; loss by 3+;
shutout loss = 0 goals, not a 0-0 shootout; favorite = shorter 1P
moneyline; game type from the division/conference table. Grading follows
the site's existing rules: a 1P tie is a push (0u) on the moneyline and is
left out of win %; units = $100 per bet at the saved closing price, only on
games that have that price.
"""
import json
import math
import os
from datetime import date as Date, datetime, timezone
from zoneinfo import ZoneInfo

# Every threshold in one place.
CONFIG = {
    'rate_diff_pts': 8,        # hit rate must differ from the league rate by this many points...
    'units_threshold': 2.0,    # ...or units must be at least +/- this
    'min_games': 10,           # rate trends need at least this many games
    'combine_2025_26': False,  # True: splits under current_min_games also use 2025-26 (needs history passed in)
    'current_min_games': 20,
    'min_streak': 5,           # streak trends qualify at this many in a row
    'small_rate': 20,          # "small sample" tag for rate trends under this many games
    'streak_weight': 4,        # streak score = length x this
    'shown': 6,                # trends per date
    'max_per_market': 2,       # at most this many trends with the same market tag
}

ET = ZoneInfo('America/New_York')

DIVISION_CONF = {'Atlantic': 'East', 'Metropolitan': 'East', 'Central': 'West', 'Pacific': 'West'}


def _num(v):
    try:
        return None if v is None or v == '' else float(v)
    except (TypeError, ValueError):
        return None


def win_units(price):
    p = _num(price)
    if p is None or p == 0:
        return None
    return 100 / abs(p) if p < 0 else p / 100


class Rec:
    """W-L-T plus units over the priced bets."""
    def __init__(self):
        self.w = self.l = self.t = self.n = self.priced = 0
        self.units = 0.0

    def add(self, res, price):
        self.n += 1
        if res == 'W':
            self.w += 1
        elif res == 'L':
            self.l += 1
        else:
            self.t += 1
        if _num(price) is not None:
            u = -1.0 if res == 'L' else 0.0 if res == 'T' else win_units(price)
            if u is not None:
                self.units += u
                self.priced += 1

    @property
    def decisions(self):
        """W + L: ties and pushes aren't decisions (they're 0u and left
        out of rates, and minimum samples count decisions, not games)."""
        return self.w + self.l

    @property
    def rate(self):
        d = self.w + self.l
        return self.w / d if d else None

    @property
    def unit_total(self):
        return self.units if self.priced else None


def fmt_units(u):
    r = round(u + 0.0, 2)
    if r == 0:
        return '0.00u'
    return ('+' if r > 0 else '-') + f'{abs(r):.2f}u'


def fmt_price(p):
    p = _num(p)
    if p is None:
        return ''
    p = int(p) if p == int(p) else p
    return f'+{p}' if p > 0 else f'{p}'


# ---------------------------------------------------------------- games

def prepare_games(history, schedule_games, season_start, divisions):
    div_of = {c: d for d, codes in divisions.items() for c in codes}

    def game_type(a, b):
        if a not in div_of or b not in div_of:
            return None
        if div_of[a] == div_of[b]:
            return 'div'
        return 'conf' if DIVISION_CONF[div_of[a]] == DIVISION_CONF[div_of[b]] else 'nonconf'

    games = []
    for g in history:
        games.append(dict(src=g, season='2025-26', date=g['date'], done=True))
    for d, gs in schedule_games.items():
        if d < season_start:
            continue
        for g in gs:
            games.append(dict(src=g, season='2026-27', date=d, done=g.get('state') in ('FINAL', 'OFF')))
    games.sort(key=lambda G: (G['src'].get('startTimeUTC') or G['date'], G['date']))

    last = {}
    for G in games:
        g = G['src']
        G['away'], G['home'] = g['away'], g['home']
        G['key'] = f"{G['date']}|{g['away']}|{g['home']}"
        G['graded'] = g.get('awayP1') is not None and g.get('homeP1') is not None
        G['total'] = g['awayP1'] + g['homeP1'] if G['graded'] else None
        G['over'] = G['graded'] and G['total'] > 1
        G['btts'] = G['graded'] and g['awayP1'] >= 1 and g['homeP1'] >= 1
        G['type'] = game_type(g['away'], g['home'])
        odds = (g.get('odds') or {}) if G['season'] == '2026-27' else {}
        ml = odds.get('ml') or {}
        tot = (odds.get('totals') or {}).get('1.5') or {}
        G['price'] = {'away': _num(ml.get(g['away'])), 'home': _num(ml.get(g['home'])),
                      'over': _num(tot.get('over')), 'under': _num(tot.get('under')),
                      'yes': _num(odds.get('btts_yes')), 'no': _num(odds.get('btts_no'))}
        pa, ph = G['price']['away'], G['price']['home']
        G['fav'] = ('home' if ph < pa else 'away') if pa is not None and ph is not None and pa != ph else None
        for side in ('away', 'home'):
            team = g[side]
            prev = last.get((G['season'], team))
            c = {'team': team, 'opp': g['home'] if side == 'away' else g['away'], 'side': side,
                 'rest': None, 'prev': None, 'price': G['price'][side]}
            if prev:
                c['rest'] = (Date.fromisoformat(G['date']) - Date.fromisoformat(prev['date'])).days - 1
                pg = prev['src']
                own = pg.get('awayFinal') if pg['away'] == team else pg.get('homeFinal')
                opp = pg.get('homeFinal') if pg['away'] == team else pg.get('awayFinal')
                if prev['done'] and own is not None and opp is not None:
                    c['prev'] = {'lost': own < opp, 'lostBy3': opp - own >= 3,
                                 'shutout': own == 0 and pg.get('ot') != 'SO'}
            if G['graded']:
                mine = g['awayP1'] if side == 'away' else g['homeP1']
                theirs = g['homeP1'] if side == 'away' else g['awayP1']
                c['res'] = 'W' if mine > theirs else 'L' if mine < theirs else 'T'
            G[side] = c
            last[(G['season'], team)] = G
        G['sides'] = (G['away'], G['home'])
    return games


# ---------------------------------------------------------------- angles

def _other(G, c):
    return G['home'] if c is G['away'] else G['away']


def _rest_edge(G):
    a, h = G['away']['rest'], G['home']['rest']
    return a is not None and h is not None and a != h


# Side angles: (key, plural noun for sentences, test(G, side ctx), pair key or None, priced-only)
SIDE_ANGLES = [
    ('home_fav', 'Home Favorites', lambda G, c: c['side'] == 'home' and G['fav'] == 'home', 'ha_fav', True),
    ('road_dog', 'Road Underdogs', lambda G, c: c['side'] == 'away' and G['fav'] == 'home', 'ha_fav', True),
    ('home_dog', 'Home Underdogs', lambda G, c: c['side'] == 'home' and G['fav'] == 'away', 'ha_dog', True),
    ('road_fav', 'Road Favorites', lambda G, c: c['side'] == 'away' and G['fav'] == 'away', 'ha_dog', True),
    ('tier1', 'Sides at -150 or shorter', lambda G, c: c['price'] is not None and c['price'] <= -150, None, True),
    ('tier2', 'Sides priced -149 to -101', lambda G, c: c['price'] is not None and -150 < c['price'] <= -101, None, True),
    ('tier3', 'Sides priced +100 to +149', lambda G, c: c['price'] is not None and (100 <= c['price'] <= 149 or c['price'] == -100), None, True),
    ('tier4', 'Sides at +150 or longer', lambda G, c: c['price'] is not None and c['price'] >= 150, None, True),
    ('b2b', 'Teams on a back-to-back', lambda G, c: c['rest'] == 0 and _other(G, c)['rest'] != 0, 'b2b', False),
    ('b2b_opp', 'Opponents of a back-to-back team', lambda G, c: c['rest'] != 0 and _other(G, c)['rest'] == 0, 'b2b', False),
    ('rested', 'Rested teams (rest edge)', lambda G, c: _rest_edge(G) and c['rest'] > _other(G, c)['rest'], 'rest', False),
    ('tired', 'Tired teams (rest edge)', lambda G, c: _rest_edge(G) and c['rest'] < _other(G, c)['rest'], 'rest', False),
    ('off_loss', 'Teams coming off a loss', lambda G, c: bool(c['prev'] and c['prev']['lost']), None, False),
    ('off_loss3', 'Teams coming off a loss by 3+', lambda G, c: bool(c['prev'] and c['prev']['lostBy3']), None, False),
    ('off_shutout', 'Teams coming off a shutout loss', lambda G, c: bool(c['prev'] and c['prev']['shutout']), None, False),
]

# Game angles: (key, phrase for "in ___", streak phrase for "N straight ___", test(G), priced-only)
GAME_ANGLES = [
    ('div', 'Divisional games', 'Divisional games', lambda G: G['type'] == 'div', False),
    ('conf', 'Conference games', 'Conference games', lambda G: G['type'] == 'conf', False),
    ('nonconf', 'Non-Conference games', 'Non-Conference games', lambda G: G['type'] == 'nonconf', False),
    ('rest_edge', 'games with a rest edge', 'games with a rest edge', _rest_edge, False),
    ('even_rest', 'games with even rest', 'games with even rest',
     lambda G: G['away']['rest'] is not None and G['away']['rest'] == G['home']['rest'], False),
    ('b2b_game', 'games with a team on a back-to-back', 'games with a team on a back-to-back',
     lambda G: G['away']['rest'] == 0 or G['home']['rest'] == 0, False),
    ('off_loss_game', 'games with a team coming off a loss', 'games with a team coming off a loss',
     lambda G: any(c['prev'] and c['prev']['lost'] for c in G['sides']), False),
    ('off_loss3_game', 'games with a team coming off a loss by 3+', 'games with a team coming off a loss by 3+',
     lambda G: any(c['prev'] and c['prev']['lostBy3'] for c in G['sides']), False),
    ('off_shutout_game', 'games with a team coming off a shutout loss', 'games with a team coming off a shutout loss',
     lambda G: any(c['prev'] and c['prev']['shutout'] for c in G['sides']), False),
    ('home_fav_game', 'games with a Home Favorite', 'games with a Home Favorite', lambda G: G['fav'] == 'home', True),
    ('home_dog_game', 'games with a Home Underdog', 'games with a Home Underdog', lambda G: G['fav'] == 'away', True),
]

# Game markets: tag, result(G) -> 'W'/'L', price key
GAME_MARKETS = {
    'O1.5': (lambda G: 'W' if G['over'] else 'L', 'over'),
    'U1.5': (lambda G: 'L' if G['over'] else 'W', 'under'),
    'BTTS Yes': (lambda G: 'W' if G['btts'] else 'L', 'yes'),
    'BTTS No': (lambda G: 'L' if G['btts'] else 'W', 'no'),
}
MARKET_FAMILY = {'O1.5': 'ou', 'U1.5': 'ou', 'BTTS Yes': 'btts', 'BTTS No': 'btts', 'ML': 'ml'}


def _market_rate_words(tag, pct, phrase, window):
    if tag == 'O1.5':
        return f'Over 1.5 has hit {pct}% in {phrase} {window}'
    if tag == 'U1.5':
        return f'Under 1.5 has hit {pct}% in {phrase} {window}'
    if tag == 'BTTS Yes':
        return f'BTTS has hit {pct}% in {phrase} {window}'
    return f'BTTS has missed {pct}% in {phrase} {window}'


def _market_streak_words(tag, n, phrase):
    return {
        'O1.5': f'The Over 1.5 has hit in {n} straight {phrase}',
        'U1.5': f'The Under 1.5 has hit in {n} straight {phrase}',
        'BTTS Yes': f'BTTS has hit in {n} straight {phrase}',
        'BTTS No': f'BTTS has missed in {n} straight {phrase}',
    }[tag]


# ---------------------------------------------------------------- generator

def _tonight_side(G, c):
    opp = _other(G, c)
    price = fmt_price(c['price'])
    return {'key': G['key'], 'kind': 'side', 'side': c['side'], 'market': 'ML',
            'label': f"{c['team']}{' ' + price if price else ''} {'vs' if c['side'] == 'home' else '@'} {opp['team']}"}


def _tonight_game(G, tag):
    price = fmt_price(G['price'][GAME_MARKETS[tag][1]])
    short = {'O1.5': 'O', 'U1.5': 'U', 'BTTS Yes': 'Y', 'BTTS No': 'N'}[tag]
    return {'key': G['key'], 'kind': 'game', 'market': tag,
            'label': f"{G['away']['team']}–{G['home']['team']}" + (f' ({short} {price})' if price else '')}


def _pick_sig(g):
    """(game + market family, which side of it) for one pick."""
    if g['kind'] == 'side':
        return (g['key'] + ':ml', g['side'])
    return (g['key'] + ':' + MARKET_FAMILY[g['market']], g['market'])


def generate_for_date(games, d):
    """Candidates for date d using only games before d; returns the top list."""
    before = [G for G in games if G['date'] < d and G['graded']]
    cur_before = [G for G in before if G['season'] == '2026-27']
    tonight = [G for G in games if G['date'] == d and G['season'] == '2026-27']
    if not tonight:
        return []
    cands = []

    # ---- side angles on the 1P moneyline
    for key, noun, test, pair, priced_only in SIDE_ANGLES:
        # A game where both teams fit the angle would mean betting both sides.
        sides_tonight = [(G, c) for G in tonight for c in G['sides'] if test(G, c) and not test(G, _other(G, c))]
        if not sides_tonight:
            continue
        tonight_list = [_tonight_side(G, c) for G, c in sides_tonight]

        def tally(pool):
            r = Rec()
            for G in pool:
                for c in G['sides']:
                    if test(G, c):
                        r.add(c['res'], c['price'])
            return r

        cur = tally(cur_before)
        since = False
        rec = cur
        if CONFIG['combine_2025_26'] and cur.n < CONFIG['current_min_games'] and not priced_only:
            rec, since = tally(before), True
        rate, units = rec.rate, rec.unit_total
        if rec.decisions >= CONFIG['min_games'] and rate is not None:
            diff = (rate - 0.5) * 100
            if abs(diff) >= CONFIG['rate_diff_pts'] or (units is not None and abs(units) >= CONFIG['units_threshold']):
                window = 'since 2025–26' if since else 'this season'
                u_txt = f' ({fmt_units(units)})' if units is not None else ''
                # A losing angle is shown as a fade (bet against it).
                fade = (units is not None and units <= -CONFIG['units_threshold']) or \
                    (diff < 0 and not (units is not None and units >= CONFIG['units_threshold']))
                sentence = (f'Fade: {noun} are' if fade else f'{noun} are') + f' {rec.w}-{rec.l}-{rec.t}{u_txt} in the 1st period {window}'
                score = abs(diff) * math.sqrt(rec.decisions)
                if units is not None and rec.priced:
                    score = max(score, abs(units / rec.priced) * 100 * math.sqrt(rec.priced))
                picks = [_tonight_side(G, _other(G, c)) for G, c in sides_tonight] if fade else tonight_list
                cands.append({'id': f'rate:{key}:ML', 'family': pair or key, 'market': 'ML', 'sentence': sentence,
                              'record': f'{rec.w}-{rec.l}-{rec.t}', 'units': units, 'n': rec.decisions, 'fade': fade,
                              'small': rec.decisions < CONFIG['small_rate'], 'score': score, 'games': picks})

        # streak: consecutive won / lost 1P for this angle, current season, newest first
        seq = [c['res'] for G in reversed(cur_before) for c in G['sides'] if test(G, c)]
        if seq and seq[0] in ('W', 'L'):
            n = 0
            for r in seq:
                if r != seq[0]:
                    break
                n += 1
            if n >= CONFIG['min_streak']:
                verb = 'won' if seq[0] == 'W' else 'lost'
                cands.append({'id': f'streak:{key}:ML', 'family': pair or key, 'market': 'ML',
                              'sentence': f'{noun} have {verb} the 1P in {n} straight', 'record': f'{n} straight',
                              'units': None, 'n': n, 'small': n < CONFIG['min_streak'],
                              'score': n * CONFIG['streak_weight'], 'games': tonight_list})

    # ---- game angles on Over/Under 1.5 and BTTS
    for key, phrase, streak_phrase, test, priced_only in GAME_ANGLES:
        games_tonight = [G for G in tonight if test(G)]
        if not games_tonight:
            continue
        cur_pool = [G for G in cur_before if test(G)]
        since = CONFIG['combine_2025_26'] and len(cur_pool) < CONFIG['current_min_games'] and not priced_only
        pool = [G for G in before if test(G)] if since else cur_pool
        league = before if since else cur_before
        for fam, (hit_tag, miss_tag) in (('ou', ('O1.5', 'U1.5')), ('btts', ('BTTS Yes', 'BTTS No'))):
            best = None
            for tag in (hit_tag, miss_tag):
                res_fn, pkey = GAME_MARKETS[tag]
                r = Rec()
                for G in pool:
                    r.add(res_fn(G), G['price'][pkey])
                lg = Rec()
                for G in league:
                    lg.add(res_fn(G), None)
                if r.decisions < CONFIG['min_games'] or not lg.n:
                    continue
                rate, lrate, units = r.w / r.n, lg.w / lg.n, r.unit_total
                diff = (rate - lrate) * 100
                if diff < 0 and not (units is not None and units >= CONFIG['units_threshold']):
                    continue  # the other side of this angle is the one to show
                if diff >= CONFIG['rate_diff_pts'] or (units is not None and abs(units) >= CONFIG['units_threshold']):
                    window = 'since 2025–26' if since else 'this season'
                    # Qualified only on losing units: say it's a fade.
                    fade = diff < CONFIG['rate_diff_pts'] and units is not None and units <= -CONFIG['units_threshold']
                    sentence = ('Fade: ' if fade else '') + _market_rate_words(tag, round(rate * 100), phrase, window) + \
                        f' (league {round(lrate * 100)}%)'
                    score = abs(diff) * math.sqrt(r.decisions)
                    pick_tag = (miss_tag if tag == hit_tag else hit_tag) if fade else tag
                    c = {'id': f'rate:{key}:{tag}', 'family': f'{key}:{fam}', 'market': pick_tag, 'sentence': sentence,
                         'record': f'{r.w}/{r.n} ({round(rate * 100)}%)', 'units': units, 'n': r.decisions, 'fade': fade,
                         'small': r.decisions < CONFIG['small_rate'], 'score': score,
                         'games': [_tonight_game(G, pick_tag) for G in games_tonight]}
                    if best is None or c['score'] > best['score']:
                        best = c
            if best:
                cands.append(best)

            # streak, current season only
            seq = [G for G in reversed(cur_before) if test(G)]
            if seq:
                first_hit = GAME_MARKETS[hit_tag][0](seq[0]) == 'W'
                tag = hit_tag if first_hit else miss_tag
                n = 0
                for G in seq:
                    if (GAME_MARKETS[hit_tag][0](G) == 'W') != first_hit:
                        break
                    n += 1
                if n >= CONFIG['min_streak']:
                    cands.append({'id': f'streak:{key}:{tag}', 'family': f'{key}:{fam}', 'market': tag,
                                  'sentence': _market_streak_words(tag, n, streak_phrase), 'record': f'{n} straight',
                                  'units': None, 'n': n, 'small': False,
                                  'score': n * CONFIG['streak_weight'],
                                  'games': [_tonight_game(G, tag) for G in games_tonight]})

    # ---- rank: one trend per angle family (never both sides), max per market, top N
    cands.sort(key=lambda c: (-c['score'], -len(c['games'])))
    picked, families, per_market, taken = [], set(), {}, {}
    for c in cands:
        if c['family'] in families or per_market.get(c['market'], 0) >= CONFIG['max_per_market']:
            continue
        # Never let two trends pick opposite sides of the same game.
        sigs = [_pick_sig(g) for g in c['games']]
        if any(taken.get(k, v) != v for k, v in sigs):
            continue
        for k, v in sigs:
            taken[k] = v
        picked.append(c)
        families.add(c['family'])
        per_market[c['market']] = per_market.get(c['market'], 0) + 1
        if len(picked) >= CONFIG['shown']:
            break
    for c in picked:
        c.pop('family', None)
        c['score'] = round(c['score'], 1)
    return picked


def grade(entry, games_by_key):
    """Fill each tonight game's status: PENDING, or W / L / P (push) once the 1P is graded."""
    w = l = 0
    for t in entry['trends']:
        for g in t['games']:
            G = games_by_key.get(g['key'])
            if not G or not G['graded']:
                g['status'] = 'PENDING'
                continue
            if g['kind'] == 'side':
                res = G[g['side']]['res']
            else:
                res = GAME_MARKETS[g['market']][0](G)
            g['status'] = 'P' if res == 'T' else res
            w += res == 'W'
            l += res == 'L'
    entry['record'] = {'w': w, 'l': l}


def update_log(log, games, today_et, now_utc):
    """Regenerate open dates, keep frozen ones, regrade everything."""
    games_by_key = {G['key']: G for G in games if G['season'] == '2026-27'}
    dates = sorted({G['date'] for G in games if G['season'] == '2026-27'})
    for d in dates:
        starts = [G['src'].get('startTimeUTC') for G in games if G['date'] == d and G['season'] == '2026-27']
        starts = [s for s in starts if s]
        first = min(starts) if starts else None
        started = d < today_et or (first is not None and now_utc >= datetime.fromisoformat(first.replace('Z', '+00:00')))
        entry = log.get(d)
        if entry is None or not entry.get('frozen'):
            entry = {'trends': generate_for_date(games, d), 'frozen': started}
            log[d] = entry
        elif started:
            entry['frozen'] = True
        grade(entry, games_by_key)
    return log


def build(history, schedule_games, season_start, divisions, log_path):
    games = prepare_games(history, schedule_games, season_start, divisions)
    log = {}
    if os.path.exists(log_path):
        with open(log_path, encoding='utf-8') as f:
            log = json.load(f)
    now_utc = datetime.now(timezone.utc)
    today_et = now_utc.astimezone(ET).date().isoformat()
    update_log(log, games, today_et, now_utc)
    with open(log_path, 'w', encoding='utf-8') as f:
        json.dump(log, f, separators=(',', ':'), ensure_ascii=False)
    return log
