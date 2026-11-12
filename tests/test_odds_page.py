"""Odds page data: the segment score shown next to each team once a game
starts (sport_build.seg_scores), and the backfill's merge into the per-day
history (backfill_odds_history.fill): rows the live feed archived win."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import backfill_odds_history  # noqa: E402
import sport_build  # noqa: E402
import sports  # noqa: E402


class SegScoresTest(unittest.TestCase):
    def test_quarters_and_halves_so_far(self):
        g = {'als': [29, 25, 30], 'hls': [38, 23, 20]}
        self.assertEqual(sport_build.seg_scores(sports.BY_KEY['nba'], g), {'1q': [29, 38], '1h': [54, 61]})

    def test_live_first_quarter(self):
        self.assertEqual(sport_build.seg_scores(sports.BY_KEY['nba'], {'als': [12], 'hls': [9]}), {'1q': [12, 9], '1h': [12, 9]})

    def test_ncaab_half_is_period_one(self):
        self.assertEqual(sport_build.seg_scores(sports.BY_KEY['ncaab'], {'als': [30, 40], 'hls': [28, 35]}), {'1h': [30, 28]})

    def test_not_started(self):
        self.assertIsNone(sport_build.seg_scores(sports.BY_KEY['nba'], {'als': [], 'hls': []}))


class BackfillTest(unittest.TestCase):
    def test_archived_rows_win(self):
        have = {'1q': {'ats': {'1': {'away': {'line': -1.5, 'price': -110}}}}}
        add = {'1q': {'ats': {'1': {'away': {'line': -2.5, 'price': -105}}, '2': {'away': {'line': -1.5, 'price': -108}}}},
               '1h': {'ml': {'1': {'away': {'price': 120}}}}}
        out = backfill_odds_history.fill(have, add)
        self.assertEqual(out['1q']['ats']['1']['away']['line'], -1.5)
        self.assertIn('2', out['1q']['ats'])
        self.assertIn('1h', out)

    def test_links_dropped(self):
        self.assertEqual(backfill_odds_history.unlinked({'away': {'price': 100, 'link': 'x'}}), {'away': {'price': 100}})


if __name__ == '__main__':
    unittest.main()
