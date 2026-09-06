from datetime import date, datetime, timezone
from decimal import Decimal
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
from backend.app.data_sources.cathay_constituent_adapter import (
    fetch_cathay_constituent_snapshot, parse_cathay_snapshot,
)


class TestCathayConstituents(unittest.TestCase):
    def test_pipeline_preserves_identity_and_refuses_overwrite(self):
        from backend.app.database.connection import get_connection
        from backend.app.database.init_db import initialize_database
        from backend.app.data_sources.constituent_pipeline import import_official_constituents_with_status

        snapshot = self.parse()
        changed = self.parse(stocks=[{"stockCode": "2330", "stockName": "台積電", "weights": "94"}])
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "cathay-test.db"
            initialize_database(database_path)
            connection = get_connection(database_path)
            connection.execute("INSERT INTO etf_master (code, name) VALUES ('00878', '國泰永續高股息')")
            connection.commit()
            connection.close()
            with patch("backend.app.data_sources.constituent_pipeline.fetch_cathay_constituent_snapshot",
                       side_effect=[snapshot, snapshot, changed]):
                first = import_official_constituents_with_status("cathay", "00878", database_path)
                second = import_official_constituents_with_status("cathay", "00878", database_path)
                self.assertEqual(first.outcome, "IMPORTED")
                self.assertEqual(second.outcome, "UNCHANGED")
                self.assertEqual(first.snapshot.source_id, "cathay_official_stock_list")
                self.assertEqual(first.snapshot.total_weight_pct, Decimal("95"))
                with self.assertRaisesRegex(ValueError, "拒絕覆寫"):
                    import_official_constituents_with_status("cathay", "00878", database_path)

    def parse(self, **changes):
        values = dict(code="00878", fund_code="CN",
            identity={"stockCode": "00878", "fundCode": "CN"},
            assets={"preDate": "2026/09/04"},
            stocks=[{"stockCode": "2330", "stockName": "台積電", "weights": "95"}],
            evaluated_on=date(2026, 9, 6), fetched_at=datetime.now(timezone.utc))
        values.update(changes)
        return parse_cathay_snapshot(**values)

    def test_keeps_disclosed_weight_and_effective_date(self):
        snapshot = self.parse()
        self.assertEqual(snapshot.positions[0].weight_pct, Decimal("95"))
        self.assertEqual(snapshot.as_of_date, date(2026, 9, 4))
        self.assertIn("/ECN?", snapshot.source_url)

    def test_rejects_wrong_identity_and_dates(self):
        for changes in (
            {"identity": {"stockCode": "0050", "fundCode": "CN"}},
            {"identity": {"stockCode": "00878", "fundCode": "ECN"}},
            {"assets": {"preDate": "2026/09/07"}},
            {"assets": {"preDate": "2026/08/01"}},
            {"assets": {}},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.parse(**changes)

    def test_rejects_incomplete_duplicate_invalid_weights(self):
        for weights in (["89"], ["101"], ["NaN"], ["-1"], ["50", "45"]):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                self.parse(stocks=[dict(stockCode="2330", stockName="台積電", weights=w) for w in weights])

    def test_catalog_fund_code_and_asset_date_drive_stock_request(self):
        calls = []
        def handle(request):
            calls.append(request)
            endpoint = request.url.path.rsplit("/", 1)[-1]
            result = {
                "GetETFDetailPriceList": [{"stockCode": "00878", "fundCode": "CN"}],
                "GetETFInfoMain": {"stockCode": "00878", "fundCode": "CN"},
                "GetETFAssets": {"preDate": "2026/09/04"},
                "GetETFDetailStockList": [{"stockCode": "2330", "stockName": "台積電", "weights": "95"}],
            }[endpoint]
            return httpx.Response(200, json={"returnCode": "2000", "result": result})
        with httpx.Client(transport=httpx.MockTransport(handle)) as client:
            snapshot = fetch_cathay_constituent_snapshot("00878", evaluated_on=date(2026,9,6), client=client)
        self.assertEqual(calls[-1].url.params["FundCode"], "CN")
        self.assertEqual(calls[-2].url.params["SearchDate"], "")
        self.assertEqual(calls[-1].url.params["SearchDate"], "2026-09-04")
        self.assertEqual(len(snapshot.positions), 1)

    def test_api_error_does_not_create_snapshot(self):
        with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
            200, json={"returnCode": "4005", "result": None}
        ))) as client, self.assertRaises(ValueError):
            fetch_cathay_constituent_snapshot("00878", client=client)

    def test_rejects_nested_etf_and_malformed_rows(self):
        for rows in ([None], [{"weights": "invalid"}],
                     [{"stockCode": "1488.JP", "stockName": "DAIWA ETF - TSE REIT INDEX", "weights": "98.19"}]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.parse(stocks=rows)

    def test_latest_disclosure_cannot_leak_into_historical_evaluation(self):
        with self.assertRaisesRegex(ValueError, "future or stale"):
            self.parse(evaluated_on=date(2026, 9, 2))

    def test_http_error_and_oversized_response_fail_closed(self):
        for response in (httpx.Response(403), httpx.Response(200, content=b" " * 5_000_001)):
            with self.subTest(status=response.status_code), httpx.Client(
                transport=httpx.MockTransport(lambda request: response)
            ) as client, self.assertRaises((httpx.HTTPStatusError, ValueError)):
                fetch_cathay_constituent_snapshot("00878", client=client)
