"""V3-4 多種配置結果服務測試。"""

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.models.allocation_results import AllocationResultsRequest
from backend.app.models.integer_allocation import (
    IntegerAllocationAssumptions,
    IntegerAllocationResponse,
)
from backend.app.services.allocation_results import build_allocation_results


_SNAPSHOT = "sha256:" + "a" * 64


def allocation_result(code: str) -> IntegerAllocationResponse:
    additions = []
    capital = Decimal("0")
    if code:
        additions = [
            {
                "etf_code": code,
                "name": f"ETF {code}",
                "historical_quality_grade": {
                    "status": "RATED",
                    "grade": "A",
                    "evidence_period_years": 3,
                    "explanation": "歷史品質評等。",
                },
                "additional_shares": 100,
                "reference_price": 20,
                "reference_price_as_of": "2026-01-01",
                "reference_price_source_id": "TEST",
                "estimated_transaction_cost": 0,
                "required_capital": 2000,
                "supported_target_months": [1],
            }
        ]
        capital = Decimal("2000")
    return IntegerAllocationResponse(
        status="TARGET_MET",
        optimality="BOUNDED_BEST_EFFORT" if code else "PROVED_OPTIMAL",
        analysis_date=date(2026, 1, 1),
        snapshot_id=_SNAPSHOT,
        target_after_tax_cash_twd=100,
        target_months=[1],
        assumptions=IntegerAllocationAssumptions(
            cash_deduction_rate_pct=0,
            max_candidate_allocation_pct=20,
        ),
        universe_count=3,
        eligible_count=3,
        additions=additions,
        total_required_additional_capital=capital,
        monthly_results=[
            {
                "month": 1,
                "current_after_tax_cash": 0,
                "added_after_tax_cash": 100,
                "modeled_after_tax_cash": 100,
                "target_after_tax_cash": 100,
                "shortfall": 0,
            }
        ],
        resulting_holdings=[
            {
                "etf_code": "HELD",
                "existing_shares": 10,
                "additional_shares": 0,
                "resulting_shares": 10,
                "reference_price": 10,
                "reference_price_as_of": "2026-01-01",
                "reference_price_source_id": "TEST",
                "resulting_value": 100,
                "allocation_pct": 100,
            }
        ],
    )


class TestAllocationResults(unittest.TestCase):
    def setUp(self) -> None:
        self.request = AllocationResultsRequest(
            target_after_tax_cash_twd=100,
            target_months=[1],
            existing_holdings=[],
            history_years=3,
            cash_deduction_rate_pct=0,
        )
        self.built_index = SimpleNamespace(
            response=SimpleNamespace(snapshot_id=_SNAPSHOT, candidates=[]),
            ranked_eligible_candidates=(),
        )

    @patch("backend.app.services.allocation_results.build_integer_allocation")
    @patch("backend.app.services.allocation_results.build_market_eligibility_index")
    def test_returns_capital_plan_without_preselecting_by_quality_score(
        self,
        build_index,
        build_integer,
    ) -> None:
        build_index.return_value = self.built_index
        build_integer.side_effect = [
            allocation_result("0050"),
            allocation_result("0060"),
            allocation_result("0070"),
        ]

        response = build_allocation_results(
            self.request,
            Path("unused.db"),
            as_of_date=date(2026, 1, 1),
        )

        self.assertEqual(
            [plan.label for plan in response.plans],
            ["資金精簡方案", "穩定均衡方案", "分散防護方案"],
        )
        self.assertEqual(build_integer.call_count, 3)
        self.assertEqual(
            [call.kwargs["plan_objective"] for call in build_integer.call_args_list],
            ["CAPITAL_EFFICIENT", "MONTHLY_BALANCED", "DIVERSIFIED_PROTECTION"],
        )
        # These mocked plans have equal cash/capital metrics but distinct codes:
        # retain them without an invented percentage-improvement filter.
        self.assertEqual(len(response.plans), 3)
        self.assertTrue(
            all(
                any(
                    holding.etf_code == "HELD" and holding.existing_shares == 10
                    for holding in plan.result.resulting_holdings
                )
                for plan in response.plans
            )
        )
        self.assertNotIn(
            "MATERIALLY_DISTINCT_ALTERNATIVES_LIMITED",
            {issue.code for issue in response.strategy_issues},
        )
        serialized = str(response.model_dump(mode="json"))
        self.assertNotIn("quality_score", serialized)
        self.assertNotIn("confidence", serialized)

    @patch("backend.app.services.allocation_results.build_integer_allocation")
    @patch("backend.app.services.allocation_results.build_market_eligibility_index")
    def test_returns_no_duplicate_alternative_without_primary_additions(
        self,
        build_index,
        build_integer,
    ) -> None:
        build_index.return_value = self.built_index
        build_integer.return_value = allocation_result("")

        response = build_allocation_results(
            self.request,
            Path("unused.db"),
            as_of_date=date(2026, 1, 1),
        )

        self.assertEqual(len(response.plans), 1)
        self.assertIn(
            "ALTERNATIVE_UNAVAILABLE_WITHOUT_PRIMARY_ALLOCATION",
            {issue.code for issue in response.strategy_issues},
        )


if __name__ == "__main__":
    unittest.main()
