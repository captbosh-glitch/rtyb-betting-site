"""
The Arena hubs (/{sport}/): each sport's front page, drawn by assets/sport.js
(renderHub) from the sport's data.json (NHL: sport.json), trends.json and the
{slug}/hub.json written here:

  {slate, weekly, motd, motdRecord: {last, season}, daily: {recap, preview}, learn}

Matchup of the Day (football: of the Week) is the game on the slate with the
most trends pointing at the same bet, by the Trends page's rules:
  - League Trends: the slate's cards (trends.json) that pick the game
  - Matchup Trends: a team that leans a way in a market (60%+ over 10+
    games before the slate; the moneyline counts ties as games played)
  - Streak Trends: a team on a run of 3 or more
It needs 3 agreeing trends; ties go to the bigger edge over the league rate
(the average of the trends that have one). Every pick is kept in
matchup_of_the_day_log.json -- frozen once its game starts -- and graded
when the game is final, so the card can show the last result and the
season record.
"""
import os
from datetime import date, datetime, timedelta, timezone

import daily
import sport_build
from sport_build import read_json, write_json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(ROOT, 'matchup_of_the_day_log.json')
TIPS = os.path.join(ROOT, 'content', 'trend_tooltips.json')
MIN_AGREE = 3

HIT = {'ml': 'W', 'ats': 'W', 'total': 'O', 'btts': 'Y', 'rfi': 'Y'}
MISS = {'ml': 'L', 'ats': 'L', 'total': 'U', 'btts': 'N', 'rfi': 'N'}
GAME_PICK = {'O': 'over', 'U': 'under', 'Y': 'yes', 'N': 'no'}
FLIP = {'W': 'L', 'L': 'W'}
# when each piece of The Daily is drafted (ET), for the "Coming at" cards
DAILY_TIME = {'recap': '8 AM', 'preview': '11 AM'}
WEEKLY_TIME = {'recap': 'Monday at 8 AM', 'preview': 'Thursday at 9 AM'}


# ------------------------------------------------------------- the slate
def all_games(doc):
    for d in sorted(doc.get('games') or {}):
        for g in doc['games'][d]:
            yield d, g


def current_week(doc):
    """The first week with a game still to play, else the last (as the pages do)."""
    weeks = doc.get('weeks') or []
    for w in weeks:
        if any(g.get('wk') == w['key'] and g.get('state') in ('pre', 'in') for _, g in all_games(doc)):
            return w
    return weeks[-1] if weeks else None


def slate(doc, today):
    """(key, games, before): today's date, or (football) this week."""
    if doc.get('schedule') == 'week':
        w = current_week(doc)
        if not w:
            return None, [], today
        return w['key'], [g for _, g in all_games(doc) if g.get('wk') == w['key']], w['start']
    return today, list((doc.get('games') or {}).get(today) or []), today


def previous_key(doc, key):
    if doc.get('schedule') == 'week':
        keys = [w['key'] for w in doc.get('weeks') or []]
        i = keys.index(key) if key in keys else -1
        return keys[i - 1] if i > 0 else None
    return (date.fromisoformat(key) - timedelta(days=1)).isoformat()


# ------------------------------------------------- team runs and leans
def team_seqs(doc, before, k):
    """{team: {market: [result, ...]}} over the finished games before the
    slate, oldest first (the Trends page's teamSeqs)."""
    out = {}
    for d, g in all_games(doc):
        if d >= before:
            break
        r = (g.get('res') or {}).get(k)
        if g.get('state') != 'final' or not r or not r.get('sc') or r.get('na'):
            continue
        for side in ('away', 'home'):
            o = out.setdefault(g[side], {m: [] for m in HIT})
            if r.get('su') not in (None, 'NA'):
                o['ml'].append(r['su'] if side == 'away' else FLIP.get(r['su'], r['su']))
            if r.get('ats') not in (None, 'NA'):
                o['ats'].append(r['ats'] if side == 'away' else FLIP.get(r['ats'], r['ats']))
            if r.get('tot') not in (None, 'NA'):
                o['total'].append(r['tot'])
            if r.get('btts') in ('Y', 'N'):
                o['btts'].append(r['btts'])
            if r.get('rfi') in ('Y', 'N'):
                o['rfi'].append(r['rfi'])
    return out


def lean_of(m, seq):
    a = sum(1 for x in seq if x == HIT[m])
    b = sum(1 for x in seq if x == MISS[m])
    y = len(seq) if m == 'ml' else a + b
    if y < 10:
        return None
    kind, x = (HIT[m], a) if a >= b else (MISS[m], b)
    return {'kind': kind, 'x': x, 'y': y, 'rate': x / y} if x / y >= 0.6 else None


def streak_of(seq):
    if not seq or seq[-1] in ('T', 'P'):
        return None
    n = 0
    for x in reversed(seq):
        if x != seq[-1]:
            break
        n += 1
    return {'kind': seq[-1], 'n': n}


