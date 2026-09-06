"""Streamlit ETF 配息詳細區塊測試。"""

import unittest

from streamlit.testing.v1 import (
    AppTest,
)

from frontend.pages.etf_detail import (
    build_annual_dividend_chart_rows,
    build_component_display_rows,
    build_dividend_summary_rows,
    chart_axis_upper_bound,
    format_cash_stock_dividend,
    format_dividend_amount,
    format_dividend_event_row_label,
    format_dividend_period,
    format_dividend_percentage,
    get_component_display_name,
    get_display_width,
)


DETAIL_DIVIDEND_PAGE_SCRIPT = """
import frontend.pages.etf_detail as page
page.render_page_title = lambda title: page.st.title(title)


def fake_fetch_etf_by_code(**kwargs):
    return {
        "code": "00918",
        "name": "大華優利高填息30",
        "is_active": False,
        "is_bond": False,
        "listing_date": "2022-11-24",
        "fund_size": 100.0,
        "expense_ratio": 0.5,
    }


def fake_fetch_etf_performance(**kwargs):
    return {
        "etf_code": "00918",
        "metric_code": "PRICE_RETURN",
        "items": [],
    }


def fake_fetch_etf_dividends(**kwargs):
    return {
        "etf_code": "00918",
        "total": 2,
        "limit": 20,
        "offset": 0,
        "items": [
            {
                "dividend_id": 2,
                "source_event_id": "event-2",
                "announcement_date": None,
                "ex_dividend_date": "2026-06-18",
                "record_date": "2026-06-24",
                "payment_date": "2026-07-10",
                "amount_per_unit": 0.7,
                "currency": "TWD",
                "source_id": "official",
                "distribution_period": "2026Q2",
                "distribution_period_source_id": (
                    "official"
                ),
                "yield_pct": 2.8,
                "yield_basis": "OFFICIAL",
                "yield_source_id": "official",
                "reference_trade_date": None,
                "reference_close_price": None,
            },
            {
                "dividend_id": 1,
                "source_event_id": "event-1",
                "announcement_date": None,
                "ex_dividend_date": "2026-03-20",
                "record_date": "2026-03-26",
                "payment_date": "2026-04-15",
                "amount_per_unit": 0.5,
                "currency": "TWD",
                "source_id": "official",
                "distribution_period": None,
                "distribution_period_source_id": None,
                "yield_pct": 2.0,
                "yield_basis": "CALCULATED",
                "yield_source_id": "twse_stock_day",
                "reference_trade_date": (
                    "2026-03-19"
                ),
                "reference_close_price": 25.0,
            },
        ],
    }


def fake_fetch_etf_actual_76w(**kwargs):
    return {
        "etf_code": "00918",
        "total_dividend_count": 2,
        "actual_76w_record_count": 2,
        "full_76w_count": 1,
        "latest_76w_ratio_pct": 100.0,
        "average_76w_ratio_pct": 90.0,
        "items": [],
    }


def fake_fetch_dividend_detail(
    dividend_id,
    **kwargs,
):
    return {
        "dividend_id": dividend_id,
        "etf_code": "00918",
        "source_event_id": (
            f"event-{dividend_id}"
        ),
        "announcement_date": None,
        "ex_dividend_date": "2026-06-18",
        "record_date": "2026-06-24",
        "payment_date": "2026-07-10",
        "amount_per_unit": 0.7,
        "currency": "TWD",
        "source_id": "official",
        "components": [
            {
                "component_id": 1,
                "dividend_id": dividend_id,
                "component_code": (
                    "EST_REALIZED_CAPITAL_GAIN"
                ),
                "component_basis": "ESTIMATED",
                "component_name": (
                    "已實現資本利得"
                ),
                "amount_per_unit": None,
                "ratio_pct": 90.0,
                "source_id": (
                    "twse_etfortune_dividend"
                ),
            },
            {
                "component_id": 2,
                "dividend_id": dividend_id,
                "component_code": "76W",
                "component_basis": "ACTUAL",
                "component_name": (
                    "實際所得類別 76W"
                ),
                "amount_per_unit": 0.63,
                "ratio_pct": 100.0,
                "source_id": (
                    "official_distribution_notice"
                ),
            },
        ],
    }


def fake_fetch_etf_data_profile(**kwargs):
    code = str(
        kwargs.get("code", "00918")
    ).strip().upper()

    return {
        "etf_code": code,
        "master": {
            "sources": [
                {
                    "source_id": "twse_openapi",
                    "display_name": (
                        "臺灣證券交易所 OpenAPI"
                    ),
                }
            ],
            "latest_import_at": (
                "2026-07-30T00:05:00+00:00"
            ),
        },
        "performance": {
            "metric_code": "PRICE_RETURN",
            "sources": [],
            "record_count": 0,
            "available_periods": [],
            "latest_as_of_date": None,
            "latest_import_at": None,
        },
        "dividends": {
            "sources": [
                {
                    "source_id": "official",
                    "display_name": "正式配息來源",
                }
            ],
            "event_count": 0,
            "latest_event_date": None,
            "latest_import_at": None,
        },
        "actual_dividend": {
            "sources": [],
            "actual_component_event_count": 0,
            "actual_76w_event_count": 0,
            "source_document_event_count": 0,
            "latest_source_document_date": None,
            "latest_import_at": None,
        },
    }


page.fetch_etf_by_code = (
    fake_fetch_etf_by_code
)
page.fetch_etf_data_profile = (
    fake_fetch_etf_data_profile
)
page.fetch_etf_performance = (
    fake_fetch_etf_performance
)
page.fetch_etf_dividends = (
    fake_fetch_etf_dividends
)
page.fetch_etf_actual_76w = (
    fake_fetch_etf_actual_76w
)
page.fetch_dividend_detail = (
    fake_fetch_dividend_detail
)

page.load_etf_detail.clear()
page.load_etf_data_profile.clear()
page.load_etf_performance.clear()
page.load_etf_dividends.clear()
page.load_etf_actual_76w.clear()
page.load_dividend_detail.clear()

page.render_etf_detail()
"""


