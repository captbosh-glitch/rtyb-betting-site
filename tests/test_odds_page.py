"""
The Odds page's RTYB badges (sport_build.odds_agree): only trends that
aren't weak, on bets still to play, count toward "N trends agree".
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import sport_build  # noqa: E402


def pick(key, kind, market, side=None, status='PENDING', seg='1q'):
    return {'key': key, 'kind': kind, 'market': market, 'side': side, 'status': status, 'seg': seg}


class OddsAgreeTest(unittest.TestCase):
    def where(self, p):
        return ('2026-11-10', 'mil', 'ny', p['seg'])

    def test_counts_non_weak_pending_picks(self):
        log = {'2026-11-10': {'trends': [
            {'kind': 'side', 'strength': 'strong', 'games': [pick('1', 'side', 'ats', 'away')]},
            {'kind': 'side', 'strength': 'moderate', 'games': [pick('1', 'side', 'ats', 'away')]},
            {'kind': 'side', 'strength': 'weak', 'games': [pick('1', 'side', 'ats', 'away')]},
            {'kind': 'side', 'strength': 'strong', 'games': [pick('1', 'side', 'su', 'home', status='LIVE')]},
            {'kind': 'game', 'strength': 'strong', 'games': [pick('1', 'game', 'over')]},
        ]}}
        got = sport_build.odds_agree(log, self.where)
        self.assertEqual(got, {('2026-11-10', 'mil', 'ny'): {'1q': {'ats': {'away': 2}, 'total': {'over': 1}}}})

    def test_nhl_total_tags(self):
        log = {'d': {'trends': [{'kind': 'game', 'strength': 'strong', 'games': [pick('k', 'game', 'U1.5', seg='1p')]}]}}
        got = sport_build.odds_agree(log, self.where)
        self.assertEqual(got[('2026-11-10', 'mil', 'ny')]['1p']['total'], {'under': 1})


if __name__ == '__main__':
    unittest.main()