def league_rate(seqs, m, kind):
    """How often the league hits `kind` in a game market (each game counted
    from both teams, so the share is the same); 0.5 for the side markets."""
    if m in ('ml', 'ats'):
        return 0.5
    a = sum(1 for o in seqs.values() for x in o[m] if x == kind)
    n = sum(1 for o in seqs.values() for x in o[m] if x in (HIT[m], MISS[m]))
    return a / n if n else 0.5


# ------------------------------------------------------------ the words
def seg_of(doc, k):
    return next((s for s in doc['segments'] if s['key'] == k), {'key': k, 'label': k, 'tag': k.upper()})


def code(doc, slug):
    t = (doc.get('teams') or {}).get(slug) or {}
    return t.get('code') or str(t.get('short') or slug)[:4].upper()


def short(doc, slug):
    t = (doc.get('teams') or {}).get(slug) or {}
    return t.get('short') or t.get('name') or (doc.get('otherTeams') or {}).get(slug) or slug


def bet_words(doc, g, k, m, pick):
    tag = seg_of(doc, k)['tag']
    if pick in ('away', 'home'):
        return f"{code(doc, g[pick])} {tag} " + {'ml': 'ML', 'ats': 'spread', 'ml3': '3-way ML'}[m]
    if m == 'total':
        return f"{tag} {'Over' if pick == 'over' else 'Under'}" + (' 1.5' if doc['sport'] == 'nhl' else '')
    if m == 'btts':
        return f"{tag} BTTS {'Yes' if pick == 'yes' else 'No'}"
    if m == 'rfi':
        return 'YRFI' if pick == 'yes' else 'NRFI'
    return f'{tag} 3-way: Tie'


def lean_words(doc, slug, m, kind, k):
    s = seg_of(doc, k)['label'].lower()
    who = code(doc, slug)
    if m == 'ml':
        return f"{who} has {'won' if kind == 'W' else 'lost'} the {s}"
    if m == 'ats':
        return f"{who} has {'covered' if kind == 'W' else 'failed to cover'} the {s} spread"
    if m == 'total':
        return f"{who} has gone {'Over' if kind == 'O' else 'Under'}" + (' 1.5' if doc['sport'] == 'nhl' else f' the {s} total')
    if m == 'btts':
        return f"{who} has gone BTTS {'Yes' if kind == 'Y' else 'No'}"
    return f"{who} has gone {'YRFI' if kind == 'Y' else 'NRFI'}"


def streak_words(doc, slug, m, st, k):
    s = seg_of(doc, k)['label'].lower()
    nm, n = short(doc, slug), f"{st['n']} straight"
    if m == 'ml':
        return f"{nm} have {'won' if st['kind'] == 'W' else 'lost'} the {s} {n}"
    if m == 'ats':
        return f"{nm} have {'covered' if st['kind'] == 'W' else 'failed to cover'} the {s} spread {n}"
    w = {'total': ('Over' if st['kind'] == 'O' else 'Under') + (' 1.5' if doc['sport'] == 'nhl' else ''),
         'btts': 'BTTS ' + ('Yes' if st['kind'] == 'Y' else 'No'), 'rfi': 'YRFI' if st['kind'] == 'Y' else 'NRFI'}[m]
    plural = s if s.endswith('innings') else s[:-4] + 'halves' if s.endswith('half') else s + 's'
    return f'{nm} {plural} have gone {w} {n}'


# ------------------------------------------------------------- the pick
def market_keys(doc):
    """[(segment, market)] the pages show, the 3-way left to the league cards."""
    return [(x[0], x[1]) for x in doc.get('markets') or [] if x[1] in HIT]


def game_trends(doc, g, cards, seqs_by_seg):
    """{(segment, market, pick): [trend, ...]} for one game."""
    out = {}
    for c in cards:
        for x in c.get('games') or []:
            if str(x.get('id')) != str(g['id']):
                continue
            pick = x.get('side') or x.get('bet')
            out.setdefault((c['seg'], c['mk'], pick), []).append({
                'kind': 'league', 'text': f"{c['title']} ({c['tag']})", 'rec': f"{c['w']}–{c['l']}",
                'edge': (c.get('rate') or 0) - (c.get('base') or 0)})
    for k, m in market_keys(doc):
        seqs = seqs_by_seg[k]
        for side in ('away', 'home'):
            seq = (seqs.get(g[side]) or {}).get(m) or []
            found = []
            ln, st = lean_of(m, seq), streak_of(seq)
            if ln:
                found.append((ln['kind'], {'kind': 'matchup', 'text': f"{lean_words(doc, g[side], m, ln['kind'], k)} in {ln['x']} of {ln['y']}",
                                           'rec': f"{round(ln['rate'] * 100)}%", 'edge': ln['rate'] - league_rate(seqs, m, ln['kind'])}))
            if st and st['n'] >= 3:
                found.append((st['kind'], {'kind': 'streak', 'text': streak_words(doc, g[side], m, st, k), 'rec': f"{st['n']} straight", 'edge': None}))
            for kind, t in found:
                # a team's lean or run picks that team (or its opponent); a game market picks the side
                pick = (side if kind == HIT[m] else 'home' if side == 'away' else 'away') if m in ('ml', 'ats') else GAME_PICK[kind]
                out.setdefault((k, m, pick), []).append(t)
    return out


