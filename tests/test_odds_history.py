"""
fetch_odds_unabated: every source's first price (opens) is noted, and when
a game starts its opens and closing lines move to history/{sport}/{date}.json
without links.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import fetch_odds_unabated as F  # noqa: E402

LINK = 'https://www.gambly.com/deeplink/odds/1/99/_?utm_campaign=rtyb'


def ml(away, home):
    return {'away': {'price': away, 'link': LINK}, 'home': {'price': home, 'link': LINK}}


class History(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = F.HISTORY_DIR
        F.HISTORY_DIR = self.tmp.name

    def tearDown(self):
        F.HISTORY_DIR = self.old
        self.tmp.cleanup()

    def test_opens_keep_first_price(self):
        rec = {}
        F.note_opens(rec, '1p', 'ml', {'1': ml(-120, 100)})
        F.note_opens(rec, '1p', 'ml', {'1': ml(-130, 110), '2': ml(-125, 105)})
        self.assertEqual(rec['opens']['1p']['ml']['1'], {'away': {'price': -120}, 'home': {'price': 100}})
        self.assertEqual(rec['opens']['1p']['ml']['2']['away']['price'], -125)

    def test_started_game_moves_to_history(self):
        games = {
            '2026-11-10|BOS|TOR': {'date': '2026-11-10', 'away': 'BOS', 'home': 'TOR', 'start': '2026-11-11T00:00:00Z',
                                   'books': {'1p': {'ml': {'1': ml(-130, 110)}}},
                                   'opens': {'1p': {'ml': {'1': {'away': {'price': -120}, 'home': {'price': 100}}}}}},
            '2026-11-11|NYR|PHI': {'date': '2026-11-11', 'away': 'NYR', 'home': 'PHI', 'start': '2026-11-12T00:00:00Z',
                                   'books': {'1p': {'ml': {'1': ml(-110, -110)}}}},
        }
        now = datetime(2026, 11, 11, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(F.archive_started('nhl', games, now), 1)
        with open(os.path.join(self.tmp.name, 'nhl', '2026-11-10.json')) as f:
            row = json.load(f)['games']['BOS|TOR']
        self.assertEqual(row['close']['1p']['ml']['1'], {'away': {'price': -130}, 'home': {'price': 110}})
        self.assertEqual(row['open']['1p']['ml']['1']['away']['price'], -120)
        self.assertNotIn('books', games['2026-11-10|BOS|TOR'])
        self.assertIn('books', games['2026-11-11|NYR|PHI'])   # not started yet



class Logos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = (F.LOGO_DIR, F.LOGO_MANIFEST)
        F.LOGO_DIR = self.tmp.name
        F.LOGO_MANIFEST = os.path.join(self.tmp.name, 'sources.json')
        self.calls = []

    def tearDown(self):
        F.LOGO_DIR, F.LOGO_MANIFEST = self.old
        self.tmp.cleanup()

    def fetch(self, url):
        self.calls.append(url)
        return b'img'

    def test_new_changed_and_daily(self):
        src = [{'id': 1, 'name': 'DraftKings', 'modifiedOn': 'a', 'thumbnailUrl': 'https://x/t/dk.webp'},
               {'id': 80, 'name': 'BetMGM Direct'}]
        day1 = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
        self.assertEqual(F.download_logos(src, day1, self.fetch), 1)
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, '1.webp')))
        self.assertEqual(F.download_logos(src, day1, self.fetch), 0)          # checked today already
        day2 = datetime(2026, 11, 12, 13, tzinfo=timezone.utc)
        self.assertEqual(F.download_logos(src, day2, self.fetch), 0)          # unchanged
        src[0].update(modifiedOn='b', thumbnailUrl='https://x/t/dk.png')
        day3 = datetime(2026, 11, 13, 14, tzinfo=timezone.utc)
        self.assertEqual(F.download_logos(src, day3, self.fetch), 1)          # changed: new file replaces the old
        self.assertTrue(os.path.exists(os.path.join(self.tmp.name, '1.png')))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, '1.webp')))
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
