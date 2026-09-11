"""V3-3 公開整數配置 API 邊界測試。"""

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_database_path
from backend.app.database.init_db import initialize_database
from backend.app.main import app


class TestIntegerAllocationApi(unittest.TestCase):
    def test_optional_ceiling_validation_and_echo_on_both_endpoints(self) -> None:
        for endpoint in ("integer-allocation", "allocation-results"):
            for cap in (None, "0", "1234.56"):
                with self.subTest(endpoint=endpoint, cap=cap):
                    response = self.client.post(
                        f"/api/v1/allocation-plans/{endpoint}",
                        json={"target_after_tax_cash_twd": "0", "target_months": [1],
                              "max_additional_capital_twd": cap},
                    )
                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    result = payload if endpoint == "integer-allocation" else payload["plans"][0]["result"]
                    self.assertEqual(result["assumptions"]["max_additional_capital_twd"], cap)
            for cap in ("-1", "NaN", "Infinity", "1.001", "10000000000000000.00"):
                with self.subTest(endpoint=endpoint, invalid=cap):
                    response = self.client.post(
                        f"/api/v1/allocation-plans/{endpoint}",
                        json={"target_after_tax_cash_twd": "0", "target_months": [1],
                              "max_additional_capital_twd": cap},
                    )
                    self.assertEqual(response.status_code, 422)

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "api.db"
        initialize_database(self.database_path)
        app.dependency_overrides[get_database_path] = lambda: self.database_path
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.temp_directory.cleanup()

    def test_public_endpoint_is_stateless_and_validates_request(self) -> None:
        response = self.client.post(
            "/api/v1/allocation-plans/integer-allocation",
            json={
                "target_after_tax_cash_twd": "0",
                "target_months": [1],
                "existing_holdings": [],
                "history_years": 3,
                "cash_deduction_rate_pct": "0",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["profile_scope"], "PUBLIC_STATELESS")
        self.assertFalse(body["request_persisted"])
        self.assertFalse(body["broker_connected"])
        self.assertNotIn("quality_score", response.text)

        invalid = self.client.post(
            "/api/v1/allocation-plans/integer-allocation",
            json={
                "target_after_tax_cash_twd": "100",
                "target_months": [],
            },
        )
        self.assertEqual(invalid.status_code, 422)


if __name__ == "__main__":
    unittest.main()
