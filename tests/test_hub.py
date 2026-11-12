"""The Arena hub's Matchup of the Day (scripts/hub.py): the Trends page's
lean and streak rules, the bet's wording, and grading a logged pick."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import hub  # noqa: E402


def final(res):
    return {'state': 'final', 'res': {'1p': dict(res, sc=[1, 0])}}


class LeanStreakTest(unittest.TestCase):
    def test_lean_needs_ten_games_and_sixty_percent(self):
        self.assertIsNone(hub.lean_of('ats', ['W'] * 9))
        self.assertEqual(hub.lean_of('ats', ['W'] * 6 + ['L'] * 4)['kind'], 'W')
        self.assertIsNone(hub.lean_of('ats', ['W'] * 5 + ['L'] * 5))

    def test_moneyline_counts_ties_as_games(self):
        # 6 wins in 11 with a tie: 55%, no lean (the spread would leave a push out)
        self.assertIsNone(hub.lean_of('ml', ['W'] * 6 + ['L'] * 4 + ['T']))

    def test_streak_ends_on_tie(self):
        self.assertEqual(hub.streak_of(['L', 'W', 'W', 'W']), {'kind': 'W', 'n': 3})
        self.assertIsNone(hub.streak_of(['W', 'T']))


class GradeTest(unittest.TestCase):
    def test_sides_from_the_away_result(self):
        g = final({'su': 'L', 'ats': 'W'})
        self.assertEqual(hub.grade(g, '1p', 'ml', 'home'), 'W')
        self.assertEqual(hub.grade(g, '1p', 'ats', 'away'), 'W')

    def test_three_way_tie_loses_a_side(self):
        g = final({'su': 'T'})
        self.assertEqual(hub.grade(g, '1p', 'ml3', 'home'), 'L')
        self.assertEqual(hub.grade(g, '1p', 'ml', 'home'), 'P')

    def test_not_final(self):
        self.assertIsNone(hub.grade({'state': 'in', 'res': {}}, '1p', 'ml', 'home'))


if __name__ == '__main__':
    unittest.main()
