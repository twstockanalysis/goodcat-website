"""Calculation precision boundaries independent of display formatting."""

import unittest
from decimal import Decimal, ROUND_DOWN, localcontext

from backend.app.services.calculation_precision import (
    round_money, round_percentage, round_units,
)


class TestCalculationPrecision(unittest.TestCase):
    def test_money_half_way_values_and_scale(self):
        cases = [("1.005", "1.01"), ("-1.005", "-1.01"),
                 ("1.0049", "1.00"), ("0", "0.00"), ("100", "100.00")]
        with localcontext() as context:
            context.rounding = ROUND_DOWN
            for raw, expected in cases:
                with self.subTest(raw=raw):
                    self.assertEqual(str(round_money(Decimal(raw))), expected)

    def test_percentage_and_units_keep_six_places(self):
        for formatter in (round_percentage, round_units):
            for raw, expected in [("0.0000005", "0.000001"),
                                  ("-0.0000005", "-0.000001"),
                                  ("0", "0.000000")]:
                with self.subTest(formatter=formatter.__name__, raw=raw):
                    self.assertEqual(str(formatter(Decimal(raw))), expected)

    def test_round_after_aggregation_not_each_distribution(self):
        distributions = [Decimal("0.004"), Decimal("0.004")]
        self.assertEqual(round_money(sum(distributions)), Decimal("0.01"))
        self.assertEqual(distributions, [Decimal("0.004"), Decimal("0.004")])


if __name__ == "__main__":
    unittest.main()
