"""V4-3 公開股利試算頁資訊架構測試。"""

import unittest
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from PIL import Image
from streamlit.testing.v1 import AppTest

from frontend.pages.public_planner import (
    ANNUAL_DIVIDEND_CREDIT_CAP_TWD,
    DEFAULT_HISTORY_YEARS,
    MARGINAL_TAX_RATE_OPTIONS,
    MONTH_OPTIONS,
    PLANNER_GOODCAT_HERO_FILENAMES,
    PLANNER_WORKING_GOODCAT_FRAME_INTERVAL_SECONDS,
    PLANNER_WORKING_GOODCAT_FRAMES,
    get_planner_goodcat_hero_filename,
    get_planner_working_goodcat_frame,
    fetch_portfolio_projections_with_working_animation,
    render_allocation_results,
    render_planner_goodcat,
    render_public_planner,
)
from frontend.ui.goodcat import GOODCAT_ASSET_DIRECTORY, GoodCatState
from frontend.ui.theme import GLOBAL_STYLES


PLANNER_PAGE_SCRIPT = """
import frontend.pages.public_planner as page

page.render_page_title = lambda title: page.st.title(title)
page.render_public_planner()
"""

PLANNER_API_ERROR_SCRIPT = """
from unittest.mock import patch

from frontend.api.errors import APIClientError
import frontend.pages.public_planner as page

page.render_page_title = lambda title: page.st.title(title)

with patch(
    "frontend.pages.public_planner.fetch_portfolio_projections",
    side_effect=APIClientError("offline"),
):
    page.render_public_planner()
"""

ALLOCATION_RESULT_SCRIPT = """
from frontend.pages.public_planner import render_allocation_results

render_allocation_results(
    {
        "estimate_label": "依歷史資料建立的配置情境。",
        "plans": [
            {
                "strategy": "RECOMMENDED",
                "label": "資金精簡方案",
                "simple_explanation": "依現金流缺口與所需資金產生。",
                "result": {
                    "status": "PARTIAL",
                    "optimality": "BOUNDED_BEST_EFFORT",
                    "snapshot_id": "sha256:test",
                    "total_required_additional_capital": "3500",
                    "additions": [
                        {
                            "etf_code": "0056",
                            "name": "元大高股息",
                            "additional_shares": 100,
                            "required_capital": "3500",
                            "supported_target_months": [1, 7],
                            "reasons": ["用來縮小 1 月與 7 月的現金流缺口。"],
                            "risks": ["部分歷史證據仍不足。"],
                            "historical_quality_grade": {
                                "status": "UNRATED",
                                "grade": None,
                                "explanation": "市場校準尚未達到發布門檻。",
                                "strengths": [],
                                "unavailable_evidence": ["可信樣本不足。"],
                            },
                        }
                    ],
                    "monthly_results": [
                        {
                            "month": 1,
                            "current_after_tax_cash": "0",
                            "added_after_tax_cash": "100",
                            "modeled_after_tax_cash": "100",
                            "target_after_tax_cash": "100",
                            "shortfall": "0",
                        },
                        {
                            "month": 7,
                            "current_after_tax_cash": "0",
                            "added_after_tax_cash": "50",
                            "modeled_after_tax_cash": "50",
                            "target_after_tax_cash": "100",
                            "shortfall": "50",
                        },
                    ],
                    "resulting_holdings": [],
                    "issues": [{"message": "7 月仍有缺口。"}],
                    "assumptions": {"transaction_cost_note": "交易成本固定以 0 元試算。"},
                },
            }
        ],
        "strategy_issues": [{"message": "成分股資料不足，暫無其他方案。"}],
        "excluded_candidates": [
            {
                "etf_code": "00999",
                "name": "測試 ETF",
                "reasons": [{"message": "總報酬資料不足。"}],
            }
        ],
    }
)
"""


