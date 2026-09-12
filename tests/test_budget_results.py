"""Objective-specific budget search, additive API and compatibility evidence."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from pathlib import Path
from random import Random
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_database_path
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.main import create_app
from backend.app.models.budget_allocation import BudgetAllocationRequest
from backend.app.models.budget_results import BudgetResultsResponse
from backend.app.services.budget_allocation import build_budget_allocation, build_budget_results
from backend.app.services.complete_portfolio_solver import (
    _budget_strategy_order, _non_dominated_budget, solve_budget_frontier,
)
from backend.app.services.market_eligibility_index import build_market_eligibility_index
from tests.test_budget_allocation import candidate
from tests import test_integer_allocation as allocation_fixtures


class TestBudgetStrategySolver(unittest.TestCase):
    def test_three_real_objectives_and_balanced_dominance(self):
        inputs = [candidate("A", "10", {1: "10", 2: "20"}),
                  candidate("B", "10", {1: "10", 2: "10"}),
                  candidate("C", "10", {2: "40"})]
        kwargs = dict(selected_months=[1, 2], investable_budget=Decimal(10))
        primary = solve_budget_frontier(inputs, **kwargs).frontier[0]
        self.assertEqual(primary.shares, (("A", 1),))
        for objective, code in (("MONTHLY_BALANCED", "B"), ("TOTAL_MONTH_CASH", "C")):
            result = solve_budget_frontier(inputs, **kwargs, objective=objective, seed_plan=primary)
            self.assertEqual(result.frontier[0].shares, ((code, 1),))
            self.assertEqual(result, solve_budget_frontier(inputs[::-1], **kwargs,
                             objective=objective, seed_plan=primary))
        balanced = solve_budget_frontier(inputs, **kwargs, objective="MONTHLY_BALANCED", seed_plan=primary).frontier[0]
        self.assertEqual(balanced.minimum_month_cash, primary.minimum_month_cash)
        self.assertEqual(balanced.month_imbalance, 0)
        # Higher cash alone must not eliminate the more balanced plan.
        self.assertIn(balanced, _non_dominated_budget([primary, balanced], "MONTHLY_BALANCED", Decimal(10)))

    def test_seed_is_validated_against_facts_and_bounds(self):
        inputs = [candidate("A", "1", {1: "1"})]
        kwargs = dict(selected_months=[1], investable_budget=Decimal(10))
        seed = solve_budget_frontier(inputs, **kwargs).frontier[0]
        for changes in ({"used_budget": Decimal(9)}, {"monthly_resulting_cash": ((1, Decimal(11)),)},
                        {"shares": (("UNKNOWN", 10),)}, {"shares": (("A", -1),)}):
            with self.assertRaises(ValueError):
                solve_budget_frontier(inputs, **kwargs, objective="MONTHLY_BALANCED", seed_plan=replace(seed, **changes))
        for options in ({"objective": "UNKNOWN"}, {"objective": "MONTHLY_BALANCED"}, {"seed_plan": seed}):
            with self.assertRaises(ValueError):
                solve_budget_frontier(inputs, **kwargs, **options)

    def test_original_cash_exact_floor_rounding_and_bounds_on_seeded_cases(self):
        rng = Random(145)
        for case in range(10):
            inputs = [candidate(str(i), str(Decimal(rng.randrange(1, 20)) / 10),
                                {m: str(Decimal(rng.randrange(8)) / 1000) for m in (1, 2, 3)})
                      for i in range(4)]
            current = {1: Decimal('.004'), 2: Decimal('.027'), 3: Decimal(0)}
            kwargs = dict(selected_months=[1, 2, 3], investable_budget=Decimal(10),
                          current_cash_by_month=current, beam_width=4, max_added_etfs=3)
            seed = solve_budget_frontier(inputs, **kwargs, max_expansions=500).frontier[0]
            for objective in ("MONTHLY_BALANCED", "TOTAL_MONTH_CASH"):
                for limit in (1, 80, 500):
                    result = solve_budget_frontier(inputs, **kwargs, max_expansions=limit,
                                                   objective=objective, seed_plan=seed)
                    plan = result.frontier[0]
                    with self.subTest(case=case, objective=objective, limit=limit):
                        self.assertLessEqual(result.explored_states, limit)
                        self.assertLessEqual(_budget_strategy_order(plan, objective, seed.minimum_month_cash),
                                             _budget_strategy_order(seed, objective, seed.minimum_month_cash))
                        self.assertLessEqual(plan.added_etf_count, 3)
                        self.assertLessEqual(plan.used_budget, 10)
                        prices = {c.etf_code: c.reference_price for c in inputs}
                        displayed = sum((prices[c] * q).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                                        for c, q in plan.shares)
                        self.assertLessEqual(displayed, 10)
                        for m, cash in plan.monthly_resulting_cash:
                            self.assertEqual(cash - dict(plan.monthly_added_cash)[m], current[m])
                        if objective == "MONTHLY_BALANCED":
                            self.assertGreaterEqual(plan.minimum_month_cash, seed.minimum_month_cash)
                            self.assertLessEqual(plan.month_imbalance, seed.month_imbalance)
                        else:
                            self.assertGreaterEqual(plan.total_month_cash, seed.total_month_cash)


class TestBudgetResults(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "results.db"
        initialize_database(self.database_path)

    def seed(self, count=2):
        allocation_fixtures.TestIntegerAllocation._insert_ready_etfs(self, count)

    def request(self, **updates):
        return BudgetAllocationRequest(**({"investable_budget_twd": 100, "selected_months": [1]} | updates))

    def build(self, **updates):
        return build_budget_results(self.request(**updates), self.database_path, as_of_date=date(2026, 1, 1))

    def test_primary_exact_compatibility_single_evidence_load_and_duplicate_disclosure(self):
        self.seed()
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        with patch("backend.app.services.budget_allocation.build_market_eligibility_index",
                   wraps=build_market_eligibility_index) as loader:
            result = self.build()
        self.assertEqual(loader.call_count, 1)
        expected = build_budget_allocation(self.request(), self.database_path, as_of_date=date(2026, 1, 1))
        self.assertEqual(result.primary, expected)
        self.assertEqual(result.alternatives, [])
        self.assertEqual(len(result.alternate_searches), 2)
        self.assertTrue(all(s.duplicate_of == expected.objective for s in result.alternate_searches))
        self.assertEqual(len(result.issues), 2)
        self.assertEqual(BudgetResultsResponse.model_validate_json(result.model_dump_json()), result)
        self.assertEqual(before, hashlib.sha256(self.database_path.read_bytes()).hexdigest())

    def test_zero_no_eligible_and_unavailable_do_not_manufacture_strategies(self):
        for updates in ({}, {"investable_budget_twd": 0}):
            result = self.build(**updates)
            self.assertEqual(result.alternatives, [])
            self.assertEqual(result.alternate_searches, [])
        self.seed(1)
        connection = get_connection(self.database_path)
        connection.execute("DELETE FROM etf_daily_close")
        connection.commit()
        connection.close()
        result = self.build(existing_holdings=[{"etf_code": "T0000", "held_units": 2}])
        self.assertEqual(result.primary.status, "UNAVAILABLE")
        self.assertEqual(result.primary.existing_holdings[0].held_units, 2)
        self.assertEqual(result.alternatives, [])
        self.assertEqual(result.alternate_searches, [])

    def test_distinct_alternates_are_rendered_with_shared_evidence(self):
        self.seed(3)
        # Keep real loaders/renderers; substitute only gated monthly vectors to
        # exercise the three selection paths independently of distribution ETL.
        from backend.app.services.budget_allocation import _load_budget_facts
        request = self.request(investable_budget_twd=20, selected_months=[1, 2])
        facts = _load_budget_facts(request, self.database_path, date(2026, 1, 1))
        built = facts[2]
        vectors = ({1: "10", 2: "20"}, {1: "10", 2: "10"}, {2: "40"})
        ranked = tuple(replace(c, monthly_after_tax_cash_per_share=candidate("X", "20", v).monthly_cash_per_share)
                       for c, v in zip(built.ranked_eligible_candidates, vectors, strict=True))
        changed = replace(built, ranked_eligible_candidates=ranked)
        with patch("backend.app.services.budget_allocation._load_budget_facts", return_value=(*facts[:2], changed)):
            result = build_budget_results(request, self.database_path, as_of_date=date(2026, 1, 1))
        self.assertEqual(len(result.alternatives), 2)
        self.assertEqual([a.objective for a in result.alternatives], ["MONTHLY_BALANCED", "TOTAL_MONTH_CASH"])
        self.assertEqual(result.alternatives[0].minimum_month_cash_floor, 10)
        self.assertIsNone(result.alternatives[1].minimum_month_cash_floor)
        for plan in result.alternatives:
            self.assertEqual(plan.candidate_evidence, result.primary.candidate_evidence)
            self.assertEqual(plan.snapshot_id, result.primary.snapshot_id)
            self.assertEqual(plan.existing_holdings, result.primary.existing_holdings)
            self.assertLessEqual(plan.used_budget_twd, 20)
        self.assertEqual(BudgetResultsResponse.model_validate_json(result.model_dump_json()), result)

    def test_original_holdings_and_zero_floor_no_addition_omission(self):
        self.seed(1)
        result = self.build(selected_months=[1, 2], existing_holdings=[{"etf_code": "T0000", "held_units": 7}])
        self.assertEqual(result.primary.resulting_holdings[0].existing_shares, 7)
        self.assertEqual(result.primary.monthly_results[0].current_after_tax_cash, 7)
        self.assertEqual(result.primary.monthly_results[1].current_after_tax_cash, 0)
        self.assertEqual(result.alternatives, [])
        self.assertEqual(result.alternate_searches[0].omission_reason, "NO_ADDITIONS")
        self.assertEqual(result.alternate_searches[1].omission_reason, "DUPLICATE")
        self.assertIn("NO_ADDITION_BUDGET_STRATEGY_OMITTED", {i.code for i in result.issues})

    def test_api_real_service_validation_rate_limit_and_sanitized_errors(self):
        self.seed()
        app = create_app(public_rate_limit=1000)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        client = TestClient(app, raise_server_exceptions=False)
        path = "/api/v1/allocation-plans/budget-results"
        payload = {"investable_budget_twd": 100, "selected_months": [1]}
        with patch("backend.app.services.budget_allocation.date") as clock:
            clock.today.return_value = date(2026, 1, 1)
            response = client.post(path, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["primary"]["status"], "AVAILABLE")
        for invalid in ({"target_after_tax_cash_twd": 1}, {"investable_budget_twd": None}, {"selected_months": []}):
            self.assertEqual(client.post(path, json=payload | invalid).status_code, 422)
        with patch("backend.app.api.routers.public_planner.build_budget_results", side_effect=KeyError("private")):
            error = client.post(path, json=payload)
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.json(), {"detail": "Internal server error"})
        limited_app = create_app(public_rate_limit=1)
        limited_app.dependency_overrides[get_database_path] = lambda: self.database_path
        limited = TestClient(limited_app)
        limited.post(path, json={"investable_budget_twd": 0, "selected_months": [1]})
        self.assertEqual(limited.post(path, json=payload).status_code, 429)


if __name__ == "__main__":
    unittest.main()
