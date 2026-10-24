"""
Today's Picks (/picks/): trend-based plays for the opening segment of
today's games in every sport, ranked by confidence. Each play is saved to
picks_log.json before its game starts (frozen from then on) and graded
once the segment is final, so every tier's record is public and real.

How a play is built (build_plays):
  1. For each game on today's slate that hasn't started, each period and
     each market with a saved line -- moneyline (needs a price), spread,
     total (NHL: Over/Under 1.5 and BTTS; MLB 1st inning: YRFI / NRFI) --
     and each side, collect "angles" from this season's graded games, all
     played before this game, at TODAY's line:
       the team's record in that market this season, over its last 8,
       and at this venue (home / road), and the opponent's record at its
       venue, read from the side being bet.
  2. Confidence: each angle's hit rate is pulled toward 50% by RULES
     ['shrink'] pseudo-games, and the angles are averaged by sample size
     (moneylines: the team's rate head to head against the opponent's,
     log5). The market price is the starting point: the estimate moves the
     price's implied chance by n / (n + RULES['market']), n = the season
     sample, and the EDGE is how far it moved (-110 when no price was saved
     for a spread / total). Small samples barely move it.
  3. A play needs RULES['min_angles'] angles that agree (over 50%) and an
     edge of at least RULES['min_edge']. Tiers: A / B by edge and sample
     (RULES['tiers']); a season sample under RULES['small'] can't rank
     above C, and a play without a saved price can't rank above B.
  4. Personalities tag each play: Chalk Eater (favorite), Dog Hunter
     (underdog), Over Lover (over / BTTS yes / YRFI), Under Grinder (under /
     BTTS no / NRFI), Streak Rider (rides a streak of RULES['streak_min']+
     at this line), Contrarian (bets against one), Early Bird (kickoff
     before 1:30 PM ET).

Grading uses the line and price saved with the play: W / L / P (a push,
or a tied segment on a moneyline) and units at the saved price (-110 when
none), NA when the game isn't played.
"""
import json
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import grading
import sports

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
LOG_PATH = os.path.join(ROOT, 'picks_log.json')

# Tune here.
RULES = {
    'shrink': 8,            # pseudo-games at 50% each angle is pulled toward
    'market': 30,           # trust in the price: the trend estimate moves it by n / (n + this)
    'min_n': 3,             # an angle needs this many decisions to count
    'min_angles': 2,        # agreeing angles a play needs
    'min_edge': 0.03,       # edge over the price's implied probability
    'tiers': [('A', 0.06, 15), ('B', 0.04, 10)],   # (tier, min edge, min season sample); else C
    'small': 10,            # season sample under this: C at most
    'per_game': 2,          # plays per game at most
    'max_plays': 12,        # plays per day at most
    'free': 3,              # plays shown free; the rest are Premium
    'last_n': 8,
    'streak_min': 4,
    'early_bird': 13 * 60 + 30,   # kickoff before 1:30 PM ET
}
PERSONALITIES = ['Chalk Eater', 'Dog Hunter', 'Streak Rider', 'Contrarian', 'Over Lover', 'Under Grinder', 'Early Bird']
DEFAULT_PRICE = -110


# ------------------------------------------------------------------ games

def _state(st):
    return {'OFF': 'final', 'FINAL': 'final', 'LIVE': 'in', 'CRIT': 'in', 'final': 'final', 'in': 'in',
            'postponed': 'off', 'canceled': 'off', 'suspended': 'off', 'PPD': 'off', 'CNCL': 'off'}.get(st, 'pre')


def et_date(iso):
    return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET).date().isoformat()


