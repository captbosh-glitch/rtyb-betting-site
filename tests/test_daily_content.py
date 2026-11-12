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


class EverySportTest(unittest.TestCase):
    def test_titles_follow_the_sport(self):
        self.assertEqual(dc.title('recap', 'ncaab', '2026-11-12'), 'NCAAB First Half Betting Recap — Nov 12, 2026')
        self.assertEqual(dc.title('preview', 'nfl', '2026-11-12', {'week': 'Week 11'}),
                         'NFL First Quarter and First Half Betting Week 11 Preview — Nov 12, 2026')
        self.assertEqual(dc.title('recap', 'ncaaf', '2026-11-16'), 'NCAAF First Quarter and First Half Betting Weekend Recap — Nov 16, 2026')

    def test_football_is_weekly(self):
        self.assertEqual(dc.WEEKLY_WINDOWS['recap'][0], 0)     # Monday
        self.assertEqual(dc.WEEKLY_WINDOWS['preview'][:2], (3, 9))   # Thursday 9 AM ET
        self.assertTrue(dc.weekly('nfl') and dc.weekly('ncaaf') and not dc.weekly('nba'))

    def test_big_slates_keep_the_busiest_games_in_order(self):
        games = [{'trends_on_this_game': i % 4, 'streaks': []} for i in range(40)]
        got = dc.busiest(games)
        self.assertEqual(len(got), dc.PREVIEW_MAX)
        self.assertTrue(all(g['trends_on_this_game'] >= 2 for g in got))
        self.assertEqual(got, [g for g in games if any(g is x for x in got)])

    def test_preview_tease_has_no_records_or_prices(self):
        for kind in ('preview', 'week_preview'):
            self.assertIn('no records, hit rates, percentages, prices or specific bets', dc.TASK[kind])


if __name__ == '__main__':
    unittest.main()
