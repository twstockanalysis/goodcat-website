"""Presentation-only safeguards for optional plan metadata."""

from copy import deepcopy
import unittest

from streamlit.testing.v1 import AppTest

from frontend.ui.planning_metrics import build_planning_metric_rows, FIELDS


def sample():
    plans = [{"strategy": key, "label": label,
              "result": {"status": "TARGET_MET", "target_months": [1, 7]}}
             for key, label in (("RECOMMENDED", "資金精簡"), ("BALANCED", "穩定均衡"))]
    entries = [{"plan_key": p["strategy"], "metrics": {
        "methodology": "DESCRIPTIVE_PLAN_METRICS_V5_4", "mode": "CASH_TARGET",
        "amount_basis": "DISPLAYED_RESPONSE_AMOUNTS", "source_status": "TARGET_MET",
        "target_attainment": "MET", "selected_months": [1, 7],
        **{field: str(index * 10) for field, _ in FIELDS}, "issues": [],
    }} for index, p in enumerate(plans)]
    return {"plans": plans, "plan_metrics": entries}


class TestFrontendPlanningMetrics(unittest.TestCase):
    def test_key_matching_and_immutable_order(self):
        payload = sample()
        payload["plan_metrics"].reverse()
        before = deepcopy(payload)
        rows = build_planning_metric_rows(payload)
        self.assertEqual(list(rows[0]), ["指標", "1. 資金精簡", "2. 穩定均衡"])
        self.assertEqual(rows[2]["1. 資金精簡"], "0.00")
        self.assertEqual(rows[2]["2. 穩定均衡"], "10.00")
        self.assertEqual(payload, before)

    def test_missing_and_invalid_values_are_not_zero(self):
        for value in (None, "NaN", "Infinity", "-1", True, {}, "oops"):
            payload = sample()
            payload["plan_metrics"][0]["metrics"]["minimum_month_cash_twd"] = value
            self.assertEqual(build_planning_metric_rows(payload)[2]["1. 資金精簡"], "未提供")

    def test_absent_duplicate_and_malformed_metadata(self):
        for entries in (None, {}, [], [None], sample()["plan_metrics"] * 2):
            payload = sample()
            payload["plan_metrics"] = entries
            self.assertEqual(build_planning_metric_rows(payload)[2]["1. 資金精簡"], "未提供")

    def test_mismatched_metadata_is_unavailable(self):
        for field, value in (("mode", "BUDGET"), ("source_status", "PARTIAL"),
                             ("target_attainment", "NOT_MET"), ("selected_months", [1]),
                             ("amount_basis", "EXACT"), ("methodology", "UNKNOWN")):
            payload = sample()
            payload["plan_metrics"][0]["metrics"][field] = value
            self.assertEqual(build_planning_metric_rows(payload)[2]["1. 資金精簡"], "未提供")

    def test_unavailable_plan_suppresses_even_supplied_numbers(self):
        payload = sample()
        payload["plans"][0]["result"]["status"] = "UNAVAILABLE"
        payload["plan_metrics"][0]["metrics"].update(source_status="UNAVAILABLE", target_attainment="UNAVAILABLE")
        rows = build_planning_metric_rows(payload)
        self.assertEqual(rows[1]["1. 資金精簡"], "資料不足")
        self.assertEqual(rows[7]["1. 資金精簡"], "0.00")
        self.assertTrue(all(r["1. 資金精簡"] == "未提供"
                            for i, r in enumerate(rows[2:-1], 2) if i != 7))

    def test_percentage_bounds_and_reasons(self):
        payload = sample()
        m = payload["plan_metrics"][0]["metrics"]
        m.update(capital_usage_pct="101", issues=[{"message": "上限未提供"}])
        rows = build_planning_metric_rows(payload)
        self.assertEqual(rows[9]["1. 資金精簡"], "未提供")
        self.assertIn("上限未提供", rows[-1]["1. 資金精簡"])

    def test_native_streamlit_render(self):
        app = AppTest.from_string('''
from tests.test_frontend_planning_metrics import sample
from frontend.ui.planning_metrics import render_planning_metrics
render_planning_metrics(sample())
''').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.dataframe), 1)
        self.assertEqual(app.dataframe[0].value.iloc[2, 1], "0.00")
        self.assertIn("不加權", app.caption[0].value)

    def test_result_page_with_metrics_keeps_original_details(self):
        from tests.test_frontend_public_planner_ui import ALLOCATION_RESULT_SCRIPT
        prefix = '''
from frontend.pages.public_planner import render_allocation_results as actual_render
from tests.test_frontend_planning_metrics import sample
def render_with_metrics(payload):
    payload['plan_metrics'] = []
    for plan in payload['plans']:
        result = plan['result']
        result['target_months'] = [row['month'] for row in result['monthly_results']]
        metric = sample()['plan_metrics'][0]['metrics']
        metric.update(source_status=result['status'], target_attainment='NOT_MET',
                      selected_months=result['target_months'])
        payload['plan_metrics'].append({'plan_key': plan['strategy'], 'metrics': metric})
    actual_render(payload)
'''
        script = prefix + ALLOCATION_RESULT_SCRIPT.replace('render_allocation_results(', 'render_with_metrics(')
        app = AppTest.from_string(script).run()
        self.assertEqual(len(app.exception), 0)
        tables = [table.value for table in app.dataframe]
        comparison = next(table for table in tables if '指標' in table.columns)
        self.assertEqual(comparison.iloc[1, 1], '未達標')
        self.assertEqual(comparison.iloc[2, 1], '0.00')
        self.assertGreater(len(tables), 1)


if __name__ == "__main__":
    unittest.main()
