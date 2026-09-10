"""Annual expense evidence, immutable import and additive API regression."""

from contextlib import closing
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend.app.api.dependencies import get_database_path
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.data_sources.detail_page_coverage import build_detail_page_coverage
from backend.app.data_sources.reviewed_annual_expense import create_candidate, reviewed_observations, SOURCE_URL
from backend.app.main import create_app
from backend.app.models.annual_expense import AnnualExpenseEvidence
from backend.app.repositories.annual_expense_repository import annual_expense_catalog, save_annual_expenses
from backend.app.repositories.etf_repository import get_etf_by_code, list_etfs


def observation(**changes):
    fields = dict(etf_code="0056", issuer_product_id="1084", legal_name="Synthetic fund",
        reporting_year=2025, expense_ratio_pct="0.57", publication_date=date(2026, 7, 29),
        retrieved_at=datetime(2026, 9, 8, tzinfo=timezone.utc), source_url=SOURCE_URL,
        identity_url="https://www.yuantafunds.com/myfund/information/1084",
        document_sha256="a" * 64, document_page=3,
        review_reference="https://github.com/twstockanalysis/goodcat-website/issues/130")
    return AnnualExpenseEvidence(**(fields | changes))


class TestAnnualExpense(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "source.db"
        initialize_database(self.db)
        with closing(get_connection(self.db)) as conn, conn:
            conn.execute("INSERT INTO etf_master(code,name,listing_date) VALUES('0056','Synthetic fund','2007-12-26')")
        self.on = date(2026, 9, 6)
        clock = patch("backend.app.repositories.etf_repository.date")
        clock.start().today.return_value = self.on
        self.addCleanup(clock.stop)

    def save(self, *values):
        return save_annual_expenses(list(values), self.db, evaluated_on=self.on)

    def catalog(self, on=None):
        conn = get_connection(self.db)
        try:
            return annual_expense_catalog(conn, evaluated_on=on or self.on)
        finally:
            conn.close()

    def test_latest_annual_value_and_master_preserved(self):
        self.save(observation(reporting_year=2024, expense_ratio_pct="0.60"), observation())
        self.assertEqual(self.catalog()["0056"].reporting_year, 2025)
        self.assertEqual(get_etf_by_code("0056", self.db)["expense_ratio"], .57)
        self.assertEqual(list_etfs(self.db)[0]["annual_expense"]["reporting_year"], 2025)
        conn = get_connection(self.db)
        try:
            self.assertIsNone(conn.execute("SELECT expense_ratio FROM etf_master").fetchone()[0])
        finally:
            conn.close()

    def test_idempotent_retrieval_keeps_original_record(self):
        self.assertEqual(self.save(observation()), 1)
        self.assertEqual(self.save(observation(retrieved_at=datetime(2026, 9, 9, tzinfo=timezone.utc))), 0)
        self.assertEqual(self.catalog()["0056"].retrieved_at.day, 8)

    def test_conflict_rolls_back_whole_batch(self):
        self.save(observation())
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.save(observation(reporting_year=2024), observation(expense_ratio_pct="0.58"))
        conn = get_connection(self.db)
        try:
            self.assertEqual(conn.execute("SELECT count(*) FROM etf_annual_expense_evidence").fetchone()[0], 1)
        finally:
            conn.close()

    def test_zero_is_not_missing(self):
        self.save(observation(expense_ratio_pct="0"))
        self.assertEqual(self.catalog()["0056"].expense_ratio_pct, Decimal(0))
        self.assertEqual(get_etf_by_code("0056", self.db)["expense_ratio"], 0)

    def test_unknown_etf_and_partial_year_rejected(self):
        with self.assertRaisesRegex(ValueError, "not found"):
            self.save(observation(etf_code="0099"))
        with closing(get_connection(self.db)) as conn, conn:
            conn.execute("UPDATE etf_master SET listing_date='2025-02-01'")
        with self.assertRaisesRegex(ValueError, "Full-year"):
            self.save(observation())

    def test_future_publication_rejected(self):
        with self.assertRaisesRegex(ValueError, "after evaluation"):
            self.save(observation(publication_date=date(2026, 9, 7)))

    def test_selection_publication_boundary(self):
        self.save(observation())
        self.assertEqual(self.catalog(date(2026, 7, 28)), {})
        self.assertIn("0056", self.catalog(date(2026, 7, 29)))

    def test_invalid_values_dates_and_identity(self):
        for fields in ({"expense_ratio_pct": "NaN"}, {"expense_ratio_pct": "Infinity"},
                       {"expense_ratio_pct": "NA"}, {"expense_ratio_pct": None},
                       {"expense_ratio_pct": "-0.1"}, {"expense_ratio_pct": "101"},
                       {"reporting_year": 2026}, {"reporting_year": True},
                       {"retrieved_at": datetime(2026, 9, 8)},
                       {"retrieved_at": datetime(2026, 1, 1, tzinfo=timezone.utc)},
                       {"issuer_product_id": "1066"}, {"source_url": "https://evil.invalid/a.pdf"}):
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                observation(**fields)

    def test_old_database_and_legacy_value(self):
        with closing(get_connection(self.db)) as conn, conn:
            conn.execute("DROP TABLE etf_annual_expense_evidence")
            conn.execute("UPDATE etf_master SET expense_ratio=0.4")
        item = get_etf_by_code("0056", self.db)
        self.assertEqual(item["expense_ratio"], .4)
        self.assertNotIn("annual_expense", item)

    def test_api_exposes_year_and_source(self):
        self.save(observation())
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: self.db
        with TestClient(app) as client:
            for path in ("/api/v1/etfs/0056", "/api/v1/etfs"):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                item = data["items"][0] if "items" in data else data
                self.assertEqual(item["annual_expense"]["reporting_year"], 2025)
                self.assertEqual(item["annual_expense"]["source_url"], SOURCE_URL)
                self.assertEqual(item["expense_ratio"], .57)

    def test_coverage_uses_evaluation_not_generation_date(self):
        self.save(observation())
        for on, count in ((date(2026, 7, 28), 0), (self.on, 1)):
            report = build_detail_page_coverage(self.db, evaluated_on=on)
            self.assertEqual(report["field_coverage"]["expense_ratio"]["available_count"], count)

    def test_unknown_document_rejected_before_candidate_creation(self):
        pdf = Path(self.tmp.name) / "unknown.pdf"
        pdf.write_bytes(b"unreviewed PDF")
        target = Path(self.tmp.name) / "candidate.db"
        with self.assertRaisesRegex(ValueError, "Unknown document"):
            create_candidate(self.db, target, pdf, evaluated_on=self.on)
        self.assertFalse(target.exists())

    def test_candidate_exclusive_and_source_unchanged(self):
        before = self.db.read_bytes()
        target = Path(self.tmp.name) / "candidate.db"
        with patch("backend.app.data_sources.reviewed_annual_expense.reviewed_observations", return_value=[observation()]):
            self.assertEqual(create_candidate(self.db, target, Path("synthetic"), evaluated_on=self.on), 1)
            with self.assertRaises(FileExistsError):
                create_candidate(self.db, target, Path("synthetic"), evaluated_on=self.on)
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_database_not_created(self):
        target = Path(self.tmp.name) / "missing.db"
        with self.assertRaises(FileNotFoundError):
            save_annual_expenses([observation()], target, evaluated_on=self.on)
        self.assertFalse(target.exists())
