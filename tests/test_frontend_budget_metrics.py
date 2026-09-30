"""Budget comparison preserves backend identity and missing-value semantics."""
from copy import deepcopy
import unittest

from streamlit.testing.v1 import AppTest
from frontend.pages.budget_planner import LABELS
from frontend.ui.planning_metrics import build_budget_metric_rows, FIELDS


def sample():
    plans = [{"objective": key, "status": "AVAILABLE", "selected_months": [1, 7]}
             for key in LABELS]
    entries = [{"plan_key": p["objective"], "metrics": {
        "methodology": "DESCRIPTIVE_PLAN_METRICS_V5_4", "mode": "BUDGET",
        "amount_basis": "DISPLAYED_RESPONSE_AMOUNTS", "source_status": "AVAILABLE",
        "target_attainment": "NOT_APPLICABLE", "selected_months": [1, 7],
        **{field: str(i * 10) for field, _ in FIELDS}, "issues": [],
    }} for i, p in enumerate(plans)]
    return {"primary": plans[0], "alternatives": plans[1:], "plan_metrics": entries}


class TestBudgetMetrics(unittest.TestCase):
    def test_order_identity_and_nonmutation(self):
        payload = sample()
        payload['plan_metrics'].reverse()
        before = deepcopy(payload)
        rows = build_budget_metric_rows(payload, LABELS)
        self.assertEqual(list(rows[0])[1:], [f'{i}. {label}' for i, label in enumerate(LABELS.values(), 1)])
        self.assertEqual(list(rows[2].values())[1:], ['0.00', '10.00', '20.00'])
        self.assertTrue(all('不適用' in v for v in list(rows[1].values())[1:]))
        self.assertEqual(payload, before)

    def test_absent_duplicate_and_mismatched_metadata(self):
        for entries in (None, [], {}, [None], sample()['plan_metrics'] * 2):
            payload = sample()
            payload['plan_metrics'] = entries
            self.assertEqual(list(build_budget_metric_rows(payload, LABELS)[2].values())[1], '未提供')
        for field, value in [('mode', 'CASH_TARGET'), ('source_status', 'NO_ADDITIONS'),
                             ('target_attainment', 'MET'), ('selected_months', [1]),
                             ('methodology', 'unknown'), ('amount_basis', 'unknown')]:
            payload = sample()
            payload['plan_metrics'][0]['metrics'][field] = value
            self.assertEqual(list(build_budget_metric_rows(payload, LABELS)[2].values())[1], '未提供')

    def test_zero_budget_and_unavailable(self):
        payload = sample()
        metric = payload['plan_metrics'][0]['metrics']
        metric.update(capital_usage_pct=None, issues=[{'message': '零預算無法計算使用率'}])
        rows = build_budget_metric_rows(payload, LABELS)
        self.assertEqual(list(rows[7].values())[1], '0.00')
        self.assertEqual(list(rows[9].values())[1], '未提供')
        self.assertIn('零預算', list(rows[-1].values())[1])
        payload['primary']['status'] = 'UNAVAILABLE'
        metric['source_status'] = 'UNAVAILABLE'
        rows = build_budget_metric_rows(payload, LABELS)
        self.assertTrue(all(list(r.values())[1] == '未提供' for i, r in enumerate(rows[2:-1], 2) if i != 7))
        self.assertIn('不適用', list(rows[1].values())[1])

    def test_omitted_alternatives_do_not_create_columns(self):
        payload = sample()
        payload['alternatives'] = []
        self.assertEqual(len(build_budget_metric_rows(payload, LABELS)[0]), 2)

    def test_native_render(self):
        app = AppTest.from_string('''
from tests.test_frontend_budget_metrics import sample
from frontend.pages.budget_planner import LABELS
from frontend.ui.planning_metrics import render_budget_metrics
render_budget_metrics(sample(), LABELS)
''').run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[2, 1], '0.00')
