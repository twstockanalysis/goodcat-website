"""V5-4 complete-portfolio solver and Pareto-frontier tests."""

from decimal import Decimal
import unittest

from backend.app.services.complete_portfolio_solver import (
    CompletePortfolioCandidate,
    solve_budget_frontier,
    solve_cash_target_frontier,
)
from backend.app.services.integer_allocation import _select_plan


def candidate(
    code: str,
    price: str,
    monthly: dict[int, str],
) -> CompletePortfolioCandidate:
    cash = [Decimal("0") for _ in range(12)]
    for month, value in monthly.items():
        cash[month - 1] = Decimal(value)
    return CompletePortfolioCandidate(
        etf_code=code,
        reference_price=Decimal(price),
        monthly_cash_per_share=tuple(cash),
    )


class TestCompletePortfolioSolver(unittest.TestCase):
    def test_balance_tradeoff_survives_cheaper_uneven_plan(self) -> None:
        inputs = [
            candidate("CHEAP", "10", {1: "10", 2: "20"}),
            candidate("BALANCED", "20", {1: "15", 2: "15"}),
        ]
        arguments = dict(
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal("10"), 2: Decimal("10")},
            max_added_etfs=1,
        )
        search = solve_cash_target_frontier(inputs, **arguments)
        self.assertEqual(search.frontier[0].shares, (("CHEAP", 1),))
        selected = _select_plan(
            search.frontier, "MONTHLY_BALANCED", {1: Decimal(0), 2: Decimal(0)}
        )
        self.assertEqual(selected.shares, (("BALANCED", 1),))
        self.assertEqual(
            search, solve_cash_target_frontier(list(reversed(inputs)), **arguments)
        )

    def test_balance_uses_existing_cash_not_added_cash_alone(self) -> None:
        current = {1: Decimal("10"), 2: Decimal("0")}
        search = solve_cash_target_frontier(
            [
                candidate("CHEAP", "10", {2: "20"}),
                candidate("BALANCED", "20", {1: "5", 2: "15"}),
            ],
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal("10"), 2: Decimal("10")},
            current_cash_by_month=current,
            max_added_etfs=1,
        )
        selected = _select_plan(search.frontier, "MONTHLY_BALANCED", current)
        self.assertEqual(selected.shares, (("BALANCED", 1),))

    def test_balance_is_resulting_cash_not_overshoot_with_unequal_targets(self) -> None:
        search = solve_cash_target_frontier(
            [
                candidate("CHEAP", "10", {1: "10", 2: "20", 3: "999"}),
                candidate("BALANCED", "20", {1: "20", 2: "20"}),
            ],
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal("10"), 2: Decimal("20")},
            max_added_etfs=1,
        )
        selected = _select_plan(
            search.frontier, "MONTHLY_BALANCED", {1: Decimal(0), 2: Decimal(0)}
        )
        self.assertEqual(selected.shares, (("BALANCED", 1),))

    def test_solves_complementary_whole_share_portfolio_before_evidence_scoring(
        self,
    ) -> None:
        search = solve_cash_target_frontier(
            [
                candidate("JAN", "10", {1: "10"}),
                candidate("FEB", "10", {2: "10"}),
                candidate("BOTH", "15", {1: "4", 2: "4"}),
            ],
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal("10"), 2: Decimal("10")},
        )

        self.assertTrue(search.frontier)
        best = search.frontier[0]
        self.assertTrue(best.complete)
        self.assertEqual(best.shares, (("FEB", 1), ("JAN", 1)))
        self.assertEqual(best.additional_capital, Decimal("20"))
        self.assertEqual(best.total_overshoot, Decimal("0"))

    def test_existing_cash_reduces_only_the_remaining_monthly_constraints(self) -> None:
        search = solve_cash_target_frontier(
            [
                candidate("JAN", "10", {1: "10"}),
                candidate("FEB", "10", {2: "5"}),
            ],
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal("10"), 2: Decimal("10")},
            current_cash_by_month={1: Decimal("10"), 2: Decimal("5")},
        )

        best = search.frontier[0]
        self.assertEqual(best.shares, (("FEB", 1),))
        self.assertEqual(best.additional_capital, Decimal("10"))
        self.assertTrue(best.complete)

    def test_removes_a_strictly_dominated_plan(self) -> None:
        search = solve_cash_target_frontier(
            [
                candidate("CHEAP", "10", {1: "10"}),
                candidate("EXPENSIVE", "20", {1: "10"}),
            ],
            selected_months=[1],
            target_cash_by_month={1: Decimal("10")},
        )

        signatures = {plan.shares for plan in search.frontier}
        self.assertIn((("CHEAP", 1),), signatures)
        self.assertNotIn((("EXPENSIVE", 1),), signatures)

    def test_equivalent_input_order_returns_the_same_frontier(self) -> None:
        inputs = [
            candidate("JAN", "10", {1: "10"}),
            candidate("FEB", "10", {2: "10"}),
            candidate("BOTH", "15", {1: "4", 2: "4"}),
        ]
        arguments = {
            "selected_months": [1, 2],
            "target_cash_by_month": {
                1: Decimal("10"),
                2: Decimal("10"),
            },
        }

        forward = solve_cash_target_frontier(inputs, **arguments)
        reverse = solve_cash_target_frontier(list(reversed(inputs)), **arguments)

        self.assertEqual(forward.frontier, reverse.frontier)
        self.assertEqual(forward.explored_states, reverse.explored_states)

    def test_existing_value_is_included_in_every_plan_concentration(self) -> None:
        search = solve_cash_target_frontier(
            [
                candidate("A", "10", {1: "5"}),
                candidate("B", "10", {1: "5"}),
            ],
            selected_months=[1],
            target_cash_by_month={1: Decimal("10")},
            current_cash_by_month={1: Decimal("0")},
            current_value_by_code={"HELD": Decimal("80")},
            max_added_etfs=5,
        )

        self.assertTrue(search.frontier)
        self.assertTrue(
            all(plan.max_position_pct >= Decimal("80") / Decimal("100") * 100
                for plan in search.frontier if plan.additional_capital == 20)
        )

    def test_returns_explicit_partial_frontier_when_five_etfs_cannot_cover_six_months(
        self,
    ) -> None:
        candidates = [
            candidate(f"M{month:02d}", "10", {month: "10"})
            for month in range(1, 7)
        ]
        search = solve_cash_target_frontier(
            candidates,
            selected_months=list(range(1, 7)),
            target_cash_by_month={
                month: Decimal("10") for month in range(1, 7)
            },
        )

        self.assertTrue(search.frontier)
        self.assertTrue(all(not plan.complete for plan in search.frontier))
        self.assertTrue(all(plan.added_etf_count <= 5 for plan in search.frontier))
        self.assertEqual(search.frontier[0].total_shortfall, Decimal("10"))

    def test_budget_search_never_exceeds_budget_and_prefers_month_balance(self) -> None:
        search = solve_budget_frontier(
            [
                candidate("JAN", "10", {1: "12"}),
                candidate("BOTH", "10", {1: "5", 2: "5"}),
            ],
            selected_months=[1, 2],
            investable_budget=Decimal("20"),
        )

        self.assertTrue(search.frontier)
        self.assertTrue(
            all(plan.used_budget <= Decimal("20") for plan in search.frontier)
        )
        self.assertEqual(search.frontier[0].shares, (("BOTH", 2),))
        self.assertEqual(search.frontier[0].minimum_month_cash, Decimal("10"))

    def test_budget_search_includes_existing_cash_in_month_balance(self) -> None:
        search = solve_budget_frontier(
            [
                candidate("JAN", "10", {1: "12"}),
                candidate("BOTH", "10", {1: "5", 2: "5"}),
            ],
            selected_months=[1, 2],
            investable_budget=Decimal("20"),
            current_cash_by_month={2: Decimal("20")},
        )

        self.assertEqual(search.frontier[0].shares, (("JAN", 2),))
        self.assertEqual(
            dict(search.frontier[0].monthly_resulting_cash),
            {1: Decimal("24"), 2: Decimal("20")},
        )

    def test_candidate_validation_preserves_missing_versus_formal_zero_boundary(
        self,
    ) -> None:
        with self.assertRaisesRegex(ValueError, "twelve months"):
            solve_cash_target_frontier(
                [
                    CompletePortfolioCandidate(
                        etf_code="BAD",
                        reference_price=Decimal("10"),
                        monthly_cash_per_share=(Decimal("0"),),
                    )
                ],
                selected_months=[1],
                target_cash_by_month={1: Decimal("10")},
            )


if __name__ == "__main__":
    unittest.main()
