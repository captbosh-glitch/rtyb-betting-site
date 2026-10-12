"""
One-time backfill of the 2025-26 NHL regular season from the NHL's free
public API, for the Advanced Stats (Situational Results, Goal Stats) and
Trends, which compute over 2025-26 + 2026-27 combined.

Writes data_seed/nhl_2025_26_games.json: one entry per regular-season game,
sorted by start time --
  {id, date, startTimeUTC, away, home, awayP1, homeP1, awayFinal, homeFinal, ot}
where ot is '' (regulation), 'OT' or 'SO'. No odds: closing prices weren't
saved for that season.

Run from the repo root:  python3 scripts/backfill_2025_26.py
Safe to re-run; it overwrites the file.
"""
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_schedule import fetch_json, first_period_score, rt  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON_FIRST = date(2025, 10, 7)
SEASON_LAST = date(2026, 4, 16)
OUT = os.path.join(ROOT, 'data_seed', 'nhl_2025_26_games.json')


def main():
    games = {}
    d = SEASON_FIRST
    while d <= SEASON_LAST:
        data = fetch_json(f'https://api-web.nhle.com/v1/score/{d.isoformat()}') or {}
        for g in data.get('games', []):
            if g.get('gameType') != 2:  # 2 = regular season
                continue
            entry = {
                'id': g.get('id'),
                'date': d.isoformat(),
                'startTimeUTC': g.get('startTimeUTC'),
                'away': rt(g.get('awayTeam', {}).get('abbrev', '?')),
                'home': rt(g.get('homeTeam', {}).get('abbrev', '?')),
                'awayFinal': g.get('awayTeam', {}).get('score'),
                'homeFinal': g.get('homeTeam', {}).get('score'),
                'ot': (g.get('gameOutcome') or {}).get('lastPeriodType') if (g.get('gameOutcome') or {}).get('lastPeriodType') in ('OT', 'SO') else '',
            }
            goals = g.get('goals')
            if goals is None:
                landing = fetch_json(f'https://api-web.nhle.com/v1/gamecenter/{entry["id"]}/landing') or {}
                goals = [goal for period in (landing.get('summary') or {}).get('scoring', [])
                         for goal in [dict(x, period=period.get('periodDescriptor', {}).get('number')) for x in period.get('goals', [])]]
            entry['awayP1'], entry['homeP1'] = first_period_score(goals)
            games[entry['id']] = entry
        d += timedelta(days=1)

    out = sorted(games.values(), key=lambda g: (g['startTimeUTC'] or '', g['id']))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f'wrote {len(out)} games to {OUT}')


if __name__ == '__main__':
    main()
