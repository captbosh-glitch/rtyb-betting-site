"""
The Daily's drafts, written by Claude from the site's own numbers:

  recap    The Morning Run: last night's results, from 8 AM ET
  preview  On Tap: today's slate, from 11 AM ET

for every sport with games that day (scripts/sports.py). Football is
weekly: the Weekend Recap on Monday from 8 AM ET and the Week Preview on
Thursday from 9 AM ET. Previews tease (games, start times, streaks, where
our trends stack up) with no records, hit rates, prices or picks, and end
with a link to the sport's Trends page.

Each run of the refresh workflow calls this (no arguments). A draft is
written once per sport and day, on the first run inside its window, to
content/drafts/{sport}-{kind}-{date}.md; nothing is published until
someone approves it. A draft already written (or published) is never
redone. Without the ANTHROPIC_API_KEY secret it does nothing.

The packet sent to Claude holds every fact the piece may use. After
writing, every number in the draft is checked against the packet; any
that isn't there is listed in the draft's `check:` line for the editor.

  python3 scripts/daily_content.py                     # the scheduled run
  python3 scripts/daily_content.py recap nba 2026-11-10 --dry-run   # print the packet
"""
import json
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grading  # noqa: E402
import sports  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
DRAFTS = os.path.join(ROOT, 'content', 'drafts')
PUBLISHED = os.path.join(ROOT, 'content', 'published')
SPORTS = tuple(sp['key'] for sp in sports.SPORTS)   # a sport with no games that day gets no draft
# kind -> (weekday, first ET hour, last ET hour) a scheduled run may write
# it; weekday None is every day. Football's pieces are weekly: the Weekend
# Recap on Monday, the Week Preview on Thursday.
WINDOWS = {'recap': (None, 8, 14), 'preview': (None, 11, 18)}
WEEKLY_WINDOWS = {'recap': (0, 8, 14), 'preview': (3, 9, 18)}
MODEL = 'claude-opus-5-5'
STREAK_MIN = 3   # runs this long are worth a mention


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def et_time(iso):
    if not iso:
        return None
    t = datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone(ET)
    return t.strftime('%-I:%M %p ET')


def units(result, price):
    u = grading.bet_units(result, price) if price is not None else None
    return None if u is None else round(u, 2)


def trend_results(entry, games_on=None):
    """Graded picks from the league trends that were bets (not weak)."""
    out = []
    for t in (entry or {}).get('trends') or []:
        if not t.get('kind') or t.get('strength') == 'weak':
            continue
        for p in t.get('games') or []:
            out.append({'trend': t['title'], 'strength': t['strength'], 'season_record': t.get('record'),
                        'pick': p.get('label') or p.get('chip'), 'game': p.get('matchup'),
                        'result': {'W': 'hit', 'L': 'miss', 'P': 'push', 'NA': 'no action'}.get(p.get('status'), 'pending')})
    return out


def runs(seq):
    """(result, length) of the run ending at the last item."""
    if not seq:
        return None, 0
    n = 0
    for r in reversed(seq):
        if r != seq[-1]:
            break
        n += 1
    return seq[-1], n


def streak_changes(seqs, played, labels):
    """Streaks extended or snapped by the latest game, for teams in `played`.
    seqs: {(team, market): [results oldest first]}; labels: market -> {result: word}."""
    out = []
    for (team, market), seq in seqs.items():
        if team not in played or len(seq) < 2:
            continue
        r, n = runs(seq)
        pr, pn = runs(seq[:-1])
        word = labels[market]
        if r == pr and n >= STREAK_MIN:
            out.append({'team': team, 'market': market, 'streak': f'{word.get(r, r)} {n} straight', 'change': 'extended'})
        elif r != pr and pn >= STREAK_MIN:
            out.append({'team': team, 'market': market, 'streak': f'{word.get(pr, pr)} {pn} straight', 'change': 'snapped',
                        'snapped_by': word.get(r, r)})
    return sorted(out, key=lambda x: (x['change'], x['team']))


def active_streaks(seqs, teams, labels):
    out = []
    for (team, market), seq in seqs.items():
        r, n = runs(seq)
        if team in teams and n >= STREAK_MIN and r in labels[market]:
            out.append({'team': team, 'market': market, 'streak': f'{labels[market][r]} {n} straight'})
    return sorted(out, key=lambda x: (-int(x['streak'].split()[-2]), x['team']))


