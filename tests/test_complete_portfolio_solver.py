"""V5-4 complete-portfolio solver and Pareto-frontier tests."""

from decimal import Decimal
from random import Random
import unittest

from backend.app.services.complete_portfolio_solver import (
    CompletePortfolioCandidate,
    CompletePortfolioPlan,
    _dominates,
    _non_dominated,
    cash_target_plan_order,
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
    def test_cap_zero_exact_and_insufficient_for_every_objective(self) -> None:
        inputs = [candidate("A", "10", {1: "1"})]
        for objective in ("CAPITAL_EFFICIENT", "MONTHLY_BALANCED", "DIVERSIFIED_PROTECTION"):
            for ceiling in (Decimal(0), Decimal(19), Decimal(20)):
                with self.subTest(objective=objective, ceiling=ceiling):
                    search = solve_cash_target_frontier(
                        inputs, selected_months=[1], target_cash_by_month={1: Decimal(2)},
                        current_value_by_code={"HELD": Decimal(10000)},
                        max_additional_capital=ceiling, objective=objective,
                    )
                    self.assertTrue(all(p.additional_capital <= ceiling for p in search.frontier))
                    self.assertEqual(any(p.complete for p in search.frontier), ceiling == 20)
                    if ceiling == 0:
                        self.assertEqual(search.frontier[0].shares, ())

    def test_cap_search_explores_affordable_partial_boundary(self) -> None:
        search = solve_cash_target_frontier(
            [candidate("A", "10", {1: "1"})], selected_months=[1],
            target_cash_by_month={1: Decimal(100)}, max_additional_capital=Decimal(35),
        )
        self.assertEqual(search.frontier[0].shares, (("A", 3),))
        self.assertEqual(search.frontier[0].total_shortfall, 97)

    def test_cap_limits_balance_refinement_without_counting_existing_value(self) -> None:
        search = solve_cash_target_frontier(
            [candidate("FEB", "1", {2: "1"})], selected_months=[1, 2],
            target_cash_by_month={1: Decimal(10), 2: Decimal(10)},
            current_cash_by_month={1: Decimal(100)},
            current_value_by_code={"HELD": Decimal(10000)},
            max_additional_capital=Decimal(40), objective="MONTHLY_BALANCED",
        )
        best = _select_plan(search.frontier, "MONTHLY_BALANCED", {})
        self.assertEqual(best.shares, (("FEB", 40),))
        self.assertEqual(best.month_imbalance, 60)
        self.assertTrue(best.complete)

    def test_cap_checks_sum_of_rounded_position_costs(self) -> None:
        inputs = [candidate("JAN", "0.335", {1: "1"}),
                  candidate("FEB", "0.335", {2: "1"})]
        for cap, complete in (("0.67", False), ("0.68", True)):
            search = solve_cash_target_frontier(
                inputs, selected_months=[1, 2],
                target_cash_by_month={1: Decimal(1), 2: Decimal(1)},
                max_additional_capital=Decimal(cap),
            )
            self.assertEqual(any(p.complete for p in search.frontier), complete)

    def test_null_cap_preserves_default_and_invalid_caps_fail_closed(self) -> None:
        args = dict(selected_months=[1], target_cash_by_month={1: Decimal(10)})
        inputs = [candidate("A", "10", {1: "1"})]
        self.assertEqual(solve_cash_target_frontier(inputs, **args),
                         solve_cash_target_frontier(inputs, max_additional_capital=None, **args))
        for value in ("-1", "NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "ceiling"):
                solve_cash_target_frontier(inputs, max_additional_capital=Decimal(value), **args)

    def test_incremental_frontier_matches_all_pairs_reference(self) -> None:
        rng = Random(137)
        # Synthetic comparison vectors exercise ties, partials and trade-offs.
        plans = [CompletePortfolioPlan(
            shares=((str(i), 1),), additional_capital=Decimal(rng.randrange(8)),
            monthly_added_cash=((1, Decimal(0)),),
            monthly_resulting_cash=((1, Decimal(0)), (2, Decimal(rng.randrange(8)))),
            monthly_shortfall=((1, Decimal(rng.randrange(3))),),
            monthly_overshoot=((1, Decimal(rng.randrange(8))),),
            max_position_pct=Decimal(rng.randrange(8)),
        ) for i in range(100)]
        ordered = sorted(plans, key=lambda p: cash_target_plan_order(p, "CAPITAL_EFFICIENT"))
        expected = tuple(p for p in ordered if not any(
            other.shares != p.shares and _dominates(other, p) for other in ordered
        ))
        self.assertEqual(_non_dominated(plans + [plans[0]]), expected)
        self.assertEqual(_non_dominated(list(reversed(plans))), expected)

    def test_zero_cap_preserves_already_sufficient_existing_cash(self) -> None:
        search = solve_cash_target_frontier(
            [], selected_months=[1], target_cash_by_month={1: Decimal(10)},
            current_cash_by_month={1: Decimal(10)},
            current_value_by_code={"HELD": Decimal(5000)},
            max_additional_capital=Decimal(0), objective="DIVERSIFIED_PROTECTION",
        )
        self.assertTrue(search.frontier[0].complete)
        self.assertEqual(search.frontier[0].additional_capital, 0)
        self.assertEqual(search.frontier[0].shares, ())

    def test_balanced_search_refines_beyond_first_complete_plan(self) -> None:
        arguments = dict(
            selected_months=[1, 2],
            target_cash_by_month={1: Decimal(10), 2: Decimal(10)},
            current_cash_by_month={1: Decimal(100)},
            max_added_etfs=1,
        )
        inputs = [candidate("FEB", "1", {2: "1"})]
        capital = solve_cash_target_frontier(inputs, **arguments)
        balanced = solve_cash_target_frontier(
            inputs, objective="MONTHLY_BALANCED", **arguments
        )
        selected = _select_plan(balanced.frontier, "MONTHLY_BALANCED", {})
        self.assertEqual(capital.frontier[0].shares, (("FEB", 10),))
        self.assertEqual(selected.shares, (("FEB", 100),))
        self.assertEqual(selected.month_imbalance, 0)
        self.assertTrue(selected.complete)

    def test_diversified_search_refines_existing_position_concentration(self) -> None:
        inputs = [candidate("A", "10", {1: "10"}),
                  candidate("B", "10", {1: "10"})]
        arguments = dict(
            selected_months=[1], target_cash_by_month={1: Decimal(10)},
            current_value_by_code={"HELD": Decimal(80)},
            max_added_etfs=2, beam_width=4, max_expansions=300,
        )
        search = solve_cash_target_frontier(
            inputs, objective="DIVERSIFIED_PROTECTION", **arguments
        )
        selected = _select_plan(search.frontier, "DIVERSIFIED_PROTECTION", {})
        self.assertEqual(selected.shares, (("A", 8), ("B", 8)))
        self.assertEqual(selected.max_position_pct, Decimal(100) / 3)
        self.assertEqual(search, solve_cash_target_frontier(
            list(reversed(inputs)), objective="DIVERSIFIED_PROTECTION", **arguments
        ))
        self.assertLessEqual(search.explored_states, 300)

    def test_each_objective_preserves_bounds_and_explicit_partial_state(self) -> None:
        inputs = [candidate("JAN", "1", {1: "1"})]
        for objective in ("CAPITAL_EFFICIENT", "MONTHLY_BALANCED", "DIVERSIFIED_PROTECTION"):
            with self.subTest(objective=objective):
                search = solve_cash_target_frontier(
                    inputs, selected_months=[1, 2],
                    target_cash_by_month={1: Decimal(10), 2: Decimal(10)},
                    objective=objective, beam_width=1, max_expansions=5,
                )
                self.assertTrue(all(not p.complete for p in search.frontier))
                self.assertLessEqual(search.explored_states, 5)
                self.assertTrue(search.truncated)
                self.assertTrue(all(p.added_etf_count <= 5 for p in search.frontier))
                zero = solve_cash_target_frontier(
                    inputs, selected_months=[1], target_cash_by_month={1: Decimal(0)},
                    objective=objective,
                )
                self.assertEqual(zero.frontier[0].shares, ())
                self.assertEqual(zero.explored_states, 1)

    def test_unknown_objective_rejected_even_for_zero_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "objective"):
            solve_cash_target_frontier(
                [], selected_months=[1], target_cash_by_month={1: Decimal(0)},
                objective="UNKNOWN",
            )

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
