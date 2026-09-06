"""Streamlit 共用格式化工具測試。"""

import unittest
from decimal import Decimal

from frontend.ui.formatters import (
    asset_type_label,
    format_amount,
    format_etf_display_name,
    format_iso_date,
    format_iso_datetime,
    format_number,
    format_optional_text,
    format_percentage,
    format_source_references,
    management_type_label,
    truncate_text,
)


class TestFrontendFormatters(
    unittest.TestCase
):
    """驗證跨頁面共用格式化語意。"""

    def test_integer_formatting_preserves_significant_trailing_zeros(self):
        for value, expected in [(100, "100"), (1000, "1,000"), (0, "0"), (-100, "-100")]:
            with self.subTest(value=value):
                self.assertEqual(
                    format_number(value, decimal_places=0, trim_trailing_zeros=True),
                    expected,
                )
                self.assertEqual(
                    format_amount(value, decimal_places=0), expected + " NTD"
                )
        self.assertEqual(
            format_number(100, decimal_places=0, trim_trailing_zeros=True,
                          signed=True, suffix=" 股"),
            "+100 股",
        )

    def test_fractional_trailing_zeros_are_trimmed_only_after_decimal_point(self):
        for value, expected in [(100, "100"), (100.5, "100.5"), (0, "0")]:
            with self.subTest(value=value):
                self.assertEqual(
                    format_number(value, decimal_places=4, trim_trailing_zeros=True),
                    expected,
                )

    def test_nonfinite_and_overflow_values_use_invalid_label(self):
        for value in [float("nan"), float("inf"), float("-inf"),
                      "NaN", "Infinity", Decimal("NaN"),
                      Decimal("1e10000"), 10 ** 10000]:
            with self.subTest(value_type=type(value).__name__):
                for formatter in (format_number, format_percentage, format_amount):
                    self.assertEqual(formatter(value, invalid_text="格式異常"), "格式異常")

    def test_missing_zero_and_invalid_values_remain_distinct(self):
        self.assertEqual(format_amount(None), "尚無資料")
        self.assertEqual(format_amount(0), "0 NTD")
        self.assertEqual(format_amount(float("nan")), "資料格式異常")

    def test_amount_display_rounds_without_changing_value_or_other_currency(self):
        amount = Decimal("1234.56")
        self.assertEqual(format_amount(amount, "twd"), "1,235 NTD")
        self.assertEqual(format_amount(-amount, "NTD"), "-1,235 NTD")
        self.assertEqual(format_amount(amount, "USD"), "1,235 USD")
        self.assertEqual(amount, Decimal("1234.56"))

    def test_percentage_keeps_missing_and_zero_distinct(
        self,
    ) -> None:
        """確認缺值與正式零值不會混淆。"""

        self.assertEqual(
            format_percentage(
                None,
                missing_text="尚未取得",
            ),
            "尚未取得",
        )

        self.assertEqual(
            format_percentage(0),
            "0.00%",
        )

        self.assertEqual(
            format_percentage(
                5.125,
                signed=True,
            ),
            "+5.12%",
        )

    def test_number_and_amount_formats_are_stable(
        self,
    ) -> None:
        """確認數字、單位及幣別格式一致。"""

        self.assertEqual(
            format_number(
                5000,
                suffix=" 億元",
            ),
            "5,000.00 億元",
        )

        self.assertEqual(
            format_amount(
                0.7000,
                "twd",
            ),
            "1 NTD",
        )

        self.assertEqual(
            format_number(
                "bad",
                invalid_text="格式異常",
            ),
            "格式異常",
        )

    def test_optional_date_and_datetime(
        self,
    ) -> None:
        """確認日期缺值與 ISO 日期時間顯示。"""

        self.assertEqual(
            format_iso_date(
                None,
                missing_text="尚無資料",
            ),
            "尚無資料",
        )

        self.assertEqual(
            format_iso_datetime(
                "2026-07-31T12:34:56+00:00",
                utc_label=True,
                timespec=None,
            ),
            "2026-07-31 12:34:56 UTC",
        )

        self.assertEqual(
            format_optional_text(
                "   ",
            ),
            "—",
        )

    def test_etf_display_name_hides_former_name_suffix(
        self,
    ) -> None:
        """確認 ETF 原名註記只在顯示層移除。"""

        self.assertEqual(
            format_etf_display_name(
                (
                    "期元大S&P黃金反1"
                    "(原名：元大S&P黃金反1)"
                )
            ),
            "期元大S&P黃金反1",
        )

        self.assertEqual(
            format_etf_display_name(
                (
                    "期街口布蘭特正2"
                    "（原名:街口布蘭特正2）"
                )
            ),
            "期街口布蘭特正2",
        )

        self.assertEqual(
            format_etf_display_name(
                "某某ETF（美元）"
            ),
            "某某ETF（美元）",
        )

    def test_classification_labels(
        self,
    ) -> None:
        """確認 ETF 分類標籤跨頁一致。"""

        self.assertEqual(
            management_type_label(True),
            "主動式",
        )

        self.assertEqual(
            management_type_label(False),
            "被動式",
        )

        self.assertEqual(
            asset_type_label(True),
            "債券",
        )

        self.assertEqual(
            asset_type_label(False),
            "非債券",
        )

    def test_source_references_and_truncation(
        self,
    ) -> None:
        """確認來源名稱與錯誤摘要格式。"""

        self.assertEqual(
            format_source_references(
                [
                    {
                        "source_id": "twse_openapi",
                        "display_name": "證交所 OpenAPI",
                    },
                    {
                        "source_id": "manual",
                        "display_name": "manual",
                    },
                ]
            ),
            (
                "證交所 OpenAPI (twse_openapi)"
                "、manual"
            ),
        )

        self.assertEqual(
            truncate_text(
                "abcdef",
                maximum_length=4,
            ),
            "abcd…",
        )


if __name__ == "__main__":
    unittest.main()
