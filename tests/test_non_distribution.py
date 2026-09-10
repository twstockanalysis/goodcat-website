"""Separate notices never create payments, composition or planner input."""

from contextlib import closing
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

from backend.app.api.dependencies import get_database_path
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.data_sources.reviewed_non_distribution import create_candidate, reviewed_notices
from backend.app.main import create_app
from backend.app.models.non_distribution import NonDistributionNotice, NonDistributionEvidence
from backend.app.repositories.etf_repository import get_etf_by_code
from backend.app.repositories.non_distribution_repository import (
    read_non_distribution_evidence, save_non_distribution_notices,
)


class TestNonDistribution(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "source.db"
        initialize_database(self.db)
        with closing(get_connection(self.db)) as c, c:
            for code in ("00660", "00920", "0050"):
                c.execute("INSERT INTO etf_master(code,name,listing_date) VALUES (?,?,'2010-01-01')",
                          (code, "Synthetic fund"))
        self.on = date(2026, 9, 6)

    def save(self, notices=None):
        return save_non_distribution_notices(
            reviewed_notices() if notices is None else notices, self.db, evaluated_on=self.on)

    def read(self, code="00920", on=None):
        return read_non_distribution_evidence(code, self.db, evaluated_on=on or self.on)

    def test_manifest_dates_and_no_payment_fields(self):
        notices = reviewed_notices()
        self.assertEqual([(n.etf_code, str(n.evaluation_date), str(n.publication_date)) for n in notices],
                         [("00660", "2025-09-30", "2025-10-01"),
                          ("00920", "2025-12-31", "2026-01-02")])
        self.assertNotIn("amount_per_unit", notices[0].model_dump())
        self.assertEqual(notices[0].evidence_method, "REVIEWED_TRANSCRIPTION")

    def test_atomic_idempotent_and_not_planner_input(self):
        before = get_etf_by_code("00920", self.db)
        self.assertEqual(self.save(), 2)
        self.assertEqual(self.save(), 0)
        self.assertEqual(get_etf_by_code("00920", self.db), before)
        with closing(get_connection(self.db)) as c:
            for table in ("etf_dividend", "etf_dividend_component"):
                self.assertEqual(c.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0)

    def test_cutoff_and_unknown_evidence(self):
        self.save()
        self.assertEqual(self.read(on=date(2026, 1, 1)).status, "NO_REVIEWED_NOTICE")
        self.assertEqual(self.read(on=date(2026, 1, 2)).status, "REVIEWED_NOTICES")
        self.assertEqual(self.read("0050").items, [])

    def test_conflicting_batch_rolls_back(self):
        a, b = reviewed_notices()
        self.save([b])
        conflict = b.model_copy(update={"legal_name": "Different fund"})
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.save([a, conflict])
        self.assertEqual(self.read("00660").items, [])

    def test_invalid_dates_identity_extra_and_status(self):
        base = reviewed_notices()[1].model_dump()
        for update in ({"evaluation_date": date(2027, 1, 1)},
                       {"reviewed_on": date(2025, 1, 1)},
                       {"source_url": "https://evil.invalid/"},
                       {"etf_code": "0050"}, {"amount_per_unit": 0}):
            with self.subTest(update=update), self.assertRaises(ValidationError):
                NonDistributionNotice(**(base | update))
        with self.assertRaises(ValidationError):
            NonDistributionEvidence(status="REVIEWED_NOTICES", items=[])

    def test_future_and_unknown_master_rejected(self):
        with self.assertRaisesRegex(ValueError, "Publication"):
            save_non_distribution_notices(reviewed_notices(), self.db, evaluated_on=date(2025, 1, 1))
        with closing(get_connection(self.db)) as c, c:
            c.execute("DELETE FROM etf_master WHERE code='00920'")
        with self.assertRaisesRegex(ValueError, "Unknown"):
            self.save()
        self.assertEqual(self.read("00660").items, [])

    def test_old_database_is_readable_without_migration(self):
        with closing(get_connection(self.db)) as c, c:
            c.execute("DROP TABLE etf_non_distribution_notice")
        before = self.db.read_bytes()
        self.assertEqual(self.read().status, "NO_REVIEWED_NOTICE")
        self.assertEqual(self.db.read_bytes(), before)

    def test_exclusive_candidate_and_source_preserved(self):
        before = self.db.read_bytes()
        target = Path(self.tmp.name) / "candidate.db"
        self.assertEqual(create_candidate(self.db, target, evaluated_on=self.on), 2)
        with self.assertRaises(FileExistsError):
            create_candidate(self.db, target, evaluated_on=self.on)
        with self.assertRaises(FileExistsError):
            create_candidate(self.db, self.db, evaluated_on=self.on)
        self.assertEqual(self.db.read_bytes(), before)

    def test_missing_database_is_not_created(self):
        path = Path(self.tmp.name) / "absent.db"
        with self.assertRaises(FileNotFoundError):
            read_non_distribution_evidence("00920", path, evaluated_on=self.on)
        with self.assertRaises(FileNotFoundError):
            save_non_distribution_notices([], path, evaluated_on=self.on)
        self.assertFalse(path.exists())

    def test_detail_api_and_real_information_component(self):
        self.save()
        app = create_app()
        app.dependency_overrides[get_database_path] = lambda: self.db
        with patch("backend.app.api.routers.etfs.date") as clock, TestClient(app) as client:
            clock.today.return_value = self.on
            response = client.get("/api/v1/etfs/00920")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["non_distribution_evidence"]["status"], "REVIEWED_NOTICES")
            self.assertEqual(client.get("/api/v1/etfs/UNKNOWN").status_code, 404)
        ui = AppTest.from_string(
            "from frontend.pages.etf_detail import render_etf_information\n"
            f"render_etf_information({payload!r})"
        ).run(timeout=30)
        self.assertFalse(ui.exception)
        self.assertTrue(any("2025-12-31" in x.value for x in ui.markdown))
        self.assertTrue(any("不是 0 元" in x.value for x in ui.caption))
        self.assertEqual(ui.get("link_button")[0].proto.url, reviewed_notices()[1].source_url)

    def test_missing_evidence_ui_is_not_zero_or_permanent_status(self):
        ui = AppTest.from_string(
            "from frontend.pages.etf_detail import render_non_distribution_evidence\n"
            "render_non_distribution_evidence({'non_distribution_evidence': "
            "{'status':'NO_REVIEWED_NOTICE','items':[]}})"
        ).run(timeout=30)
        self.assertFalse(ui.exception)
        self.assertIn("不表示已配息或配息為零", ui.caption[0].value)
        self.assertEqual(len(ui.get("link_button")), 0)
