"""NHL games in the shared sport shape (scripts/nhl_sport.py), read by the
Stats page in assets/sport.js."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import nhl_sport  # noqa: E402

GAME = {'id': 1, 'away': 'NJ', 'home': 'WPG', 'startTimeUTC': '2026-11-11T00:00:00Z', 'state': 'FINAL',
        'awayFinal': 2, 'homeFinal': 4, 'ot': '', 'awayP1': 1, 'homeP1': 1, 'awayP2': 1, 'homeP2': 0,
        'awayP3': 0, 'homeP3': 3, 'firstGoal': 'home', 'fgMl': {'away': -142, 'home': 120},
        'odds': {'ml3': {'away': 152, 'draw': 189, 'home': 208}, 'ml': {'NJ': -132, 'WPG': 115},
                 'totals': {'1.5': {'over': -140, 'under': 120}}, 'btts_yes': 170, 'btts_no': -225}}


class NhlSportTest(unittest.TestCase):
    def test_tied_first_period(self):
        g = nhl_sport.game(GAME, '2026-11-10')
        self.assertEqual(g['state'], 'final')
        self.assertEqual((g['as'], g['hs'], g['als'], g['hls']), (2, 4, [1, 1, 0], [1, 0, 3]))
        r = g['res']['1p']
        self.assertEqual((r['sc'], r['su'], r['tot'], r['btts']), ([1, 1], 'T', 'O', 'Y'))
        self.assertEqual(r['u']['su'], [0.0, 0.0])            # a tie is a push on the 2-way
        self.assertEqual(r['u']['ml3'], [-1.0, -1.0, 1.89])   # and wins the tie on the 3-way
        self.assertEqual(r['u']['tot'], [0.7143, -1.0])
        self.assertEqual(r['u']['btts'], [1.7, -1.0])
        self.assertEqual(g['odds']['1p']['ml'], {'away': -132, 'home': 115})
        self.assertEqual(g['fml'], {'away': -142, 'home': 120})

    def test_unplayed_game_has_no_result(self):
        g = nhl_sport.game({'id': 2, 'away': 'LA', 'home': 'TOR', 'startTimeUTC': '2026-11-20T00:00:00Z', 'state': 'FUT'}, '2026-11-19')
        self.assertEqual(g['state'], 'pre')
        self.assertNotIn('res', g)
        self.assertNotIn('odds', g)

    def test_live_first_period_score_so_far(self):
        live = {'id': 3, 'away': 'TB', 'home': 'BUF', 'startTimeUTC': '2026-11-12T00:00:00Z', 'state': 'LIVE',
                'awayFinal': 1, 'homeFinal': 0, 'period': 1, 'detail': '8:12 - 1st'}
        g = nhl_sport.game(live, '2026-11-11')
        self.assertEqual((g['state'], g['detail'], g['als'], g['hls']), ('in', '8:12 - 1st', [1], [0]))
        self.assertNotIn('res', g)   # not graded until the period ends
        g = nhl_sport.game(dict(live, period=2, awayFinal=3, awayP1=2, homeP1=0), '2026-11-11')
        self.assertEqual((g['als'], g['hls'], g['res']['1p']['sc']), ([2], [0], [2, 0]))

    def test_doc(self):
        d = nhl_sport.doc({'2026-09-30': [GAME], '2026-11-10': [GAME]}, '2026-10-01', '2026–27',
                          {'NJ': {'name': 'New Jersey Devils'}, 'CBJ': {'name': 'Columbus Blue Jackets'}},
                          {'Metropolitan': ['NJ', 'CBJ']}, {'NJ': '#CE1126'}, None, 'now')
        self.assertEqual(list(d['games']), ['2026-11-10'])   # this season only
        self.assertEqual(d['teams']['CBJ']['short'], 'Blue Jackets')
        self.assertEqual(d['teams']['NJ']['conference'], 'East')
        self.assertEqual(d['teams']['NJ']['color'], 'CE1126')
        self.assertEqual(d['segments'][0]['key'], '1p')


if __name__ == '__main__':
    unittest.main()
