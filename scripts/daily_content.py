"""
The Daily's drafts, written by Claude from the site's own numbers:

  recap    The Morning Run: last night's NHL / NBA results, from 8 AM ET
  preview  On Tap: today's slate, from 11 AM ET

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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ET = ZoneInfo('America/New_York')
DRAFTS = os.path.join(ROOT, 'content', 'drafts')
PUBLISHED = os.path.join(ROOT, 'content', 'published')
SPORTS = ('nhl', 'nba')
# kind -> (first ET hour, last ET hour) a scheduled run may write it
WINDOWS = {'recap': (8, 14), 'preview': (11, 18)}
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
    log = read_json(os.path.join(ROOT, 'league_trends_log.json'), {})
    picks = {}
    for t in (log.get(day) or {}).get('trends') or []:
        if t.get('kind') and t.get('strength') != 'weak':
            for p in t['games']:
                picks.setdefault(p['key'], []).append({'trend': t['title'], 'strength': t['strength'], 'season_record': t.get('record'), 'pick': p.get('label')})
    seqs = nhl_seqs(D, day)
    games = []
    for g in slate:
        a, h = g['away'], g['home']
        o = g.get('odds') or {}
        games.append({'matchup': f'{nhl_name(D, a)} at {nhl_name(D, h)}', 'start': et_time(g.get('startTimeUTC')),
                      'prices_1p': {'moneyline': o.get('ml'), '3-way': o.get('ml3'), 'total_1.5': (o.get('totals') or {}).get('1.5'),
                                    'btts_yes': o.get('btts_yes'), 'btts_no': o.get('btts_no')},
                      'trends': picks.get(f'{day}|{a}|{h}', []),
                      'streaks': active_streaks(seqs, {a, h}, NHL_LABELS)})
    return {'sport': 'NHL', 'segment': '1st period', 'date': day, 'games': games}


# ----------------------------------------------------------------- NBA

NBA_LABELS = {'su': {'W': 'won', 'L': 'lost'}, 'ats': {'W': 'covered', 'L': 'failed to cover'}, 'tot': {'O': 'Over', 'U': 'Under'}}
FLIP = {'W': 'L', 'L': 'W'}


def nba_team(D, slug):
    t = D['teams'].get(slug) or D.get('otherTeams', {}).get(slug) or {}
    return t.get('name', slug), t.get('code', slug.upper())


def nba_seqs(D, through):
    seqs = {}
    for d in sorted(D.get('games') or {}):
        if d > through:
            continue
        for g in D['games'][d]:
            for k, r in (g.get('res') or {}).items():
                for side in ('away', 'home'):
                    code = nba_team(D, g[side])[1]
                    for m in ('su', 'ats', 'tot'):
                        x = r.get(m)
                        if x in (None, 'NA'):
                            continue
                        if m != 'tot' and side == 'home':
                            x = FLIP.get(x, x)
                        seqs.setdefault((code, f'{k}:{m}'), []).append(x)
    return seqs


def nba_labels(D):
    return {f"{s['key']}:{m}": {r: f'{w} the {s["tag"]}' if m != 'tot' else f'{w} in the {s["tag"]}' for r, w in NBA_LABELS[m].items()}
            for s in D['segments'] for m in NBA_LABELS}


def nba_recap(day):
    D = read_json(os.path.join(ROOT, 'nba', 'data.json'), {})
    finals = [g for g in (D.get('games') or {}).get(day, []) if g.get('state') == 'final' and g.get('res')]
    if not finals:
        return None
    seg_tag = {s['key']: s['tag'] for s in D['segments']}
    games, bets = [], []
    for g in finals:
        (an, ac), (hn, hc) = nba_team(D, g['away']), nba_team(D, g['home'])
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
            row['segments'][seg_tag.get(k, k)] = seg
            for name, m in (('moneyline', 'ml'), ('spread', 'ats')):
                for code, v in (seg.get(name) or {}).items():
                    bets.append({'bet': f"{code} {seg_tag.get(k, k)} {name}" + (f" {v['line']:+g}" if v.get('line') is not None else ''),
                                 'game': row['matchup'], 'price': v.get('price'), 'result': v['result'], 'units': v.get('units')})
            if seg.get('total'):
                t = seg['total']
                for side, res in (('Over', 'W' if t['result'] == 'Over' else 'L'), ('Under', 'W' if t['result'] == 'Under' else 'L')):
                    bets.append({'bet': f"{side} {t['line']} {seg_tag.get(k, k)}", 'game': row['matchup'], 'price': t[side.lower() + '_price'],
                                 'result': res if t['result'] != 'Push' else 'P', 'units': t[side.lower() + '_units']})
        games.append(row)
    log = read_json(os.path.join(ROOT, 'trends_log', 'nba.json'), {})
    labels = nba_labels(D)
    played = {nba_team(D, g[s])[1] for g in finals for s in ('away', 'home')}
    today = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
    tonight = (D.get('games') or {}).get(today, [])
    return {'sport': 'NBA', 'segments': '1st quarter and 1st half', 'date_of_games': day, 'games': games,
            'league_trends': {'record': (log.get(day) or {}).get('record'), 'picks': trend_results(log.get(day))},
            'streaks': streak_changes(nba_seqs(D, day), played, labels),
            'night': best_and_worst(bets),
            'carries_into_today': {'date': today, 'games_today': len(tonight),
                                   'active_streaks_for_teams_playing_today': active_streaks(
                                       nba_seqs(D, day), {nba_team(D, g[s])[1] for g in tonight for s in ('away', 'home')}, labels)[:8]}}


def nba_preview(day):
    D = read_json(os.path.join(ROOT, 'nba', 'data.json'), {})
    slate = (D.get('games') or {}).get(day, [])
    if not slate:
        return None
    seg_tag = {s['key']: s['tag'] for s in D['segments']}
    log = read_json(os.path.join(ROOT, 'trends_log', 'nba.json'), {})
    picks = {}
    for t in (log.get(day) or {}).get('trends') or []:
        if t.get('kind') and t.get('strength') != 'weak':
            for p in t['games']:
                picks.setdefault(p['key'], []).append({'trend': t['title'], 'strength': t['strength'], 'season_record': t.get('record'), 'pick': p.get('label')})
    seqs, labels = nba_seqs(D, day), nba_labels(D)
    games = []
    for g in slate:
        (an, ac), (hn, hc) = nba_team(D, g['away']), nba_team(D, g['home'])
        games.append({'matchup': f'{an} at {hn}', 'start': et_time(g.get('start')),
                      'prices': {seg_tag.get(k, k): {m: v[m] for m in ('ml', 'ats', 'total') if m in v} for k, v in (g.get('odds') or {}).items()},
                      'trends': picks.get(g['id'], []),
                      'streaks': active_streaks(seqs, {ac, hc}, labels)})
    return {'sport': 'NBA', 'segments': '1st quarter and 1st half', 'date': day, 'games': games}


BUILDERS = {('recap', 'nhl'): nhl_recap, ('recap', 'nba'): nba_recap,
            ('preview', 'nhl'): nhl_preview, ('preview', 'nba'): nba_preview}

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

TASK = {
    'recap': "Write The Morning Run, today's recap of last night's {sport} {seg} betting results, from this packet. Cover the biggest results, how RTYB's league trends did, the night's best and worst results, and the streaks that were extended or snapped. End with what carries into today (the 'carries_into_today' part).",
    'preview': "Write On Tap, today's {sport} {seg} betting preview, from this packet. Name only games in the packet, with their start times and prices as given, and the trends and streaks on each game. Point out where several trends line up on one game. Don't promise outcomes.",
}


def title(kind, sport, day):
    seg = 'First Period' if sport == 'nhl' else 'First Quarter and Half'
    when = date.fromisoformat(day).strftime('%b %-d, %Y')
    return f"{sport.upper()} {seg} Betting {'Recap' if kind == 'recap' else 'Preview'} — {when}"


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
    prompt = TASK[kind].format(sport=packet['sport'], seg=seg) + '\n\n<packet>\n' + json.dumps(packet, indent=1, ensure_ascii=False) + '\n</packet>'
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
    front = ['---', f'title: {json.dumps(title(kind, sport, day), ensure_ascii=False)}', f'sport: {sport}', f'kind: {kind}',
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
    games_day = (date.fromisoformat(day) - timedelta(days=1)).isoformat() if kind == 'recap' else day
    return BUILDERS[(kind, sport)](games_day)


def scheduled(now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(ET)
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print('ANTHROPIC_API_KEY not set; no drafts written')
        return
    day = now.date().isoformat()
    for kind, (start, end) in WINDOWS.items():
        if not start <= now.hour <= end:
            continue
        for sport in SPORTS:
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
