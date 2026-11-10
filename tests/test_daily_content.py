"""
The Daily's drafts (scripts/daily_content.py): streaks extended or snapped
by last night's game, and the check that flags any number in a draft that
isn't in the packet Claude was given.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import daily_content as dc  # noqa: E402

LABELS = {'ml': {'W': 'won', 'L': 'lost'}}


class StreakTest(unittest.TestCase):
    def test_extended_and_snapped(self):
        seqs = {('BOS', 'ml'): ['L', 'W', 'W', 'W'], ('CHI', 'ml'): ['L', 'L', 'L', 'W'], ('NY', 'ml'): ['W', 'W']}
        got = dc.streak_changes(seqs, {'BOS', 'CHI', 'NY'}, LABELS)
        self.assertEqual([(x['team'], x['change'], x['streak']) for x in got],
                         [('BOS', 'extended', 'won 3 straight'), ('CHI', 'snapped', 'lost 3 straight')])

    def test_only_teams_that_played(self):
        self.assertEqual(dc.streak_changes({('BOS', 'ml'): ['W', 'W', 'W']}, set(), LABELS), [])


class NumberCheckTest(unittest.TestCase):
    def test_flags_numbers_not_in_packet(self):
        packet = {'price': -125, 'units': 0.8, 'streak': 'won 3 straight'}
        body = 'Boston won at -125 for +0.80u, 3 straight now, and trends went 9-4. 21+. Call 1-800-GAMBLER.'
        self.assertEqual(dc.unchecked_numbers(body, packet), ['9', '-4'])


if __name__ == '__main__':
    unittest.main()
