"""Teams pages: the market pills each sport's data file carries
(sport_build.page_markets) and the team page title and header
(build_site.sport_team_meta)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_site  # noqa: E402
import sport_build  # noqa: E402
import sports  # noqa: E402


class MarketsTest(unittest.TestCase):
    def test_no_three_way_for_the_spread_family(self):
        for key in ('nba', 'wnba', 'ncaab', 'nfl', 'ncaaf'):
            self.assertNotIn('ml3', [m[1] for m in sport_build.page_markets(sports.BY_KEY[key])], key)

    def test_period_family_pills_in_order(self):
        self.assertEqual([m[1] for m in sport_build.page_markets(sports.BY_KEY['nhl'])], ['ml', 'total', 'btts', 'ml3'])
        self.assertEqual([(m[0], m[1]) for m in sport_build.page_markets(sports.BY_KEY['mlb'])],
                         [('1i', 'rfi'), ('f5', 'ml'), ('f5', 'ats'), ('f5', 'total'), ('f5', 'ml3')])

    def test_ncaab_has_one_segment(self):
        self.assertEqual({m[0] for m in sport_build.page_markets(sports.BY_KEY['ncaab'])}, {'1h'})


class TeamMetaTest(unittest.TestCase):
    def test_title_and_header(self):
        team = {'slug': 'bos', 'code': 'BOS', 'name': 'Boston Celtics', 'division': 'Atlantic', 'conference': 'Eastern Conference'}
        meta = build_site.sport_team_meta(sports.BY_KEY['nba'], team, '2026–27')
        self.assertEqual(meta['title'], 'Boston Celtics First Quarter & First Half Stats & Betting Record 2026–27')
        self.assertEqual(meta['h1'], 'Boston Celtics')
        self.assertEqual(meta['desc'], 'Atlantic · Eastern Conference')

    def test_nhl_title_and_logo(self):
        team = {'slug': 'tor', 'code': 'TOR', 'name': 'Toronto Maple Leafs', 'division': 'Atlantic Division', 'conference': 'Eastern Conference'}
        meta = build_site.sport_team_meta(sports.BY_KEY['nhl'], team, '2026–27')
        self.assertEqual(meta['title'], 'Toronto Maple Leafs First Period Stats & Betting Record 2026–27')
        self.assertIn('assets/logos/TOR_light.svg', meta['icon'])

    def test_team_body_has_no_second_heading(self):
        team = {'slug': 'bos', 'code': 'BOS', 'name': 'Boston Celtics', 'division': 'Atlantic', 'conference': 'Eastern Conference'}
        body = build_site.team_detail_html(sports.BY_KEY['nba'], team)
        self.assertNotIn('<h1', body)
        self.assertIn('data-team="bos"', body)
        nhl = build_site.team_detail_html(sports.BY_KEY['nhl'], dict(team, slug='bos', code='BOS'))
        self.assertIn('data-team="BOS"', nhl)   # NHL's data is keyed by code


if __name__ == '__main__':
    unittest.main()
