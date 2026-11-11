"""League Trends cards (scripts/trends.py), drawn by renderTrends in
assets/sport.js."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import sports  # noqa: E402
import trends  # noqa: E402

NHL = sports.BY_KEY['nhl']
TEAMS = {c: {'name': c, 'short': c, 'code': c} for c in ('AAA', 'BBB', 'CCC', 'DDD')}


def game(i, day, home_won):
    """A 1st period with the home side favored at -150."""
    sc = [0, 1] if home_won else [1, 0]
    away, home = ('AAA', 'BBB') if i % 2 else ('CCC', 'DDD')
    return {'id': i, 'start': f'2026-10-{day:02d}T23:00:00Z', 'state': 'final', 'away': away, 'home': home,
            'as': sc[0], 'hs': sc[1], 'odds': {'1p': {'ml': {'away': 130, 'home': -150}}},
            'res': {'1p': {'sc': sc, 'su': 'L' if home_won else 'W', 'tot': 'U', 'btts': 'N',
                           'u': {'su': [-1.0, 0.6667] if home_won else [1.3, -1.0]}}}}


def doc():
    games = {}
    for i in range(1, 25):   # home favorites go 18-6
        g = game(i, i, i % 4 != 0)
        games.setdefault(g['start'][:10], []).append(g)
    nxt = {'id': 99, 'start': '2026-10-30T23:00:00Z', 'state': 'pre', 'away': 'AAA', 'home': 'BBB',
           'odds': {'1p': {'ml': {'away': 130, 'home': -150}}}}
    games['2026-10-30'] = [nxt]
    return {'teams': TEAMS, 'games': games}


class ResultTest(unittest.TestCase):
    def test_tied_period(self):
        g = {'res': {'1p': {'sc': [1, 1], 'su': 'T', 'tot': 'O', 'btts': 'Y',
                            'u': {'su': [0, 0], 'ml3': [-1, -1, 1.9], 'tot': [0.7, -1], 'btts': [1.5, -1]}}}}
        self.assertEqual(trends.side_result(g, '1p', 'ml', 'home'), ('P', 0))
        self.assertEqual(trends.side_result(g, '1p', 'ml3', 'away'), ('L', -1))   # a tie loses a team bet
        self.assertEqual(trends.game_result(g, '1p', 'ml3', 'tie'), ('W', 1.9))
        self.assertEqual(trends.game_result(g, '1p', 'total', 'over'), ('W', 0.7))
        self.assertEqual(trends.game_result(g, '1p', 'btts', 'no'), ('L', -1))

    def test_ml3_only_for_period_family(self):
        self.assertIn(('ml3', 'game', 'tie'), trends.bets_for(NHL, '1p'))
        self.assertNotIn('ml3', [m for m, _, _ in trends.bets_for(sports.BY_KEY['nba'], '1q')])

    def test_qualify(self):
        r = trends.Rec()
        for _ in range(12):
            r.add('W', 0.9)
        for _ in range(8):
            r.add('L', -1.0)
        self.assertEqual(trends.qualify(r, 0.5)['rate'], 0.6)
        self.assertIsNone(trends.qualify(r, 0.56))   # under 5 points of edge
        r.add('P', 0)
        self.assertEqual(trends.qualify(r, 0.5)['n'], 20)   # pushes don't count


class CardsTest(unittest.TestCase):
    def test_home_favorites_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, 'nhl.json')
            now = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
            out = trends.page_doc(NHL, doc(), now, log)
            cards = out['slates']['2026-10-30']['cards']
            card = next(c for c in cards if c['id'] == 'home_fav:1p:ml:back')
            self.assertEqual((card['w'], card['l'], card['base'], card['dir']), (18, 6, 0.5, 'Back'))
            self.assertEqual(card['title'], 'Back home favorites')
            self.assertEqual(card['games'][0]['id'], 99)
            self.assertEqual(card['games'][0]['side'], 'home')
            # its mirror ("Fade road underdogs") makes the same bets: one card
            self.assertEqual(sum(1 for c in cards if c['mk'] == 'ml' and c['w'] == 18 and c['l'] == 6), 1)
            self.assertFalse(out['slates']['2026-10-30']['frozen'])
            self.assertIn(['1p', 'ml3', '3-way ML'], out['markets'])
            # once the first game starts the slate is frozen and kept as it was
            later = datetime(2026, 10, 31, 1, tzinfo=timezone.utc)
            d = doc()
            d['games']['2026-10-30'][0]['odds'] = {}
            again = trends.page_doc(NHL, d, later, log)
            self.assertTrue(again['slates']['2026-10-30']['frozen'])
            self.assertEqual(again['slates']['2026-10-30']['cards'], cards)


if __name__ == '__main__':
    unittest.main()
