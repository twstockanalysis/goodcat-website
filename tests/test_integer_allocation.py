"""V3-3 全市場整數股數配置服務測試。"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.models.integer_allocation import IntegerAllocationRequest
from backend.app.services.integer_allocation import build_integer_allocation
from backend.app.services.complete_portfolio_solver import solve_cash_target_frontier


class TestIntegerAllocation(unittest.TestCase):
    def test_service_reports_cap_and_explicit_incomplete_state(self) -> None:
        self._insert_ready_etfs(2)
        for objective in ("CAPITAL_EFFICIENT", "MONTHLY_BALANCED", "DIVERSIFIED_PROTECTION"):
            with self.subTest(objective=objective):
                result = build_integer_allocation(
                    self._request(max_additional_capital_twd="1999.99"), self.database_path,
                    as_of_date=date(2026, 1, 1), plan_objective=objective,
                )
                self.assertEqual(result.status, "PARTIAL")
                self.assertLessEqual(result.total_required_additional_capital, Decimal("1999.99"))
                self.assertEqual(result.assumptions.max_additional_capital_twd, Decimal("1999.99"))
                self.assertIn("NO_COMPLETE_PLAN_WITHIN_CAP", {i.code for i in result.issues})
                self.assertNotIn("TARGET_MONTH_COVERAGE_INCOMPLETE", {i.code for i in result.issues})

    def test_service_propagates_strategy_to_real_solver(self) -> None:
        self._insert_ready_etfs(2)
        for objective in ("MONTHLY_BALANCED", "DIVERSIFIED_PROTECTION"):
            with self.subTest(objective=objective), patch(
                "backend.app.services.integer_allocation.solve_cash_target_frontier",
                wraps=solve_cash_target_frontier,
            ) as solve:
                result = build_integer_allocation(
                    self._request(), self.database_path,
                    as_of_date=date(2026, 1, 1), plan_objective=objective,
                )
                self.assertEqual(solve.call_args.kwargs["objective"], objective)
                self.assertEqual(result.status, "TARGET_MET")
                self.assertLessEqual(len(result.additions), 5)

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "integer.db"
        initialize_database(self.database_path)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _insert_ready_etfs(self, count: int, *, july_cash: bool = False) -> None:
        connection = get_connection(self.database_path)
        try:
            for index in range(count):
                code = f"T{index:04d}"
                connection.execute(
                    "INSERT INTO etf_master (code, name, is_active, is_bond) "
                    "VALUES (?, ?, 0, 0);",
                    (code, f"測試 ETF {index}"),
                )
                connection.execute(
                    "INSERT INTO etf_daily_close "
                    "(etf_code, trade_date, close_price, source_id) "
                    "VALUES (?, '2026-01-01', 20, 'twse_stock_day');",
                    (code,),
                )
                connection.executemany(
                    "INSERT INTO etf_performance "
                    "(etf_code, as_of_date, period_code, metric_code, "
                    "return_pct, source_id) "
                    "VALUES (?, '2026-01-01', ?, 'PRICE_RETURN', ?, 'twse_stock_day');",
                    [(code, period, value) for period, value in (
                        ("1M", 1), ("3M", 2), ("6M", 3), ("1Y", 5)
                    )],
                )
                latest_dividend_id = None
                for year in (2023, 2024, 2025, 2026):
                    months = (1, 7) if july_cash else (1,)
                    for month in months:
                        cursor = connection.execute(
                            "INSERT INTO etf_dividend "
                            "(etf_code, source_event_id, payment_date, "
                            "amount_per_unit, currency, source_id) "
                            "VALUES (?, ?, ?, 1, 'TWD', 'TEST');",
                            (code, f"{code}-{year}-{month}", f"{year}-{month:02d}-01"),
                        )
                        latest_dividend_id = int(cursor.lastrowid)
                connection.execute(
                    "INSERT INTO etf_dividend_component "
                    "(dividend_id, component_code, component_basis, ratio_pct, source_id) "
                    "VALUES (?, '76W', 'ACTUAL', 100, 'TEST');",
                    (latest_dividend_id,),
                )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _request(**updates) -> IntegerAllocationRequest:
        values = {
            "target_after_tax_cash_twd": 100,
            "target_months": [1],
            "existing_holdings": [],
            "history_years": 3,
            "cash_deduction_rate_pct": 0,
        }
        values.update(updates)
        return IntegerAllocationRequest(**values)

    def test_returns_capital_efficient_complete_whole_share_portfolio(self) -> None:
        self._insert_ready_etfs(5)

        response = build_integer_allocation(
            self._request(), self.database_path, as_of_date=date(2026, 1, 1)
        )

        self.assertEqual(response.status, "TARGET_MET")
        self.assertEqual(response.optimality, "BOUNDED_BEST_EFFORT")
        self.assertEqual(len(response.additions), 1)
        self.assertTrue(all(item.additional_shares > 0 for item in response.additions))
        self.assertEqual(response.total_required_additional_capital, Decimal("2000.00"))
        self.assertEqual(response.resulting_holdings[0].allocation_pct, Decimal("100.00"))
        self.assertEqual(response.monthly_results[0].shortfall, Decimal("0.00"))
        self.assertGreater(response.search_explored_states, 0)
        self.assertEqual(
            response.search_truncated,
            "V5_4_BOUNDED_SEARCH" in {issue.code for issue in response.issues},
        )

    def test_zero_target_is_proved_without_additions(self) -> None:
        self._insert_ready_etfs(1)

        response = build_integer_allocation(
            self._request(target_after_tax_cash_twd=0),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        )

        self.assertEqual(response.status, "TARGET_MET")
        self.assertEqual(response.optimality, "PROVED_OPTIMAL")
        self.assertEqual(response.additions, [])
        self.assertEqual(response.total_required_additional_capital, Decimal("0"))

    def test_does_not_add_capital_only_to_repair_legacy_concentration(self) -> None:
        self._insert_ready_etfs(4)

        response = build_integer_allocation(
            self._request(), self.database_path, as_of_date=date(2026, 1, 1)
        )

        self.assertEqual(response.status, "TARGET_MET")
        self.assertEqual(len(response.additions), 1)
        self.assertNotIn(
            "CONCENTRATION_CONSTRAINT_INFEASIBLE",
            {issue.code for issue in response.issues},
        )

    def test_returns_partial_when_an_target_month_has_no_cash_source(self) -> None:
        self._insert_ready_etfs(5)

        response = build_integer_allocation(
            self._request(target_months=[1, 7]),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        )

        self.assertEqual(response.status, "PARTIAL")
        by_month = {item.month: item for item in response.monthly_results}
        self.assertEqual(by_month[1].shortfall, Decimal("0.00"))
        self.assertEqual(by_month[7].shortfall, Decimal("100.00"))

    def test_public_payload_does_not_expose_internal_scores(self) -> None:
        self._insert_ready_etfs(5, july_cash=True)
        response = build_integer_allocation(
            self._request(target_months=[1, 7]),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        )

        payload = str(response.model_dump(mode="json"))
        self.assertNotIn("quality_score", payload)
        self.assertNotIn("confidence", payload)


if __name__ == "__main__":
    unittest.main()