def best_and_worst(bets):
    graded = [b for b in bets if b.get('units') is not None]
    best = sorted([b for b in graded if b['units'] > 0], key=lambda b: -b['units'])[:3]
    worst = sorted([b for b in graded if b['units'] < 0 and (b.get('price') or 0) < -150], key=lambda b: b['price'])[:3]
    return {'best_paying_winners': best, 'biggest_favorites_that_lost': worst}


# ----------------------------------------------------------------- NHL

NHL_LABELS = {'1P ML': {'W': 'won the 1st period', 'L': 'lost the 1st period', 'T': 'tied the 1st period'},
              'Over 1.5': {'W': 'Over 1.5 1P', 'L': 'Under 1.5 1P'},
              'BTTS': {'W': 'both teams scored in the 1P', 'L': 'no BTTS in the 1P'}}


def nhl_seqs(D, through):
    seqs = {}
    for code, log in (D.get('gamelog') or {}).items():
        for e in log:
            if e['date'] > through:
                continue
            seqs.setdefault((code, '1P ML'), []).append('W' if e['p1t'] > e['p1o'] else 'L' if e['p1t'] < e['p1o'] else 'T')
            seqs.setdefault((code, 'Over 1.5'), []).append('W' if e['p1t'] + e['p1o'] > 1 else 'L')
            seqs.setdefault((code, 'BTTS'), []).append('W' if e.get('btts') else 'L')
    return seqs


def nhl_name(D, code):
    return (D.get('summary', {}).get(code) or {}).get('name', code)


def nhl_recap(day):
    D = read_json(os.path.join(ROOT, 'nhl', 'data.json'), {})
    games, bets = [], []
    for g in (D.get('schedule', {}).get('games') or {}).get(day, []):
        if g.get('state') not in ('OFF', 'FINAL') or g.get('awayP1') is None:
            continue
        a, h = g['away'], g['home']
        o = g.get('odds') or {}
        ml = o.get('ml') or {}
        ap, hp = g['awayP1'], g['homeP1']
        p1 = 'away' if ap > hp else 'home' if hp > ap else 'tie'
        tot = ap + hp
        over = ((o.get('totals') or {}).get('1.5') or {})
        res_a = 'W' if p1 == 'away' else 'L' if p1 == 'home' else 'T'
        res_h = {'W': 'L', 'L': 'W', 'T': 'T'}[res_a]
        row = {'matchup': f'{nhl_name(D, a)} at {nhl_name(D, h)}', 'final': f"{a} {g.get('awayFinal')} - {h} {g.get('homeFinal')}" + (' (OT)' if g.get('ot') == 'OT' else ' (SO)' if g.get('ot') == 'SO' else ''),
               'first_period': f'{a} {ap} - {h} {hp}', 'first_goal': g.get('firstGoal'),
               'markets': {
                   '1P moneyline (2-way, a tie is a push)': {
                       a: {'price': ml.get(a), 'result': res_a, 'units': units(res_a, ml.get(a))},
                       h: {'price': ml.get(h), 'result': res_h, 'units': units(res_h, ml.get(h))}},
                   '1P 3-way': {'prices': o.get('ml3'), 'winner': p1},
                   '1P total 1.5': {'goals': tot, 'result': 'Over' if tot > 1 else 'Under', 'over_price': over.get('over'), 'under_price': over.get('under'),
                                    'over_units': units('W' if tot > 1 else 'L', over.get('over')), 'under_units': units('L' if tot > 1 else 'W', over.get('under'))},
                   '1P BTTS': {'result': 'Yes' if ap and hp else 'No', 'yes_price': o.get('btts_yes'), 'no_price': o.get('btts_no')}}}
        games.append(row)
        for code, res in ((a, res_a), (h, res_h)):
            bets.append({'bet': f'{code} 1P moneyline', 'game': row['matchup'], 'price': ml.get(code), 'result': res, 'units': units(res, ml.get(code))})
        bets.append({'bet': 'Over 1.5 1P', 'game': row['matchup'], 'price': over.get('over'), 'result': 'W' if tot > 1 else 'L', 'units': units('W' if tot > 1 else 'L', over.get('over'))})
        bets.append({'bet': 'Under 1.5 1P', 'game': row['matchup'], 'price': over.get('under'), 'result': 'L' if tot > 1 else 'W', 'units': units('L' if tot > 1 else 'W', over.get('under'))})
    if not games:
        return None
    log = read_json(os.path.join(ROOT, 'league_trends_log.json'), {})
    played = {c for g in D['schedule']['games'][day] for c in (g['away'], g['home'])}
    today = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    tonight = (D.get('schedule', {}).get('games') or {}).get(today, [])
    return {'sport': 'NHL', 'segment': '1st period', 'date_of_games': day, 'games': games,
            'league_trends': {'record': (log.get(day) or {}).get('record'), 'picks': trend_results(log.get(day))},
            'streaks': streak_changes(nhl_seqs(D, day), played, NHL_LABELS),
            'night': best_and_worst(bets),
            'carries_into_today': {'date': today, 'games_today': len(tonight),
                                   'active_streaks_for_teams_playing_today': active_streaks(
                                       nhl_seqs(D, day), {c for g in tonight for c in (g['away'], g['home'])}, NHL_LABELS)[:8]}}


