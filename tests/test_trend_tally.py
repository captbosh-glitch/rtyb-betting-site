"""
Trend strength and the daily record (scripts/trend_rules.py): a label
needs both an edge and profit per bet, and a bet two trends point at
counts once in the record and says "2 trends agree".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import trend_rules  # noqa: E402


def trend(z, units, priced, picks):
    return {'z': z, 'units': units, 'priced': priced, 'n': priced, 'games': picks}


class LabelTest(unittest.TestCase):
    def test_needs_edge_and_profit(self):
        self.assertEqual(trend_rules.label(2.5, 12.0, 100), 'strong')     # +0.12u a bet
        self.assertEqual(trend_rules.label(2.5, 6.0, 100), 'moderate')    # big edge, +0.06u
        self.assertEqual(trend_rules.label(2.5, 1.0, 100), 'weak')        # big edge, +0.01u
        self.assertEqual(trend_rules.label(0.8, 30.0, 100), 'weak')       # profit, no edge

    def test_no_prices_goes_by_strength(self):
        self.assertEqual(trend_rules.label(2.1), 'strong')
        self.assertEqual(trend_rules.label(1.2, None, 0), 'moderate')


class SlateTest(unittest.TestCase):
    def test_shared_bet_counts_once(self):
        over = lambda: {'key': 'g1', 'market': 'O1.5', 'status': 'W'}
        entry = {'trends': [
            trend(2.5, 15.0, 100, [over(), {'key': 'g2', 'market': 'O1.5', 'status': 'L'}]),
            trend(1.5, 8.0, 100, [over()]),
            trend(0.5, 1.0, 100, [{'key': 'g3', 'market': 'O1.5', 'status': 'W'}]),   # weak: not a bet
        ]}
        trend_rules.finish_slate(entry, lambda p: (p['key'], p['market']))
        self.assertEqual(entry['record'], {'w': 1, 'l': 1})
        self.assertEqual(entry['trends'][0]['games'][0]['agree'], 2)
        self.assertEqual(entry['trends'][1]['games'][0]['agree'], 2)
        self.assertEqual(entry['trends'][0]['games'][1]['agree'], 1)
        self.assertNotIn('agree', entry['trends'][2]['games'][0])
        self.assertEqual([t['strength'] for t in entry['trends']], ['strong', 'moderate', 'weak'])


if __name__ == '__main__':
    unittest.main()
