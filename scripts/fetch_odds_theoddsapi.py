"""
Pull NHL 1st-period Moneyline (h2h_p1) and Totals (totals_p1, at the 0.5/1.5/2.5
lines) from The Odds API and write odds_theoddsapi.json, keyed by a
(away, home, date) match against schedule_data.json so build_site.py can join
prices onto the right game card.

Requires env var ODDS_API_KEY (set as a GitHub Actions repo secret -- never
written to a file or committed). The Odds API does NOT offer a BTTS market
for hockey at all (soccer only) -- that gap is filled by
fetch_odds_sportsgameodds.py instead.

If the key is missing or the request fails, this script writes an empty
result rather than raising, so the site still builds (with odds cells
showing "--") instead of the whole pipeline breaking.
"""
import json
import os
import sys
import urllib.request
import urllib.error

API_KEY = os.environ.get('ODDS_API_KEY', '').strip()
BASE = 'https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds'

ABBREV_MAP = {'TBL': 'TB', 'MTL': 'MON', 'NJD': 'NJ', 'SJS': 'SJ', 'LAK': 'LA'}
TEAM_NAME_TO_ABBREV = {
    'Anaheim Ducks': 'ANH', 'Boston Bruins': 'BOS', 'Buffalo Sabres': 'BUF',
    'Calgary Flames': 'CGY', 'Carolina Hurricanes': 'CAR', 'Chicago Blackhawks': 'CHI',
    'Colorado Avalanche': 'COL', 'Columbus Blue Jackets': 'CBJ', 'Dallas Stars': 'DAL',
    'Detroit Red Wings': 'DET', 'Edmonton Oilers': 'EDM', 'Florida Panthers': 'FLA',
    'Los Angeles Kings': 'LA', 'Minnesota Wild': 'MIN', 'Montreal Canadiens': 'MON',
    'Nashville Predators': 'NSH', 'New Jersey Devils': 'NJ', 'New York Islanders': 'NYI',
    'New York Rangers': 'NYR', 'Ottawa Senators': 'OTT', 'Philadelphia Flyers': 'PHI',
    'Pittsburgh Penguins': 'PIT', 'San Jose Sharks': 'SJ', 'Seattle Kraken': 'SEA',
    'St Louis Blues': 'STL', 'St. Louis Blues': 'STL', 'Tampa Bay Lightning': 'TB',
    'Toronto Maple Leafs': 'TOR', 'Utah Mammoth': 'UTA', 'Vancouver Canucks': 'VAN',
    'Vegas Golden Knights': 'VGK', 'Washington Capitals': 'WSH', 'Winnipeg Jets': 'WPG',
}


def team_abbrev(name):
    return TEAM_NAME_TO_ABBREV.get(name, name[:3].upper())


def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'rtyb-fetch/1.0'})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"WARN: The Odds API request failed: {e}", file=sys.stderr)
        return None


def main():
    if not API_KEY:
        print("WARN: ODDS_API_KEY not set -- writing empty odds_theoddsapi.json", file=sys.stderr)
        json.dump({}, open('odds_theoddsapi.json', 'w'))
        return

    params = (
        f'?apiKey={API_KEY}'
        '&regions=us'
        '&markets=h2h_p1,totals_p1'
        '&oddsFormat=american'
        '&dateFormat=iso'
    )
    data = fetch_json(BASE + params)
    if not data:
        json.dump({}, open('odds_theoddsapi.json', 'w'))
        return

    out = {}
    for event in data:
        away = team_abbrev(event.get('away_team', ''))
        home = team_abbrev(event.get('home_team', ''))
        commence = event.get('commence_time', '')
        date_str = commence[:10] if commence else ''
        key = f'{date_str}|{away}|{home}'

        entry = {'ml': {}, 'totals': {}}
        for book in event.get('bookmakers', []):
            for market in book.get('markets', []):
                mkey = market.get('key')
                if mkey == 'h2h_p1':
                    for outcome in market.get('outcomes', []):
                        team = team_abbrev(outcome.get('name', ''))
                        if team not in entry['ml']:
                            entry['ml'][team] = outcome.get('price')
                elif mkey == 'totals_p1':
                    for outcome in market.get('outcomes', []):
                        point = outcome.get('point')
                        side = outcome.get('name', '').lower()  # "Over" / "Under"
                        line_key = str(point)
                        entry['totals'].setdefault(line_key, {})
                        if side not in entry['totals'][line_key]:
                            entry['totals'][line_key][side] = outcome.get('price')
            # first bookmaker with data wins per event -- good enough for a
            # single reference price; revisit if consensus/median is wanted later
            if entry['ml'] or entry['totals']:
                break

        out[key] = entry

    with open('odds_theoddsapi.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f"wrote odds_theoddsapi.json: {len(out)} events")


if __name__ == '__main__':
    main()
