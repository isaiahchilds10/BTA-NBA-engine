import unittest
from engine import decimal_odds, implied_probability, expected_return, assess, profit_for_result

class EngineTests(unittest.TestCase):
    def test_odds_conversion(self):
        self.assertAlmostEqual(decimal_odds(-110), 1.90909090909)
        self.assertAlmostEqual(decimal_odds(150), 2.5)
        self.assertAlmostEqual(implied_probability(-110), 110/210)
        with self.assertRaises(ValueError): decimal_odds(50)

    def test_expected_value(self):
        self.assertAlmostEqual(expected_return(0.55, -110), 0.05, places=9)
        self.assertLess(expected_return(0.5, -110), 0)

    def test_gate_and_bankroll(self):
        base = dict(probability=.60,american=-110,grade='BTA+',bankroll=1000,
                    open_exposure=0,evidence_reviewed=True,blockers=False)
        self.assertEqual(assess(**base).stake, 5.00)
        self.assertEqual(assess(**{**base,'blockers':True}).stake, 0)
        self.assertEqual(assess(**{**base,'same_event_already_open':True}).stake, 0)
        self.assertEqual(assess(**{**base,'open_exposure':49}).stake, 1)
        self.assertEqual(assess(**{**base,'grade':'Conditional'}).stake, 0)

    def test_profit(self):
        self.assertAlmostEqual(profit_for_result(10, -110, 'WIN'), 9.09)
        self.assertAlmostEqual(profit_for_result(10, -110, 'LOSS'), -10)
        self.assertIsNone(profit_for_result(10, -110, 'OPEN'))

if __name__ == '__main__': unittest.main()
