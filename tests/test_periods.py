"""
Tests for scripts/periods.py (NHL per-period scores from the goal list).

  python3 -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import periods as p  # noqa: E402


def score_goals(*running):
    """/v1/score goals[]: (period, awayScore, homeScore) running score after each goal."""
    return [{'period': per, 'periodDescriptor': {'number': per}, 'awayScore': a, 'homeScore': h} for per, a, h in running]


def landing(*running):
    """/v1/gamecenter/{id}/landing: goals grouped by period, no period-level score."""
    by = {}
    for per, a, h in running:
        by.setdefault(per, []).append({'awayScore': a, 'homeScore': h})
    return {'summary': {'scoring': [{'periodDescriptor': {'number': n}, 'goals': by.get(n, [])} for n in range(1, 6)]}}


class ParseTest(unittest.TestCase):
    def test_regulation(self):
        # UTA @ BOS, Oct 8: 0-3, 0-3, 1-0 -> 1-6
        g = p.goals_from_score(score_goals((1, 0, 1), (1, 0, 2), (1, 0, 3), (2, 0, 4), (2, 0, 5), (2, 0, 6), (3, 1, 6)))
        f, err = p.parse(g, 1, 6, '')
        self.assertIsNone(err)
        self.assertEqual(f, {'awayP1': 0, 'homeP1': 3, 'awayP2': 0, 'homeP2': 3, 'awayP3': 1, 'homeP3': 0, 'firstGoal2P': 'home',
                             'firstGoal': 'home'})

    def test_overtime(self):
        # SJ @ STL: 0-1, 1-0, 1-1, OT winner -> 3-2
        g = p.goals_from_score(score_goals((1, 0, 1), (2, 1, 1), (3, 2, 1), (3, 2, 2), (4, 3, 2)))
        f, err = p.parse(g, 3, 2, 'OT')
        self.assertIsNone(err)
        self.assertEqual((f['awayP2'], f['homeP2'], f['awayP3'], f['homeP3'], f['firstGoal2P']), (1, 0, 1, 1, 'away'))

    def test_shootout(self):
        # TOR @ VGK: 3-1, 0-2, 0-0, SO -> 3-4 (the shootout winner counts as one goal)
        run = ((1, 1, 0), (1, 2, 0), (1, 3, 0), (1, 3, 1), (2, 3, 2), (2, 3, 3), (5, 3, 4))
        f, err = p.parse(p.goals_from_score(score_goals(*run)), 3, 4, 'SO')
        self.assertIsNone(err)
        self.assertEqual(f, {'awayP1': 3, 'homeP1': 1, 'awayP2': 0, 'homeP2': 2, 'awayP3': 0, 'homeP3': 0, 'firstGoal2P': 'home',
                             'firstGoal': 'away'})
        # the landing summary gives the same answer
        self.assertEqual(p.parse(p.goals_from_landing(landing(*run)), 3, 4, 'SO'), (f, None))

    def test_first_goal_ignores_the_shootout(self):
        g = p.goals_from_score(score_goals((5, 0, 1)))
        f, err = p.parse(g, 0, 1, 'SO')
        self.assertIsNone(err)
        self.assertIsNone(f['firstGoal'])

    def test_no_second_period_goals(self):
        g = p.goals_from_score(score_goals((1, 1, 0), (3, 1, 1), (3, 2, 1)))
        f, err = p.parse(g, 2, 1, '')
        self.assertIsNone(err)
        self.assertEqual((f['awayP2'], f['homeP2'], f['firstGoal2P']), (0, 0, None))
        self.assertEqual((f['awayP3'], f['homeP3']), (1, 1))

    def test_fails_sanity_rule(self):
        # a goal missing from the list: periods add to 2-1 but the final is 3-1
        g = p.goals_from_score(score_goals((1, 1, 0), (2, 1, 1), (3, 2, 1)))
        f, err = p.parse(g, 3, 1, '')
        self.assertIn('!= final', err)
        self.assertEqual((f['awayP1'], f['homeP1']), (1, 0))
        self.assertTrue(all(f[k] is None for k in p.PERIOD_FIELDS))
        # an OT game whose final is more than one goal past regulation
        f, err = p.parse(p.goals_from_score(score_goals((1, 1, 0), (3, 1, 1))), 3, 1, 'OT')
        self.assertIn('not 1', err)
        self.assertIsNone(f['awayP2'])

    def test_landing_has_no_period_score(self):
        # the old fallback read awayScore/homeScore off the period entry,
        # which the landing doesn't have -- 1P must come from the goals
        L = landing((1, 0, 1), (1, 1, 1), (2, 1, 2))
        self.assertNotIn('awayScore', L['summary']['scoring'][0])
        f, err = p.parse(p.goals_from_landing(L), 1, 2, '')
        self.assertEqual((f['awayP1'], f['homeP1']), (1, 1))
        self.assertIsNone(err)


if __name__ == '__main__':
    unittest.main()
