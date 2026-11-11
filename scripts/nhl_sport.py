"""
NHL games in the shared sport shape (assets/sport.js, assets/situational.js),
so NHL's Stats page is drawn by the same code as every other sport's.

Written to nhl/sport.json by build_site.py. One segment, the 1st period:
  res['1p'] = {sc [away, home], su (away side W/L/T), tot O/U (1.5),
               btts Y/N, u {su [away, home], ml3 [away, home, tie],
               tot [over, under], btts [yes, no]}}
  odds['1p'] = {ml {away, home}, ml3 {away, draw, home},
                total {line 1.5, over, under}, btts {yes, no}}
als / hls are the period scores (1st, 2nd, 3rd); as / hs the final score,
which counts OT goals and the shootout winner, the way books grade it.
The same rules as nhlSitGame in template.html: a tied 1st period is a push
on the moneyline (0 units), a loss for both teams on the 3-way.
"""
from grading import bet_units, flip, num

STATE = {'LIVE': 'in', 'CRIT': 'in', 'FINAL': 'final', 'OFF': 'final'}
CONFERENCE = {'Atlantic': 'East', 'Metropolitan': 'East', 'Central': 'West', 'Pacific': 'West'}
SEGMENTS = [{'key': '1p', 'label': '1st Period', 'tag': '1P'}]
TWO_WORD = ('Blue Jackets', 'Maple Leafs', 'Red Wings', 'Golden Knights')


def nickname(name):
    return next((w for w in TWO_WORD if name.endswith(w)), name.split(' ')[-1])


def _won(yes):
    return 'W' if yes else 'L'


def game(g, date):
    out = {'id': g.get('id'), 'start': g.get('startTimeUTC') or date + 'T23:00:00Z',
           'state': STATE.get(g.get('state'), 'pre'), 'away': g['away'], 'home': g['home'],
           'as': g.get('awayFinal'), 'hs': g.get('homeFinal'), 'ot': g.get('ot') or '',
           'firstGoal': g.get('firstGoal'), 'ag': g.get('awayGoalie'), 'hg': g.get('homeGoalie'),
           'fml': g.get('fgMl')}
    periods = [(g.get(f'awayP{i}'), g.get(f'homeP{i}')) for i in (1, 2, 3)]
    if all(a is not None and h is not None for a, h in periods):
        out['als'] = [a for a, _ in periods]
        out['hls'] = [h for _, h in periods]
    o = g.get('odds') or {}
    ml = o.get('ml') or {}
    t = (o.get('totals') or {}).get('1.5') or {}
    m3 = o.get('ml3') or {}
    pa, ph = num(ml.get(g['away'])), num(ml.get(g['home']))
    po, pu = num(t.get('over')), num(t.get('under'))
    py, pn = num(o.get('btts_yes')), num(o.get('btts_no'))
    ta, td, th = num(m3.get('away')), num(m3.get('draw')), num(m3.get('home'))
    odds = {}
    if pa is not None and ph is not None:
        odds['ml'] = {'away': pa, 'home': ph}
    if ta is not None and td is not None and th is not None:
        odds['ml3'] = {'away': ta, 'draw': td, 'home': th}
    if po is not None and pu is not None:
        odds['total'] = {'line': 1.5, 'over': po, 'under': pu}
    if py is not None and pn is not None:
        odds['btts'] = {'yes': py, 'no': pn}
    if odds:
        out['odds'] = {'1p': odds}
    a, h = periods[0]
    if a is None or h is None:
        return out
    su = 'W' if a > h else 'L' if a < h else 'T'
    over, btts = a + h > 1, a >= 1 and h >= 1
    u = {}
    if 'ml' in odds:
        u['su'] = [bet_units(su, pa), bet_units(flip(su), ph)]
    if 'ml3' in odds:
        u['ml3'] = [bet_units(_won(su == 'W'), ta), bet_units(_won(su == 'L'), th), bet_units(_won(su == 'T'), td)]
    if 'total' in odds:
        u['tot'] = [bet_units(_won(over), po), bet_units(_won(not over), pu)]
    if 'btts' in odds:
        u['btts'] = [bet_units(_won(btts), py), bet_units(_won(not btts), pn)]
    out['res'] = {'1p': {'sc': [a, h], 'su': su, 'tot': 'O' if over else 'U', 'btts': 'Y' if btts else 'N', 'u': u}}
    return out


def doc(games_by_date, season_start, season_label, summary, divisions, colors, tz, generated):
    teams = {}
    for div, codes in divisions.items():
        for code in codes:
            name = (summary.get(code) or {}).get('name') or code
            teams[code] = {'name': name, 'short': nickname(name), 'code': code, 'svg': 1,
                           'color': (colors.get(code) or '').lstrip('#') or None,
                           'division': div, 'conference': CONFERENCE.get(div)}
    return {
        'sport': 'nhl', 'label': 'NHL', 'slug': 'nhl', 'sportType': 'period', 'segments': SEGMENTS,
        'schedule': 'day', 'season': int(season_start[:4]) + 1, 'seasonLabel': season_label,
        'generated': generated, 'teams': teams, 'tz': tz,
        'games': {d: [game(g, d) for g in gs] for d, gs in sorted(games_by_date.items()) if d >= season_start},
    }
