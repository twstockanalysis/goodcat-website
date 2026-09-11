"""Regression evidence for bounded exchange refinement of proposed additions."""

from decimal import Decimal, ROUND_HALF_UP
from random import Random
import unittest
from unittest.mock import patch

from backend.app.services.complete_portfolio_solver import (
    BudgetPortfolioSearch, _budget_order, _refine_budget_frontier,
    solve_budget_frontier,
)
from tests.test_budget_allocation import candidate


def unrefined(*args):
    return BudgetPortfolioSearch(args[0], args[6], args[8])


class TestBudgetRefinement(unittest.TestCase):
    def test_crossings_recover_complementary_quantity_missed_by_half_batches(self):
        inputs = [candidate("A", "1", {1: "1", 2: "3"}),
                  candidate("B", "1", {1: "3"})]
        kwargs = dict(selected_months=[1, 2], investable_budget=Decimal(10))
        with patch("backend.app.services.complete_portfolio_solver._refine_budget_frontier", side_effect=unrefined):
            before = solve_budget_frontier(inputs, **kwargs)
        self.assertEqual(before.frontier[0].minimum_month_cash, 15)
        after = solve_budget_frontier(inputs, **kwargs)
        self.assertEqual(after.frontier[0].shares, (("A", 6), ("B", 4)))
        self.assertEqual(after.frontier[0].minimum_month_cash, 18)
        self.assertEqual(after, solve_budget_frontier(inputs[::-1], **kwargs))
        self.assertGreater(after.explored_states, before.explored_states)

    def test_crossings_include_unchanged_original_holding_cash(self):
        result = solve_budget_frontier(
            [candidate("A", "1", {1: "1", 2: "3"}), candidate("B", "1", {1: "3"})],
            selected_months=[1, 2], investable_budget=Decimal(10),
            current_cash_by_month={1: Decimal(4), 2: Decimal(0)},
        )
        best = result.frontier[0]
        self.assertEqual(best.shares, (("A", 7), ("B", 3)))
        self.assertEqual(best.minimum_month_cash, 20)
        self.assertEqual(dict(best.monthly_resulting_cash)[1] - dict(best.monthly_added_cash)[1], 4)

    def test_total_attempt_budget_includes_refinement_and_keeps_incumbent(self):
        inputs = [candidate("A", "1", {1: "1", 2: "3"}), candidate("B", "1", {1: "3"})]
        kwargs = dict(selected_months=[1, 2], investable_budget=Decimal(10))
        with patch("backend.app.services.complete_portfolio_solver._refine_budget_frontier", side_effect=unrefined):
            original = solve_budget_frontier(inputs, **kwargs)
        for spare in (0, 1, 3, 20):
            limit = original.explored_states + spare
            with self.subTest(limit=limit):
                result = solve_budget_frontier(inputs, max_expansions=limit, **kwargs)
                self.assertLessEqual(result.explored_states, limit)
                self.assertLessEqual(_budget_order(result.frontier[0]), _budget_order(original.frontier[0]))
                if spare:
                    self.assertGreater(result.explored_states, original.explored_states)
                if spare == 1:
                    self.assertTrue(result.truncated)

    def test_no_addition_initial_state_is_unchanged_even_at_one_state_bound(self):
        result = solve_budget_frontier([], selected_months=[1], investable_budget=Decimal(0), max_expansions=1)
        self.assertEqual(result.frontier[0].shares, ())
        self.assertEqual(result.explored_states, 1)
        self.assertFalse(result.truncated)

    def test_exchanges_can_replace_a_code_without_exceeding_code_limit(self):
        inputs = (candidate("A", "1", {1: "1"}), candidate("B", "1", {1: "2"}))
        # Seed a valid coarse incumbent with its only addition slot occupied.
        original = solve_budget_frontier(inputs[:1], selected_months=[1], investable_budget=Decimal(10), max_added_etfs=1)
        result = _refine_budget_frontier(original.frontier, inputs, (1,), {}, Decimal(10), 1, 1, 100, False)
        self.assertEqual(result.frontier[0].shares, (("B", 10),))
        self.assertTrue(all(p.added_etf_count <= 1 for p in result.frontier))

    def test_refinement_rejects_rounded_over_budget_exchange(self):
        inputs = (candidate("A", ".335", {1: "1"}), candidate("B", ".335", {2: "1"}))
        for budget in (Decimal('.67'), Decimal('.68')):
            original = solve_budget_frontier(inputs[:1], selected_months=[1, 2], investable_budget=budget)
            result = _refine_budget_frontier(original.frontier, inputs, (1, 2), {}, budget, 5, 1, 100, False)
            for plan in result.frontier:
                rounded = sum((Decimal('.335') * q).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for _, q in plan.shares)
                self.assertLessEqual(rounded, budget)
                self.assertLessEqual(plan.used_budget, budget)
            self.assertEqual(result.frontier[0].minimum_month_cash > 0, budget == Decimal('.68'))

    def test_seeded_fixtures_never_worsen_original_objective(self):
        rng = Random(143)
        for case in range(12):
            inputs = [candidate(str(i), str(rng.randrange(1, 8)),
                                {m: str(rng.randrange(6)) for m in (1, 2, 3)}) for i in range(4)]
            kwargs = dict(selected_months=[1, 2, 3], investable_budget=Decimal(30),
                          current_cash_by_month={1: Decimal(rng.randrange(5))},
                          max_added_etfs=3, beam_width=4, max_expansions=500)
            with patch("backend.app.services.complete_portfolio_solver._refine_budget_frontier", side_effect=unrefined):
                before = solve_budget_frontier(inputs, **kwargs)
            after = solve_budget_frontier(inputs, **kwargs)
            with self.subTest(case=case):
                self.assertLessEqual(_budget_order(after.frontier[0]), _budget_order(before.frontier[0]))
                self.assertEqual(after, solve_budget_frontier(inputs[::-1], **kwargs))
                self.assertLessEqual(after.explored_states, 500)
                self.assertTrue(all(p.added_etf_count <= 3 and p.used_budget <= 30 for p in after.frontier))


if __name__ == "__main__":
    unittest.main()
