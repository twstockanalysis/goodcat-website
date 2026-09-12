"""Descriptive metrics must not select, grade, mutate or fill missing plans."""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_database_path
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.main import create_app
from backend.app.models.allocation_results import AllocationResultsRequest
from backend.app.models.budget_allocation import BudgetAllocationRequest
from backend.app.models.planning_metrics import PlanningMetrics
from backend.app.services.allocation_results import build_allocation_results
from backend.app.services.budget_allocation import build_budget_allocation, build_budget_results
from backend.app.services.integer_allocation import build_integer_allocation
from backend.app.services.planning_metrics import summarize_budget_plan, summarize_cash_target_plan
from tests import test_integer_allocation as fixtures


class TestPlanningMetrics(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "metrics.db"
        initialize_database(self.database_path)
        fixtures.TestIntegerAllocation._insert_ready_etfs(self, 2)
        self.day = date(2026, 1, 1)

    def budget(self, **updates):
        request = BudgetAllocationRequest(**({"investable_budget_twd": 100, "selected_months": [1]} | updates))
        return build_budget_allocation(request, self.database_path, as_of_date=self.day)

    def cash(self, **updates):
        request = AllocationResultsRequest(**({"target_after_tax_cash_twd": 5, "target_months": [1]} | updates))
        return build_integer_allocation(request, self.database_path, as_of_date=self.day)

    def test_budget_use_and_original_positions_are_not_a_grade(self):
        result = self.budget(investable_budget_twd=110, existing_holdings=[{"etf_code": "T0000", "held_units": 100}])
        original = result.model_dump()
        metrics = summarize_budget_plan(result)
        self.assertEqual(metrics.target_attainment, "NOT_APPLICABLE")
        self.assertIsNone(metrics.total_shortfall_twd)
        self.assertIsNone(metrics.total_overshoot_twd)
        self.assertEqual(metrics.additional_capital_twd, 100)
        self.assertEqual(metrics.remaining_capital_twd, 10)
        self.assertEqual(metrics.capital_usage_pct, Decimal("90.91"))
        self.assertEqual(metrics.minimum_month_cash_twd, 105)
        self.assertEqual(metrics.total_selected_month_cash_twd, 105)
        self.assertEqual(metrics.month_cash_spread_twd, 0)
        self.assertEqual(metrics.resulting_etf_count, 1)
        self.assertEqual(metrics.max_resulting_position_pct, 100)
        self.assertEqual(result.model_dump(), original)
        self.assertEqual(PlanningMetrics.model_validate_json(metrics.model_dump_json()), metrics)
        for forbidden in ("score", "grade", "weight", "risk_level", "suitability"):
            self.assertNotIn(forbidden, metrics.model_dump())

    def test_zero_budget_empty_portfolio_is_not_zero_concentration(self):
        metrics = summarize_budget_plan(self.budget(investable_budget_twd=0))
        self.assertEqual(metrics.additional_capital_twd, 0)
        self.assertEqual(metrics.remaining_capital_twd, 0)
        self.assertIsNone(metrics.capital_usage_pct)
        self.assertEqual(metrics.added_etf_count, 0)
        self.assertEqual(metrics.resulting_etf_count, 0)
        self.assertIsNone(metrics.max_resulting_position_pct)
        self.assertIn("ZERO_CAPITAL_DENOMINATOR", {i.code for i in metrics.issues})
        self.assertIn("NO_RESULTING_POSITIONS", {i.code for i in metrics.issues})

    def test_cash_target_status_not_rounded_amount_decides_attainment(self):
        result = self.cash(max_additional_capital_twd=80)
        self.assertEqual(result.status, "PARTIAL")
        metrics = summarize_cash_target_plan(result, existing_codes=[])
        self.assertEqual(metrics.target_attainment, "NOT_MET")
        self.assertEqual(metrics.total_shortfall_twd, 1)
        self.assertEqual(metrics.capital_usage_pct, 100)
        # The existing solver can have a sub-cent shortfall displayed as zero.
        rounded = result.model_copy(update={"monthly_results": [result.monthly_results[0].model_copy(
            update={"modeled_after_tax_cash": Decimal(5), "shortfall": Decimal(0)},
        )]})
        self.assertEqual(summarize_cash_target_plan(rounded, existing_codes=[]).target_attainment, "NOT_MET")

    def test_cash_zero_target_and_omitted_cap(self):
        result = self.cash(target_after_tax_cash_twd=0)
        metrics = summarize_cash_target_plan(result, existing_codes=[])
        self.assertEqual(metrics.target_attainment, "MET")
        self.assertEqual(metrics.total_shortfall_twd, 0)
        self.assertIsNone(metrics.capital_limit_twd)
        self.assertIsNone(metrics.remaining_capital_twd)
        self.assertIsNone(metrics.capital_usage_pct)
        self.assertIn("NO_CAPITAL_LIMIT", {i.code for i in metrics.issues})

    def test_original_only_concentration_and_zero_cash_cap(self):
        holdings = [{"etf_code": "T0000", "held_units": 100},
                    {"etf_code": "T0001", "held_units": 1}]
        result = self.budget(investable_budget_twd=0, existing_holdings=holdings)
        metrics = summarize_budget_plan(result)
        self.assertEqual(metrics.added_etf_count, 0)
        self.assertEqual(metrics.resulting_etf_count, 2)
        self.assertEqual(metrics.max_resulting_position_pct, max(h.allocation_pct for h in result.resulting_holdings))
        self.assertLess(metrics.max_resulting_position_pct, 100)
        cash = summarize_cash_target_plan(self.cash(max_additional_capital_twd=0), existing_codes=[])
        self.assertEqual(cash.target_attainment, "NOT_MET")
        self.assertEqual(cash.remaining_capital_twd, 0)
        self.assertIsNone(cash.capital_usage_pct)

    def test_selected_month_summaries_and_overshoot(self):
        result = self.cash()
        row = result.monthly_results[0]
        result = result.model_copy(update={"target_months": [1, 2], "monthly_results": [
            row.model_copy(update={"modeled_after_tax_cash": Decimal(8)}),
            row.model_copy(update={"month": 2, "modeled_after_tax_cash": Decimal(5)}),
        ]})
        metrics = summarize_cash_target_plan(result, existing_codes=[])
        self.assertEqual((metrics.minimum_month_cash_twd, metrics.maximum_month_cash_twd,
                          metrics.total_selected_month_cash_twd, metrics.month_cash_spread_twd), (5, 8, 13, 3))
        self.assertEqual(metrics.total_overshoot_twd, 3)
        incomplete = result.model_copy(update={"monthly_results": [row]})
        missing = summarize_cash_target_plan(incomplete, existing_codes=[])
        self.assertIsNone(missing.total_selected_month_cash_twd)
        self.assertIsNone(missing.total_shortfall_twd)

    def test_unavailable_is_not_fabricated_zero_or_poor_grade(self):
        connection = get_connection(self.database_path)
        connection.execute("DELETE FROM etf_daily_close")
        connection.commit()
        connection.close()
        holdings = [{"etf_code": "T0000", "held_units": 2}]
        budget = summarize_budget_plan(self.budget(existing_holdings=holdings))
        cash = summarize_cash_target_plan(self.cash(existing_holdings=holdings), existing_codes=["T0000"])
        self.assertEqual(budget.target_attainment, "NOT_APPLICABLE")
        self.assertEqual(cash.target_attainment, "UNAVAILABLE")
        for metrics in (budget, cash):
            self.assertEqual(metrics.source_status, "UNAVAILABLE")
            for field in ("minimum_month_cash_twd", "total_selected_month_cash_twd", "additional_capital_twd",
                          "added_etf_count", "resulting_etf_count", "max_resulting_position_pct"):
                self.assertIsNone(getattr(metrics, field))

    def test_absent_original_positions_do_not_imply_empty_portfolio(self):
        result = self.cash().model_copy(update={"resulting_holdings": []})
        metrics = summarize_cash_target_plan(result, existing_codes=["T0000"])
        self.assertIsNone(metrics.resulting_etf_count)
        self.assertIsNone(metrics.max_resulting_position_pct)
        self.assertIn("RESULTING_POSITIONS_UNAVAILABLE", {i.code for i in metrics.issues})

    def test_metrics_follow_selected_plans_without_touching_single_results(self):
        request = AllocationResultsRequest(target_after_tax_cash_twd=5, target_months=[1])
        expected = build_integer_allocation(request, self.database_path, as_of_date=self.day)
        result = build_allocation_results(request, self.database_path, as_of_date=self.day)
        self.assertEqual(result.plans[0].result, expected)
        self.assertEqual([m.plan_key for m in result.plan_metrics], [p.strategy for p in result.plans])
        budget_request = BudgetAllocationRequest(investable_budget_twd=100, selected_months=[1])
        budget = build_budget_results(budget_request, self.database_path, as_of_date=self.day)
        self.assertEqual(budget.primary, self.budget())
        self.assertEqual([m.plan_key for m in budget.plan_metrics],
                         [p.objective for p in [budget.primary, *budget.alternatives]])
        self.assertNotIn("plan_metrics", expected.model_dump())
        self.assertNotIn("plan_metrics", budget.primary.model_dump())

    def test_api_additive_metrics_and_request_boundary(self):
        app = create_app(public_rate_limit=1000)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        client = TestClient(app)
        for endpoint, module, payload in (
            ("allocation-results", "allocation_results", {"target_after_tax_cash_twd": 5, "target_months": [1]}),
            ("budget-results", "budget_allocation", {"investable_budget_twd": 100, "selected_months": [1]}),
        ):
            path = "/api/v1/allocation-plans/" + endpoint
            with patch("backend.app.services." + module + ".date") as clock:
                clock.today.return_value = self.day
                response = client.post(path, json=payload)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertGreater(len(response.json()["plan_metrics"]), 0)
            self.assertEqual(client.post(path, json=payload | {"plan_metrics": []}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