class TestFrontendPublicPlannerUI(unittest.TestCase):
    def test_working_animation_alternates_dark_theme_frames_each_second(
        self,
    ) -> None:
        expected_result = {"status": "ok"}
        future = MagicMock()
        future.result.side_effect = [TimeoutError(), expected_result]
        executor = MagicMock()
        executor.__enter__.return_value.submit.return_value = future
        goodcat_slot = MagicMock()

        with (
            patch(
                "frontend.pages.public_planner.ThreadPoolExecutor",
                return_value=executor,
            ),
            patch(
                "frontend.pages.public_planner.st.context",
                SimpleNamespace(theme=SimpleNamespace(type="dark")),
            ),
            patch(
                "frontend.pages.public_planner.render_planner_goodcat"
            ) as render_goodcat,
        ):
            result = fetch_portfolio_projections_with_working_animation(
                "http://api.test",
                {"target": 1},
                goodcat_slot,
            )

        self.assertEqual(result, expected_result)
        future.result.assert_has_calls(
            [call(timeout=1.0), call(timeout=1.0)]
        )
        render_goodcat.assert_has_calls(
            [
                call(
                    goodcat_slot,
                    GoodCatState.WORKING,
                    "咪正在努力核對中",
                    asset_filename="goodcat-researching-white-hero.png",
                ),
                call(
                    goodcat_slot,
                    GoodCatState.WORKING,
                    "資料好多，喵覺得累",
                    asset_filename=(
                        "goodcat-researching-tired-white-hero.png"
                    ),
                ),
            ]
        )

    def test_allocation_result_separates_owner_fit_from_etf_quality(self) -> None:
        app = AppTest.from_string(ALLOCATION_RESULT_SCRIPT, default_timeout=10)
        app.run()

        self.assertEqual(len(app.exception), 0)
        page_text = "\n".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
        )
        self.assertIn("主人目標適配只針對本次輸入", page_text)
        self.assertIn("這是 ETF 喵喵評等，不代表一定適合每位主人", page_text)
        self.assertIn("為什麼放進這個配置", page_text)
        self.assertNotIn("quality_score", page_text)
        self.assertNotIn("confidence", page_text)

        metric_labels = [item.label for item in app.metric]
        self.assertIn("新增所需資金", metric_labels)
        self.assertIn("達標月份", metric_labels)
        self.assertIn("尚缺總額", metric_labels)
        self.assertIn("增加股數", metric_labels)

        source = getsource(render_allocation_results)
        self.assertIn("查看配置後持股與計算假設", source)
        self.assertIn("為什麼沒有更多不同方案", source)
        self.assertIn("查看未納入的 ETF", source)

    def test_primary_inputs_follow_beginner_order(self) -> None:
        app = AppTest.from_string(PLANNER_PAGE_SCRIPT, default_timeout=10)
        app.run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "股利試算")

        number_labels = [item.label for item in app.number_input]
        self.assertEqual(
            number_labels[:2],
            [
                "每個目標月想領多少股利 (NTD)",
                "想持有年限",
            ],
        )
        self.assertEqual(app.number_input[0].value, 3000)
        self.assertEqual(app.number_input[1].value, 10)
        self.assertIn(
            "個人所得稅率（115年度級距）",
            [item.label for item in app.selectbox],
        )
        self.assertNotIn(
            "預估個人所得稅率（%）",
            number_labels,
        )
        self.assertFalse(
            any("股利抵減上限" in label for label in number_labels)
        )
        monthly_button = next(item for item in app.button if item.label == "每月")
        self.assertEqual(monthly_button.proto.type, "primary")

        source = getsource(render_public_planner)
        page_text = "\n".join(
            [item.value for item in app.markdown]
            + [item.value for item in app.caption]
        )
        self.assertNotIn("不用自己先挑候選 ETF", page_text)
        self.assertEqual(MONTH_OPTIONS, list(range(1, 13)))
        self.assertEqual(DEFAULT_HISTORY_YEARS, 3)
        self.assertEqual(
            list(MARGINAL_TAX_RATE_OPTIONS.values()),
            [5.0, 12.0, 20.0, 30.0, 40.0],
        )
        self.assertEqual(ANNUAL_DIVIDEND_CREDIT_CAP_TWD, 80_000.0)
        self.assertEqual(
            [item.value for item in app.subheader[:5]],
            [
                ":material/calendar_month: 1. 數錢月份",
                ":material/payments: 2. 罐頭錢目標",
                ":material/timeline: 3. 想持有年限",
                ":material/account_balance_wallet: 4. 主人的庫存",
                "5. 股息再投入與否",
            ],
        )
        self.assertIn("可以點選每月、單數月或雙數月", page_text)
        self.assertIn("咪會用主人的目標去計算", page_text)
        self.assertIn("使用AI預測長期表現", page_text)
        self.assertIn(
            "將持有的ETF輸入，咪可以更精準規劃，也可留白",
            page_text,
        )
        self.assertIn('key="public-planner-month-card"', source)
        self.assertIn('key="public-planner-target-card"', source)
        self.assertIn('key="public-planner-years-card"', source)
        self.assertIn('key="public-planner-holding-card"', source)
        self.assertIn('key="public-planner-reinvestment-card"', source)
        self.assertIn("st.columns([2, 3])", source)
        self.assertIn("range(0, len(MONTH_OPTIONS), 3)", source)
        self.assertIn(
            'key=f"public-planner-month-row-{row_start}"',
            source,
        )
        self.assertIn("horizontal=True", source)
        self.assertNotIn("month_columns = st.columns(3)", source)
        self.assertEqual(
            [item.label for item in app.button if item.label.endswith("月")][-12:],
            [f"{month}月" for month in MONTH_OPTIONS],
        )
        self.assertLess(
            source.index('key="public_planner_add_holding"'),
            source.index("價格自動擷取收盤價"),
        )
        self.assertNotIn('st.pills(', source)
        self.assertIn('on_click=toggle_target_month', source)
        self.assertIn('key="public-planner-guided-form"', source)
        self.assertIn("GoodCatState.ATTENTIVE", source)
        self.assertIn("如果都選完了，就「讓咪開始工作」吧！", source)
        self.assertNotIn("主人告訴咪月份、目標與庫存就好", source)
        working_animation_source = getsource(
            fetch_portfolio_projections_with_working_animation
        )
        self.assertIn("GoodCatState.WORKING", working_animation_source)
        self.assertIn("GoodCatState.CAUTION", source)
        goodcat_source = getsource(render_planner_goodcat)
        self.assertIn("st.columns(\n                [2, 3]", goodcat_source)
        self.assertIn("width=260", goodcat_source)
        self.assertIn("hero_asset_path", goodcat_source)
        self.assertEqual(
            set(PLANNER_GOODCAT_HERO_FILENAMES),
            {
                GoodCatState.ATTENTIVE,
                GoodCatState.WORKING,
                GoodCatState.READY,
                GoodCatState.REWARD,
                GoodCatState.CAUTION,
            },
        )
        self.assertEqual(
            get_planner_goodcat_hero_filename(
                GoodCatState.ATTENTIVE,
                "light",
            ),
            "goodcat-planner-start-hero.png",
        )
        self.assertEqual(
            get_planner_goodcat_hero_filename(
                GoodCatState.ATTENTIVE,
                "dark",
            ),
            "goodcat-planner-start-white-hero.png",
        )
        self.assertEqual(
            get_planner_goodcat_hero_filename(
                GoodCatState.WORKING,
                "dark",
            ),
            "goodcat-researching-white-hero.png",
        )
        self.assertEqual(
            get_planner_goodcat_hero_filename(
                GoodCatState.REWARD,
                "dark",
            ),
            "goodcat-result-reward-white-hero.png",
        )
        self.assertEqual(PLANNER_WORKING_GOODCAT_FRAME_INTERVAL_SECONDS, 1.0)
        self.assertEqual(
            [frame["message"] for frame in PLANNER_WORKING_GOODCAT_FRAMES],
            ["咪正在努力核對中", "資料好多，喵覺得累"],
        )
        self.assertEqual(
            get_planner_working_goodcat_frame(0, "light"),
            ("goodcat-researching-hero.png", "咪正在努力核對中"),
        )
        self.assertEqual(
            get_planner_working_goodcat_frame(1, "dark"),
            (
                "goodcat-researching-tired-white-hero.png",
                "資料好多，喵覺得累",
            ),
        )
        self.assertEqual(
            get_planner_working_goodcat_frame(2, "light"),
            ("goodcat-researching-hero.png", "咪正在努力核對中"),
        )
        for frame in PLANNER_WORKING_GOODCAT_FRAMES:
            self.assertEqual(
                set(frame),
                {"message", "light", "dark"},
            )
            for theme_key in ("light", "dark"):
                filename = frame[theme_key]
                with Image.open(GOODCAT_ASSET_DIRECTORY / filename) as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.size, (1254, 1254))
                    self.assertEqual(image.getpixel((0, 0))[3], 0)
                    self.assertEqual(
                        image.getchannel("A").getextrema(),
                        (0, 255),
                    )
        for theme_mapping in PLANNER_GOODCAT_HERO_FILENAMES.values():
            self.assertEqual(set(theme_mapping), {"light", "dark"})
            for filename in theme_mapping.values():
                self.assertTrue(filename.endswith("-hero.png"))
                with Image.open(GOODCAT_ASSET_DIRECTORY / filename) as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.size, (1254, 1254))
                    self.assertEqual(image.getpixel((0, 0))[3], 0)
                    self.assertEqual(
                        image.getchannel("A").getextrema(),
                        (0, 255),
                    )
        self.assertLess(
            source.index("goodcat_slot = st.empty()"),
            source.index('"讓咪開始工作"'),
        )
        self.assertGreater(
            source.index("goodcat_slot = st.empty()"),
            source.index('st.expander("稅務試算選項")'),
        )
        self.assertIn("查看歷史績效與長期情境", source)
        self.assertIn("年稅務與再投入試算", source)
        self.assertNotIn('st.form(', source)
        self.assertNotIn('st.form_submit_button(', source)
        self.assertIn('num_rows="fixed"', source)
        self.assertIn('width="content"', source)
        self.assertIn('CheckboxColumn(', source)
        self.assertIn('st.expander("稅務試算選項")', source)
        self.assertIn(
            'st.selectbox(\n                    "個人所得稅率（115年度級距）"',
            source,
        )
        self.assertNotIn("今年剩餘股利抵減上限", source)
        self.assertIn("可適用的股利 × 8.5%", source)
        self.assertIn("每戶/年上限 80,000 元", source)
        self.assertIn("help=MARGINAL_TAX_RATE_HELP", source)
        self.assertNotIn("其他配息項目預估稅率", source)
        self.assertIn(
            "僅預估收入來源為股利，喵之後會再增加手動輸入",
            source,
        )
        self.assertIn("薪資所得欄，讓計算更準確", source)
        self.assertIn("other_income_tax_rate = 0.0", source)
        self.assertNotIn('st.expander("稅務假設")', source)
        self.assertNotIn("稅務假設（可調整）", source)
        self.assertNotIn("稅務與再投入假設", source)
        self.assertIn(
            '.st-key-public-planner-holdings [data-testid="stElementToolbar"]',
            GLOBAL_STYLES,
        )
        self.assertIn(
            ".st-key-public-planner-holdings\n"
            ".stDataFrameGlideDataEditor",
            GLOBAL_STYLES,
        )
        self.assertGreater(source.index('"持股"'), source.index("st.data_editor("))
        self.assertIn('alignment="left"', source)

        captions = [item.value for item in app.caption]
        self.assertIn(
            "價格自動擷取收盤價；若盤中，則為前一日收盤價。",
            captions,
        )
        self.assertIn(
            "可調整或依照預設值，咪會算出預計產生的所得稅與二代健保費",
            captions,
        )
        self.assertNotIn("若不調整，系統會依合併計稅", "\n".join(captions))
        self.assertNotIn("本網站提供之數據僅供個人參考", "\n".join(captions))
        self.assertIn('key="public-planner-disclaimer"', source)
        self.assertIn("不構成任何形式之投資建議", source)
        self.assertIn("過往績效不代表未來表現", source)
        self.assertGreater(
            source.index('key="public-planner-disclaimer"'),
            source.index("render_portfolio_projection("),
        )

    def test_odd_month_preset_updates_month_buttons(self) -> None:
        app = AppTest.from_string(PLANNER_PAGE_SCRIPT, default_timeout=10)
        app.run()

        odd_button = next(item for item in app.button if item.label == "單數月")
        odd_button.click().run()

        self.assertEqual(len(app.exception), 0)
        month_button_types = {
            item.label: item.proto.type
            for item in app.button
            if item.label in [f"{month}月" for month in MONTH_OPTIONS]
        }
        self.assertEqual(
            [
                month
                for month in MONTH_OPTIONS
                if month_button_types[f"{month}月"] == "primary"
            ],
            [1, 3, 5, 7, 9, 11],
        )
        monthly_button = next(item for item in app.button if item.label == "每月")
        odd_button = next(item for item in app.button if item.label == "單數月")
        self.assertEqual(monthly_button.proto.type, "secondary")
        self.assertEqual(odd_button.proto.type, "primary")

    def test_delete_action_is_hidden_until_a_holding_is_selected(self) -> None:
        app = AppTest.from_string(PLANNER_PAGE_SCRIPT, default_timeout=10)
        app.run()

        button_labels = [item.label for item in app.button]
        self.assertIn("持股", button_labels)
        self.assertNotIn("刪除已選取（1）", button_labels)

    def test_technical_allocation_inputs_are_not_exposed(self) -> None:
        app = AppTest.from_string(PLANNER_PAGE_SCRIPT, default_timeout=10)
        app.run()

        labels = [item.label for item in app.number_input]
        self.assertNotIn("歷史配息年數", labels)
        self.assertNotIn("配置階段現金扣除率（%）", labels)
        self.assertEqual(len(app.multiselect), 0)

        page_text = "\n".join(
            [item.value for item in app.caption]
            + [item.value for item in app.markdown]
        )
        self.assertIn(
            "咪會算出預計產生的所得稅與二代健保費",
            page_text,
        )

    def test_service_error_keeps_inputs_and_uses_plain_language_caution(self) -> None:
        app = AppTest.from_string(PLANNER_API_ERROR_SCRIPT, default_timeout=10)
        app.run()

        submit = next(
            item for item in app.button if item.label == "讓咪開始工作"
        )
        submit.click().run()

        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.number_input[0].value, 3000)
        self.assertIn(
            "暫時無法完成股利試算，請確認服務已啟動後再試一次。",
            [item.value for item in app.error],
        )
        page_text = "\n".join(item.value for item in app.markdown)
        self.assertIn("主人剛才的輸入仍留在畫面上", page_text)
        self.assertNotIn("offline", page_text)


if __name__ == "__main__":
    unittest.main()
