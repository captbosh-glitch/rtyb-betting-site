"""
Fill in the extra NHL game fields on this season's finished games in
schedule_data.json that don't have them yet -- games that aged out of
fetch_schedule.py's window before those fields existed. Run by refresh.yml
before the build.
  period scores   awayP2, homeP2, awayP3, homeP3, firstGoal2P, firstGoal (periods.py)
  goalies         awayGoalie, homeGoalie: the starters (nhl_extras.py)
  fgMl            ESPN's closing full-game moneyline (nhl_extras.py)

Idempotent and capped: only games missing a field are fetched, at most CAP
per run, so a few runs finish the season. A game that fails the
sanity rule (scripts/periods.py) is logged and saved with its 2P / 3P
fields None, so it isn't fetched again.

Also re-checks the 1P score from the same goal list: the old landing
fallback in fetch_schedule.py saved 0-0 for every game that went through
it, so a mismatch is corrected and logged. Games with an Admin results
override are left alone (build_site.py applies the override anyway).

  python3 scripts/backfill_periods.py [--all]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nhl_extras  # noqa: E402
import periods  # noqa: E402
from fetch_schedule import fetch_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'schedule_data.json')
CAP = 60
EXTRA = ('awayGoalie', 'fgMl')


def main():
    cap = None if '--all' in sys.argv else CAP
    if not os.path.exists(PATH):
        print('no schedule_data.json; nothing to backfill')
        return
    data = json.load(open(PATH, encoding='utf-8'))
    overrides = {}
    op = os.path.join(ROOT, 'data_admin', 'results_overrides.json')
    if os.path.exists(op):
        overrides = json.load(open(op, encoding='utf-8'))

    todo = [(d, g) for d, gs in sorted(data.get('games', {}).items()) if d >= periods.SEASON_START
            for g in gs if g.get('state') in ('FINAL', 'OFF') and g.get('id')
            and any(f not in g for f in ('awayP2', 'firstGoal') + EXTRA)]
    todo = todo[:cap]
    # goalies (one request a game) and ESPN moneylines (one date at a time)
    lines = {}
    for d in sorted({d for d, g in todo if 'fgMl' not in g}):
        lines[d] = nhl_extras.espn_moneylines(d)
    extras = 0
    for d, g in todo:
        if 'awayGoalie' not in g:
            g['awayGoalie'], g['homeGoalie'] = nhl_extras.goalies(g['id'])
        if 'fgMl' not in g and lines.get(d) is not None and (g['away'], g['home']) in lines[d]:
            g['fgMl'] = lines[d][(g['away'], g['home'])]
        extras += 1
    done = failed = fixed = 0
    for d, g in [(d, g) for d, g in todo if 'awayP2' not in g or 'firstGoal' not in g]:
        landing = fetch_json(f'https://api-web.nhle.com/v1/gamecenter/{g["id"]}/landing')
        goals = periods.goals_from_landing(landing)
        if goals is None:
            print(f'WARN: {g["id"]} {g["away"]}@{g["home"]}: no landing scoring; will retry', file=sys.stderr)
            continue
        fields, err = periods.parse(goals, g.get('awayFinal'), g.get('homeFinal'), g.get('ot') or '')
        if err:
            failed += 1
            print(f'WARN: {g["id"]} {d} {g["away"]}@{g["home"]}: {err}; 2P/3P left empty', file=sys.stderr)
        key = f'{d}|{g["away"]}|{g["home"]}'
        p1 = (fields.pop('awayP1'), fields.pop('homeP1'))
        if key not in overrides and (g.get('awayP1'), g.get('homeP1')) != p1:
            print(f'1P fixed: {g["id"]} {d} {g["away"]}@{g["home"]} {g.get("awayP1")}-{g.get("homeP1")} -> {p1[0]}-{p1[1]}')
            g['awayP1'], g['homeP1'] = p1
            fixed += 1
        g.update(fields)
        done += 1

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))
    left = sum(1 for d, gs in data.get('games', {}).items() if d >= periods.SEASON_START for g in gs
               if g.get('state') in ('FINAL', 'OFF') and any(f not in g for f in ('awayP2', 'firstGoal') + EXTRA))
    print(f'backfill_periods: {done} games given period scores ({failed} failed the sanity rule, {fixed} 1P scores fixed), '
          f'{extras} given goalies / moneylines, {left} left')


if __name__ == '__main__':
    main()