def matchup_label(doc, g, k, seqs):
    """Tug of war / Fireworks / Lockdown (totals, BTTS), Mismatch /
    Heavyweights (moneyline), from both teams' leans in the segment."""
    labels = (read_json(TIPS, {}).get('matchup_labels') or {})
    leans = {}
    for m in ('total', 'btts', 'ml'):
        for side in ('away', 'home'):
            ln = lean_of(m, (seqs.get(g[side]) or {}).get(m) or []) if m in HIT else None
            if ln:
                leans.setdefault(m, {})[side] = ln['kind']
    for m in ('total', 'btts'):
        x = leans.get(m) or {}
        if x.get('away') and x.get('home'):
            key = 'tug_of_war' if x['away'] != x['home'] else 'fireworks' if x['away'] == HIT[m] else 'lockdown'
            return (labels.get(key) or {}).get('label')
    x = leans.get('ml') or {}
    if x.get('away') and x.get('home'):
        key = 'mismatch' if x['away'] != x['home'] else 'heavyweights' if x['away'] == 'W' else None
        return (labels.get(key) or {}).get('label') if key else None
    return None


def best_price(slug_dir, day, g, k, m, pick):
    """(price, line, source name) of the best price for the bet on the Odds
    page, or None: the sportsbooks' best (spreads and totals at the line
    most books post), else the exchanges'."""
    if not day:
        return None
    odds = read_json(os.path.join(slug_dir, 'odds', f'{day}.json'), {})
    names = read_json(os.path.join(slug_dir, 'odds.json'), {}).get('sources') or {}
    og = next((x for x in odds.get('games') or [] if x['away'] == g['away'] and x['home'] == g['home']), None)
    if not og:
        return None
    books = ((og.get('books') or {}).get(k) or {}).get(m) or {}
    best = ((og.get('best') or {}).get(k) or {}).get(m) or {}
    side = {'over': 'over', 'under': 'under', 'yes': 'yes', 'no': 'no', 'tie': 'draw'}.get(pick, pick)
    want = best.get('line') if m == 'total' else (best.get(side) or {}).get('line') if m == 'ats' else None

    def pick(exchanges):
        top = None
        for b, row in books.items():
            if bool((names.get(b) or {}).get('x')) != exchanges or not isinstance(row.get(side), dict):
                continue
            price = row[side].get('price')
            line = row.get('line') if m == 'total' else row[side].get('line')
            if price is None or (want is not None and line != want):
                continue
            if top is None or price > top[0]:
                top = (price, line, (names.get(b) or {}).get('name') or b)
        return top
    # the exchanges only when no sportsbook has it (the free feed's 3-way)
    return pick(False) or pick(True)


def grade(g, k, m, pick):
    """'W' / 'L' / 'P' once the game is final, else None."""
    r = (g.get('res') or {}).get(k)
    if g.get('state') != 'final' or not r or not r.get('sc'):
        return None
    if r.get('na'):
        return 'P'
    if m in ('ml', 'ats', 'ml3'):
        x = r.get('su' if m != 'ats' else 'ats')
        if x in (None, 'NA'):
            return 'P'
        if pick == 'tie':
            return 'W' if x == 'T' else 'L'
        x = x if pick == 'away' else FLIP.get(x, x)
        if m == 'ml3':
            return 'W' if x == 'W' else 'L'
        return x if x in ('W', 'L') else 'P'
    x = r.get({'total': 'tot', 'btts': 'btts', 'rfi': 'rfi'}[m])
    if x in (None, 'NA', 'P'):
        return 'P'
    return 'W' if GAME_PICK.get(x) == pick else 'L'


