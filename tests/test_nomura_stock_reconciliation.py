"""Synthetic evidence for the bounded Nomura stock reconciliation path."""

import copy
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock, patch

from backend.app.data_sources.direct_constituent_adapters import (
    fetch_nomura_constituent_snapshot, parse_nomura_constituent_payload,
)

FETCHED = datetime(2026, 9, 8, tzinfo=timezone.utc)


def payload():
    def columns(*names):
        return [{"Name": name} for name in names]
    return {"StatusCode": 0, "Entries": {"FundID": "00985A", "Data": {
        "FundAsset": {"Aum": "1000000", "NavDate": "2026/09/04"},
        "Table": [
            {"TableTitle": "股票", "NavDate": "2026/09/04",
             "Columns": columns("股票代號", "股票名稱", "股數", "權重(%)"),
             "Rows": [["2330", "Stock A", "100", "60"],
                      ["2454", "Stock B", "100", "28.02"],
                      ["2308", "Stock C", "1", "0"]]},
            {"TableTitle": "", "NavDate": "2026/09/04",
             "Columns": columns("項目", "金額", "幣別", "金額(原幣)"),
             "Rows": [["股票", "TWD$880,200", "TWD", "880200"]]},
            {"TableTitle": "期貨", "NavDate": "2026/09/04",
             "Rows": [["TX", "Futures", "1", "5"]]},
        ],
    }}}


def parse(value):
    return parse_nomura_constituent_payload(
        value, etf_code="00985A", source_url="https://example.test",
        fetched_at=FETCHED,
    )


class NomuraStockReconciliationTests(unittest.TestCase):
    def test_accepts_reconciled_stocks_without_normalizing_or_futures(self):
        result = parse(payload())
        self.assertEqual(sum(p.weight_pct for p in result.positions), Decimal("88.02"))
        self.assertEqual([p.constituent_id for p in result.positions], ["2330", "2454", "2308"])
        self.assertEqual(result.positions[-1].weight_pct, 0)

    def test_missing_or_ambiguous_evidence_fails(self):
        for change in ("aum", "summary", "duplicate_summary", "duplicate_stock", "headers"):
            with self.subTest(change=change):
                value = payload()
                data = value["Entries"]["Data"]
                if change == "aum": del data["FundAsset"]
                elif change == "summary": del data["Table"][1]
                elif change == "duplicate_summary": data["Table"].append(copy.deepcopy(data["Table"][1]))
                elif change == "duplicate_stock": data["Table"].append(copy.deepcopy(data["Table"][0]))
                else: data["Table"][0]["Columns"].reverse()
                with self.assertRaises(ValueError): parse(value)

    def test_dates_must_match(self):
        for target in ("aum", "summary"):
            value = payload()
            data = value["Entries"]["Data"]
            (data["FundAsset"] if target == "aum" else data["Table"][1])["NavDate"] = "2026/09/03"
            with self.assertRaises(ValueError): parse(value)

    def test_stock_amount_currency_and_duplicates_fail(self):
        for index, replacement in ((1, "USD$880,200"), (1, "TWD$880,201"),
                                   (2, "USD"), (3, "NaN"), (3, "-1")):
            value = payload()
            value["Entries"]["Data"]["Table"][1]["Rows"][0][index] = replacement
            with self.assertRaises(ValueError): parse(value)
        value = payload()
        rows = value["Entries"]["Data"]["Table"][1]["Rows"]
        rows.append(copy.deepcopy(rows[0]))
        with self.assertRaises(ValueError): parse(value)

    def test_invalid_aum_fails(self):
        for amount in ("0", "-1", "NaN", "Infinity", "800000", None):
            value = payload()
            value["Entries"]["Data"]["FundAsset"]["Aum"] = amount
            with self.assertRaises(ValueError): parse(value)

    def test_partial_rows_and_invalid_weights_fail(self):
        for row in (["X"], ["X", "", "1", "1"], ["X", "X", "1", "NaN"],
                    ["X", "X", "1", "-1"], ["X", "X", "1", "0.001"],
                    ["合計", "Total", "1", "0"], "not a row"):
            value = payload()
            value["Entries"]["Data"]["Table"][0]["Rows"].append(row)
            with self.assertRaises(ValueError): parse(value)

    def test_duplicate_identifier_fails(self):
        value = payload()
        value["Entries"]["Data"]["Table"][0]["Rows"][2][0] = "2330"
        with self.assertRaises(ValueError): parse(value)

    def test_two_decimal_rounding_is_bounded(self):
        value = payload()
        value["Entries"]["Data"]["Table"][0]["Rows"][1][3] = "28.03"
        parse(value)  # 0.01 pp within the three-row 0.015 pp bound.
        value["Entries"]["Data"]["Table"][0]["Rows"][1][3] = "28.04"
        with self.assertRaises(ValueError): parse(value)

    def test_below_85_still_fails(self):
        value = payload()
        value["Entries"]["Data"]["Table"][0]["Rows"][1][3] = "24.99"
        with self.assertRaises(ValueError): parse(value)

    def test_exact_85_boundary_requires_reconciliation(self):
        value = payload()
        data = value["Entries"]["Data"]
        data["Table"][0]["Rows"][1][3] = "25"
        data["Table"][1]["Rows"][0] = ["股票", "TWD$850,000", "TWD", "850000"]
        self.assertEqual(sum(p.weight_pct for p in parse(value).positions), 85)

    def test_rounding_tolerance_cannot_grow_past_quarter_point(self):
        value = payload()
        rows = value["Entries"]["Data"]["Table"][0]["Rows"]
        rows.extend([[str(4000 + i), "Zero", "1", "0"] for i in range(100)])
        rows[1][3] = "28.28"
        with self.assertRaises(ValueError): parse(value)

    def test_nested_etf_is_not_stock(self):
        value = payload()
        value["Entries"]["Data"]["Table"][0]["TableTitle"] = "ETF"
        with self.assertRaises(ValueError): parse(value)

    def test_identity_and_failure_status(self):
        value = payload()
        value["Entries"]["FundID"] = "00944"
        with self.assertRaises(ValueError): parse(value)
        value = payload()
        value["StatusCode"] = 1
        with self.assertRaises(ValueError): parse(value)

    @patch("backend.app.data_sources.direct_constituent_adapters.httpx.post")
    def test_historical_request_checks_exact_date(self, post):
        post.return_value = Mock()
        post.return_value.json.return_value = payload()
        fetch_nomura_constituent_snapshot("00985A", snapshot_on=date(2026, 9, 4), fetched_at=FETCHED)
        self.assertEqual(post.call_args.kwargs["json"]["SearchDate"], "2026-09-04")
        with self.assertRaises(ValueError):
            fetch_nomura_constituent_snapshot("00985A", snapshot_on=date(2026, 9, 3), fetched_at=FETCHED)
        post.reset_mock()
        with self.assertRaises(ValueError):
            fetch_nomura_constituent_snapshot("00985A", snapshot_on=date(2026, 9, 9), fetched_at=FETCHED)
        post.assert_not_called()