MISSING_76W_PAGE_SCRIPT = """
import frontend.pages.etf_detail as page
page.render_page_title = lambda title: page.st.title(title)


def fake_fetch_etf_by_code(**kwargs):
    return {
        "code": "0050",
        "name": "元大台灣50",
        "is_active": False,
        "is_bond": False,
        "listing_date": "2003-06-30",
        "fund_size": None,
        "expense_ratio": None,
    }


def fake_fetch_etf_performance(**kwargs):
    return {
        "etf_code": "0050",
        "metric_code": "PRICE_RETURN",
        "items": [],
    }


def fake_fetch_etf_dividends(**kwargs):
    return {
        "etf_code": "0050",
        "total": 0,
        "limit": 20,
        "offset": 0,
        "items": [],
    }


def fake_fetch_etf_actual_76w(**kwargs):
    return {
        "etf_code": "0050",
        "total_dividend_count": 0,
        "actual_76w_record_count": 0,
        "full_76w_count": 0,
        "latest_76w_ratio_pct": None,
        "average_76w_ratio_pct": None,
        "items": [],
    }


def fake_fetch_etf_data_profile(**kwargs):
    code = str(
        kwargs.get("code", "00918")
    ).strip().upper()

    return {
        "etf_code": code,
        "master": {
            "sources": [
                {
                    "source_id": "twse_openapi",
                    "display_name": (
                        "臺灣證券交易所 OpenAPI"
                    ),
                }
            ],
            "latest_import_at": (
                "2026-07-30T00:05:00+00:00"
            ),
        },
        "performance": {
            "metric_code": "PRICE_RETURN",
            "sources": [],
            "record_count": 0,
            "available_periods": [],
            "latest_as_of_date": None,
            "latest_import_at": None,
        },
        "dividends": {
            "sources": [
                {
                    "source_id": "official",
                    "display_name": "正式配息來源",
                }
            ],
            "event_count": 0,
            "latest_event_date": None,
            "latest_import_at": None,
        },
        "actual_dividend": {
            "sources": [],
            "actual_component_event_count": 0,
            "actual_76w_event_count": 0,
            "source_document_event_count": 0,
            "latest_source_document_date": None,
            "latest_import_at": None,
        },
    }


page.fetch_etf_by_code = (
    fake_fetch_etf_by_code
)
page.fetch_etf_data_profile = (
    fake_fetch_etf_data_profile
)
page.fetch_etf_performance = (
    fake_fetch_etf_performance
)
page.fetch_etf_dividends = (
    fake_fetch_etf_dividends
)
page.fetch_etf_actual_76w = (
    fake_fetch_etf_actual_76w
)

page.load_etf_detail.clear()
page.load_etf_data_profile.clear()
page.load_etf_performance.clear()
page.load_etf_dividends.clear()
page.load_etf_actual_76w.clear()
page.load_dividend_detail.clear()

page.render_etf_detail()
"""


