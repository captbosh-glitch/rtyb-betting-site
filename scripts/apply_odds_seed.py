"""
One-off: merge the real odds from your RTYB spreadsheet (Sept 29 - Oct 1,
16 games -- the ones that already had numbers filled in) into your live
odds_theoddsapi.json / odds_sportsgameodds.json, WITHOUT touching anything
else already in those files.

Why a merge instead of just overwriting the two files with the seed data:
odds_theoddsapi.json / odds_sportsgameodds.json are the live pipeline's
fetch output, re-fetched and REPLACED wholesale by the real API scripts on
every scheduled run. If they currently hold odds for other games/dates
(from a real API key already in use), dropping the seed files straight in
as a replacement would silently wipe those out. This merges by the
"date|away|home" key instead -- only the 16 games from the spreadsheet are
added/overwritten; everything else already in the files is left alone.

Run this ONCE, from the repo root:

    python3 scripts/apply_odds_seed.py
    python3 scripts/build_site.py

Then check nhl/games/ for Sept 29, Sept 30, and Oct 1 -- those 16 games
should now show the real moneyline/total/BTTS pills instead of a dash.
Oct 2-4 are deliberately left out (no odds in the spreadsheet yet for
those days), so you can also confirm the "future day, no odds published"
empty-pill state looks right.

This script's seed data was read once from the spreadsheet you sent
(RTYB - NHL.xlsx) and is static from here on -- re-running it is always
safe/idempotent (it just re-applies the same 16 entries), but it will NOT
pick up any further edits you make to that spreadsheet. For ongoing odds
updates you'll want the Admin Matchups Tool (next up).
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
    ml_seed = load('data_seed/odds_theoddsapi_seed.json', {})
    btts_seed = load('data_seed/odds_sportsgameodds_seed.json', {})

    ml_live = load('odds_theoddsapi.json', {})
    btts_live = load('odds_sportsgameodds.json', {})

    ml_live.update(ml_seed)
    btts_live.update(btts_seed)

    with open(os.path.join(ROOT, 'odds_theoddsapi.json'), 'w', encoding='utf-8') as f:
        json.dump(ml_live, f, separators=(',', ':'))
    with open(os.path.join(ROOT, 'odds_sportsgameodds.json'), 'w', encoding='utf-8') as f:
        json.dump(btts_live, f, separators=(',', ':'))

    print(f"Merged {len(ml_seed)} ML/Totals entries and {len(btts_seed)} BTTS entries "
          f"into odds_theoddsapi.json ({len(ml_live)} total) and "
          f"odds_sportsgameodds.json ({len(btts_live)} total).")


if __name__ == '__main__':
    main()