def nhl_preview(day):
    D = read_json(os.path.join(ROOT, 'nhl', 'data.json'), {})
    slate = (D.get('schedule', {}).get('games') or {}).get(day, [])
    if not slate:
        return None
    # a tease (teaser_games): start, how many trends land on it, streaks
    log = read_json(os.path.join(ROOT, 'league_trends_log.json'), {})
    on = {}
    for t in (log.get(day) or {}).get('trends') or []:
        if t.get('kind') and t.get('strength') != 'weak':
            for p in t['games']:
                on[p['key']] = on.get(p['key'], 0) + 1
    seqs = nhl_seqs(D, (date.fromisoformat(day) - timedelta(days=1)).isoformat())
    games = []
    for g in slate:
        a, h = g['away'], g['home']
        games.append({'matchup': f'{nhl_name(D, a)} at {nhl_name(D, h)}', 'start': et_time(g.get('startTimeUTC')),
                      'trends_on_this_game': on.get(f'{day}|{a}|{h}', 0),
                      'streaks': [f"{x['team']} {x['streak']}" for x in active_streaks(seqs, {a, h}, NHL_LABELS)][:4]})
    return {'sport': 'NHL', 'segment': '1st period', 'date': day, 'games': games, 'trends_page': '/nhl/trends/'}


# ------------------------------------------------- every other sport
# The shared data.json shape (scripts/sport_build.py), so one builder covers
# the NBA, WNBA, NCAAB and MLB by day and the NFL and NCAAF by week.

LABELS = {'su': {'W': 'won', 'L': 'lost'}, 'ats': {'W': 'covered', 'L': 'failed to cover'}, 'tot': {'O': 'Over', 'U': 'Under'},
          'rfi': {'Y': 'had a run in the 1st inning', 'N': 'had no run in the 1st inning'}}
FLIP = {'W': 'L', 'L': 'W'}


def doc_of(key):
    return read_json(os.path.join(ROOT, sports.BY_KEY[key]['slug'], 'data.json'), {})


def team_of(D, slug):
    t = D['teams'].get(slug)
    if t:
        return t.get('name', slug), t.get('code', slug.upper())
    name = D.get('otherTeams', {}).get(slug) or slug   # non-Division I opponents: a name only
    return name, name


def seqs_of(D, through):
    """{(team code, 'seg:market'): results oldest first}, games on or before `through`."""
    seqs = {}
    for d in sorted(D.get('games') or {}):
        if d > through:
            continue
        for g in D['games'][d]:
            for k, r in (g.get('res') or {}).items():
                for side in ('away', 'home'):
                    code = team_of(D, g[side])[1]
                    for m in LABELS:
                        x = r.get(m)
                        if x in (None, 'NA'):
                            continue
                        if m in ('su', 'ats') and side == 'home':
                            x = FLIP.get(x, x)
                        seqs.setdefault((code, f'{k}:{m}'), []).append(x)
    return seqs


