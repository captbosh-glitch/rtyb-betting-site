"""
Share tags (seo.head_block): each arena gets its own image, an existing
canonical isn't repeated, and the analytics file adds nothing while it's
only comments.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import seo  # noqa: E402

BASE = 'https://example.com/'
PAGE = '<head><meta name="description" content="Odds &amp; trends"></head><title>RTYB — NBA Games</title>'


class HeadBlock(unittest.TestCase):
    def test_arena_image_and_tags(self):
        b = seo.head_block('nba/games/', PAGE, BASE, '')
        self.assertIn('content="https://example.com/assets/share/nba.jpg"', b)
        self.assertIn('og:title" content="RTYB — NBA Games"', b)
        self.assertIn('og:description" content="Odds &amp; trends"', b)
        self.assertIn('<link rel="canonical" href="https://example.com/nba/games/">', b)

    def test_other_pages_use_home_image(self):
        self.assertIn('assets/share/home.jpg', seo.head_block('daily/', PAGE, BASE, ''))

    def test_existing_canonical_kept(self):
        page = PAGE.replace('</head>', '<link rel="canonical" href="x"></head>')
        self.assertNotIn('rel="canonical"', seo.head_block('learn/', page, BASE, ''))

    def test_analytics_only_when_pasted(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'analytics.html')
            old, seo.ANALYTICS_FILE = seo.ANALYTICS_FILE, path
            try:
                with open(path, 'w') as f:
                    f.write('<!-- paste here -->\n')
                self.assertEqual(seo.analytics(), '')
                with open(path, 'a') as f:
                    f.write('<script src="https://a.example/s.js"></script>\n')
                self.assertIn('<script', seo.analytics())
            finally:
                seo.ANALYTICS_FILE = old


if __name__ == '__main__':
    unittest.main()
