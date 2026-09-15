"""Target-free frontend boundary and real backend serialization compatibility."""

from copy import deepcopy
from datetime import date
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.database.init_db import initialize_database
from backend.app.models.budget_allocation import BudgetAllocationRequest
from backend.app.services.budget_allocation import build_budget_results
from frontend.api.budget_planner import fetch_budget_results, validate_budget_results
from frontend.api.errors import APIConnectionError, APIResponseError
from tests import test_integer_allocation as allocation_fixtures


class TestBudgetClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        db = Path(cls.temp.name) / 'budget-client.db'
        initialize_database(db)
        allocation_fixtures.TestIntegerAllocation._insert_ready_etfs(SimpleNamespace(database_path=db), 2)
        cls.responses = [build_budget_results(
            BudgetAllocationRequest(investable_budget_twd=budget, selected_months=[1, 7]),
            db, as_of_date=date(2026, 1, 1),
        ).model_dump(mode='json') for budget in (0, 100)]

    def sample(self):
        return deepcopy(self.responses[1])

    def test_real_serialized_backend_and_zero_budget(self):
        for payload in deepcopy(self.responses):
            before = deepcopy(payload)
            self.assertIs(validate_budget_results(payload), payload)
            self.assertEqual(payload, before)

    def test_fetch_route_timeout_and_request_not_modified(self):
        request = {'investable_budget_twd': '100', 'selected_months': [1, 7]}
        before = deepcopy(request)
        with patch('frontend.api.budget_planner.post_json', return_value=self.sample()) as post:
            fetch_budget_results('http://127.0.0.1:8000', request, timeout_seconds=75)
        self.assertEqual(post.call_args.kwargs['endpoint_path'], '/api/v1/allocation-plans/budget-results')
        self.assertEqual(post.call_args.kwargs['timeout_seconds'], 75)
        self.assertIs(post.call_args.kwargs['payload'], request)
        self.assertEqual(request, before)

    def test_transport_errors_propagate(self):
        with patch('frontend.api.budget_planner.post_json', side_effect=APIConnectionError('offline')):
            with self.assertRaises(APIConnectionError):
                fetch_budget_results('http://127.0.0.1:8000', {})

    def test_missing_cash_is_preserved_and_missing_field_rejected(self):
        payload = self.sample()
        payload['primary']['monthly_results'][0]['modeled_after_tax_cash'] = None
        self.assertIsNone(validate_budget_results(payload)['primary']['monthly_results'][0]['modeled_after_tax_cash'])
        del payload['primary']['monthly_results'][0]['modeled_after_tax_cash']
        with self.assertRaises(APIResponseError): validate_budget_results(payload)

    def test_cash_has_no_new_frontend_cap(self):
        payload = self.sample()
        payload['primary']['monthly_results'][0]['modeled_after_tax_cash'] = '1000000000000000000'
        self.assertIs(validate_budget_results(payload), payload)

    def test_invalid_money_reconciliation_and_stateless_flags(self):
        for field, value in (('used_budget_twd', '101'), ('remaining_budget_twd', '999'),
                             ('investable_budget_twd', 'NaN'), ('used_budget_twd', True),
                             ('used_budget_twd', '-1'), ('request_persisted', True),
                             ('broker_connected', True), ('status', 'TARGET_MET')):
            payload = self.sample()
            payload['primary'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(APIResponseError):
                validate_budget_results(payload)

    def test_whole_shares_unique_codes_and_cost(self):
        for field, value in (('additional_shares', 1.5), ('additional_shares', True),
                             ('additional_shares', 0), ('required_capital', '0'),
                             ('reference_price', 'Infinity')):
            payload = self.sample()
            self.assertTrue(payload['primary']['additions'])
            payload['primary']['additions'][0][field] = value
            with self.subTest(field=field), self.assertRaises(APIResponseError): validate_budget_results(payload)
        payload = self.sample()
        payload['primary']['additions'] *= 6
        with self.assertRaises(APIResponseError): validate_budget_results(payload)

    def test_month_alignment_and_target_contamination(self):
        for months in ([7, 1], [1, 1], [True, 7], []):
            payload = self.sample()
            payload['primary']['selected_months'] = months
            with self.assertRaises(APIResponseError): validate_budget_results(payload)
        payload = self.sample()
        payload['primary']['monthly_results'][0]['shortfall'] = '0'
        with self.assertRaises(APIResponseError): validate_budget_results(payload)

    def test_alternate_order_and_same_request(self):
        payload = self.sample()
        alternate = deepcopy(payload['primary'])
        alternate.update(objective='TOTAL_MONTH_CASH', tradeoff='Different objective')
        payload['alternatives'] = [alternate]
        self.assertIs(validate_budget_results(payload), payload)
        for field, value in (('selected_months', [1]), ('snapshot_id', 'different'),
                             ('objective', 'UNKNOWN'), ('existing_holdings', [{}])):
            changed = deepcopy(payload)
            changed['alternatives'][0][field] = value
            with self.assertRaises(APIResponseError): validate_budget_results(changed)
        payload['alternatives'] *= 2
        with self.assertRaises(APIResponseError): validate_budget_results(payload)

    def test_optional_metrics_and_internal_fields(self):
        payload = self.sample()
        del payload['plan_metrics']
        validate_budget_results(payload)
        payload['primary']['issues'].append({'message': 'No confidence or quality_score is published'})
        validate_budget_results(payload)
        payload['primary']['issues'][0]['confidence'] = 1
        with self.assertRaises(APIResponseError): validate_budget_results(payload)

    def test_malformed_containers_have_domain_error(self):
        for payload in (None, [], {}, {'primary': []}, {'primary': {'selected_months': {}}}):
            with self.assertRaises(APIResponseError): validate_budget_results(payload)


if __name__ == '__main__': unittest.main()