def labels_of(D):
    out = {}
    for s in D['segments']:
        for m, words in LABELS.items():
            if m == 'rfi':
                out[f"{s['key']}:{m}"] = dict(words)
            else:
                out[f"{s['key']}:{m}"] = {r: f'{w} the {s["tag"]}' if m != 'tot' else f'{w} in the {s["tag"]}' for r, w in words.items()}
    return out


def seg_words(key):
    return ' and '.join(s['label'] for s in sports.BY_KEY[key]['segments']).lower()


def finals_between(D, first, last):
    return [g for d in sorted(D.get('games') or {}) if first <= d <= last for g in D['games'][d]
            if g.get('state') == 'final' and g.get('res')]


def results_packet(key, D, finals):
    """Every finished game's segment results, and the bets for best / worst."""
    seg_tag = {s['key']: s['tag'] for s in D['segments']}
    games, bets = [], []
    for g in finals:
        (an, ac), (hn, hc) = team_of(D, g['away']), team_of(D, g['home'])
        row = {'matchup': f'{an} at {hn}', 'final': f"{ac} {g['as']} - {hc} {g['hs']}", 'segments': {}}
        for k, r in g['res'].items():
            o = (g.get('odds') or {}).get(k) or {}
            u = {m: [None if x is None else round(x, 2) for x in v] for m, v in (r.get('u') or {}).items()}
            sc = r.get('sc') or [None, None]
            ats = o.get('ats') or {}
            tot = o.get('total') or {}
            seg = {'score': f'{ac} {sc[0]} - {hc} {sc[1]}'}
            if r.get('su') not in (None, 'NA'):
                seg['moneyline'] = {ac: {'price': (o.get('ml') or {}).get('away'), 'result': r['su'], 'units': (u.get('su') or [None])[0]},
                                    hc: {'price': (o.get('ml') or {}).get('home'), 'result': FLIP.get(r['su'], r['su']), 'units': (u.get('su') or [None, None])[1]}}
            if r.get('ats') not in (None, 'NA'):
                seg['spread'] = {ac: {'line': (ats.get('away') or {}).get('line'), 'price': (ats.get('away') or {}).get('price'), 'result': r['ats'], 'units': (u.get('ats') or [None])[0]},
                                 hc: {'line': (ats.get('home') or {}).get('line'), 'price': (ats.get('home') or {}).get('price'), 'result': FLIP.get(r['ats'], r['ats']), 'units': (u.get('ats') or [None, None])[1]}}
            if r.get('tot') not in (None, 'NA'):
                seg['total'] = {'line': tot.get('line'), 'result': {'O': 'Over', 'U': 'Under', 'P': 'Push'}[r['tot']],
                                'over_price': tot.get('over'), 'under_price': tot.get('under'),
                                'over_units': (u.get('tot') or [None])[0], 'under_units': (u.get('tot') or [None, None])[1]}
            if r.get('rfi') in ('Y', 'N'):
                seg['run_in_1st_inning'] = 'Yes' if r['rfi'] == 'Y' else 'No'
            row['segments'][seg_tag.get(k, k)] = seg
            for name in ('moneyline', 'spread'):
                for code, v in (seg.get(name) or {}).items():
                    bets.append({'bet': f"{code} {seg_tag.get(k, k)} {name}" + (f" {v['line']:+g}" if v.get('line') is not None else ''),
                                 'game': row['matchup'], 'price': v.get('price'), 'result': v['result'], 'units': v.get('units')})
            if seg.get('total'):
                t = seg['total']
                for side, res in (('Over', 'W' if t['result'] == 'Over' else 'L'), ('Under', 'W' if t['result'] == 'Under' else 'L')):
                    bets.append({'bet': f"{side} {t['line']} {seg_tag.get(k, k)}", 'game': row['matchup'], 'price': t[side.lower() + '_price'],
                                 'result': res if t['result'] != 'Push' else 'P', 'units': t[side.lower() + '_units']})
        games.append(row)
    return games, bets