DIVIDEND_ERROR_PAGE_SCRIPT = """
import frontend.pages.etf_detail as page
page.render_page_title = lambda title: page.st.title(title)

from frontend.api_client import (
    APIResponseError,
)


def fake_fetch_etf_by_code(**kwargs):
    return {
        "code": "00918",
        "name": "大華優利高填息30",
        "is_active": False,
        "is_bond": False,
        "listing_date": "2022-11-24",
        "fund_size": None,
        "expense_ratio": None,
    }


def fake_fetch_etf_performance(**kwargs):
    return {
        "etf_code": "00918",
        "metric_code": "PRICE_RETURN",
        "items": [],
    }


def raise_dividend_error(**kwargs):
    raise APIResponseError(
        "ETF 配息歷史回應格式不正確"
    )


def fake_fetch_etf_actual_76w(**kwargs):
    return {
        "etf_code": "00918",
        "total_dividend_count": 0,
        "actual_76w_record_count": 0,
        "full_76w_count": 0,
        "latest_76w_ratio_pct": None,
        "average_76w_ratio_pct": None,
        "items": [],
    }


def fake_fetch_etf_data_profile(**kwargs):
    code = str(
        kwargs.get("code", "00918")
    ).strip().upper()

    return {
        "etf_code": code,
        "master": {
            "sources": [
                {
                    "source_id": "twse_openapi",
                    "display_name": (
                        "臺灣證券交易所 OpenAPI"
                    ),
                }
            ],
            "latest_import_at": (
                "2026-07-30T00:05:00+00:00"
            ),
        },
        "performance": {
            "metric_code": "PRICE_RETURN",
            "sources": [],
            "record_count": 0,
            "available_periods": [],
            "latest_as_of_date": None,
            "latest_import_at": None,
        },
        "dividends": {
            "sources": [
                {
                    "source_id": "official",
                    "display_name": "正式配息來源",
                }
            ],
            "event_count": 0,
            "latest_event_date": None,
            "latest_import_at": None,
        },
        "actual_dividend": {
            "sources": [],
            "actual_component_event_count": 0,
            "actual_76w_event_count": 0,
            "source_document_event_count": 0,
            "latest_source_document_date": None,
            "latest_import_at": None,
        },
    }


page.fetch_etf_by_code = (
    fake_fetch_etf_by_code
)
page.fetch_etf_data_profile = (
    fake_fetch_etf_data_profile
)
page.fetch_etf_performance = (
    fake_fetch_etf_performance
)
page.fetch_etf_dividends = (
    raise_dividend_error
)
page.fetch_etf_actual_76w = (
    fake_fetch_etf_actual_76w
)

page.load_etf_detail.clear()
page.load_etf_data_profile.clear()
page.load_etf_performance.clear()
page.load_etf_dividends.clear()
page.load_etf_actual_76w.clear()
page.load_dividend_detail.clear()

page.render_etf_detail()
"""