def load_games(nhl_data, nhl_city):
    """Every sport's current-season games in one shape:
    {sport, label, slug, key, start, date, state, away, home, names{code: short},
     segs: {k: {tag, label, sc (away, home) or None, odds{ml, ats, total, btts}}}}"""
    out = []
    names = {c: nhl_city.get(c) or v.get('name', c) for c, v in (nhl_data.get('summary') or {}).items()}
    for d, games in ((nhl_data.get('schedule') or {}).get('games') or {}).items():
        for g in games:
            st = _state(g.get('state'))
            o = g.get('odds') or {}
            ml = o.get('ml') or {}
            t15 = (o.get('totals') or {}).get('1.5') or {}
            p1 = (g.get('awayP1'), g.get('homeP1'))
            out.append({
                'sport': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'key': f"nhl|{g.get('id')}", 'start': g.get('startTimeUTC'),
                'date': d, 'state': st, 'away': g['away'], 'home': g['home'],
                'names': {g['away']: names.get(g['away'], g['away']), g['home']: names.get(g['home'], g['home'])},
                'href': f'nhl/games/?date={d}',
                'segs': {'1p': {'tag': '1P', 'label': '1st Period',
                                'sc': p1 if st == 'final' and None not in p1 else None,
                                'odds': {'ml': {'away': ml.get(g['away']), 'home': ml.get(g['home'])},
                                         'total': {'line': 1.5, 'over': t15.get('over'), 'under': t15.get('under')} if t15 else None,
                                         'btts': {'yes': o.get('btts_yes'), 'no': o.get('btts_no')}}}},
            })
    for sp in sports.SPORTS:
        if sp['key'] == 'nhl':
            continue
        path = os.path.join(ROOT, sp['slug'], 'data.json')
        doc = json.load(open(path, encoding='utf-8')) if os.path.exists(path) else {}
        teams = doc.get('teams') or {}
        segs = doc.get('segments') or []
        for d, games in (doc.get('games') or {}).items():
            for g in games:
                st = _state(g.get('state'))
                nm = {}
                for side in ('away', 'home'):
                    t = teams.get(g[side]) or {}
                    nm[g[side]] = t.get('short') or t.get('name') or g.get(side + 'Name') or g[side]
                G = {'sport': sp['key'], 'label': sp['label'], 'slug': sp['slug'], 'key': f"{sp['key']}|{g['id']}",
                     'start': g.get('start'), 'date': d, 'state': st, 'away': g['away'], 'home': g['home'], 'names': nm,
                     'href': f"{sp['slug']}/games/", 'segs': {}}
                for s in segs:
                    k = s['key']
                    r = ((g.get('res') or {}).get(k)) or {}
                    o = ((g.get('odds') or {}).get(k)) or {}
                    if k == '1i':   # MLB 1st inning: YRFI / NRFI as Over / Under 0.5
                        ny = o.get('nrfi_yrfi') or {}
                        odds = {'total': {'line': 0.5, 'over': ny.get('yrfi'), 'under': ny.get('nrfi'), 'rfi': True}} if ny else {}
                    else:
                        ats = o.get('ats') or {}
                        tot = o.get('total') or {}
                        odds = {'ml': o.get('ml') or {},
                                'ats': {'line': (ats.get('away') or {}).get('line'), 'away': (ats.get('away') or {}).get('price'),
                                        'home': (ats.get('home') or {}).get('price')} if ats.get('away') else None,
                                'total': {'line': tot.get('line'), 'over': tot.get('over'), 'under': tot.get('under')} if tot.get('line') is not None else None}
                    G['segs'][k] = {'tag': s['tag'] if k != '1i' else '1st Inn', 'label': s['label'],
                                    'sc': tuple(r['sc']) if r.get('sc') and not r.get('na') else None, 'odds': odds}
                out.append(G)
    return [g for g in out if g.get('start')]


# ------------------------------------------------------------- outcomes

def outcome(market, side, line, sc, from_home=False):
    """'W' / 'L' / 'P' for a bet on a final segment score sc (away, home).
    side: 'away' / 'home' (ml, ats), 'over' / 'under' (total), 'yes' / 'no'
    (btts). ats line is the bet side's line."""
    a, h = sc
    if market == 'ml':
        m = (a - h) if side == 'away' else (h - a)
        return 'W' if m > 0 else 'L' if m < 0 else 'P'
    if market == 'ats':
        m = ((a - h) if side == 'away' else (h - a)) + line
        return 'W' if m > 0 else 'L' if m < 0 else 'P'
    if market == 'total':
        t = a + h
        if t == line:
            return 'P'
        return 'W' if (t > line) == (side == 'over') else 'L'
    if market == 'btts':
        both = a >= 1 and h >= 1
        return 'W' if both == (side == 'yes') else 'L'
    return None


def units(result, price):
    return grading.bet_units(result, price if price is not None else DEFAULT_PRICE)


def implied(price):
    if price is None:
        return None
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def rec_text(w, l, p):
    return f'{w}-{l}' + (f'-{p}' if p else '')


# ---------------------------------------------------------------- angles

def team_history(games):
    """{(sport, team): [(game, side, k, sc), ...]} oldest first, finals only."""
    hist = {}
    for g in sorted(games, key=lambda x: x['start']):
        for k, s in g['segs'].items():
            if s['sc'] is None:
                continue
            for side in ('away', 'home'):
                hist.setdefault((g['sport'], g[side]), []).append((g, side, k, s['sc']))
    return hist


def _rows(hist, sport, team, k, before):
    return [h for h in hist.get((sport, team), []) if h[2] == k and h[0]['start'] < before]


def _tally(rows, fn):
    w = l = p = 0
    for row in rows:
        r = fn(row)
        if r == 'W':
            w += 1
        elif r == 'L':
            l += 1
        elif r == 'P':
            p += 1
    return w, l, p


def _streak(rows, fn):
    """Current run, newest back: (+n hits) or (-n misses); pushes end it."""
    n, kind = 0, None
    for row in reversed(rows):
        r = fn(row)
        if r not in ('W', 'L'):
            break
        if kind is None:
            kind = r
        if r != kind:
            break
        n += 1
    return n if kind == 'W' else -n