def sport_recap(key, day):
    """Daily sports: the night of `day`."""
    D = doc_of(key)
    finals = finals_between(D, day, day)
    if not finals:
        return None
    games, bets = results_packet(key, D, finals)
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    labels, seqs = labels_of(D), seqs_of(D, day)
    played = {team_of(D, g[s])[1] for g in finals for s in ('away', 'home')}
    today = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    tonight = (D.get('games') or {}).get(today, [])
    return {'sport': sports.BY_KEY[key]['label'], 'segments': seg_words(key), 'date_of_games': day, 'games': games,
            'league_trends': {'record': (log.get(day) or {}).get('record'), 'picks': trend_results(log.get(day))},
            'streaks': streak_changes(seqs, played, labels),
            'night': best_and_worst(bets),
            'carries_into_today': {'date': today, 'games_today': len(tonight),
                                   'active_streaks_for_teams_playing_today': active_streaks(
                                       seqs, {team_of(D, g[s])[1] for g in tonight for s in ('away', 'home')}, labels)[:8]}}


def teaser_games(key, D, slate, log_entry, through):
    """Previews tease: each game's start, how many of our trends land on it
    and the teams' active streaks -- no records, hit rates, prices or picks."""
    on = {}
    for t in (log_entry or {}).get('trends') or []:
        if t.get('kind') and t.get('strength') != 'weak':
            for p in t.get('games') or []:
                on[p.get('key')] = on.get(p.get('key'), 0) + 1
    seqs, labels = seqs_of(D, through), labels_of(D)
    weekly = D.get('schedule') == 'week'
    out = []
    for g in slate:
        (an, ac), (hn, hc) = team_of(D, g['away']), team_of(D, g['home'])
        start = g.get('start')
        when = (datetime.fromisoformat(start.replace('Z', '+00:00')).astimezone(ET).strftime('%A %-I:%M %p ET') if weekly and start
                else et_time(start))
        out.append({'matchup': f'{an} at {hn}', 'start': when, 'trends_on_this_game': on.get(g['id'], 0),
                    'streaks': [f"{x['team']} {x['streak']}" for x in active_streaks(seqs, {ac, hc}, labels)][:4]})
    return busiest(out)


PREVIEW_MAX = 15   # a college slate can run 60+ games: tease the ones with the most going on


def busiest(games):
    if len(games) <= PREVIEW_MAX:
        return games
    keep = sorted(range(len(games)), key=lambda i: (-games[i]['trends_on_this_game'], -len(games[i]['streaks']), i))[:PREVIEW_MAX]
    return [games[i] for i in sorted(keep)]


def sport_preview(key, day):
    D = doc_of(key)
    slate = (D.get('games') or {}).get(day, [])
    if not slate:
        return None
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    sp = sports.BY_KEY[key]
    return {'sport': sp['label'], 'segments': seg_words(key), 'date': day, 'games_on_the_slate': len(slate),
            'games': teaser_games(key, D, slate, log.get(day), (date.fromisoformat(day) - timedelta(days=1)).isoformat()),
            'trends_page': f"/{sp['slug']}/trends/"}


def week_of(D, day):
    """The week `day` falls in, else the next one."""
    weeks = D.get('weeks') or []
    return next((w for w in weeks if w['start'] <= day <= w['end']), None) or next((w for w in weeks if w['start'] > day), None)


def week_recap(key, day):
    """Football, Monday: the week's games through Sunday."""
    D = doc_of(key)
    yday = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
    wk = next((w for w in D.get('weeks') or [] if w['start'] <= yday <= w['end']), None)
    if not wk:
        return None
    finals = [g for g in finals_between(D, wk['start'], yday) if g.get('wk') == wk['key']]
    if not finals:
        return None
    games, bets = results_packet(key, D, finals)
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    labels, seqs = labels_of(D), seqs_of(D, yday)
    played = {team_of(D, g[s])[1] for g in finals for s in ('away', 'home')}
    return {'sport': sports.BY_KEY[key]['label'], 'segments': seg_words(key), 'week': wk['label'],
            'games_from': wk['start'], 'games_through': yday, 'games': games,
            'league_trends': {'record': (log.get(wk['key']) or {}).get('record'), 'picks': trend_results(log.get(wk['key']))},
            'streaks': streak_changes(seqs, played, labels),
            'weekend': best_and_worst(bets)}


