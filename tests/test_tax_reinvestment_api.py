"""M10-4 稅務與再投資 API 測試。"""

from datetime import date
from pathlib import Path
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_database_path
from backend.app.main import create_app
from backend.app.services.target_analysis_data import TargetAnalysisData


class TestTaxReinvestmentAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.database_path = Path("tax-reinvestment-test.db")
        self.application = create_app()
        self.application.dependency_overrides[get_database_path] = (
            lambda: self.database_path
        )
        self.client = TestClient(self.application)

    def tearDown(self) -> None:
        self.client.close()
        self.application.dependency_overrides.clear()

    @staticmethod
    def request_payload() -> dict:
        return {
            "held_units": 1000,
            "unit_price": 20,
            "monthly_cash_target": 1000,
            "analysis_years": 5,
            "history_years": 3,
            "payments_per_year": 4,
            "custom_reinvestment_pct": 50,
            "tax_rule": {
                "rule_version": "TW-INDIVIDUAL-2026.1",
                "effective_date": "2021-01-01",
                "component_assumptions": [
                    {
                        "component_code": "54C",
                        "income_tax_rate_pct": 12,
                        "tax_credit_rate_pct": 8.5,
                        "supplementary_premium_applicable": True,
                    },
                    {
                        "component_code": "76W",
                        "income_tax_rate_pct": 0,
                    },
                ],
            },
        }

    def test_stale_actual_falls_back_with_explicit_warning(self):
        class FixedDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 9, 6)

        module = 'backend.app.api.routers.target_analysis.'
        rows = [
            dict(dividend_id=1, source_event_id='old-actual', payment_date='2023-09-11',
                 component_basis='ACTUAL', component_code='76W', ratio_pct=100),
            dict(dividend_id=2, source_event_id='fresh-estimate', payment_date='2026-06-12',
                 component_basis='ESTIMATED', component_code='EST_REALIZED_CAPITAL_GAIN', ratio_pct=100),
        ]
        loaded = TargetAnalysisData(monthly_income={
            'analysis_currency':'TWD', 'window_start_date':date(2023,9,6),
            'as_of_date':date(2026,9,6), 'total_amount_per_unit':6,
        }, dividends=[], selected_performance={'period_code':'3Y','return_pct':3},
            warnings=[], unavailable_fields=[])
        with patch(module+'get_etf_by_code', return_value={'code':'00878'}), patch(
            module+'load_target_analysis_data', return_value=loaded
        ), patch(module+'list_etf_actual_component_history', return_value=rows), patch(
            module+'date', FixedDate
        ):
            response = self.client.post('/api/v1/etfs/00878/tax-reinvestment-scenarios',
                                        json=self.request_payload())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        facts = body['historical_facts']
        self.assertEqual(facts['component_calculation_basis'], 'ESTIMATED_FALLBACK')
        self.assertEqual(facts['component_source_event_id'], 'fresh-estimate')
        self.assertIsNone(facts['actual_component_mix'])
        self.assertIn('2023-09-11', body['warnings'][0])

    def test_openapi_contains_tax_reinvestment_path(self) -> None:
        path = "/api/v1/etfs/{code}/tax-reinvestment-scenarios"
        self.assertIn(path, self.application.openapi()["paths"])
        self.assertIn("post", self.application.openapi()["paths"][path])

    @patch(
        "backend.app.api.routers.target_analysis."
        "list_etf_actual_component_history"
    )
    @patch(
        "backend.app.api.routers.target_analysis.load_target_analysis_data"
    )
    @patch("backend.app.api.routers.target_analysis.get_etf_by_code")
    def test_returns_traceable_four_scenario_result(
        self,
        mock_get_etf,
        mock_load_data,
        mock_list_components,
    ) -> None:
        mock_get_etf.return_value = {"code": "0056"}
        mock_load_data.return_value = TargetAnalysisData(
            monthly_income={
                "analysis_currency": "TWD",
                "window_start_date": date(2023, 1, 1),
                "as_of_date": date(2025, 12, 31),
                "total_amount_per_unit": 6,
            },
            dividends=[],
            selected_performance={
                "period_code": "3Y",
                "return_pct": 3,
            },
            warnings=[],
            unavailable_fields=[],
        )
        common = {
            "dividend_id": 7,
            "source_event_id": "official-7",
            "payment_date": "2025-12-20",
        }
        mock_list_components.return_value = [
            {
                **common,
                "component_code": "54C",
                "component_name": "境內股利",
                "ratio_pct": 40,
            },
            {
                **common,
                "component_code": "76W",
                "component_name": "國內財產交易",
                "ratio_pct": 60,
            },
        ]

        response = self.client.post(
            "/api/v1/etfs/0056/tax-reinvestment-scenarios",
            json=self.request_payload(),
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "AVAILABLE")
        self.assertEqual(
            body["historical_facts"]["component_source_event_id"],
            "official-7",
        )
        self.assertEqual(len(body["calculation"]["scenarios"]), 4)
        self.assertEqual(
            body["historical_facts"]["price_return_period_code"],
            "3Y",
        )
        self.assertAlmostEqual(
            float(body["historical_facts"]["annual_price_return_pct"]),
            0.990163,
            places=6,
        )
        self.assertEqual(
            body["calculation"]["estimate_label"],
            "情境估算，非稅務建議",
        )

    @patch(
        "backend.app.api.routers.target_analysis."
        "list_etf_actual_component_history"
    )
    @patch(
        "backend.app.api.routers.target_analysis.load_target_analysis_data"
    )
    @patch("backend.app.api.routers.target_analysis.get_etf_by_code")
    def test_estimated_mix_is_used_as_labeled_fallback(
        self,
        mock_get_etf,
        mock_load_data,
        mock_list_components,
    ) -> None:
        mock_get_etf.return_value = {"code": "0050"}
        mock_load_data.return_value = TargetAnalysisData(
            monthly_income={
                "analysis_currency": "TWD",
                "window_start_date": date(2023, 1, 1),
                "as_of_date": date(2025, 12, 31),
                "total_amount_per_unit": 6,
            },
            dividends=[],
            selected_performance={"period_code": "3Y", "return_pct": 3},
            warnings=[],
            unavailable_fields=[],
        )
        common = {
            "dividend_id": 8,
            "source_event_id": "twse-estimated-8",
            "payment_date": "2025-12-20",
            "component_basis": "ESTIMATED",
        }
        mock_list_components.return_value = [
            {
                **common,
                "component_code": "EST_DIVIDEND",
                "component_name": "股利所得",
                "ratio_pct": 26,
            },
            {
                **common,
                "component_code": "EST_REALIZED_CAPITAL_GAIN",
                "component_name": "已實現資本利得",
                "ratio_pct": 74,
            },
        ]
        payload = self.request_payload()
        payload["tax_rule"]["component_assumptions"].extend(
            [
                {
                    "component_code": "EST_DIVIDEND",
                    "income_tax_rate_pct": 12,
                    "tax_credit_rate_pct": 8.5,
                    "supplementary_premium_applicable": True,
                },
                {
                    "component_code": "EST_REALIZED_CAPITAL_GAIN",
                    "income_tax_rate_pct": 0,
                },
            ]
        )

        response = self.client.post(
            "/api/v1/etfs/0050/tax-reinvestment-scenarios",
            json=payload,
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "AVAILABLE")
        facts = body["historical_facts"]
        self.assertIsNone(facts["actual_component_mix"])
        self.assertEqual(
            facts["component_calculation_basis"],
            "ESTIMATED_FALLBACK",
        )
        self.assertEqual(
            facts["calculation_component_mix"][0]["component_code"],
            "EST_DIVIDEND",
        )
        self.assertEqual(
            body["calculation"]["historical_component_basis"],
            "ESTIMATED_FALLBACK",
        )


if __name__ == "__main__":
    unittest.main()