class TestFrontendDividendUI(
    unittest.TestCase
):
    """測試配息格式、分組與 Streamlit 畫面。"""

    def test_missing_and_zero_percent_are_distinct(
        self,
    ) -> None:
        """確認缺資料與正式 0% 顯示不同。"""

        self.assertEqual(
            format_dividend_percentage(
                None
            ),
            "尚未取得",
        )

        self.assertEqual(
            format_dividend_percentage(
                0
            ),
            "0.00%",
        )

    def test_dividend_amount_is_formatted(
        self,
    ) -> None:
        """確認配息金額與幣別顯示。"""

        self.assertEqual(
            format_dividend_amount(
                0.7,
                "twd",
            ),
            "1 NTD",
        )

        self.assertEqual(
            format_dividend_amount(
                None
            ),
            "資料抓取中",
        )

    def test_estimated_gain_is_not_labeled_76w(
        self,
    ) -> None:
        """確認 e添富資本利得不標示為 76W。"""

        label = get_component_display_name(
            {
                "component_code": (
                    "EST_REALIZED_CAPITAL_GAIN"
                ),
                "component_name": (
                    "已實現資本利得"
                ),
            }
        )

        self.assertEqual(
            label,
            "已實現資本利得",
        )

        self.assertNotIn(
            "76W",
            label,
        )

    def test_component_rows_are_grouped_by_basis(
        self,
    ) -> None:
        """確認預估與實際組成分開顯示。"""

        components = [
            {
                "component_code": (
                    "EST_REALIZED_CAPITAL_GAIN"
                ),
                "component_basis": "ESTIMATED",
                "component_name": (
                    "已實現資本利得"
                ),
                "amount_per_unit": None,
                "ratio_pct": 80.0,
                "source_id": "estimated",
            },
            {
                "component_code": "76W",
                "component_basis": "ACTUAL",
                "component_name": "76W",
                "amount_per_unit": 0.5,
                "ratio_pct": 100.0,
                "source_id": "notice",
            },
        ]

        estimated_rows = (
            build_component_display_rows(
                components,
                "ESTIMATED",
                dividend_amount_per_unit=0.6,
                currency="TWD",
            )
        )

        actual_rows = (
            build_component_display_rows(
                components,
                "ACTUAL",
            )
        )

        self.assertEqual(
            len(estimated_rows),
            1,
        )

        self.assertEqual(
            estimated_rows[0]["金額"],
            "0",
        )
        self.assertEqual(
            list(estimated_rows[0]),
            ["組成", "比例", "金額"],
        )

        self.assertEqual(
            len(actual_rows),
            1,
        )

        self.assertEqual(
            actual_rows[0]["金額"],
            "0",
        )

    def test_0050_estimated_components_are_converted_to_amounts(self) -> None:
        """0050 範例依 0.6 元總配息換算，但不改標正式代碼。"""

        rows = build_component_display_rows(
            [
                {
                    "component_code": "EST_DIVIDEND",
                    "component_basis": "ESTIMATED",
                    "component_name": "股利所得",
                    "amount_per_unit": None,
                    "ratio_pct": 26,
                    "source_id": "twse_etfortune_dividend",
                },
                {
                    "component_code": "EST_REALIZED_CAPITAL_GAIN",
                    "component_basis": "ESTIMATED",
                    "component_name": "已實現資本利得",
                    "amount_per_unit": None,
                    "ratio_pct": 74,
                    "source_id": "twse_etfortune_dividend",
                },
            ],
            "ESTIMATED",
            dividend_amount_per_unit=0.6,
            currency="TWD",
        )

        self.assertEqual(rows[0]["金額"], "0")
        self.assertEqual(rows[1]["金額"], "0")
        self.assertEqual(
            rows[1]["組成"],
            "已實現資本利得",
        )
        self.assertNotIn("預估", rows[1]["組成"])

    def test_summary_rows_preserve_period_and_hide_yield_basis(
        self,
    ) -> None:
        """確認年季可由除息日補齊且不顯示殖利率依據。"""

        items = [
            {
                "distribution_period": "2026Q2",
                "amount_per_unit": 0.7,
                "currency": "TWD",
                "yield_pct": 2.8,
                "yield_basis": "OFFICIAL",
                "yield_source_id": "notice",
                "ex_dividend_date": "2026-06-18",
                "payment_date": "2026-07-10",
            },
            {
                "distribution_period": None,
                "amount_per_unit": 0.5,
                "currency": "TWD",
                "yield_pct": 2.0,
                "yield_basis": "CALCULATED",
                "yield_source_id": "twse_stock_day",
                "reference_trade_date": "2026-03-19",
                "reference_close_price": 25.0,
                "ex_dividend_date": "2026-03-20",
                "payment_date": "2026-04-15",
            },
        ]

        rows = build_dividend_summary_rows(
            items
        )

        self.assertEqual(
            rows[0]["年/季"],
            "2026/Q2",
        )
        self.assertEqual(
            rows[0]["殖利率"],
            "2.80%",
        )
        self.assertEqual(
            rows[1]["年/季"],
            "2026/Q1",
        )
        self.assertEqual(rows[0]["現金/股票"], "1/—")
        self.assertEqual(rows[0]["發放日"], "2026-07-10")
        self.assertNotIn("股利發放日", rows[0])
        self.assertNotIn(
            "殖利率依據",
            rows[0],
        )
        self.assertNotIn(
            "殖利率依據",
            rows[1],
        )

    def test_expandable_rows_keep_fixed_visual_column_widths(
        self,
    ) -> None:
        """確認缺值與長值不會改變分隔符號位置。"""

        labels = [
            format_dividend_event_row_label(
                (
                    "年/季",
                    "現金/股票",
                    "殖利率",
                    "除息日",
                    "發放日",
                )
            ),
            format_dividend_event_row_label(
                (
                    "2026/Q3",
                    "0/—",
                    "—",
                    "2026-08-05",
                    "2026-08-31",
                )
            ),
            format_dividend_event_row_label(
                (
                    "2026/Q2",
                    "12.3456/0",
                    "10.84%",
                    "2026-07-09",
                    "2026-07-31",
                )
            ),
        ]

        separator_positions = [
            tuple(
                get_display_width(label[:index])
                for index, character in enumerate(label)
                if character == "｜"
            )
            for label in labels
        ]

        self.assertEqual(
            separator_positions[1:],
            separator_positions[:1] * 2,
        )
        self.assertEqual(separator_positions[0][0], 9)
        for label in labels:
            self.assertEqual(label.count(" ｜ "), 4)
            self.assertEqual(len(label.split(" ｜ ")), 5)

    def test_cash_stock_dividend_preserves_missing_and_zero(self) -> None:
        """未取得股票值保留缺值，正式零值則顯示 0。"""

        self.assertEqual(
            format_cash_stock_dividend(0.12, None),
            "0/—",
        )
        self.assertEqual(
            format_cash_stock_dividend(0.12, 0),
            "0/0",
        )

    def test_dividend_period_falls_back_to_ex_dividend_quarter(self) -> None:
        """官方年季缺少時依除息日顯示 YYYY/Qn。"""

        self.assertEqual(
            format_dividend_period(
                {
                    "distribution_period": None,
                    "ex_dividend_date": "2026-08-05",
                }
            ),
            "2026/Q3",
        )

    def test_summary_charts_aggregate_by_year_without_filling_stock_zero(
        self,
    ) -> None:
        """確認年度圖排序、彙總並保留股票股利缺值。"""

        dividend_rows, yield_rows, stock_available = (
            build_annual_dividend_chart_rows(
                [
                    {
                        "ex_dividend_date": "2026-06-18",
                        "amount_per_unit": 0.7,
                        "yield_pct": None,
                    },
                    {
                        "ex_dividend_date": "2026-03-20",
                        "amount_per_unit": 0.5,
                        "yield_pct": 2.0,
                    },
                    {
                        "ex_dividend_date": "2025-12-18",
                        "amount_per_unit": 0.4,
                        "yield_pct": 1.5,
                    },
                ],
                current_year=2026,
            )
        )

        self.assertEqual(
            list(dict.fromkeys(
                row["年份"]
                for row in dividend_rows
            )),
            [
                "2022",
                "2023",
                "2024",
                "2025",
                "2026",
            ],
        )
        self.assertEqual(
            [
                row["每單位股利"]
                for row in dividend_rows
                if row["股利類型"] == "現金股利"
                and row["每單位股利"] is not None
            ],
            [0.4, 0.5, 0.7],
        )
        self.assertTrue(
            all(
                row["每單位股利"] is None
                for row in dividend_rows
                if row["股利類型"] == "股票股利"
            )
        )
        self.assertFalse(stock_available)
        self.assertEqual(
            yield_rows[4]["殖利率"],
            2.0,
        )
        self.assertEqual(
            yield_rows[4]["已取得筆數"],
            1,
        )
        self.assertEqual(
            yield_rows[4]["配息筆數"],
            2,
        )
        current_year_cash_rows = [
            row
            for row in dividend_rows
            if row["年份"] == "2026"
            and row["股利類型"] == "現金股利"
        ]
        self.assertEqual(
            [
                row["累計股利"]
                for row in current_year_cash_rows
            ],
            [0.5, 1.2],
        )
        self.assertEqual(
            [
                row["顯示分隔線"]
                for row in current_year_cash_rows
            ],
            [True, False],
        )
        self.assertEqual(
            [
                row["年度股利合計"]
                for row in current_year_cash_rows
            ],
            [0.5, 1.2],
        )
        self.assertEqual(
            [
                row["顯示年度合計"]
                for row in current_year_cash_rows
            ],
            [False, True],
        )

    def test_chart_axis_upper_bound_adds_one_nice_tick_above_maximum(
        self,
    ) -> None:
        """Y 軸需高於最大值，並保留易讀的整齊刻度。"""

        self.assertEqual(chart_axis_upper_bound([0.24]), 0.25)
        self.assertEqual(chart_axis_upper_bound([0.84]), 1.0)
        self.assertEqual(chart_axis_upper_bound([0.25]), 0.3)

    def test_detail_page_renders_dividend_sections(
        self,
    ) -> None:
        """確認 ETF 詳細頁顯示配息與 76W。"""

        app = AppTest.from_string(
            DETAIL_DIVIDEND_PAGE_SCRIPT,
            default_timeout=10,
        )

        app.query_params["code"] = "00918"

        app.run()

        self.assertEqual(
            len(app.exception),
            0,
        )

        subheaders = [
            item.value
            for item in app.subheader
        ]

        self.assertIn(
            "配息資料",
            subheaders,
        )

        self.assertIn(
            "資本利得組成 (76W) 統計",
            subheaders,
        )

        self.assertNotIn(
            "配息歷史與組成",
            subheaders,
        )

        expander_labels = [
            item.label
            for item in app.expander
        ]
        self.assertTrue(
            any(
                "2026/Q2" in label
                and "1/—" in label
                and "2.80%" in label
                for label in expander_labels
            )
        )

        self.assertNotIn(
            "每月領息分布",
            subheaders,
        )

        metric_values = [
            str(item.value)
            for item in app.metric
        ]

        self.assertIn(
            "2 次",
            metric_values,
        )

        self.assertIn(
            "1/—",
            metric_values,
        )

        self.assertIn(
            "100.00%",
            metric_values,
        )

        self.assertIn(
            "90.00%",
            metric_values,
        )

    def test_missing_actual_76w_shows_explicit_message(
        self,
    ) -> None:
        """確認沒有正式 76W 時不顯示 0%。"""

        app = AppTest.from_string(
            MISSING_76W_PAGE_SCRIPT,
            default_timeout=10,
        )

        app.query_params["code"] = "0050"

        app.run()

        self.assertEqual(
            len(app.exception),
            0,
        )

        info_messages = [
            item.value
            for item in app.info
        ]

        self.assertTrue(
            any(
                "尚未取得可用的正式 76W"
                in message
                for message in info_messages
            )
        )

        metric_values = [
            str(item.value)
            for item in app.metric
        ]

        self.assertNotIn(
            "0.00%",
            metric_values,
        )

    def test_estimated_composite_populates_capital_gain_analysis(self) -> None:
        """正式 76W 缺少時仍顯示 e添富替代比例且不改標正式資料。"""

        app = AppTest.from_string(
            """
from frontend.pages.etf_detail import render_actual_76w_summary

render_actual_76w_summary({
    "actual_76w_record_count": 0,
    "full_76w_count": 0,
    "latest_76w_ratio_pct": None,
    "average_76w_ratio_pct": None,
    "analysis_record_count": 1,
    "analysis_actual_count": 0,
    "analysis_estimated_fallback_count": 1,
    "full_realized_gain_count": 0,
    "latest_realized_gain_ratio_pct": 68.0,
    "average_realized_gain_ratio_pct": 68.0,
}, show_owner_details=True)
""",
            default_timeout=10,
        )
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertIn(
            "資本利得組成 (76W) 統計",
            [item.value for item in app.subheader],
        )
        self.assertIn(
            "68.00%",
            [str(item.value) for item in app.metric],
        )
        self.assertTrue(
            any(
                "e添富替代 1 次" in item.value
                for item in app.caption
            )
        )
        self.assertFalse(
            any(
                "尚未取得可用" in item.value
                for item in app.info
            )
        )

    def test_public_capital_gain_analysis_hides_owner_details(self) -> None:
        """公開頁保留指標，但不顯示選擇器與分析基礎診斷。"""

        app = AppTest.from_string(
            """
from frontend.pages.etf_detail import render_actual_76w_summary

render_actual_76w_summary({
    "analysis_record_count": 6,
    "analysis_actual_count": 0,
    "analysis_estimated_fallback_count": 6,
    "full_realized_gain_count": 0,
    "latest_realized_gain_ratio_pct": 74.0,
    "average_realized_gain_ratio_pct": 66.19,
})
""",
            default_timeout=10,
        )
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertIn(
            "74.00%",
            [str(item.value) for item in app.metric],
        )
        captions = [item.value for item in app.caption]
        self.assertFalse(
            any("每次配息優先" in value for value in captions)
        )
        self.assertFalse(
            any("分析基礎" in value for value in captions)
        )

    def test_dividend_api_error_does_not_crash_page(
        self,
    ) -> None:
        """確認配息 API 錯誤不使詳細頁崩潰。"""

        app = AppTest.from_string(
            DIVIDEND_ERROR_PAGE_SCRIPT,
            default_timeout=10,
        )

        app.query_params["code"] = "00918"

        app.run()

        self.assertEqual(
            len(app.exception),
            0,
        )

        warning_messages = [
            item.value
            for item in app.warning
        ]

        self.assertTrue(
            any(
                "無法取得 ETF 配息歷史"
                in message
                for message in warning_messages
            )
        )

        headers = [
            item.value
            for item in app.header
        ]

        self.assertTrue(
            any(
                "00918" in header
                for header in headers
            )
        )


if __name__ == "__main__":
    unittest.main()