def pick_matchup(doc, trends_doc, slug_dir, key, games, before):
    cards = ((trends_doc.get('slates') or {}).get(key) or {}).get('cards') or []
    seqs_by_seg = {k: team_seqs(doc, before, k) for k in {x[0] for x in market_keys(doc)}}
    best = None
    for g in games:
        for (k, m, pick), ts in game_trends(doc, g, cards, seqs_by_seg).items():
            if len(ts) < MIN_AGREE:
                continue
            edges = [t['edge'] for t in ts if t['edge'] is not None]
            score = (len(ts), sum(edges) / len(edges) if edges else 0)
            if best is None or score > best[0]:
                best = (score, g, k, m, pick, ts)
    if not best:
        return None
    _, g, k, m, pick, ts = best
    day = next((d for d, x in all_games(doc) if x is g), None)
    price = best_price(slug_dir, day, g, k, m, pick)
    return {'id': g['id'], 'date': day, 'start': g.get('start'), 'away': g['away'], 'home': g['home'], 'seg': k, 'mk': m, 'pick': pick,
            'bet': bet_words(doc, g, k, m, pick), 'n': len(ts), 'label': matchup_label(doc, g, k, seqs_by_seg.get(k) or {}),
            'trends': [{'kind': t['kind'], 'text': t['text'], 'rec': t['rec']} for t in ts],
            'price': {'price': price[0], 'line': price[1], 'book': price[2]} if price else None}


def started(g, now_utc):
    if g.get('state') in ('in', 'final'):
        return True
    try:
        return bool(g.get('start')) and datetime.fromisoformat(g['start'].replace('Z', '+00:00')) <= now_utc
    except ValueError:
        return False


def update_log(sp, doc, trends_doc, slug_dir, now_utc, today):
    """Today's pick (kept once its game starts) and every logged pick graded."""
    log = read_json(LOG_PATH, {})
    mine = log.setdefault(sp['key'], {})
    key, games, before = slate(doc, today)
    by_id = {str(g['id']): g for _, g in all_games(doc)}
    if key:
        old = mine.get(key)
        frozen = old and old.get('id') is not None and started(by_id.get(str(old['id'])) or {}, now_utc)
        if not frozen:
            pick = pick_matchup(doc, trends_doc, slug_dir, key, games, before)
            if pick:
                mine[key] = pick
            elif old and not started(by_id.get(str(old.get('id'))) or {}, now_utc):
                mine.pop(key, None)
    for entry in mine.values():
        g = by_id.get(str(entry.get('id')))
        if g and entry.get('result') is None:
            r = grade(g, entry['seg'], entry['mk'], entry['pick'])
            if r:
                entry['result'] = r
                sc = ((g.get('res') or {}).get(entry['seg']) or {}).get('sc')
                if sc:
                    entry['score'] = f'{sc[0]}–{sc[1]}'
    if not mine:
        log.pop(sp['key'], None)
    write_json(LOG_PATH, log)
    return key, mine


def daily_cards(sp, today, weekly):
    """The latest recap and preview for the sport, or when they're due."""
    pieces = daily.load()
    out = {}
    for kind in ('recap', 'preview'):
        p = daily.latest(pieces, kind, sp['key'])
        if weekly:
            # this week's piece: since Monday (recap) / Thursday (preview)
            d = date.fromisoformat(today)
            since = (d - timedelta(days=d.weekday() if kind == 'recap' else (d.weekday() - 3) % 7)).isoformat()
            fresh = p and p['date'] >= since
            due = WEEKLY_TIME[kind]
        else:
            fresh = p and p['date'] == today
            due = DAILY_TIME[kind]
        out[kind] = ({'title': p['hook'] or p['title'], 'teaser': p['teaser'], 'path': p['path']} if fresh
                     else {'due': due})
    return out


def build(sp, doc, trends_doc, slug_dir, now_utc=None):
    """Writes {slug}/hub.json; returns today's Matchup of the Day (or None)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today = now_utc.astimezone(sport_build.ET).date().isoformat()
    weekly = doc.get('schedule') == 'week'
    key, mine = update_log(sp, doc, trends_doc, slug_dir, now_utc, today) if doc.get('games') else (None, {})
    prev = previous_key(doc, key) if key else None
    graded = [e for e in mine.values() if e.get('result') in ('W', 'L')]
    last = mine.get(prev) if prev else None
    if weekly:
        wk = next((w for w in doc.get('weeks') or [] if w['key'] == key), None)
        h1 = f"{sp['label']} · {wk['label']}" if wk else sp['label']
    else:
        d = date.fromisoformat(today)
        h1 = f"{sp['label']} Today · {d.strftime('%A, %b')} {d.day}"
    hub = {'h1': h1, 'slate': key, 'weekly': weekly, 'motd': mine.get(key) if key else None,
           'motdRecord': {'last': {k: last.get(k) for k in ('bet', 'result', 'score')} if last and last.get('result') else None,
                          'season': [sum(1 for e in graded if e['result'] == 'W'), sum(1 for e in graded if e['result'] == 'L')]},
           'daily': daily_cards(sp, today, weekly),
           'learn': f"/learn/{sp['slug']}/" if os.path.exists(os.path.join(ROOT, 'learn', sp['slug'], 'index.html')) else '/learn/'}
    write_json(os.path.join(slug_dir, 'hub.json'), hub)
    return hub['motd']
