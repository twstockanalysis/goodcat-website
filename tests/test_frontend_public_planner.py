"""公開現金流試算頁的純函式測試。"""

import unittest

import pandas as pd

from frontend.pages.public_planner import (
    HOLDING_SELECTION_COLUMN,
    add_empty_holding_row,
    allocation_goodcat_feedback,
    build_addition_rows,
    build_allocation_month_rows,
    build_holding_payload,
    build_historical_evidence_rows,
    build_monthly_rows,
    build_scenario_chart_rows,
    empty_holding_editor_rows,
    merge_holding_editor_changes,
    remove_selected_holding_rows,
    sort_holding_editor_rows,
    summarize_allocation_result,
)
from frontend.ui.goodcat import GoodCatState


class TestFrontendPublicPlanner(unittest.TestCase):
    def test_allocation_summary_counts_met_months_and_shortfall(self) -> None:
        summary = summarize_allocation_result(
            {
                "monthly_results": [
                    {"month": 1, "shortfall": "0"},
                    {"month": 3, "shortfall": "125.5"},
                    {"month": 5, "shortfall": "0"},
                ]
            }
        )

        self.assertEqual(summary["target_month_count"], 3)
        self.assertEqual(summary["met_month_count"], 2)
        self.assertEqual(str(summary["total_shortfall"]), "125.5")

    def test_goodcat_feedback_distinguishes_ready_partial_and_missing(self) -> None:
        def payload(status: str, additions: list[dict] | None = None) -> dict:
            return {
                "long_term_scenarios": {
                    "allocation_results": {
                        "plans": [
                            {
                                "strategy": "RECOMMENDED",
                                "result": {
                                    "status": status,
                                    "additions": additions or [],
                                },
                            }
                        ]
                    }
                }
            }

        state, message = allocation_goodcat_feedback(
            payload("TARGET_MET", [{"etf_code": "0056"}])
        )
        self.assertEqual(state, GoodCatState.REWARD)
        self.assertIn("ETF、股數", message)

        state, message = allocation_goodcat_feedback(payload("PARTIAL"))
        self.assertEqual(state, GoodCatState.REWARD)
        self.assertIn("仍有缺口", message)

        state, message = allocation_goodcat_feedback({})
        self.assertEqual(state, GoodCatState.CAUTION)
        self.assertIn("沒有足夠資料", message)

    def test_empty_editor_supports_zero_holdings_with_explicit_dtypes(self) -> None:
        rows = empty_holding_editor_rows()
        self.assertTrue(rows.empty)
        self.assertEqual(str(rows["ETF 代號"].dtype), "string")
        self.assertEqual(str(rows["持有股數"].dtype), "Int64")
        self.assertEqual(build_holding_payload(rows), ([], []))

    def test_holding_rows_require_selection_before_delete(self) -> None:
        rows = add_empty_holding_row(empty_holding_editor_rows())
        rows.loc[0, "ETF 代號"] = "0050"
        rows.loc[0, "持有股數"] = 100
        rows = add_empty_holding_row(rows)
        rows.loc[1, "ETF 代號"] = "0056"
        rows.loc[1, "持有股數"] = 200

        untouched = remove_selected_holding_rows(rows)
        self.assertEqual(untouched["ETF 代號"].tolist(), ["0050", "0056"])

        rows.loc[0, HOLDING_SELECTION_COLUMN] = True
        remaining = remove_selected_holding_rows(rows)
        self.assertEqual(remaining["ETF 代號"].tolist(), ["0056"])
        self.assertFalse(remaining[HOLDING_SELECTION_COLUMN].any())

    def test_holding_rows_sort_by_etf_code_and_keep_blank_rows_last(self) -> None:
        rows = pd.DataFrame(
            {
                HOLDING_SELECTION_COLUMN: [False, False, False],
                "ETF 代號": ["00878", pd.NA, " 0050 "],
                "持有股數": [100, pd.NA, 200],
            }
        )

        sorted_rows = sort_holding_editor_rows(rows)

        self.assertEqual(
            sorted_rows["ETF 代號"].dropna().tolist(), ["0050", "00878"]
        )
        self.assertTrue(pd.isna(sorted_rows.iloc[-1]["ETF 代號"]))

    def test_editor_changes_are_merged_before_automatic_sorting(self) -> None:
        rows = pd.DataFrame(
            {
                HOLDING_SELECTION_COLUMN: [False, False],
                "ETF 代號": ["00878", pd.NA],
                "持有股數": [100, pd.NA],
            }
        )

        merged = merge_holding_editor_changes(
            rows,
            {
                0: {HOLDING_SELECTION_COLUMN: True},
                1: {"ETF 代號": "0050", "持有股數": 200},
            },
        )

        self.assertEqual(merged["ETF 代號"].tolist(), ["0050", "00878"])
        self.assertEqual(merged["持有股數"].tolist(), [200, 100])
        self.assertEqual(merged[HOLDING_SELECTION_COLUMN].tolist(), [False, True])

    def test_holding_payload_normalizes_and_rejects_duplicates(self) -> None:
        rows = pd.DataFrame(
            {
                "ETF 代號": [" 0056 ", "0056", "00878"],
                "持有股數": [100, 200, 0],
            }
        )
        payload, errors = build_holding_payload(rows)
        self.assertEqual(
            payload,
            [
                {"etf_code": "0056", "held_units": 100},
                {"etf_code": "0056", "held_units": 200},
            ],
        )
        self.assertIn("ETF 代號不可重複：0056", errors)
        self.assertIn("第 3 列持有股數必須是正整數。", errors)

    def test_monthly_rows_keep_missing_values_distinct_from_zero(self) -> None:
        result = {
            "monthly_cash_flow": [
                {
                    "month": month,
                    "selected": month == 1,
                    "gross_cash": None if month == 1 else "0",
                    "after_tax_cash": None if month == 1 else "0",
                    "target_after_tax_cash": "100" if month == 1 else "0",
                    "shortfall": None if month == 1 else "0",
                }
                for month in range(1, 13)
            ]
        }
        rows = build_monthly_rows(result)
        self.assertEqual(rows[0]["尚缺金額"], "無法計算")
        self.assertEqual(rows[1]["尚缺金額"], "0 NTD")

    def test_allocation_rows_use_beginner_facing_labels(self) -> None:
        additions = build_addition_rows(
            {
                "additions": [
                    {
                        "etf_code": "0056",
                        "name": "元大高股息",
                        "additional_shares": 100,
                        "reference_price": "35",
                        "required_capital": "3500",
                        "supported_target_months": [1, 7],
                    }
                ]
            }
        )
        self.assertEqual(additions[0]["增加股數"], "100")
        self.assertEqual(additions[0]["支援月份"], "1 月、7 月")

        months = build_allocation_month_rows(
            {
                "monthly_results": [
                    {
                        "month": 1,
                        "current_after_tax_cash": "100",
                        "added_after_tax_cash": "200",
                        "modeled_after_tax_cash": "300",
                        "target_after_tax_cash": "300",
                        "shortfall": "0",
                    }
                ]
            }
        )
        self.assertEqual(months[0]["配置後現金"], "300 NTD")
        self.assertEqual(months[0]["尚缺"], "0 NTD")

    def test_long_term_rows_keep_unavailable_distinct_from_zero(self) -> None:
        evidence = {
            "historical_periods": [
                {
                    "period": "AVAILABLE_HISTORY",
                    "status": "AVAILABLE",
                    "period_start": "2022-01-03",
                    "period_end": "2026-01-03",
                    "total_return_pct": "28",
                    "annualized_total_return_pct": "6.4",
                },
                {
                    "period": "3Y",
                    "status": "UNAVAILABLE",
                    "issues": [{"message": "共同價格歷史不足。"}],
                },
            ],
            "scenarios": [
                {
                    "label": "保守情境",
                    "index_points": [
                        {"year": 0, "total_value_index": "100"},
                        {"year": 1, "total_value_index": "104"},
                    ],
                }
            ],
        }
        rows = build_historical_evidence_rows(evidence)
        self.assertEqual(rows[0]["含息總報酬估算"], "28.00%")
        self.assertEqual(rows[1]["含息總報酬估算"], "無法計算")
        self.assertEqual(rows[1]["說明"], "共同價格歷史不足。")
        chart_rows = build_scenario_chart_rows(evidence)
        self.assertEqual(chart_rows[1], {"年數": 1, "保守情境": 104.0})


if __name__ == "__main__":
    unittest.main()