def market_words(market, side, line, tag, rfi=False):
    """('Over 1.5', 'overs') style words for labels."""
    if market == 'total':
        if rfi:
            return ('YRFI', 'YRFIs') if side == 'over' else ('NRFI', 'NRFIs')
        return (f'{side.title()} {fmt_line(line)}', f'{side}s')
    if market == 'btts':
        return ('BTTS Yes', 'BTTS') if side == 'yes' else ('BTTS No', 'no-BTTS')
    if market == 'ats':
        return (f'{fmt_line(line, True)}', 'ATS')
    return ('ML', 'ML')


def fmt_line(x, signed=False):
    if x is None:
        return ''
    s = str(int(x)) if float(x).is_integer() else str(x)
    return (('+' + s) if x > 0 else s) if signed else s


def fmt_price(p):
    return '' if p is None else ('+' if p > 0 else '') + str(int(p))


def angles_for(hist, g, k, market, side, line):
    """The angles behind one bet, each {label, w, l, p}, plus the bet team's
    current streak at this line and a short info line."""
    seg = g['segs'][k]
    tag = seg['tag']
    rfi = bool((seg['odds'].get('total') or {}).get('rfi'))
    sport, before = g['sport'], g['start']
    if market in ('ml', 'ats'):
        team = g[side]
        opp = g['home'] if side == 'away' else g['away']
        venue = 'at home' if side == 'home' else 'on the road'
        ovenue = 'at home' if side == 'away' else 'on the road'
        word = 'ML' if market == 'ml' else f'ATS at {fmt_line(line, True)}'

        def mine(row):        # the bet team's own games, from its side
            gg, s, kk, sc = row
            return outcome(market, s, line if market == 'ats' else None, sc)

        def theirs(row):      # the opponent's games: the opponent's opponents' side
            gg, s, kk, sc = row
            return outcome(market, 'home' if s == 'away' else 'away', line if market == 'ats' else None, sc)
        rows_t = _rows(hist, sport, team, k, before)
        rows_o = _rows(hist, sport, opp, k, before)
        venue_t = [r for r in rows_t if r[1] == side]
        venue_o = [r for r in rows_o if r[1] != side]
        tn, on = g['names'][team], g['names'][opp]
        angles = [
            {'label': f'{tn} {tag} {word}, season', 'season': True, **dict(zip('wlp', _tally(rows_t, mine)))},
            {'label': f'{tn} {tag} {word}, last {RULES["last_n"]}', **dict(zip('wlp', _tally(rows_t[-RULES['last_n']:], mine)))},
            {'label': f'{tn} {tag} {word} {venue}', **dict(zip('wlp', _tally(venue_t, mine)))},
            {'label': f'{on}’s opponents {tag} {word}, {on} {ovenue}', **dict(zip('wlp', _tally(venue_o, theirs)))},
        ]
        streak = _streak(rows_t, mine)
        if market == 'ml':
            # the opponent's own moneyline record (season, and at its venue),
            # for the head-to-head estimate in evaluate()
            own = lambda row: outcome('ml', row[1], None, row[3])
            angles.append({'label': None, 'opp': True, 'season': False, **dict(zip('wlp', _tally(rows_o, own)))})
            angles.append({'label': None, 'opp': True, 'season': False, **dict(zip('wlp', _tally(venue_o, own)))})
        if market == 'ats' and rows_t:
            marg = [(sc[0] - sc[1]) if s == 'away' else (sc[1] - sc[0]) for gg, s, kk, sc in venue_t or rows_t]
            info = f'{tn} avg {tag} margin {venue if venue_t else "this season"}: {sum(marg) / len(marg):+.1f}'
        else:
            info = None
        return angles, streak, info, team
    # totals / BTTS: both teams' games at today's line, from the bet's side
    away, home = g['away'], g['home']

    def fn(row):
        gg, s, kk, sc = row
        return outcome(market, side, line, sc)
    rows_a, rows_h = _rows(hist, sport, away, k, before), _rows(hist, sport, home, k, before)
    words = market_words(market, side, line, tag, rfi)[1]
    an, hn = g['names'][away], g['names'][home]
    lt = f' ({fmt_line(line)})' if market == 'total' and not rfi else ''
    angles = [
        {'label': f'{hn} {tag} {words} at home{lt}', **dict(zip('wlp', _tally([r for r in rows_h if r[1] == 'home'], fn)))},
        {'label': f'{an} {tag} {words} on the road{lt}', **dict(zip('wlp', _tally([r for r in rows_a if r[1] == 'away'], fn)))},
        {'label': f'{hn} {tag} {words}, season{lt}', 'season': True, **dict(zip('wlp', _tally(rows_h, fn)))},
        {'label': f'{an} {tag} {words}, season{lt}', 'season': True, **dict(zip('wlp', _tally(rows_a, fn)))},
        {'label': f'{hn} {tag} {words}, last {RULES["last_n"]}{lt}', **dict(zip('wlp', _tally(rows_h[-RULES['last_n']:], fn)))},
        {'label': f'{an} {tag} {words}, last {RULES["last_n"]}{lt}', **dict(zip('wlp', _tally(rows_a[-RULES['last_n']:], fn)))},
    ]
    sa, sh = _streak(rows_a, fn), _streak(rows_h, fn)
    streak, team = (sa, away) if abs(sa) >= abs(sh) else (sh, home)
    info = None
    if market == 'total' and not rfi and (rows_a or rows_h):
        def avg(rows):
            return sum(sc[0] + sc[1] for gg, s, kk, sc in rows) / len(rows) if rows else None
        parts = [f'{n} {v:.1f}' for n, v in ((hn, avg(rows_h)), (an, avg(rows_a))) if v is not None]
        info = f'Avg {tag} total in their games: ' + ' · '.join(parts)
    return angles, streak, info, team


