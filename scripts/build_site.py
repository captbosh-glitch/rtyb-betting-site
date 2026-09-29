"""
Merge everything into the final embedded data blob and write index.html.

Inputs (all relative to repo root, where this runs from in CI):
  base_data.json          -- static: summary / streaks / gamelog (season stats,
                              baked once from the archived season file; not
                              refetched every run)
  schedule_fresh.json      -- freshly fetched this run by fetch_schedule.py
  schedule_data.json      -- the PREVIOUSLY COMMITTED schedule (if any) --
                              read here (not overwritten by fetch_schedule.py)
                              so closing odds already saved on now-completed
                              games survive even once an odds API stops
                              returning them for a finished game.
  odds_theoddsapi.json    -- fresh 1P moneyline + totals, keyed "date|away|home"
  odds_sportsgameodds.json -- fresh 1P BTTS yes price, same key shape
  template.html           -- site shell with a __RTYB_DATA_JSON__ placeholder

Output:
  index.html               -- the deployable site
  schedule_data.json       -- OVERWRITTEN with the merged result, so the next
                              run's "previous" read carries forward saved odds
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path, default):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        return default
    with open(full, encoding='utf-8') as f:
        return json.load(f)


def main():
    base = load('base_data.json', {'summary': {}, 'streaks': {}, 'gamelog': {}})
    fresh_schedule = load('schedule_fresh.json', {'gameCounts': {}, 'games': {}})
    prev_schedule = load('schedule_data.json', {'gameCounts': {}, 'games': {}})
    odds_oddsapi = load('odds_theoddsapi.json', {})
    odds_sgo = load('odds_sportsgameodds.json', {})

    prev_games_by_id = {}
    for date_str, games in prev_schedule.get('games', {}).items():
        for g in games:
            if g.get('id') is not None:
                prev_games_by_id[g['id']] = g

    merged_games = {}
    for date_str, games in fresh_schedule.get('games', {}).items():
        merged_list = []
        for g in games:
            key = f'{date_str}|{g["away"]}|{g["home"]}'
            odds = {}

            oa = odds_oddsapi.get(key)
            if oa:
                if oa.get('ml'):
                    odds['ml'] = oa['ml']
                if oa.get('totals'):
                    odds['totals'] = {
                        line: {'over': prices.get('over'), 'under': prices.get('under')}
                        for line, prices in oa['totals'].items()
                    }
            sgo = odds_sgo.get(key)
            if sgo and sgo.get('btts_yes') is not None:
                odds['btts_yes'] = sgo['btts_yes']

            # Carry forward previously-saved odds for a now-completed game if
            # this run's odds fetch didn't return anything fresh for it (the
            # normal case once a game has ended -- odds feeds stop covering it).
            if not odds and g.get('id') in prev_games_by_id:
                prev_odds = prev_games_by_id[g['id']].get('odds')
                if prev_odds:
                    odds = prev_odds

            if odds:
                g = dict(g)
                g['odds'] = odds
            merged_list.append(g)
        merged_games[date_str] = merged_list

    merged_schedule = {
        'gameCounts': fresh_schedule.get('gameCounts', {}),
        'games': merged_games,
    }

    # Persist the merged schedule so the NEXT run's "previous" read has
    # today's closing odds saved on it.
    with open(os.path.join(ROOT, 'schedule_data.json'), 'w', encoding='utf-8') as f:
        json.dump(merged_schedule, f, separators=(',', ':'))

    full_data = dict(base)
    full_data['schedule'] = merged_schedule

    template_path = os.path.join(ROOT, 'template.html')
    with open(template_path, encoding='utf-8') as f:
        template = f.read()

    data_json = json.dumps(full_data, separators=(',', ':'))
    if '__RTYB_DATA_JSON__' not in template:
        raise SystemExit('template.html is missing the __RTYB_DATA_JSON__ placeholder')
    out_html = template.replace('__RTYB_DATA_JSON__', data_json, 1)

    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(out_html)

    print(f"wrote index.html ({len(out_html)} bytes) and schedule_data.json "
          f"({sum(len(v) for v in merged_games.values())} games)")


if __name__ == '__main__':
    main()
