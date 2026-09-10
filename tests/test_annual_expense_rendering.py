"""Real Streamlit expense renderer acceptance."""
import unittest
from streamlit.testing.v1 import AppTest
from tests.test_annual_expense import observation


class TestAnnualExpenseRendering(unittest.TestCase):
    def test_search_and_comparison_keep_the_historical_year(self):
        from frontend.pages.etf_search import format_etf_result_row
        from frontend.pages.etf_comparison import build_identity_rows
        payload = dict(code="0056", name="Synthetic fund", is_active=False,
                       is_bond=False, listing_date="2007-12-26", fund_size=None,
                       expense_ratio=.57, annual_expense=observation().model_dump(mode="json"))
        search = format_etf_result_row(payload)["expense_ratio"]
        comparison = build_identity_rows({"items": [{"etf": payload}]})[0]["費用率"]
        for value in (search, comparison):
            self.assertIn("2025", value)
            self.assertIn("歷史總費用", value)

    def test_detail_information_includes_dated_expense(self):
        payload = dict(code="0056", name="Synthetic fund", is_active=False,
                       is_bond=False, listing_date="2007-12-26", fund_size=None,
                       expense_ratio=.57, annual_expense=observation().model_dump(mode="json"))
        app = AppTest.from_string(
            "from frontend.pages.etf_detail import render_etf_information\n"
            f"render_etf_information({payload!r})"
        ).run(timeout=30)
        self.assertFalse(app.exception)
        metric = next(x for x in app.metric if "2025" in x.label)
        self.assertIn("0.57", metric.value)
        self.assertEqual(app.get("link_button")[0].proto.url,
                         payload["annual_expense"]["source_url"])

    def test_historical_year_zero_and_source_are_visible(self):
        payload = {"expense_ratio": 0, "annual_expense": observation(expense_ratio_pct="0").model_dump(mode="json")}
        app = AppTest.from_string(
            "from frontend.pages.etf_detail import render_annual_expense\n"
            f"render_annual_expense({payload!r})"
        ).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertIn("2025", app.metric[0].label)
        self.assertIn("0.00", app.metric[0].value)
        self.assertTrue(any("不代表目前" in x.value for x in app.caption))
        self.assertEqual(app.get("link_button")[0].proto.url, payload["annual_expense"]["source_url"])

    def test_legacy_value_warns_and_missing_is_not_zero(self):
        for value in (.5, None):
            payload = {"expense_ratio": value}
            app = AppTest.from_string(
                "from frontend.pages.etf_detail import render_annual_expense\n"
                f"render_annual_expense({payload!r})"
            ).run(timeout=30)
            self.assertFalse(app.exception)
            if value is not None:
                self.assertTrue(any("未附年度" in x.value for x in app.caption))
            else:
                self.assertNotIn("0.00", app.metric[0].value)