def _blend(angles):
    """Sample-weighted average of the angles' hit rates, each pulled
    toward 50% by RULES['shrink'] pseudo-games."""
    K = RULES['shrink']
    num = den = 0.0
    for a in angles:
        n = a['w'] + a['l']
        if n >= RULES['min_n']:
            num += n * (a['w'] + 0.5 * K) / (n + K)
            den += n
    return num / den if den else None


def log5(pa, pb):
    """Chance A beats B from each one's win rate (Bill James' log5)."""
    d = pa * (1 - pb) + pb * (1 - pa)
    return pa * (1 - pb) / d if d else 0.5


def confidence(angles):
    """(estimate, agreeing angles, season sample). Spreads, totals, BTTS:
    the blended hit rate of every angle at today's line. Moneylines: the
    team's blended win rate against the opponent's, head to head (log5),
    so a good record against weak teams doesn't make every dog a play."""
    opp = [a for a in angles if a.get('opp')]
    angles = [a for a in angles if not a.get('opp')]
    if opp:
        pa = _blend([a for a in angles if '’s opponents' not in a['label']])
        pb = _blend(opp)
        est = log5(pa, pb) if pa is not None and pb is not None else None
    else:
        est = _blend(angles)
    agree = 0
    season_n = 0
    for a in angles:
        n = a['w'] + a['l']
        if a.get('season'):
            season_n = max(season_n, n)
        if n >= RULES['min_n'] and a['w'] / n > 0.5:
            agree += 1
    return est, agree, season_n


def tier_of(edge, sample, priced):
    if sample < RULES['small']:
        return 'C'
    for t, e, n in RULES['tiers']:
        if edge >= e and sample >= n and (priced or t != 'A'):
            return t
    return 'C'


# ------------------------------------------------------------------ plays

def candidate_bets(g, k):
    """(market, side, line, price, priced, opp_price) for every bet with a
    saved line on this game segment."""
    o = g['segs'][k]['odds'] or {}
    out = []
    ml = o.get('ml') or {}
    if grading.num(ml.get('away')) is not None and grading.num(ml.get('home')) is not None:
        out.append(('ml', 'away', None, ml['away'], True, ml['home']))
        out.append(('ml', 'home', None, ml['home'], True, ml['away']))
    ats = o.get('ats')
    if ats and grading.num(ats.get('line')) is not None:
        la = ats['line']
        out.append(('ats', 'away', la, ats.get('away'), ats.get('away') is not None, None))
        out.append(('ats', 'home', -la, ats.get('home'), ats.get('home') is not None, None))
    tot = o.get('total')
    if tot and grading.num(tot.get('line')) is not None:
        rfi = tot.get('rfi')
        for s in ('over', 'under'):
            if rfi and tot.get(s) is None:
                continue
            out.append(('total', s, tot['line'], tot.get(s), tot.get(s) is not None, None))
    b = o.get('btts') or {}
    if grading.num(b.get('yes')) is not None and grading.num(b.get('no')) is not None:
        out.append(('btts', 'yes', None, b['yes'], True, None))
        out.append(('btts', 'no', None, b['no'], True, None))
    return out


