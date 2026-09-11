"""Budget solver, real-database orchestration and public API boundaries."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from pathlib import Path
from random import Random
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.api.dependencies import get_database_path
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.main import create_app
from backend.app.models.budget_allocation import BudgetAllocationRequest, BudgetAllocationResponse
from backend.app.models.integer_allocation import IntegerAllocationRequest
from backend.app.services.budget_allocation import build_budget_allocation
from backend.app.services.complete_portfolio_solver import (
    BudgetPortfolioPlan, CompletePortfolioCandidate, _budget_dominates,
    _budget_order, _non_dominated_budget, solve_budget_frontier,
)
from backend.app.services.integer_allocation import build_integer_allocation
from backend.app.services.market_eligibility_index import build_market_eligibility_index
from tests import test_integer_allocation as allocation_fixtures


def candidate(code, price, cash):
    return CompletePortfolioCandidate(
        code, Decimal(price), tuple(Decimal(cash.get(m, 0)) for m in range(1, 13)),
    )


class TestBudgetSolver(unittest.TestCase):
    def test_zero_no_candidates_and_unaffordable_preserve_existing_cash(self):
        for inputs, amount in (([], "100"), ([candidate("A", "10", {1: "1"})], "0"),
                               ([candidate("A", "10", {1: "1"})], "9.99")):
            with self.subTest(amount=amount):
                search = solve_budget_frontier(
                    inputs, selected_months=[1], investable_budget=Decimal(amount),
                    current_cash_by_month={1: Decimal(7)},
                )
                self.assertEqual(search.frontier[0].shares, ())
                self.assertEqual(search.frontier[0].minimum_month_cash, 7)
                self.assertEqual(search.explored_states, 1)

    def test_unselected_or_zero_cash_does_not_spend_budget(self):
        result = solve_budget_frontier(
            [candidate("A", "1", {2: "100"})], selected_months=[1], investable_budget=Decimal(100),
        )
        self.assertEqual(result.frontier[0].shares, ())

    def test_rounding_checks_each_position_not_just_total(self):
        inputs = [candidate("A", ".335", {1: "1"}), candidate("B", ".335", {2: "1"})]
        for amount, expected in ((".67", False), (".68", True)):
            with self.subTest(amount=amount):
                result = solve_budget_frontier(inputs, selected_months=[1, 2], investable_budget=Decimal(amount))
                self.assertEqual(result.frontier[0].minimum_month_cash > 0, expected)
                for plan in result.frontier:
                    displayed = sum((Decimal('.335') * qty).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
                                    for _, qty in plan.shares)
                    self.assertLessEqual(displayed, Decimal(amount))
                    self.assertLessEqual(plan.used_budget, Decimal(amount))

    def test_deterministic_bounded_search_and_five_additions(self):
        inputs = [candidate(str(m), "10", {m: "1"}) for m in range(1, 7)]
        kwargs = dict(selected_months=list(range(1, 7)), investable_budget=Decimal(100),
                      beam_width=3, max_expansions=30)
        result = solve_budget_frontier(inputs, **kwargs)
        self.assertEqual(result, solve_budget_frontier(inputs[::-1], **kwargs))
        self.assertTrue(result.truncated)
        self.assertLessEqual(result.explored_states, 30)
        self.assertTrue(all(p.added_etf_count <= 5 and p.used_budget <= 100 for p in result.frontier))
        one = solve_budget_frontier(inputs, **(kwargs | {"max_expansions": 1}))
        self.assertEqual(one.frontier[0].shares, ())
        self.assertTrue(one.truncated)

    def test_finite_facts_budget_and_bounds_are_required(self):
        for amount in ("NaN", "Infinity", "-Infinity", "-1"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                solve_budget_frontier([], selected_months=[1], investable_budget=Decimal(amount))
        for inputs, current in (([candidate("A", "Infinity", {})], {}),
                                ([candidate("A", "1", {1: "NaN"})], {}),
                                ([], {1: Decimal("NaN")})):
            with self.assertRaises(ValueError):
                solve_budget_frontier(inputs, selected_months=[1], investable_budget=Decimal(10),
                                      current_cash_by_month=current)
        with self.assertRaises(ValueError):
            solve_budget_frontier([], selected_months=[1], investable_budget=Decimal(10), max_expansions=0)

    def test_skyline_matches_all_pairs_reference(self):
        rng = Random(141)
        plans = [BudgetPortfolioPlan(
            ((str(i), 1),), Decimal(rng.randrange(8)), ((1, Decimal(0)),),
            tuple((m, Decimal(rng.randrange(8))) for m in (1, 2)),
        ) for i in range(100)]
        expected = tuple(p for p in sorted(plans, key=_budget_order) if not any(
            _budget_dominates(q, p) for q in plans if q.shares != p.shares
        ))
        self.assertEqual(_non_dominated_budget(plans), expected)
        self.assertEqual(_non_dominated_budget(plans[::-1] + [plans[0]]), expected)


class TestBudgetAllocation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database_path = Path(self.temp.name) / "budget.db"
        initialize_database(self.database_path)

    def seed(self, count=2):
        allocation_fixtures.TestIntegerAllocation._insert_ready_etfs(self, count)

    def request(self, **updates):
        return BudgetAllocationRequest(**({"investable_budget_twd": "100.00", "selected_months": [1]} | updates))

    def build(self, **updates):
        return build_budget_allocation(self.request(**updates), self.database_path, as_of_date=date(2026, 1, 1))

    def test_real_service_whole_shares_and_stateless_evidence(self):
        self.seed()
        before = hashlib.sha256(self.database_path.read_bytes()).hexdigest()
        result = self.build()
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.used_budget_twd, 100)
        self.assertEqual(result.remaining_budget_twd, 0)
        self.assertEqual(sum(a.additional_shares for a in result.additions), 5)
        self.assertEqual(result.monthly_results[0].modeled_after_tax_cash, 5)
        self.assertEqual(len(result.candidate_evidence), 2)
        self.assertFalse(result.request_persisted)
        self.assertFalse(result.broker_connected)
        self.assertEqual(result.optimality, "BOUNDED_BEST_EFFORT")
        self.assertIn("V5_4_BOUNDED_BUDGET_SEARCH", {i.code for i in result.issues})
        self.assertEqual(before, hashlib.sha256(self.database_path.read_bytes()).hexdigest())
        payload = result.model_dump_json()
        self.assertEqual(BudgetAllocationResponse.model_validate_json(payload), result)
        for forbidden in ("target_after_tax_cash", "shortfall", "TARGET_MET", "quality_score", "confidence"):
            self.assertNotIn(forbidden, payload)

    def test_existing_holdings_remain_and_do_not_consume_budget(self):
        self.seed()
        result = self.build(existing_holdings=[{"etf_code": "T0000", "held_units": 100}])
        self.assertEqual(result.status, "AVAILABLE")
        self.assertEqual(result.used_budget_twd, 100)
        self.assertEqual(result.resulting_holdings[0].existing_shares, 100)
        self.assertEqual(result.resulting_holdings[0].resulting_shares, 105)
        self.assertEqual(result.monthly_results[0].modeled_after_tax_cash, 105)
        excluded = next(c for c in result.candidate_evidence if c.etf_code == "T0001")
        self.assertFalse(excluded.eligible_for_addition)
        self.assertIn("HOLDING_OVERLAP_UNAVAILABLE", {r.code for r in excluded.reasons})

    def test_more_than_five_original_codes_are_preserved_at_zero_budget(self):
        self.seed(6)
        result = self.build(investable_budget_twd="0", existing_holdings=[
            {"etf_code": f"T{i:04d}", "held_units": 1} for i in range(6)
        ])
        self.assertEqual(result.status, "NO_ADDITIONS")
        self.assertEqual(len(result.resulting_holdings), 6)
        self.assertEqual(result.monthly_results[0].modeled_after_tax_cash, 6)
        self.assertEqual(result.additions, [])

    def test_missing_cash_is_null_even_at_zero_budget(self):
        self.seed(1)
        connection = get_connection(self.database_path)
        connection.execute("DELETE FROM etf_dividend_component")
        connection.execute("DELETE FROM etf_dividend")
        connection.commit()
        connection.close()
        result = self.build(investable_budget_twd="0", existing_holdings=[{"etf_code": "T0000", "held_units": 2}])
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertIsNone(result.monthly_results[0].current_after_tax_cash)
        self.assertIsNone(result.monthly_results[0].modeled_after_tax_cash)
        self.assertIsNone(result.resulting_holdings)
        self.assertEqual(result.existing_holdings[0].held_units, 2)

    def test_missing_price_preserves_known_cash_and_original_holding(self):
        self.seed(1)
        connection = get_connection(self.database_path)
        connection.execute("DELETE FROM etf_daily_close")
        connection.commit()
        connection.close()
        result = self.build(existing_holdings=[{"etf_code": "T0000", "held_units": 2}])
        self.assertEqual(result.status, "UNAVAILABLE")
        self.assertEqual(result.monthly_results[0].current_after_tax_cash, 2)
        self.assertIsNone(result.existing_holdings[0].current_value)
        self.assertEqual(result.remaining_budget_twd, 100)

    def test_no_candidates_zero_unaffordable_and_no_selected_cash_are_distinct(self):
        self.assertEqual(self.build().status, "NO_ELIGIBLE_ALLOCATION")
        self.assertEqual(self.build(investable_budget_twd="0").status, "NO_ADDITIONS")
        self.seed(1)
        for updates in ({"investable_budget_twd": "19.99"}, {"selected_months": [7]}):
            result = self.build(**updates)
            self.assertEqual(result.status, "NO_ADDITIONS")
            self.assertEqual(result.used_budget_twd, 0)
            self.assertIn("NO_BUDGET_ADDITIONS_FOUND", {i.code for i in result.issues})

    def test_cash_target_and_eligibility_are_unchanged(self):
        self.seed()
        request = IntegerAllocationRequest(target_after_tax_cash_twd=100, target_months=[1])
        before = build_integer_allocation(request, self.database_path, as_of_date=date(2026, 1, 1))
        budget = self.build()
        after = build_integer_allocation(request, self.database_path, as_of_date=date(2026, 1, 1))
        index = build_market_eligibility_index(request, self.database_path, as_of_date=date(2026, 1, 1)).response
        self.assertEqual(before, after)
        self.assertEqual(before.total_required_additional_capital, 2000)
        self.assertEqual(index.candidates, budget.candidate_evidence)
        self.assertEqual(index.snapshot_id, budget.snapshot_id)

    def test_response_rejects_inconsistent_costs(self):
        self.seed()
        payload = self.build().model_dump()
        for updates in ({"used_budget_twd": 101}, {"remaining_budget_twd": 1}, {"additions": []}):
            with self.assertRaises(ValidationError):
                BudgetAllocationResponse.model_validate(payload | updates)
        for price in ("21", "19"):
            changed = self.build().model_dump()
            changed["additions"][0]["reference_price"] = Decimal(price)
            with self.assertRaises(ValidationError):
                BudgetAllocationResponse.model_validate(changed)

    def test_api_runs_real_service_without_cash_target_and_preserves_security(self):
        self.seed()
        app = create_app(public_rate_limit=1000)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        client = TestClient(app)
        with patch("backend.app.services.budget_allocation.date") as clock:
            clock.today.return_value = date(2026, 1, 1)
            response = client.post("/api/v1/allocation-plans/budget-allocation", json={
                "investable_budget_twd": "100.00", "selected_months": [1],
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "AVAILABLE")
        self.assertEqual(response.json()["used_budget_twd"], "100.00")
        self.assertFalse(response.json()["request_persisted"])
        unknown = client.post("/api/v1/allocation-plans/budget-allocation", json={
            "investable_budget_twd": 0, "selected_months": [1],
            "existing_holdings": [{"etf_code": "UNKNOWN", "held_units": 1}],
        })
        self.assertEqual(unknown.status_code, 404)

    def test_api_keeps_rate_limit_and_sanitized_error_boundary(self):
        app = create_app(public_rate_limit=1)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        client = TestClient(app, raise_server_exceptions=False)
        path = "/api/v1/allocation-plans/budget-allocation"
        payload = {"investable_budget_twd": 0, "selected_months": [1]}
        with patch("backend.app.api.routers.public_planner.build_budget_allocation",
                   side_effect=KeyError("internal-test-detail")):
            error = client.post(path, json=payload)
        self.assertEqual(error.status_code, 500)
        self.assertEqual(error.json(), {"detail": "Internal server error"})
        limited = client.post(path, json=payload)
        self.assertEqual(limited.status_code, 429)
        self.assertIn("retry-after", limited.headers)

    def test_api_rejects_invalid_budget_months_holdings_and_target_fields(self):
        app = create_app(public_rate_limit=1000)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        client = TestClient(app)
        valid = {"investable_budget_twd": "100", "selected_months": [1]}
        invalid = [{"investable_budget_twd": v} for v in (None, "-1", "NaN", "Infinity", "1.001", "10000000000000000.00")]
        invalid += [{"selected_months": m} for m in ([], [0], [13])]
        invalid += [{"target_after_tax_cash_twd": 0}, {"target_months": [1]},
                    {"max_additional_capital_twd": 100}, {"currency": "USD"},
                    {"existing_holdings": [{"etf_code": 50, "held_units": 1}]},
                    {"existing_holdings": [{"etf_code": "A", "held_units": 1}, {"etf_code": "a", "held_units": 2}]}]
        for updates in invalid:
            with self.subTest(updates=updates):
                response = client.post("/api/v1/allocation-plans/budget-allocation", json=valid | updates)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(client.post("/api/v1/allocation-plans/budget-allocation", json={"selected_months": [1]}).status_code, 422)
        self.assertEqual(self.request(selected_months=[7, 1, 7]).selected_months, [1, 7])


if __name__ == "__main__":
    unittest.main()
