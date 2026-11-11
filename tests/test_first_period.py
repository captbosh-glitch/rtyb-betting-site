"""
fetch_schedule.first_period_over: a live game's 1st-period score is saved
only once the period has ended (a 0-0 game ten minutes in isn't a tied
1st period).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from fetch_schedule import first_period_over  # noqa: E402


def live(number, intermission=False):
    return {'periodDescriptor': {'number': number}, 'clock': {'inIntermission': intermission}}


class FirstPeriodOver(unittest.TestCase):
    def test_during_the_first(self):
        self.assertFalse(first_period_over(live(1), 'LIVE'))

    def test_first_intermission(self):
        self.assertTrue(first_period_over(live(1, intermission=True), 'LIVE'))

    def test_later_periods(self):
        self.assertTrue(first_period_over(live(2), 'LIVE'))
        self.assertTrue(first_period_over(live(3), 'CRIT'))

    def test_final_without_period_info(self):
        self.assertTrue(first_period_over({}, 'OFF'))
        self.assertFalse(first_period_over({}, 'LIVE'))


if __name__ == '__main__':
    unittest.main()
