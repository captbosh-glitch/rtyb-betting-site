"""
One-off: add the NHL extras to the 2025-26 archive (data_seed/
nhl_2025_26_games.json) so "Since last season" rows have them too:
period scores and the first goal (periods.py, from each date's goal list),
starting goalies and ESPN's closing full-game moneyline (nhl_extras.py).

  python3 scripts/enrich_2025_26.py
Safe to re-run: games that already have a field are skipped.
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nhl_extras  # noqa: E402
import periods  # noqa: E402
from fetch_schedule import fetch_json  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data_seed', 'nhl_2025_26_games.json')


def main():
    games = json.load(open(PATH, encoding='utf-8'))
    by_id = {g['id']: g for g in games}
    dates = sorted({g['date'] for g in games if 'firstGoal' not in g})

    def day(d):
        return d, fetch_json(f'https://api-web.nhle.com/v1/score/{d}') or {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for d, data in pool.map(day, dates):
            for sg in data.get('games') or []:
                g = by_id.get(sg.get('id'))
                if g is None or sg.get('goals') is None:
                    continue
                fields, err = periods.parse(periods.goals_from_score(sg['goals']), g['awayFinal'], g['homeFinal'], g.get('ot') or '')
                fields.pop('awayP1'), fields.pop('homeP1')
                g.update(fields)
    print('periods / first goal:', sum('firstGoal' in g for g in games), 'of', len(games))

    need = [g for g in games if 'awayGoalie' not in g]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for g, (a, h) in zip(need, pool.map(lambda g: nhl_extras.goalies(g['id']), need)):
            g['awayGoalie'], g['homeGoalie'] = a, h
    print('goalies:', sum(1 for g in games if g.get('awayGoalie')), 'of', len(games))

    for d in sorted({g['date'] for g in games if g.get('fgMl') is None}):
        lines = nhl_extras.espn_moneylines(d)
        if lines is None:
            continue
        for g in games:
            if g['date'] == d and (g['away'], g['home']) in lines:
                g['fgMl'] = lines[(g['away'], g['home'])]
    print('moneylines:', sum(1 for g in games if g.get('fgMl')), 'of', len(games))
    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(games, f, separators=(',', ':'))


if __name__ == '__main__':
    main()
