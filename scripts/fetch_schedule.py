"""
Pull real NHL schedule + scores from the public api-web.nhle.com API (no key
required) for a rolling window of dates, and write schedule_fresh.json in the
shape RTYB's front end expects:

  { "gameCounts": {"YYYY-MM-DD": <int>, ...},
    "games": {"YYYY-MM-DD": [ {id, away, home, startTimeUTC, state,
                                awayFinal, homeFinal, ot, awayP1, homeP1}, ... ] } }

Only dates within WINDOW_DAYS_BACK..WINDOW_DAYS_FWD of "today" (UTC) are
covered -- that matches what the date bar in the UI lets people reach without
a huge fetch. Widen the window later if needed.

Team abbreviations are remapped to match the archived historical dataset's
codes (see ABBREV_MAP) so schedule games join cleanly against the season
stats already baked into base_data.json.
"""
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

WINDOW_DAYS_BACK = 10
WINDOW_DAYS_FWD = 10

ABBREV_MAP = {'TBL': 'TB', 'MTL': 'MON', 'NJD': 'NJ', 'SJS': 'SJ', 'LAK': 'LA'}


def rt(abbrev):
    return ABBREV_MAP.get(abbrev, abbrev)


def fetch_json(url, tries=3, timeout=15):
    last_err = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'rtyb-fetch/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    print(f"WARN: failed to fetch {url}: {last_err}", file=sys.stderr)
    return None


def first_period_score(goals):
    """Last cumulative awayScore/homeScore among goals with period == 1."""
    away_p1, home_p1 = 0, 0
    for g in goals or []:
        if g.get('period') == 1:
            away_p1 = g.get('awayScore', away_p1)
            home_p1 = g.get('homeScore', home_p1)
    return away_p1, home_p1


def main():
    today = datetime.now(timezone.utc).date()
    dates = [
        (today + timedelta(days=d)).isoformat()
        for d in range(-WINDOW_DAYS_BACK, WINDOW_DAYS_FWD + 1)
    ]

    game_counts = {}
    games_by_date = {}
    debug_logged = False

    # api-web.nhle.com's /v1/score/{date} response covers a whole gameWeek
    # (7 days starting at {date}), so we only need to hit it roughly once
    # per week of the window rather than once per day.
    seen_weeks = set()
    for d in dates:
        week_anchor = d
        if week_anchor in seen_weeks:
            continue

        data = fetch_json(f'https://api-web.nhle.com/v1/score/{d}')
        if not data:
            continue

        for day in data.get('gameWeek', []):
            date_str = day.get('date')
            if date_str not in dates:
                continue
            seen_weeks.add(date_str)
            game_counts[date_str] = day.get('numberOfGames', len(day.get('games', [])))

            day_games = []
            for g in day.get('games', []):
                away = rt(g.get('awayTeam', {}).get('abbrev', '?'))
                home = rt(g.get('homeTeam', {}).get('abbrev', '?'))
                state = g.get('gameState', 'FUT')
                entry = {
                    'id': g.get('id'),
                    'away': away,
                    'home': home,
                    'startTimeUTC': g.get('startTimeUTC'),
                    'state': state,
                }
                if state in ('FINAL', 'OFF', 'LIVE', 'CRIT'):
                    away_final = g.get('awayTeam', {}).get('score')
                    home_final = g.get('homeTeam', {}).get('score')
                    entry['awayFinal'] = away_final
                    entry['homeFinal'] = home_final
                    # OT/SO tag if present in the periodDescriptor-ish fields NHL exposes
                    ot = ''
                    if g.get('gameOutcome', {}).get('lastPeriodType') in ('OT', 'SO'):
                        ot = g['gameOutcome']['lastPeriodType']
                    entry['ot'] = ot
                    # Pull the goals[] breakdown, if present in this payload, for 1P score
                    goals = g.get('goals')
                    if goals is not None:
                        away_p1, home_p1 = first_period_score(goals)
                        entry['awayP1'] = away_p1
                        entry['homeP1'] = home_p1
                day_games.append(entry)

            expected = game_counts[date_str]
            if expected and not day_games and not debug_logged:
                # The count came through but no game entries did -- log the
                # raw shape of this one day object so we can see exactly what
                # key names the API is actually using right now, instead of
                # guessing. Only once, so a real run's log isn't flooded.
                print(f"DEBUG: {date_str} reports {expected} games but the "
                      f"'games' list came back empty. Raw day object keys: "
                      f"{sorted(day.keys())}", file=sys.stderr)
                sample = day.get('games')
                print(f"DEBUG: day['games'] raw value (truncated): "
                      f"{json.dumps(sample)[:1500]}", file=sys.stderr)
                debug_logged = True

            games_by_date[date_str] = day_games

    # Some completed games' /v1/score/{date} payload doesn't include a full
    # goals[] breakdown -- backfill 1P scores for those via the per-game
    # landing endpoint.
    for date_str, day_games in games_by_date.items():
        for entry in day_games:
            if entry.get('state') in ('FINAL', 'OFF') and 'awayP1' not in entry:
                landing = fetch_json(f'https://api-web.nhle.com/v1/gamecenter/{entry["id"]}/landing')
                if not landing:
                    continue
                periods = (landing.get('summary') or {}).get('scoring') or []
                away_p1 = home_p1 = 0
                for p in periods:
                    if p.get('periodDescriptor', {}).get('number') == 1:
                        away_p1 = p.get('awayScore', 0)
                        home_p1 = p.get('homeScore', 0)
                        break
                entry['awayP1'] = away_p1
                entry['homeP1'] = home_p1

    out = {'gameCounts': game_counts, 'games': games_by_date}
    with open('schedule_fresh.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    total_games = sum(len(v) for v in games_by_date.values())
    print(f"wrote schedule_fresh.json: {len(game_counts)} dated counts, {total_games} games")


if __name__ == '__main__':
    main()
