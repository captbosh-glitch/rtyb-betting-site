"""
Pull NHL 1st-period "both teams to score" (BTTS) prices from the
SportsGameOdds API and write odds_sportsgameodds.json, keyed the same way as
odds_theoddsapi.json ("YYYY-MM-DD|AWAY|HOME") so build_site.py can merge both
odds sources onto the same game card.

Requires env var SPORTSGAMEODDS_API_KEY (set as a GitHub Actions repo secret
-- never written to a file or committed). Auth uses the `apiKey` query
parameter (confirmed working against a real key/response; the X-Api-Key
header this script used previously returned 403 Forbidden for this key).
The key is never printed: fetch_json() only logs the exception object on
failure, never the request URL, so it can't leak into the public Actions
run log even though it's embedded in the URL for the request itself.

IMPORTANT -- read before trusting this blindly:
SportsGameOdds' public docs confirm the oddID pattern
  {statID}-{statEntityID}-{periodID}-{betTypeID}-{sideID}
and that hockey period scoping uses periodID "1p" for the 1st period, but
their docs page does NOT spell out the exact statID SportsGameOdds uses for
"both teams to score" -- it wasn't in anything fetchable at build time. So
this script does NOT hardcode a guessed statID. Instead it scans each
event's odds dict defensively for any oddID whose period token is 1st-period
AND whose stat token looks BTTS-shaped (case-insensitive match against
BTTS_STAT_HINTS below), and logs every odds key it saw for events it
couldn't match, so the first real GitHub Actions run's log output tells you
definitively which key to lock in. Update BTTS_STAT_HINTS (or hardcode the
confirmed statID) once you've seen a real response.
"""
import json
import os
import sys
import urllib.request
import urllib.error

API_KEY = os.environ.get('SPORTSGAMEODDS_API_KEY', '').strip()
BASE = 'https://api.sportsgameodds.com/v2/events'

ABBREV_MAP = {'TBL': 'TB', 'MTL': 'MON', 'NJD': 'NJ', 'SJS': 'SJ', 'LAK': 'LA'}

# Case-insensitive substrings that would plausibly appear in a BTTS statID.
BTTS_STAT_HINTS = ('bothteamsscore', 'bothtoscore', 'btts', 'bothscore')
PERIOD_1ST_TOKENS = ('1p',)  # hockey 1st period, per SportsGameOdds docs


def fetch_json(url, headers):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"WARN: SportsGameOdds request failed: {e}", file=sys.stderr)
        return None


def team_abbrev(name_or_code):
    code = (name_or_code or '')[:3].upper()
    return ABBREV_MAP.get(code, code)


def looks_like_btts_1p(odd_id):
    parts = odd_id.lower().split('-')
    if len(parts) < 5:
        return False
    stat_id, _entity, period_id, _bet_type, _side = parts[0], parts[1], parts[2], parts[3], parts[4]
    if period_id not in PERIOD_1ST_TOKENS:
        return False
    return any(hint in stat_id for hint in BTTS_STAT_HINTS)


def main():
    if not API_KEY:
        print("WARN: SPORTSGAMEODDS_API_KEY not set -- writing empty odds_sportsgameodds.json", file=sys.stderr)
        json.dump({}, open('odds_sportsgameodds.json', 'w'))
        return

    url = BASE + f'?apiKey={API_KEY}&leagueID=NHL&oddsAvailable=true&limit=50'
    data = fetch_json(url, headers={})
    if not data:
        json.dump({}, open('odds_sportsgameodds.json', 'w'))
        return

    events = data.get('data', data if isinstance(data, list) else [])
    out = {}
    unmatched_sample_logged = False

    for event in events:
        teams = event.get('teams', {})
        away = team_abbrev((teams.get('away') or {}).get('names', {}).get('short')
                            or (teams.get('away') or {}).get('teamID', ''))
        home = team_abbrev((teams.get('home') or {}).get('names', {}).get('short')
                            or (teams.get('home') or {}).get('teamID', ''))
        start = event.get('status', {}).get('startsAt') or event.get('startsAt', '')
        date_str = start[:10] if start else ''
        key = f'{date_str}|{away}|{home}'

        odds = event.get('odds', {}) or {}
        yes_price = None
        for odd_id, odd in odds.items():
            if looks_like_btts_1p(odd_id) and odd_id.lower().endswith('-yes'):
                yes_price = odd.get('bookOdds') or odd.get('fairOdds') or odd.get('odds')
                break

        if yes_price is not None:
            out[key] = {'btts_yes': yes_price}
        elif odds and not unmatched_sample_logged:
            # Log a sample of real oddID keys once, so a human can read the
            # Actions run log and tell us the correct BTTS statID to hardcode.
            sample = list(odds.keys())[:25]
            print(f"INFO: no BTTS-1P oddID matched for {key}. Sample oddIDs seen: {sample}", file=sys.stderr)
            unmatched_sample_logged = True

    with open('odds_sportsgameodds.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, separators=(',', ':'))
    print(f"wrote odds_sportsgameodds.json: {len(out)} events matched BTTS-1P")


if __name__ == '__main__':
    main()