def evaluate(hist, g, k, bet):
    market, side, line, price, priced, opp_price = bet
    angles, streak, info, team = angles_for(hist, g, k, market, side, line)
    model, agree, sample = confidence(angles)
    if model is None:
        return None
    # Start from the price and move toward the trend estimate by how much
    # this season's sample can say: n / (n + RULES['market']).
    imp = implied(price if priced else DEFAULT_PRICE)
    est = imp + sample / (sample + RULES['market']) * (model - imp)
    edge = est - imp
    seg = g['segs'][k]
    rfi = bool((seg['odds'].get('total') or {}).get('rfi'))
    word = market_words(market, side, line, seg['tag'], rfi)[0]
    if market in ('ml', 'ats'):
        title = f"{g['names'][g[side]]} {seg['tag']} {word}"
    else:
        title = f"{seg['tag']} {word}"
    tags = []
    if market == 'ml':
        if opp_price is not None and price is not None and price != opp_price:
            tags.append('Chalk Eater' if implied(price) > implied(opp_price) else 'Dog Hunter')
    elif market == 'ats' and line:
        tags.append('Chalk Eater' if line < 0 else 'Dog Hunter')
    elif market in ('total', 'btts'):
        tags.append('Over Lover' if side in ('over', 'yes') else 'Under Grinder')
    if streak >= RULES['streak_min']:
        tags.append('Streak Rider')
    elif streak <= -RULES['streak_min']:
        tags.append('Contrarian')
    st = datetime.fromisoformat(g['start'].replace('Z', '+00:00')).astimezone(ET)
    if st.hour * 60 + st.minute < RULES['early_bird']:
        tags.append('Early Bird')
    shown = sorted([a for a in angles if not a.get('opp') and a['w'] + a['l'] >= RULES['min_n'] and a['w'] / (a['w'] + a['l']) > 0.5],
                   key=lambda a: (-(a['w'] / (a['w'] + a['l'])), -(a['w'] + a['l'])))
    return {
        'id': f"{g['key']}|{k}|{market}|{side}", 'game': g['key'], 'date': g['date'], 'sport': g['sport'],
        'label': g['label'], 'slug': g['slug'], 'start': g['start'], 'seg': k, 'segTag': seg['tag'],
        'matchup': f"{g['names'][g['away']]} @ {g['names'][g['home']]}", 'href': g['href'],
        'market': market, 'side': side, 'line': line, 'price': price if priced else None,
        'title': title, 'est': round(est, 4), 'edge': round(edge, 4), 'agree': agree, 'sample': sample,
        'tier': tier_of(edge, sample, priced), 'tags': tags, 'streak': streak, 'streakTeam': team,
        'angles': [[a['label'], rec_text(a['w'], a['l'], a['p'])] for a in shown[:4]], 'info': info,
        'status': 'pending', 'units': None,
    }


def build_plays(games, now_utc):
    """Today's plays for games that haven't started, best first, plus every
    evaluated bet (for Streak to Watch)."""
    today = now_utc.astimezone(ET).date().isoformat()
    now_iso = now_utc.strftime('%Y-%m-%dT%H:%M')
    hist = team_history(games)
    plays, evaluated = [], []
    for g in games:
        if g['date'] != today or g['state'] != 'pre' or g['start'][:16] <= now_iso:
            continue
        per_game = []
        for k in g['segs']:
            best = {}
            for bet in candidate_bets(g, k):
                p = evaluate(hist, g, k, bet)
                if not p:
                    continue
                evaluated.append(p)
                if p['agree'] >= RULES['min_angles'] and p['edge'] >= RULES['min_edge']:
                    m = p['market']
                    if m not in best or p['edge'] > best[m]['edge']:
                        best[m] = p
            per_game += best.values()
        per_game.sort(key=lambda p: -p['edge'])
        plays += per_game[:RULES['per_game']]
    plays.sort(key=lambda p: (-p['edge'], p['start']))
    return plays[:RULES['max_plays']], evaluated


# ---------------------------------------------------------------- the log

def grade(play, games_by_key):
    g = games_by_key.get(play['game'])
    if g is None:
        return play
    if g['state'] == 'off':
        play['status'], play['units'] = 'NA', 0.0
        return play
    sc = (g['segs'].get(play['seg']) or {}).get('sc')
    if sc is None:
        return play
    r = outcome(play['market'], play['side'], play['line'], sc)
    play['status'] = r
    play['units'] = units(r, play['price'])
    return play


def update_log(games, plays, now_utc):
    """Plays for games not yet started are replaced each run (lines move);
    once a game starts its plays are frozen. Pending plays are graded."""
    log = {}
    if os.path.exists(LOG_PATH):
        try:
            log = json.load(open(LOG_PATH, encoding='utf-8'))
        except ValueError:
            log = {}
    today = now_utc.astimezone(ET).date().isoformat()
    now_iso = now_utc.strftime('%Y-%m-%dT%H:%M')
    by_key = {g['key']: g for g in games}
    day = log.get(today) or {'plays': []}
    kept = [p for p in day['plays'] if p['start'][:16] <= now_iso]   # started: frozen
    kept_games = {p['game'] for p in kept}
    fresh = [p for p in plays if p['game'] not in kept_games]
    day['plays'] = sorted(kept + fresh, key=lambda p: (-p['edge'], p['start']))
    log[today] = day
    for d, entry in log.items():
        for p in entry['plays']:
            if p['status'] == 'pending':
                grade(p, by_key)
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        json.dump(dict(sorted(log.items())), f, indent=1)
    return log


