"""Budget-mode input, state isolation and native rendering acceptance."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest
from frontend.api.errors import APIConnectionError
from frontend.pages.budget_planner import build_budget_request, RESULT, SIGNATURE
from tests import test_frontend_budget_planner_client as fixtures


SCRIPT = '''
import frontend.pages.public_planner as page
page.render_page_title = lambda title: page.st.title(title)
page.render_public_planner()
'''


class TestBudgetUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.TestBudgetClient.setUpClass()
        cls.addClassCleanup(fixtures.TestBudgetClient.doClassCleanups)
        cls.payload = deepcopy(fixtures.TestBudgetClient.responses[1])

    def app(self):
        app = AppTest.from_string(SCRIPT).run()
        app.radio(key='public_planner_mode').set_value('投入預算').run()
        self.assertFalse(app.exception)
        return app

    def test_decimal_request_has_no_target_or_projection(self):
        result = build_budget_request('100.01', [7, 1], [{'etf_code': '0050', 'held_units': 1}])
        self.assertEqual(result['investable_budget_twd'], '100.01')
        self.assertEqual(result['selected_months'], [1, 7])
        self.assertEqual(set(result), {'investable_budget_twd', 'selected_months', 'existing_holdings',
                                       'history_years', 'cash_deduction_rate_pct', 'currency'})
        self.assertEqual(build_budget_request('0', [1], [])['investable_budget_twd'], '0.00')

    def test_invalid_budget_or_months(self):
        for value in ('', '-1', 'NaN', 'Infinity', '1.001', '1e16'):
            with self.assertRaises(ValueError): build_budget_request(value, [1], [])
        with self.assertRaises(ValueError): build_budget_request('100', [], [])

    def test_blank_is_not_default_zero_or_api_call(self):
        app = self.app()
        self.assertEqual(app.text_input(key='budget_amount').value, '')
        with patch('frontend.pages.budget_planner.fetch_budget_results') as fetch:
            app.button(key='budget_submit').click().run()
            fetch.assert_not_called()
        self.assertTrue(app.warning)

    def test_submit_render_then_invalidate_on_edit_and_failure(self):
        app = self.app()
        app.text_input(key='budget_amount').set_value('100').run()
        app.multiselect(key='budget_months').set_value([1, 7]).run()
        with patch('frontend.pages.budget_planner.fetch_budget_results', return_value=self.payload) as fetch:
            app.button(key='budget_submit').click().run()
        self.assertFalse(app.exception)
        self.assertEqual(fetch.call_args.args[1]['investable_budget_twd'], '100.00')
        self.assertIn('預算配置情境', [s.value for s in app.subheader])
        app.text_input(key='budget_amount').set_value('101').run()
        self.assertNotIn(RESULT, app.session_state)
        with patch('frontend.pages.budget_planner.fetch_budget_results', side_effect=APIConnectionError('private')):
            app.button(key='budget_submit').click().run()
        self.assertTrue(app.error)
        self.assertNotIn('private', app.error[0].value)
        self.assertNotIn(RESULT, app.session_state)

    def test_switch_mode_discards_both_results(self):
        app = self.app()
        app.session_state[RESULT] = self.payload
        app.session_state[SIGNATURE] = 'old'
        app.session_state['public_portfolio_projections'] = {'old': True}
        app.radio(key='public_planner_mode').set_value('現金流目標').run()
        self.assertFalse(app.exception)
        self.assertNotIn(RESULT, app.session_state)
        self.assertNotIn('public_portfolio_projections', app.session_state)

    def test_missing_cash_and_existing_holdings_render(self):
        payload = deepcopy(self.payload)
        plan = payload['primary']
        plan.update(status='UNAVAILABLE', resulting_holdings=None,
                    existing_holdings=[{'etf_code': '0050', 'held_units': 10}])
        plan['monthly_results'][0]['modeled_after_tax_cash'] = None
        app = AppTest.from_string('''
import streamlit as st
from frontend.pages.budget_planner import render_budget_results
render_budget_results(st.session_state['payload'])
''')
        app.session_state['payload'] = payload
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.dataframe[0].value.iloc[0]['合計現金流（NTD）'], '尚無資料')
        self.assertTrue(any('不能推論原持股已售出' in c.value for c in app.caption))

    def test_failed_same_input_recalculation_removes_old_result(self):
        app = self.app()
        app.text_input(key='budget_amount').set_value('100').run()
        with patch('frontend.pages.budget_planner.fetch_budget_results', return_value=self.payload):
            app.button(key='budget_submit').click().run()
        self.assertIn(RESULT, app.session_state)
        with patch('frontend.pages.budget_planner.fetch_budget_results', side_effect=APIConnectionError('offline')):
            app.button(key='budget_submit').click().run()
        self.assertNotIn(RESULT, app.session_state)

    def test_alternatives_keep_order_without_target_labels(self):
        payload = deepcopy(self.payload)
        payload['alternatives'] = [deepcopy(payload['primary']) for _ in range(2)]
        for plan, objective in zip(payload['alternatives'], ['MONTHLY_BALANCED', 'TOTAL_MONTH_CASH']):
            plan.update(objective=objective, tradeoff='測試取捨')
        app = AppTest.from_string('''
import streamlit as st
from frontend.pages.budget_planner import render_budget_results
render_budget_results(st.session_state['payload'])
''')
        app.session_state['payload'] = payload
        app.run()
        self.assertFalse(app.exception)
        headings = [m.value for m in app.markdown if m.value.startswith('### ')]
        self.assertEqual(headings, ['### 最低月份現金流優先', '### 月份現金流均衡', '### 所選月份總現金流優先'])


if __name__ == '__main__': unittest.main()
