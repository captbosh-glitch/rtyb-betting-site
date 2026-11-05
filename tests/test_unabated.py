"""
Tests for scripts/fetch_odds_unabated.py and the feed merge in sport_build.py.

The partner-code check runs over every saved feed file: Unabated's free tier
is only kept while every published Gambly link carries ?utm_campaign=rtyb.

  python3 -m unittest discover tests
"""
import glob
import json
import os
import sys
import unittest
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import fetch_odds_unabated as F  # noqa: E402
import sport_build  # noqa: E402


def line(price, points=None, book=1, link='https://www.gambly.com/deeplink/odds/1/99/_'):
    d = {'marketSourceId': book, 'price': price, 'statusId': 1, 'disabled': False, 'deepLink': link}
    if points is not None:
        d['points'] = points
    return d


def side(idx, *lines, name=None):
    return {'sideIndex': idx, 'sideName': name, 'marketSourceLines': {str(l['marketSourceId']): l for l in lines}}


def links_in(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'link' and v:
                yield v
            else:
                yield from links_in(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from links_in(v)


class PartnerCode(unittest.TestCase):
    def test_tag_adds_code(self):
        self.assertEqual(F.tag_link('https://www.gambly.com/deeplink/odds/121/24178093532/_'),
                         'https://www.gambly.com/deeplink/odds/121/24178093532/_?utm_campaign=rtyb')

    def test_tag_keeps_other_params_and_replaces_old_code(self):
        self.assertEqual(F.tag_link('https://x.com/a?b=1&utm_campaign=old'), 'https://x.com/a?b=1&utm_campaign=rtyb')

    def test_every_saved_link_has_the_code(self):
        for path in glob.glob(os.path.join(ROOT, 'data_feed', 'unabated', '*.json')):
            with open(path, encoding='utf-8') as f:
                for link in links_in(json.load(f)):
                    self.assertIn('utm_campaign=rtyb', link, f'{os.path.basename(path)}: {link}')


class BestOdds(unittest.TestCase):
    def test_moneyline_best_price_each_side(self):
        sides = {0: side(0, line(120, book=1), line(130, book=2)), 1: side(1, line(-140, book=1), line(-150, book=2))}
        books = F.books_for(F.BT_ML, sides, False)
        self.assertEqual(F.best_of('ml', books, set()), {'away': 130, 'home': -140})

    def test_flipped_event_swaps_sides(self):
        sides = {0: side(0, line(120)), 1: side(1, line(-140))}
        books = F.books_for(F.BT_ML, sides, True)
        self.assertEqual(books['1']['away']['price'], -140)

    def test_spread_uses_most_common_line_then_best_price(self):
        sides = {0: side(0, line(-110, 3.5, 1), line(-105, 3.5, 2), line(-120, 4, 3)),
                 1: side(1, line(-110, -3.5, 1), line(-115, -3.5, 2), line(100, -4, 3))}
        best = F.best_of('ats', F.books_for(F.BT_SPREAD, sides, False), set())
        self.assertEqual(best, {'away': {'line': 3.5, 'price': -105}, 'home': {'line': -3.5, 'price': -110}})

    def test_total_sides_by_name(self):
        sides = {0: side(0, line(-110, 45.5), name='Under'), 1: side(1, line(-105, 45.5), name='Over')}
        best = F.best_of('total', F.books_for(F.BT_TOTAL, sides, False), set())
        self.assertEqual(best, {'line': 45.5, 'over': -105, 'under': -110})

    def test_only_sportsbooks_set_the_best_price(self):
        sides = {0: side(0, line(120, book=1), line(200, book=9)), 1: side(1, line(-140, book=1), line(-300, book=9))}
        books = F.books_for(F.BT_ML, sides, False)
        self.assertEqual(F.best_of('ml', books, {'1'}), {'away': 120, 'home': -140})

    def test_closed_lines_ignored(self):
        closed = dict(line(500, book=2), statusId=2)
        sides = {0: side(0, line(120, book=1), closed), 1: side(1, line(-140, book=1), line(-600, book=2))}
        self.assertEqual(list(F.books_for(F.BT_ML, sides, False)), ['1'])


class Matching(unittest.TestCase):
    start = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
    games = [{'away': 'phi', 'home': 'det', 'date': '2026-11-04', '_start': start}]
    aliases = {'phi': {'philadelphia 76ers', 'philadelphia', '76ers', 'phi'}, 'det': {'detroit pistons', 'detroit', 'pistons', 'det'}}

    def test_match(self):
        g, flipped = F.match_event('Philadelphia 76ers', 'Detroit Pistons', self.start, self.games, self.aliases)
        self.assertIs(g, self.games[0])
        self.assertFalse(flipped)

    def test_neutral_site_flip(self):
        g, flipped = F.match_event('Detroit Pistons', 'Philadelphia 76ers', self.start, self.games, self.aliases)
        self.assertIs(g, self.games[0])
        self.assertTrue(flipped)

    def test_wrong_time_no_match(self):
        later = datetime(2026, 11, 6, 0, 0, tzinfo=timezone.utc)
        self.assertIsNone(F.match_event('Philadelphia 76ers', 'Detroit Pistons', later, self.games, self.aliases)[0])

    def test_college_alias(self):
        al = {'m': {F.norm('Miami (OH)'), F.norm('Miami (OH) RedHawks')}, 'k': {F.norm('Kent State')}}
        games = [{'away': 'm', 'home': 'k', 'date': '2026-11-04', '_start': self.start}]
        self.assertIs(F.match_event('Miami Ohio', 'Kent State', self.start, games, al)[0], games[0])


class Merge(unittest.TestCase):
    def test_admin_wins_feed_fills_gaps(self):
        admin = {'k': {'date': 'd', 'away': 'a', 'home': 'h', 'segments': {'1h': {'ml': {'away': 100, 'home': -120}, 'total': None}}}}
        feed = {'k': {'date': 'd', 'away': 'a', 'home': 'h', 'segments': {
            '1h': {'ml': {'away': 130, 'home': -150}, 'total': {'line': 110.5, 'over': -110, 'under': -110}},
            '1q': {'ml': {'away': 120, 'home': -140}}}}}
        segs = sport_build.merge_odds(admin, feed)['k']['segments']
        self.assertEqual(segs['1h']['ml'], {'away': 100, 'home': -120})
        self.assertEqual(segs['1h']['total']['line'], 110.5)
        self.assertEqual(segs['1q']['ml'], {'away': 120, 'home': -140})


if __name__ == '__main__':
    unittest.main()
