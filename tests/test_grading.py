"""
Tests for scripts/grading.py.

  python3 -m unittest discover tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))
import grading as g  # noqa: E402


def game(away, home, done=None, final=True):
    return {'away_ls': away, 'home_ls': home, 'periods_done': len(home) if done is None else done, 'final': final}


def spread_odds(line_away=None, ml=None, total=None, prices=(None, None), ou=(None, None)):
    o = {}
    if line_away is not None:
        o['ats'] = {'away': {'line': line_away, 'price': prices[0]}, 'home': {'line': -line_away, 'price': prices[1]}}
    if ml:
        o['ml'] = {'away': ml[0], 'home': ml[1]}
    if total is not None:
        o['total'] = {'line': total, 'over': ou[0], 'under': ou[1]}
    return o


def results(market):
    return {k: v['result'] for k, v in market.items() if isinstance(v, dict) and 'result' in v}


class Units(unittest.TestCase):
    def test_prices(self):
        self.assertAlmostEqual(g.bet_units('W', -110), 0.9091, places=4)
        self.assertEqual(g.bet_units('W', 150), 1.5)
        self.assertEqual(g.bet_units('L', -300), -1.0)
        self.assertEqual(g.bet_units('P', -110), 0.0)
        self.assertEqual(g.bet_units('T', 120), 0.0)
        self.assertEqual(g.bet_units('NA', 120), 0.0)
        self.assertIsNone(g.bet_units('W', None))


class SpreadSports(unittest.TestCase):
    # NFL 1Q 7-3, 1H 14-13 (quarters 7-3 then 7-10).
    G = game([7, 7, 0, 3], [3, 10, 7, 0])

    def grade(self, odds_1q=None, odds_1h=None, sport='nfl', g_=None):
        return g.grade_game(sport, 'spread', ['1q', '1h'], g_ or self.G,
                            {'segments': {'1q': odds_1q, '1h': odds_1h}})

    def test_segment_scores(self):
        r = self.grade()
        self.assertEqual(r['1q']['score'], {'away': 7, 'home': 3})
        self.assertEqual(r['1h']['score'], {'away': 14, 'home': 13})

    def test_ats_win_loss_push(self):
        # away -3.5 wins by 4: away W; -4 pushes; -4.5 loses
        self.assertEqual(results(self.grade(spread_odds(-3.5))['1q']['ats']), {'away': 'W', 'home': 'L'})
        self.assertEqual(results(self.grade(spread_odds(-4))['1q']['ats']), {'away': 'P', 'home': 'P'})
        self.assertEqual(results(self.grade(spread_odds(-4.5))['1q']['ats']), {'away': 'L', 'home': 'W'})

    def test_ats_default_and_custom_price(self):
        r = self.grade(spread_odds(-3.5))['1q']['ats']
        self.assertAlmostEqual(r['away']['units'], 0.9091, places=4)   # default -110
        self.assertEqual(r['home']['units'], -1.0)
        r = self.grade(spread_odds(-3.5, prices=(120, -140)))['1q']['ats']
        self.assertEqual(r['away']['units'], 1.2)
        push = self.grade(spread_odds(-4))['1q']['ats']
        self.assertEqual((push['away']['units'], push['home']['units']), (0.0, 0.0))

    def test_su_and_ml_units(self):
        r = self.grade(spread_odds(ml=(-150, 130)))['1q']['su']
        self.assertEqual(results(r), {'away': 'W', 'home': 'L'})
        self.assertAlmostEqual(r['away']['units'], 0.6667, places=4)
        self.assertEqual(r['home']['units'], -1.0)

    def test_su_tie_is_zero_units(self):
        tie = game([7, 0], [7, 0])
        r = self.grade(spread_odds(ml=(-110, -110)), g_=tie)['1q']['su']
        self.assertEqual(results(r), {'away': 'T', 'home': 'T'})
        self.assertEqual((r['away']['units'], r['home']['units']), (0.0, 0.0))

    def test_su_without_odds_has_result_but_no_units(self):
        r = self.grade()['1h']
        self.assertEqual(results(r['su']), {'away': 'W', 'home': 'L'})
        self.assertIsNone(r['su']['away']['units'])
        self.assertIsNone(r['ats'])        # no line saved -> not graded, not a loss
        self.assertIsNone(r['total'])

    def test_total_over_under_push(self):
        # 1H total points 27
        self.assertEqual(results(self.grade(odds_1h=spread_odds(total=26.5))['1h']['total']), {'over': 'W', 'under': 'L'})
        self.assertEqual(results(self.grade(odds_1h=spread_odds(total=27.5))['1h']['total']), {'over': 'L', 'under': 'W'})
        push = self.grade(odds_1h=spread_odds(total=27, ou=(-115, -105)))['1h']['total']
        self.assertEqual(results(push), {'over': 'P', 'under': 'P'})
        self.assertEqual(push['over']['units'], 0.0)
        self.assertEqual(push['points'], 27)
        r = self.grade(odds_1h=spread_odds(total=26.5, ou=(-120, 100)))['1h']['total']
        self.assertAlmostEqual(r['over']['units'], 0.8333, places=4)

    def test_unfinished_segment_not_graded(self):
        live = game([7, 3], [3, 0], done=1, final=False)  # in the 2nd quarter
        r = self.grade(g_=live)
        self.assertIsNotNone(r['1q'])
        self.assertIsNone(r['1h'])

    def test_ncaab_halves(self):
        r = g.grade_game('ncaab', 'spread', ['1h'], game([35, 40], [31, 44]), {'segments': {'1h': spread_odds(-2.5, total=66.5)}})
        self.assertEqual(r['1h']['score'], {'away': 35, 'home': 31})
        self.assertEqual(results(r['1h']['ats']), {'away': 'W', 'home': 'L'})
        self.assertEqual(results(r['1h']['total']), {'over': 'L', 'under': 'W'})

    def test_overtime_does_not_change_halves(self):
        ot = game([0, 10, 0, 7, 3], [7, 3, 7, 0, 0])
        self.assertEqual(self.grade(g_=ot)['1h']['score'], {'away': 10, 'home': 10})


def mlb_game(away, home, done=None, final=True):
    return game(away, home, done, final)


def f5_odds(fav='away', prices=(-110, -110), ml=None, total=None, ou=(None, None)):
    line = -0.5 if fav == 'away' else 0.5
    return spread_odds(line, ml=ml, total=total, prices=prices, ou=ou)


class MLB(unittest.TestCase):
    SEGS = ['1i', 'f5']

    def grade(self, gm, odds_1i=None, odds_f5=None):
        return g.grade_game('mlb', 'baseball', self.SEGS, gm, {'segments': {'1i': odds_1i, 'f5': odds_f5}})

    def test_nrfi(self):
        r = self.grade(mlb_game([0, 1, 0, 0, 2, 0, 0, 0, 0], [0, 0, 0, 3, 0, 0, 0, 0, 'X']),
                       odds_1i={'nrfi_yrfi': {'yrfi': 110, 'nrfi': -135}})['1i']
        self.assertEqual(results(r['nrfi_yrfi']), {'yrfi': 'L', 'nrfi': 'W'})
        self.assertAlmostEqual(r['nrfi_yrfi']['nrfi']['units'], 0.7407, places=4)
        self.assertEqual(r['nrfi_yrfi']['yrfi']['units'], -1.0)

    def test_yrfi(self):
        r = self.grade(mlb_game([0] * 9, [1] + [0] * 7 + ['X']), odds_1i={'nrfi_yrfi': {'yrfi': 110, 'nrfi': -135}})['1i']
        self.assertEqual(results(r['nrfi_yrfi']), {'yrfi': 'W', 'nrfi': 'L'})
        self.assertEqual(r['nrfi_yrfi']['yrfi']['units'], 1.1)
        self.assertEqual(r['runs'], 1)

    def test_nrfi_no_odds_still_graded(self):
        r = self.grade(mlb_game([0] * 9, [0] * 9))['1i']
        self.assertEqual(results(r['nrfi_yrfi']), {'yrfi': 'L', 'nrfi': 'W'})
        self.assertIsNone(r['nrfi_yrfi']['nrfi']['units'])

    def test_incomplete_first_inning_is_no_action(self):
        # rained out in the bottom of the 1st
        r = self.grade(mlb_game([2], [], done=0), odds_1i={'nrfi_yrfi': {'yrfi': 110, 'nrfi': -135}})
        self.assertEqual(results(r['1i']['nrfi_yrfi']), {'yrfi': 'NA', 'nrfi': 'NA'})
        self.assertEqual(r['1i']['nrfi_yrfi']['yrfi']['units'], 0.0)
        self.assertTrue(r['f5']['no_action'])

    def test_live_first_inning_not_graded_yet(self):
        r = self.grade(mlb_game([0], [0], done=0, final=False))
        self.assertIsNone(r['1i'])
        self.assertIsNone(r['f5'])

    def test_f5_su_ats_total(self):
        # F5: away 3, home 1
        gm = mlb_game([1, 0, 2, 0, 0, 0, 0, 0, 0], [0, 1, 0, 0, 0, 2, 0, 1, 'X'])
        r = self.grade(gm, odds_f5=f5_odds('away', prices=(-105, -115), ml=(-140, 120), total=4.5))['f5']
        self.assertEqual(r['score'], {'away': 3, 'home': 1})
        self.assertEqual(results(r['su']), {'away': 'W', 'home': 'L'})
        self.assertEqual(results(r['ats']), {'away': 'W', 'home': 'L'})
        self.assertAlmostEqual(r['ats']['away']['units'], 0.9524, places=4)
        self.assertEqual(results(r['total']), {'over': 'L', 'under': 'W'})

    def test_f5_tie(self):
        # tied 2-2 after 5: ML is a tie (0u), the +0.5 side wins ATS
        gm = mlb_game([1, 0, 1, 0, 0, 3, 0, 0, 0], [0, 2, 0, 0, 0, 0, 0, 0, 1])
        r = self.grade(gm, odds_f5=f5_odds('home', prices=(-120, 100), ml=(130, -150), total=4))['f5']
        self.assertEqual(results(r['su']), {'away': 'T', 'home': 'T'})
        self.assertEqual((r['su']['away']['units'], r['su']['home']['units']), (0.0, 0.0))
        self.assertEqual(results(r['ats']), {'away': 'W', 'home': 'L'})   # away was +0.5
        self.assertAlmostEqual(r['ats']['away']['units'], 0.8333, places=4)
        self.assertEqual(results(r['total']), {'over': 'P', 'under': 'P'})  # 4 runs on a 4 line

    def test_f5_half_total_never_pushes(self):
        gm = mlb_game([1, 0, 1, 0, 0], [0, 2, 0, 0, 0])
        r = self.grade(gm, odds_f5=f5_odds(total=4.5))['f5']
        self.assertEqual(results(r['total']), {'over': 'L', 'under': 'W'})

    def test_f5_fewer_than_five_innings_is_no_action(self):
        # official after 4.5 with the home team ahead, but F5 never finished
        gm = mlb_game([0, 1, 0, 0, 0], [2, 0, 0, 1], done=4)
        r = self.grade(gm, odds_1i={'nrfi_yrfi': {'yrfi': 110, 'nrfi': -135}}, odds_f5=f5_odds(ml=(-140, 120), total=4.5))
        self.assertEqual(results(r['1i']['nrfi_yrfi']), {'yrfi': 'W', 'nrfi': 'L'})
        f5 = r['f5']
        self.assertTrue(f5['no_action'])
        self.assertEqual(results(f5['su']), {'away': 'NA', 'home': 'NA'})
        self.assertEqual(results(f5['ats']), {'away': 'NA', 'home': 'NA'})
        self.assertEqual(f5['total']['over']['units'], 0.0)

    def test_f5_live_through_four_not_graded(self):
        gm = mlb_game([0, 1, 0, 0, 0], [2, 0, 0, 1], done=4, final=False)
        self.assertIsNone(self.grade(gm)['f5'])


if __name__ == '__main__':
    unittest.main()
