"""測試逐月目標現金流顯示語意。"""

import unittest

from frontend.pages.etf_detail import build_target_monthly_cash_rows


class TestFrontendTargetCashRows(unittest.TestCase):
    def test_missing_is_not_rendered_as_zero(self) -> None:
        rows = build_target_monthly_cash_rows(
            [
                {
                    "month": 1,
                    "event_count": 0,
                    "observed_year_count": 0,
                    "annualized_gross_cash": None,
                    "annualized_after_tax_cash": None,
                    "latest_payment_date": None,
                },
                {
                    "month": 2,
                    "event_count": 1,
                    "observed_year_count": 1,
                    "annualized_gross_cash": 0,
                    "annualized_after_tax_cash": 0,
                    "latest_payment_date": "2026-02-20",
                },
            ]
        )

        self.assertEqual(rows[0]["年化稅前現金"], "無法計算")
        self.assertEqual(rows[0]["年化稅後現金"], "無法計算")
        self.assertEqual(rows[1]["年化稅前現金"], "0 NTD")
        self.assertEqual(rows[1]["年化稅後現金"], "0 NTD")


if __name__ == "__main__":
    unittest.main()