def records(plays):
    w = sum(1 for p in plays if p['status'] == 'W')
    l = sum(1 for p in plays if p['status'] == 'L')
    pu = sum(1 for p in plays if p['status'] == 'P')
    u = sum(p['units'] or 0 for p in plays if p['status'] in ('W', 'L', 'P'))
    return {'w': w, 'l': l, 'p': pu, 'units': round(u, 2), 'n': w + l + pu}


# ------------------------------------------------------------------- page

def esc(s):
    import html
    return html.escape('' if s is None else str(s), quote=True)


def units_html(u, n):
    if not n:
        return '<span class="pk-u zero">0.0u</span>'
    cls = 'pos' if u > 0 else 'neg' if u < 0 else 'zero'
    return f'<span class="pk-u {cls}">{u:+.1f}u</span>'


def time_et(iso):
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return t.strftime('%-I:%M %p')


def play_card(p, idx, free, depth):
    tier_lbl = {'A': 'A · Top Play', 'B': 'B · Solid', 'C': 'C · Lean'}[p['tier']]
    price = (f'<span class="pk-price">{esc(fmt_price(p["price"]))}</span>' if p['price'] is not None
             else '<span class="pk-price est" title="No price saved: graded at -110">-110 est.</span>')
    rows = ''.join(f'<div class="pk-angle"><span>{esc(a)}</span><b class="mono">{esc(r)}</b></div>' for a, r in p['angles'][:3])
    if p.get('info'):
        rows += f'<div class="pk-angle info"><span>{esc(p["info"])}</span></div>'
    tags = ''.join(f'<span class="pk-tag">{esc(t)}</span>' for t in p['tags'])
    status = '' if p['status'] == 'pending' else f'<span class="pk-res {p["status"]}">{esc(p["status"])}</span>'
    body = (f'<div class="pk-top"><span class="pk-tier t{p["tier"]}">{tier_lbl}</span>'
            f'<span class="pk-meta">{esc(p["label"])} · {esc(p["segTag"])} · {esc(time_et(p["start"]))}</span>'
            f'<span class="pk-match">{esc(p["matchup"])}</span></div>'
            f'<div class="pk-title-row"><h3 class="pk-title">{esc(p["title"])} {price}</h3>{status}'
            f'<span class="pk-edge">Edge {p["edge"] * 100:+.1f}%</span></div>'
            f'<div class="pk-angles">{rows}</div>'
            f'<div class="pk-foot"><div class="pk-tags">{tags}<span class="pk-agree">{p["agree"]} angles agree</span></div>'
            f'<a class="pk-link" href="{depth}{esc(p["href"])}">Matchup stats &rarr;</a></div>')
    attrs = (f'data-sport="{esc(p["sport"])}" data-tags="{esc("|".join(p["tags"]))}" data-edge="{p["edge"]}" '
             f'data-streak="{abs(p["streak"])}" data-start="{esc(p["start"])}" data-rank="{idx}"')
    if free:
        return f'<article class="pk-card" {attrs}>{body}</article>'
    return (f'<article class="pk-card locked" {attrs}><div class="pk-blur" aria-hidden="true">{body}</div>'
            f'<div class="pk-lock"><span class="pk-lock-k">Premium play</span>'
            f'<span class="pk-lock-t">{esc(p["label"])} · {esc(p["segTag"])} · Tier {p["tier"]}</span>'
            f'<a class="btn-gold" href="{depth}#premium">Go Premium</a></div></article>')


