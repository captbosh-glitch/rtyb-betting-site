"""
Win % leaves ties and pushes out, on every page (Chris's Matchups spec,
Nov 12 2026): Favorites 2-0-4 is 100%, not 33%. Tie % is still out of every
game played: a 5-0-12 team is 100% wins and 71% ties.

The rule lives in three browser files -- template.html (NHL pages),
assets/sport.js (the other sports) and assets/situational.js (the Stats
pages' Situational table). These tests pull each one-line helper out of its
file and run it under Node, so all three stay in step.
"""
import json
import os
import re
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which('node')


def helper(path, name):
    """The source of a one-line `function name(...) { ... }` in a file."""
    src = open(os.path.join(ROOT, path), encoding='utf-8').read()
    m = re.search(r'function %s\([^)]*\) \{.*\}$' % name, src, re.M)
    if not m:
        raise AssertionError(f'{name} not found in {path}')
    return m.group(0)


def run(js):
    out = subprocess.run([NODE, '-e', js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, 'node is not installed')
class WinPctTest(unittest.TestCase):
    CASES = [  # (w, l, t) -> win %, tie %
        ((5, 0, 12), (1.0, 12 / 17)),       # the many-ties team
        ((2, 0, 4), (1.0, 4 / 6)),          # the spec's Favorites row
        ((6, 3, 9), (6 / 9, 9 / 18)),
        ((10, 10, 0), (0.5, 0.0)),          # no ties: same as before
        ((0, 0, 4), (None, 1.0)),           # all ties: no win %
        ((0, 0, 0), (None, None)),          # no games: no %
    ]

    def check(self, path):
        js = (helper(path, 'winPct') + '\n' + helper(path, 'tiePct') + '\n'
              'console.log(JSON.stringify(%s.map(function(c) { return [winPct(c[0], c[1], c[2]), tiePct(c[0], c[1], c[2])]; })));'
              % json.dumps([c[0] for c in self.CASES]))
        for (case, want), got in zip(self.CASES, run(js)):
            for w, g in zip(want, got):
                if w is None:
                    self.assertIsNone(g, case)
                else:
                    self.assertAlmostEqual(g, w, places=6, msg=case)

    def test_nhl_pages(self):
        self.check('template.html')

    def test_other_sports(self):
        self.check('assets/sport.js')

    def test_situational_table(self):
        # x = {a: wins, b: losses, p: ties}; whole percents. Ties (NHL / MLB)
        # and pushes (the spread family) stay out of the win %
        js = (helper('assets/situational.js', 'decided') + '\n' + helper('assets/situational.js', 'pctOf') + '\n' + helper('assets/situational.js', 'tieOf') + '\n'
              'var src = {ties: true}, x = {a: 5, b: 0, p: 12};'
              'var out = [pctOf({id: "su"}, x), tieOf(x), pctOf({id: "ats"}, {a: 5, b: 5, p: 2})];'
              'src.ties = false; out.push(pctOf({id: "su"}, {a: 6, b: 4, p: 2}));'
              'console.log(JSON.stringify(out));')
        win, tie, cover, spread_ml = run(js)
        self.assertEqual(win, 100)
        self.assertEqual(tie, 71)
        self.assertEqual(cover, 50)   # spreads still leave pushes out
        self.assertEqual(spread_ml, 60)   # NBA moneyline: a tied quarter is a push

    def test_favorites_two_and_oh_with_four_ties(self):
        js = helper('template.html', 'winPct') + '\nconsole.log(JSON.stringify(Math.round(winPct(2, 0, 4) * 100)));'
        self.assertEqual(run(js), 100)


if __name__ == '__main__':
    unittest.main()
