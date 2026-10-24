"""
Tests for scripts/picks.py (Today's Picks: outcomes, units, confidence,
tiers, and freezing plays at kickoff).

  python3 -m unittest discover tests
"""
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import picks as pk  # noqa: E402


class OutcomeTest(unittest.TestCase):
    def test_moneyline_tie_is_a_push(self):
        self.assertEqual(pk.outcome('ml', 'away', None, (1, 0)), 'W')
        self.assertEqual(pk.outcome('ml', 'home', None, (1, 0)), 'L')
        self.assertEqual(pk.outcome('ml', 'home', None, (0, 0)), 'P')

    def test_spread_uses_the_bet_sides_line(self):
        self.assertEqual(pk.outcome('ats', 'home', -3.5, (3, 7)), 'W')    # home by 4 covers -3.5
        self.assertEqual(pk.outcome('ats', 'home', -3, (3, 6)), 'P')
        self.assertEqual(pk.outcome('ats', 'away', 3.5, (3, 7)), 'L')

    def test_totals_and_btts(self):
        self.assertEqual(pk.outcome('total', 'under', 10.5, (7, 3)), 'W')
        self.assertEqual(pk.outcome('total', 'over', 10, (7, 3)), 'P')
        self.assertEqual(pk.outcome('btts', 'yes', None, (1, 1)), 'W')
        self.assertEqual(pk.outcome('btts', 'no', None, (2, 0)), 'W')

    def test_units_at_the_saved_price_else_minus_110(self):
        self.assertAlmostEqual(pk.units('W', 150), 1.5)
        self.assertAlmostEqual(pk.units('W', None), 0.9091, places=4)
        self.assertEqual(pk.units('L', -200), -1.0)
        self.assertEqual(pk.units('P', -110), 0.0)


class ConfidenceTest(unittest.TestCase):
    def test_small_samples_move_less(self):
        small = [{'label': 'x', 'season': True, 'w': 3, 'l': 0, 'p': 0}]
        big = [{'label': 'x', 'season': True, 'w': 30, 'l': 0, 'p': 0}]
        self.assertLess(pk.confidence(small)[0], pk.confidence(big)[0])

    def test_moneyline_is_head_to_head(self):
        team = [{'label': 'A 1P ML, season', 'season': True, 'w': 7, 'l': 3, 'p': 0}]
        weak_opp = team + [{'label': None, 'opp': True, 'w': 2, 'l': 8, 'p': 0}]
        strong_opp = team + [{'label': None, 'opp': True, 'w': 8, 'l': 2, 'p': 0}]
        self.assertGreater(pk.confidence(weak_opp)[0], 0.5)
        self.assertLess(pk.confidence(strong_opp)[0], pk.confidence(weak_opp)[0])

    def test_tiers(self):
        self.assertEqual(pk.tier_of(0.08, 20, True), 'A')
        self.assertEqual(pk.tier_of(0.08, 20, False), 'B')     # no saved price: B at most
        self.assertEqual(pk.tier_of(0.08, 6, True), 'C')       # small sample: C at most
        self.assertEqual(pk.tier_of(0.035, 30, True), 'C')


class LogTest(unittest.TestCase):
    def setUp(self):
        self._path = pk.LOG_PATH
        pk.LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_picks_log_test.json')

    def tearDown(self):
        if os.path.exists(pk.LOG_PATH):
            os.remove(pk.LOG_PATH)
        pk.LOG_PATH = self._path

    def play(self, start, edge):
        return {'id': 'nhl|1|1p|ml|away', 'game': 'nhl|1', 'start': start, 'edge': edge, 'seg': '1p',
                'market': 'ml', 'side': 'away', 'line': None, 'price': 120, 'status': 'pending', 'units': None}

    def game(self, state, sc):
        return {'key': 'nhl|1', 'state': state, 'segs': {'1p': {'sc': sc}}}

    def test_frozen_at_kickoff_then_graded(self):
        before = datetime(2026, 10, 24, 22, 0, tzinfo=timezone.utc)
        log = pk.update_log([self.game('pre', None)], [self.play('2026-10-24T23:00Z', 0.05)], before)
        self.assertEqual(log['2026-10-24']['plays'][0]['edge'], 0.05)
        after = datetime(2026, 10, 24, 23, 30, tzinfo=timezone.utc)
        # a changed play after kickoff is ignored; the logged one stays
        log = pk.update_log([self.game('in', None)], [self.play('2026-10-24T23:00Z', 0.09)], after)
        self.assertEqual(log['2026-10-24']['plays'][0]['edge'], 0.05)
        done = datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)
        log = pk.update_log([self.game('final', (2, 1))], [], done)
        p = log['2026-10-24']['plays'][0]
        self.assertEqual((p['status'], p['units']), ('W', 1.2))


if __name__ == '__main__':
    unittest.main()