def render(log, plays_today, evaluated, now_utc, depth='../'):
    today = now_utc.astimezone(ET).date()
    day = log.get(today.isoformat()) or {'plays': []}
    plays = day['plays']
    all_plays = [p for d in log.values() for p in d['plays']]
    sports_today = []
    for p in plays:
        if p['label'] not in sports_today:
            sports_today.append(p['label'])
    kicker = ' · '.join([today.strftime('%a, %b %-d').upper(), f'{len(plays)} play{"" if len(plays) == 1 else "s"}'.upper()] + sports_today)

    tiers = ''
    for t in ('A', 'B', 'C'):
        r = records([p for p in all_plays if p['tier'] == t])
        tiers += (f'<div class="pk-tierbox t{t}"><span class="pk-tb-k">{t}-Tier</span>'
                  f'<b class="mono">{rec_text(r["w"], r["l"], r["p"])}</b>{units_html(r["units"], r["n"])}</div>')

    # Game to Watch: the play with the most agreeing angles
    gtw = ''
    if plays:
        g = max(plays, key=lambda p: (p['agree'], p['edge']))
        rows = ''.join(f'<div class="pk-angle"><span>{esc(a)}</span><b class="mono">{esc(r)}</b></div>' for a, r in g['angles'][:3])
        gtw = (f'<div class="pk-feature"><div class="pk-f-head"><span class="pk-kick">Game to Watch</span>'
               f'<span class="pk-meta">{esc(g["label"])} · {esc(time_et(g["start"]))}</span></div>'
               f'<h2 class="pk-f-title">{esc(g["matchup"])}</h2>'
               f'<p class="pk-f-sub">{g["agree"]} separate angles point the same way: <b>{esc(g["title"])}</b></p>'
               f'<div class="pk-angles">{rows}</div><a class="pk-link" href="{depth}{esc(g["href"])}">Full matchup stats &rarr;</a></div>')
    # Streak to Watch: the longest active streak at today's line
    stw = ''
    cands = [e for e in evaluated if abs(e['streak']) >= RULES['streak_min'] and e['streak'] > 0]
    if cands:
        s = max(cands, key=lambda e: (e['streak'], e['market'] != 'ml'))
        what = {'ml': f"{s['segTag']} wins", 'ats': f"{s['segTag']} covers at {fmt_line(s['line'], True)}",
                'total': f"{s['segTag']} {s['side']}s", 'btts': f"{s['segTag']} {'BTTS' if s['side'] == 'yes' else 'no-BTTS'}"}[s['market']]
        line_txt = (f"{s['segTag']} total: {fmt_line(s['line'])}" if s['market'] == 'total'
                    else f"{s['segTag']} line: {fmt_line(s['line'], True)}" if s['market'] == 'ats' else '')
        dashes = ''.join('<span></span>' for _ in range(min(s['streak'], 12)))
        stw = (f'<div class="pk-feature streak"><div class="pk-f-head"><span class="pk-kick gold">Streak to Watch</span>'
               f'<span class="pk-meta">{esc(s["label"])} · {esc(time_et(s["start"]))}</span></div>'
               f'<div class="pk-streak"><span class="pk-streak-n">{s["streak"]}</span>'
               f'<span class="pk-streak-t">straight {esc(s["streakTeamName"])} {esc(what)}</span></div>'
               f'<p class="pk-f-sub">On the line today: {esc(s["matchup"])}.' + (f' {esc(line_txt)}' if line_txt else '') + '</p>'
               f'<div class="pk-dashes" aria-hidden="true">{dashes}</div>'
               f'<p class="pk-note">Streak Rider says ride it. Contrarian says it&rsquo;s due.</p></div>')
    features = f'<div class="pk-features">{gtw}{stw}</div>' if (gtw or stw) else ''

    # filters
    pills = ''.join(f'<button class="pk-pill" data-pk-tag="{esc(t)}" aria-pressed="false">{esc(t)}</button>' for t in PERSONALITIES)
    sp_pills = ''.join(f'<button class="pk-pill" data-pk-sport="{esc(sp["key"])}" aria-pressed="false">{esc(sp["label"])}</button>'
                       for sp in sports.SPORTS if any(p['sport'] == sp['key'] for p in plays))
    filters = (f'<div class="pk-filters"><div class="pk-frow"><span class="pk-flabel">Personality</span>'
               f'<button class="pk-pill" data-pk-tag="" aria-pressed="true">All</button>{pills}</div>'
               f'<div class="pk-frow"><span class="pk-flabel">Sport</span>'
               f'<button class="pk-pill" data-pk-sport="" aria-pressed="true">All</button>{sp_pills}'
               f'<span class="pk-sort">Sort: <button class="on" data-pk-sort="edge">Confidence</button>'
               f'<button data-pk-sort="streak">Streak</button><button data-pk-sort="start">Start time</button></span></div></div>')
    free_n = min(RULES['free'], len(plays))
    count = (f'<p class="pk-count mono" id="pkCount">{len(plays)} play{"" if len(plays) == 1 else "s"} · {free_n} free · '
             f'{len(plays) - free_n} premium</p>')
    cards = ''.join(play_card(p, i, i < RULES['free'], depth) for i, p in enumerate(plays))
    if not plays:
        cards = ('<div class="pk-empty">No plays clear the bar yet today. A play needs a saved line, at least '
                 f'{RULES["min_angles"]} angles that agree and an edge of {RULES["min_edge"] * 100:.0f}%+ over the price. '
                 'Plays post as lines come in and lock at kickoff.</div>')

    # sidebar
    mon = today - timedelta(days=today.weekday())
    week = [p for d, e in log.items() if mon.isoformat() <= d <= today.isoformat() for p in e['plays']]
    pers = []
    for t in PERSONALITIES:
        r = records([p for p in week if t in p['tags']])
        pers.append((r['units'], t, r))
    pers.sort(key=lambda x: -x[0])
    pers_html = ''.join(f'<div class="pk-prow"><span>{esc(t)}</span><b class="mono">{rec_text(r["w"], r["l"], r["p"])}</b>{units_html(r["units"], r["n"])}</div>'
                        for u, t, r in pers)
    yd = (today - timedelta(days=1)).isoformat()
    ylist = (log.get(yd) or {}).get('plays') or []
    y_html = ''.join(f'<div class="pk-yrow"><span><b>{esc(p["title"])}</b><small>{esc(p["label"])} · {esc(p["matchup"])}</small></span>'
                     f'<span class="pk-res {p["status"] if p["status"] != "pending" else "NA"}">{esc(p["status"] if p["status"] != "pending" else "—")}</span></div>'
                     for p in ylist) or '<p class="pk-muted">No plays yesterday.</p>'
    yr = records(ylist)
    side = (f'<aside class="pk-side"><div class="pk-box"><h3>Personality Records &middot; This Week</h3>{pers_html}</div>'
            f'<div class="pk-box"><h3>How Confidence Works</h3><p>Each play is scored on its edge over the current odds, '
            f'sample size, how many trends agree and recent form. Small samples can&rsquo;t rank above C.</p>'
            f'<a class="pk-link" href="{depth}learn/#confidence">Read the method &rarr;</a></div>'
            f'<div class="pk-box"><h3>Yesterday&rsquo;s Picks</h3>'
            + (f'<p class="pk-muted mono">{rec_text(yr["w"], yr["l"], yr["p"])} · {yr["units"]:+.1f}u</p>' if yr['n'] else '')
            + f'{y_html}</div></aside>')

    head = (f'<section class="pk-hero"><div><div class="pk-kicker">{esc(kicker)}</div>'
            f'<h1 class="pk-h1">Today&rsquo;s <span>Picks.</span></h1>'
            f'<p class="pk-lede">Trend-based plays for the first period, quarter, half and inning, ranked by confidence. '
            f'Every tier&rsquo;s record is public.</p></div><div class="pk-tiers">{tiers}</div></section>')
    return (f'{head}{features}<div class="pk-layout"><div class="pk-main">{filters}{count}'
            f'<div class="pk-list" id="pkList">{cards}</div></div>{side}</div>{PAGE_JS}')


