"""
One-off: rebuild the Odds page's past days from git history.

data_feed/unabated/{sport}.json has been committed on every refresh since the
feed started (2026-11-05), each copy holding every source's current price on
the upcoming games. A game's books stop changing at its start (the feed
freezes it), so for each game:

  open   each source's price in the first committed copy that had it
  close  each source's price in the last committed copy that had it

are merged into data_feed/unabated/history/{sport}/{date}.json, the per-day
history the Odds page reads (sport_build.write_odds_page). Rows the live feed
already archived (fetch_odds_unabated.archive_started) win; the backfill only
fills sources, markets and games they're missing. Links are dropped, and the
3-way moneyline is kept for NHL only.

    python3 scripts/backfill_odds_history.py [sport ...]
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
from fetch_odds_unabated import parse_time, write_json  # noqa: E402
FEED = 'data_feed/unabated'
SPORTS = ('nhl', 'nba', 'wnba', 'mlb', 'ncaab', 'nfl', 'ncaaf')


def git(*args):
    return subprocess.run(['git', '-C', ROOT] + list(args), capture_output=True, text=True, check=True).stdout


def unlinked(row):
    if isinstance(row, dict):
        return {k: unlinked(v) for k, v in row.items() if k != 'link'}
    return row


def snapshots(path):
    """Each committed copy of a feed file, oldest first."""
    for sha in git('log', '--reverse', '--format=%H', '--', path).split():
        try:
            yield json.loads(git('show', f'{sha}:{path}'))
        except (subprocess.CalledProcessError, ValueError):
            continue


def collect(sport):
    """{(date, away, home): {start, open, close}} from every committed copy."""
    out = {}
    for doc in snapshots(f'{FEED}/{sport}.json'):
        for g in (doc.get('games') or {}).values():
            if not g.get('books') and not g.get('opens'):
                continue
            rec = out.setdefault((g['date'], g['away'], g['home']), {'start': g.get('start'), 'open': {}, 'close': {}})
            rec['start'] = g.get('start') or rec['start']
            for src, into, first in ((g.get('opens'), 'open', True), (g.get('books'), 'open', True), (g.get('books'), 'close', False)):
                for seg, mk in (src or {}).items():
                    for m, by in mk.items():
                        if m == 'ml3' and sport != 'nhl':
                            continue
                        slot = rec[into].setdefault(seg, {}).setdefault(m, {})
                        for b, row in (by or {}).items():
                            if not first or b not in slot:
                                slot[b] = unlinked(row)
    return out


def fill(have, add):
    """`have` with whatever `add` has that it doesn't (per segment, market, source)."""
    out = {seg: {m: dict(by) for m, by in mk.items()} for seg, mk in (have or {}).items()}
    for seg, mk in add.items():
        for m, by in mk.items():
            slot = out.setdefault(seg, {}).setdefault(m, {})
            for b, row in by.items():
                slot.setdefault(b, row)
    return out


def main():
    want = sys.argv[1:] or SPORTS
    now = datetime.now(timezone.utc)
    for sport in want:
        # games that haven't started stay on the live feed
        found = {k: v for k, v in collect(sport).items() if (parse_time(v['start']) or now) < now}
        by_date = {}
        for (d, a, h), rec in found.items():
            by_date.setdefault(d, {})[f'{a}|{h}'] = dict(rec, away=a, home=h)
        days = 0
        for d, games in sorted(by_date.items()):
            path = os.path.join(ROOT, FEED, 'history', sport, f'{d}.json')
            try:
                with open(path, encoding='utf-8') as f:
                    doc = json.load(f)
            except (OSError, ValueError):
                doc = {'games': {}}
            for key, rec in games.items():
                row = doc['games'].setdefault(key, {'away': rec['away'], 'home': rec['home']})
                row['start'] = row.get('start') or rec['start']
                row['open'] = fill(row.get('open'), rec['open'])
                row['close'] = fill(row.get('close'), rec['close'])
            write_json(path, doc)
            days += 1
        first = min(by_date) if by_date else None
        print(f'{sport}: {len(found)} games over {days} days, first {first}')


if __name__ == '__main__':
    main()