def week_preview(key, day):
    """Football, Thursday: the week's games still to play."""
    D = doc_of(key)
    wk = week_of(D, day)
    if not wk:
        return None
    slate = sorted((g for d in sorted(D.get('games') or {}) for g in D['games'][d]
                    if g.get('wk') == wk['key'] and g.get('state') not in ('final', 'post')), key=lambda g: g.get('start') or '')
    if not slate:
        return None
    log = read_json(os.path.join(ROOT, 'trends_log', f'{key}.json'), {})
    sp = sports.BY_KEY[key]
    return {'sport': sp['label'], 'segments': seg_words(key), 'week': wk['label'], 'games_on_the_slate': len(slate),
            'games': teaser_games(key, D, slate, log.get(wk['key']), (date.fromisoformat(wk['start']) - timedelta(days=1)).isoformat()),
            'trends_page': f"/{sp['slug']}/trends/"}


def builder(kind, key):
    if key == 'nhl':
        return nhl_recap if kind == 'recap' else nhl_preview
    if sports.BY_KEY[key].get('schedule') == 'week':
        return lambda day: (week_recap if kind == 'recap' else week_preview)(key, day)
    return lambda day: (sport_recap if kind == 'recap' else sport_preview)(key, day)


# --------------------------------------------------------------- writing

SYSTEM = """You write The Daily for Run to Your Bets (RTYB), a site of first-period, first-quarter and first-half betting stats. Your voice: a fun, confident bettor who knows the numbers cold, talking to other bettors.

Rules, all of them strict:
- Use only facts in the data packet. Every team, score, price, record, unit figure and streak you mention must appear in the packet exactly as given. If something isn't in the packet, leave it out.
- Never invent plays, goals, players, injuries, quotes or game moments. The packet has scores and results, not play-by-play, so don't describe how a goal or basket happened.
- No guarantees. Never write 'lock', 'chase it', 'can't lose', 'free money', 'sure thing' or anything like them. Trends are history, not promises.
- Odds are American (-125, +150). Units are profit on a 1-unit bet.
- 150 to 250 words of body text in Markdown: short paragraphs, no headings, no bullet lists, no tables.
- Start with one bold line that works as a hook, then the body.
- Finish with one sentence that ends on '21+. Gambling problem? Call 1-800-GAMBLER.' only if you have room; the site adds that line anyway, so it's optional."""

PREVIEW = (" It's a tease, not a tip sheet: name games, start times and streaks as given, and say where several of our trends land on one game, "
           "but give no records, hit rates, percentages, prices or specific bets. End with one sentence sending readers to the Trends page "
           "for the full picture, as a Markdown link to the packet's trends_page.")
TASK = {
    'recap': "Write The Morning Run, today's recap of last night's {sport} {seg} betting results, from this packet. Cover the biggest results, how RTYB's league trends did, the night's best and worst results, and the streaks that were extended or snapped. End with what carries into today (the 'carries_into_today' part).",
    'preview': "Write On Tap, today's {sport} {seg} betting preview, from this packet." + PREVIEW,
    'week_recap': "Write the Weekend Recap, the {sport} {seg} betting results of {week} so far, from this packet. Cover the biggest results, how RTYB's league trends did, the weekend's best and worst results, and the streaks that were extended or snapped.",
    'week_preview': "Write the {week} Preview, this week's {sport} {seg} betting preview, from this packet." + PREVIEW,
}


def weekly(sport):
    return sports.BY_KEY[sport].get('schedule') == 'week'


def title(kind, sport, day, packet=None):
    sp = sports.BY_KEY[sport]
    seg = ' and '.join(s['label'].replace('1st ', 'First ') for s in sp['segments'])
    when = date.fromisoformat(day).strftime('%b %-d, %Y')
    if weekly(sport):
        week = (packet or {}).get('week') or 'Week'
        return f"{sp['label']} {seg} Betting {'Weekend Recap' if kind == 'recap' else week + ' Preview'} — {when}"
    return f"{sp['label']} {seg} Betting {'Recap' if kind == 'recap' else 'Preview'} — {when}"


def numbers_in(text):
    return set(re.findall(r'[+-]?\d+(?:\.\d+)?', text))


def unchecked_numbers(body, packet):
    """Numbers in the draft that aren't in the packet (ignoring signs,
    trailing zeros and small counting words like 3 games)."""
    have = {n.lstrip('+-').rstrip('0').rstrip('.') for n in numbers_in(json.dumps(packet, ensure_ascii=False))}
    have |= {'21', '1-800', '800', '4357'}
    out = []
    for n in re.findall(r'[+-]?\d+(?:\.\d+)?', body.replace('1-800-GAMBLER', '')):   # in reading order
        k = n.lstrip('+-').rstrip('0').rstrip('.') if '.' in n else n.lstrip('+-')
        if k not in have and n not in out:
            out.append(n)
    return out