PAGE_JS = '''<script>
(function() {
  var list = document.getElementById('pkList');
  if (!list) return;
  var state = { tag: '', sport: '', sort: 'edge' };
  function apply() {
    var cards = [].slice.call(list.querySelectorAll('.pk-card'));
    cards.sort(function(a, b) {
      if (state.sort === 'start') return a.dataset.start < b.dataset.start ? -1 : 1;
      if (state.sort === 'streak') return (+b.dataset.streak - +a.dataset.streak) || (+a.dataset.rank - +b.dataset.rank);
      return +a.dataset.rank - +b.dataset.rank;
    });
    var shown = 0;
    cards.forEach(function(c) {
      var ok = (!state.tag || c.dataset.tags.split('|').indexOf(state.tag) !== -1) && (!state.sport || c.dataset.sport === state.sport);
      c.hidden = !ok;
      if (ok) shown++;
      list.appendChild(c);
    });
    var cnt = document.getElementById('pkCount');
    if (cnt) cnt.textContent = shown + (shown === 1 ? ' play' : ' plays') + (state.tag || state.sport ? ' match' : '') + ' · ' +
      cards.filter(function(c) { return !c.hidden && !c.classList.contains('locked'); }).length + ' free · ' +
      cards.filter(function(c) { return !c.hidden && c.classList.contains('locked'); }).length + ' premium';
  }
  function group(attr, key) {
    document.querySelectorAll('[' + attr + ']').forEach(function(b) {
      b.addEventListener('click', function() {
        state[key] = b.getAttribute(attr);
        document.querySelectorAll('[' + attr + ']').forEach(function(x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
        apply();
      });
    });
  }
  group('data-pk-tag', 'tag');
  group('data-pk-sport', 'sport');
  document.querySelectorAll('[data-pk-sort]').forEach(function(b) {
    b.addEventListener('click', function() {
      state.sort = b.getAttribute('data-pk-sort');
      document.querySelectorAll('[data-pk-sort]').forEach(function(x) { x.classList.toggle('on', x === b); });
      apply();
    });
  });
})();
</script>'''


def build(nhl_data, nhl_city, now_utc=None):
    """Update picks_log.json and return (page body html, info)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    games = load_games(nhl_data, nhl_city)
    plays, evaluated = build_plays(games, now_utc)
    by_key = {g['key']: g for g in games}
    for e in evaluated:   # names for Streak to Watch
        g = by_key[e['game']]
        e['streakTeamName'] = g['names'].get(e['streakTeam'], e['streakTeam'])
    log = update_log(games, plays, now_utc)
    today = now_utc.astimezone(ET).date().isoformat()
    body = render(log, plays, evaluated, now_utc)
    return body, {'plays': len((log.get(today) or {}).get('plays') or []), 'logged_days': len(log)}
