"""
NHL extras for the Situational Results table, beyond scores and 1P odds:

  starting goalies    /v1/gamecenter/{id}/boxscore (the NHL's "starter" flag)
                      -> awayGoalie / homeGoalie = {"id", "name"}
  full-game moneyline ESPN's game summary (DraftKings close), matched to the
                      NHL game by date and teams -> fgMl = {"away", "home"}
                      (None when ESPN has no line)

The game's first goal comes with the period scores (periods.py). Used by
backfill_periods.py (this season, capped per run) and once for the 2025-26
archive.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_schedule import fetch_json  # noqa: E402

ESPN_CODE = {'ANA': 'ANH', 'MTL': 'MON', 'UTAH': 'UTA', 'TBL': 'TB', 'NJD': 'NJ', 'SJS': 'SJ', 'LAK': 'LA'}
ESPN = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl'


def goalies(game_id):
    """(awayGoalie, homeGoalie) starters, or (None, None)."""
    box = fetch_json(f'https://api-web.nhle.com/v1/gamecenter/{game_id}/boxscore')
    if not box:
        return None, None
    out = []
    for side in ('awayTeam', 'homeTeam'):
        gs = ((box.get('playerByGameStats') or {}).get(side) or {}).get('goalies') or []
        st = next((g for g in gs if g.get('starter')), None)
        out.append({'id': st.get('playerId'), 'name': (st.get('name') or {}).get('default')} if st else None)
    return out[0], out[1]


def espn_moneylines(date):
    """{(away, home): {"away": ml, "home": ml} or None} for one date (ET);
    None when ESPN didn't answer (try again later; don't save "no line").
    A game whose summary didn't load is left out of the dict."""
    sb = fetch_json(f'{ESPN}/scoreboard?dates={date.replace("-", "")}')
    if not sb:
        return None
    events = []
    for ev in sb.get('events') or []:
        comp = (ev.get('competitions') or [{}])[0]
        teams = {c.get('homeAway'): c['team']['abbreviation'] for c in comp.get('competitors') or []}
        if 'away' in teams and 'home' in teams:
            events.append((ESPN_CODE.get(teams['away'], teams['away']), ESPN_CODE.get(teams['home'], teams['home']), ev['id']))

    def line(e):
        s = fetch_json(f'{ESPN}/summary?event={e[2]}')
        if s is None:
            return (e[0], e[1]), 'retry'
        pc = next(iter(s.get('pickcenter') or []), {}) or {}
        ml = {k: (pc.get(f'{k}TeamOdds') or {}).get('moneyLine') for k in ('away', 'home')}
        return (e[0], e[1]), (ml if all(isinstance(v, (int, float)) for v in ml.values()) else None)
    with ThreadPoolExecutor(max_workers=4) as pool:
        return {k: v for k, v in pool.map(line, events) if v != 'retry'}
