"""Synthetic official-asset shapes and isolated SQLite regression."""

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.data_sources.cathay_fund_size import parse_cathay_fund_size, fetch_cathay_fund_size
from backend.app.database.init_db import initialize_database
from backend.app.database.connection import get_connection
from backend.app.repositories.fund_size_repository import save_fund_size_evidence


DAY = date(2026, 9, 6)


def evidence(amount="123,456,789", day="2026/09/04", currency="新台幣", **changes):
    identity = {"stockCode": "00878", "fundCode": "CN", "currency": currency}
    identity.update(changes)
    return parse_cathay_fund_size("00878", "CN", {"stockCode": "00878", "fundCode": "CN"},
        identity, {"preDate": day, "fundNav": amount}, evaluated_on=DAY,
        fetched_at=datetime(2026, 9, 7, tzinfo=timezone.utc))


class TestCathayFundSize(unittest.TestCase):
    def test_exact_units_and_canonical_evidence(self):
        value = evidence()
        self.assertEqual(value.fund_size, Decimal("1.23456789"))
        self.assertEqual(len(value.evidence_sha256), 64)
        self.assertIn('"fundNav":"123,456,789"', value.evidence_json)
        self.assertIn("SearchDate=2026-09-04", value.source_url)

    def test_reported_zero_is_not_missing(self):
        self.assertEqual(evidence("0").fund_size, Decimal(0))

    def test_invalid_amounts_are_rejected(self):
        for amount in (None, "", "-", "-1", "NaN", "Infinity", "12,34", "1e9", "1,234abc"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                evidence(amount)

    def test_currency_and_identity_fail_closed(self):
        for currency in ("美元", "", None):
            with self.assertRaises(ValueError):
                evidence(currency=currency)
        with self.assertRaises(ValueError):
            evidence(stockCode="00636K")
        with self.assertRaises(ValueError):
            evidence(fundCode="OTHER")

    def test_date_boundaries(self):
        self.assertEqual(evidence(day="2026/09/06").as_of_date, DAY)
        for day in ("2026/09/07", "2026/08/29", "invalid"):
            with self.assertRaises(ValueError):
                evidence(day=day)

    def test_network_requires_explicit_permission(self):
        with self.assertRaises(ValueError):
            fetch_cathay_fund_size("00878", evaluated_on=DAY)

    @patch("backend.app.data_sources.cathay_fund_size._get")
    def test_date_request_must_be_honored(self, get):
        get.side_effect = [[{"stockCode": "00878", "fundCode": "CN"}],
            {"stockCode": "00878", "fundCode": "CN", "currency": "新台幣"},
            {"preDate": "2026/09/05", "fundNav": "100"}]
        with self.assertRaisesRegex(ValueError, "date differ"):
            fetch_cathay_fund_size("00878", evaluated_on=DAY,
                                  snapshot_on=date(2026, 9, 4), allow_network=True, client=object())


class TestFundSizePersistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = initialize_database(Path(self.temp.name)/"candidate.db")
        with get_connection(self.db) as c:
            c.execute("INSERT INTO etf_master(code,name,expense_ratio) VALUES('00878','Test',0.3)")
        c.close()

    def tearDown(self):
        self.temp.cleanup()

    def read(self):
        c = get_connection(self.db)
        try:
            return (tuple(c.execute("SELECT fund_size,expense_ratio FROM etf_master").fetchone()),
                    c.execute("SELECT count(*) FROM etf_fund_size_evidence").fetchone()[0])
        finally:
            c.close()

    def save(self, value):
        return save_fund_size_evidence(value, self.db, evaluated_on=DAY)

    def test_atomic_projection_and_idempotence(self):
        self.assertEqual(self.save(evidence()), "IMPORTED")
        self.assertEqual(self.save(evidence()), "UNCHANGED")
        self.assertEqual(self.read(), ((1.23456789, 0.3), 1))

    def test_conflict_rolls_back(self):
        self.save(evidence())
        with self.assertRaises(ValueError):
            self.save(evidence("999"))
        self.assertEqual(self.read(), ((1.23456789, 0.3), 1))

    def test_older_snapshot_does_not_replace_projection(self):
        self.save(evidence())
        self.save(evidence("1", day="2026/09/03"))
        self.assertEqual(self.read(), ((1.23456789, 0.3), 2))

    def test_newer_zero_replaces_projection(self):
        self.save(evidence())
        self.save(evidence("0", day="2026/09/05"))
        self.assertEqual(self.read(), ((0.0, 0.3), 2))

    def test_legacy_value_is_not_silently_overwritten(self):
        c = get_connection(self.db)
        c.execute("UPDATE etf_master SET fund_size=99")
        c.commit()
        c.close()
        with self.assertRaises(ValueError):
            self.save(evidence())
        self.assertEqual(self.read(), ((99.0, 0.3), 0))

    def test_additive_schema_reinitialization_preserves_data(self):
        self.save(evidence())
        initialize_database(self.db)
        self.assertEqual(self.read(), ((1.23456789, 0.3), 1))

    def test_projection_failure_rolls_back_insert(self):
        c = get_connection(self.db)
        c.execute("CREATE TRIGGER reject_size BEFORE UPDATE OF fund_size ON etf_master BEGIN SELECT RAISE(ABORT,'test'); END")
        c.commit()
        c.close()
        with self.assertRaises(Exception):
            self.save(evidence())
        self.assertEqual(self.read(), ((None, 0.3), 0))