def write_piece(kind, sport, day, packet):
    import anthropic   # only the scheduled run needs the SDK
    client = anthropic.Anthropic()
    seg = packet.get('segment') or packet.get('segments')
    task = TASK[('week_' if weekly(sport) else '') + kind]
    prompt = task.format(sport=packet['sport'], seg=seg, week=packet.get('week')) + '\n\n<packet>\n' + json.dumps(packet, indent=1, ensure_ascii=False) + '\n</packet>'
    # A declined request falls back server-side to Anthropic's recommended model
    response = client.beta.messages.create(
        model=MODEL, max_tokens=16000,
        betas=['server-side-fallback-2026-07-01'], fallbacks='default',
        output_config={'effort': 'medium'},
        system=SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    )
    if response.stop_reason == 'refusal':
        raise RuntimeError(f'{sport} {kind}: the model declined ({getattr(response.stop_details, "category", None)})')
    body = ''.join(b.text for b in response.content if b.type == 'text').strip()
    if not body:
        raise RuntimeError(f'{sport} {kind}: empty response ({response.stop_reason})')
    return body, response.model


def draft_path(kind, sport, day):
    return os.path.join(DRAFTS, f'{sport}-{kind}-{day}.md')


def save(kind, sport, day, body, model, packet):
    os.makedirs(DRAFTS, exist_ok=True)
    check = unchecked_numbers(body, packet)
    front = ['---', f'title: {json.dumps(title(kind, sport, day, packet), ensure_ascii=False)}', f'sport: {sport}', f'kind: {kind}',
             f'date: {day}', f"written: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}", f'model: {model}',
             f'check: {json.dumps(check)}', '---', '']
    with open(draft_path(kind, sport, day), 'w', encoding='utf-8') as f:
        f.write('\n'.join(front) + body + '\n')
    # the packet beside the draft, so the editor can check every number
    with open(draft_path(kind, sport, day)[:-3] + '.packet.json', 'w', encoding='utf-8') as f:
        json.dump(packet, f, indent=1, ensure_ascii=False)
    print(f'wrote {os.path.relpath(draft_path(kind, sport, day), ROOT)}' + (f' (check: {", ".join(check)})' if check else ''))


def exists(kind, sport, day):
    name = f'{sport}-{kind}-{day}.md'
    return os.path.exists(os.path.join(DRAFTS, name)) or os.path.exists(os.path.join(PUBLISHED, name))


def packet_for(kind, sport, day):
    """The recap dated `day` covers the games the night before."""
    if weekly(sport):   # the week's own rules (week_recap / week_preview)
        return builder(kind, sport)(day)
    games_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat() if kind == 'recap' else day
    return builder(kind, sport)(games_day)


def scheduled(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(ET)
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY not set; no drafts written')
        return
    day = now.date().isoformat()
    for kind in WINDOWS:
        for sport in SPORTS:
            wday, start, end = (WEEKLY_WINDOWS if weekly(sport) else WINDOWS)[kind]
            if (wday is not None and now.weekday() != wday) or not start <= now.hour <= end:
                continue
            if exists(kind, sport, day):
                continue
            packet = packet_for(kind, sport, day)
            if not packet:
                print(f'{sport} {kind} {day}: no games')
                continue
            try:
                body, model = write_piece(kind, sport, day, packet)
            except Exception as e:   # one failed draft never stops the refresh; the next run retries
                print(f'{sport} {kind} {day} failed: {e}')
                continue
            save(kind, sport, day, body, model, packet)


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if not args:
        scheduled()
    else:
        kind, sport = args[0], args[1]
        day = args[2] if len(args) > 2 else datetime.now(ET).date().isoformat()
        packet = packet_for(kind, sport, day)
        if '--dry-run' in sys.argv or not packet:
            print(json.dumps(packet, indent=1, ensure_ascii=False))
        else:
            body, model = write_piece(kind, sport, day, packet)
            save(kind, sport, day, body, model, packet)
