"""The Stats pages (Overview, Splits, Edges) for every sport: their titles
and the Overview · Splits · Edges tabs (scripts/build_site.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import build_site  # noqa: E402
import sports  # noqa: E402


class StatsPagesTest(unittest.TestCase):
    def test_titles(self):
        nba = sports.BY_KEY['nba']
        self.assertEqual(build_site.stats_meta(nba, 'stats', '2026–27')['title'], 'NBA First Quarter & First Half Stats 2026–27 | RTYB')
        self.assertEqual(build_site.stats_meta(nba, 'splits', '2026–27')['title'], 'NBA First Quarter & First Half Splits 2026–27 | RTYB')
        self.assertEqual(build_site.stats_meta(nba, 'edges', '2026–27')['title'], 'NBA First Quarter & First Half Edges: Best Closers & Faders | RTYB')

    def test_every_page_is_a_stats_page(self):
        for sp in sports.SPORTS:
            for sec, _, _ in build_site.STATS_PAGES:
                self.assertEqual(build_site.stats_meta(sp, sec, None)['section'], 'stats')

    def test_tabs_mark_the_current_page(self):
        html = build_site.stats_tabs_html(sports.BY_KEY['nhl'], 'splits')
        self.assertIn('href="/nhl/stats/splits/" aria-current="page"', html)
        self.assertIn('href="/nhl/stats/edges/"', html)
        self.assertEqual(html.count('aria-current'), 1)


if __name__ == '__main__':
    unittest.main()
