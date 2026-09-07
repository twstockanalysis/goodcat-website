"""API regression coverage for explicit not-found versus internal failures."""

from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_database_path
from backend.app.exceptions import ETFNotFoundError
from backend.app.main import create_app


PLANNER_ROUTES = {
    "baseline": "analyze_public_planner_baseline",
    "eligibility-index": "build_market_eligibility_index",
    "integer-allocation": "build_integer_allocation",
    "allocation-results": "build_allocation_results",
    "long-term-scenarios": "build_long_term_scenarios",
    "portfolio-projections": "build_portfolio_projections",
}


class TestETFErrorBoundary(unittest.TestCase):
    def setUp(self):
        app = create_app(public_rate_limit=1000)
        app.dependency_overrides[get_database_path] = lambda: Path("unused.db")
        self.client = TestClient(app, raise_server_exceptions=False)
        self.addCleanup(self.client.close)

    def request(self, route):
        if route == "comparison":
            return self.client.get("/api/v1/etfs/comparison?codes=0050,0056")
        return self.client.post(
            "/api/v1/allocation-plans/" + route,
            json={"target_after_tax_cash_twd": 3000, "target_months": [1],
                  "existing_holdings": [], "history_years": 3,
                  "cash_deduction_rate_pct": 0, "currency": "TWD"},
        )

    @staticmethod
    def targets():
        for route, function in PLANNER_ROUTES.items():
            yield route, "backend.app.api.routers.public_planner." + function
        yield "comparison", "backend.app.api.routers.etfs.build_etf_comparison"

    def test_explicit_missing_etf_preserves_404_detail(self):
        for route, target in self.targets():
            with self.subTest(route=route), patch(
                target, side_effect=ETFNotFoundError(" 9999 "),
            ):
                response = self.request(route)
                self.assertEqual(response.status_code, 404, response.text)
                self.assertEqual(response.json(), {"detail": "找不到 ETF：9999"})

    def test_programming_errors_are_sanitized_500_not_404(self):
        for route, target in self.targets():
            for error_type in (KeyError, IndexError, LookupError):
                with self.subTest(route=route, error=error_type), patch(
                    target, side_effect=error_type("internal_sensitive_field"),
                ):
                    response = self.request(route)
                    self.assertEqual(response.status_code, 500, response.text)
                    self.assertEqual(response.json(), {"detail": "Internal server error"})

    def test_comparison_preserves_multiple_missing_codes(self):
        with patch("backend.app.api.routers.etfs.build_etf_comparison",
                   side_effect=ETFNotFoundError("9998", "9999")):
            response = self.request("comparison")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "找不到 ETF：9998, 9999"})
