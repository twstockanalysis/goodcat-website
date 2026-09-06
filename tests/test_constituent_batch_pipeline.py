"""V2-10 成分股批次匯入與品質門檻測試。"""

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from backend.app.data_sources.constituent_batch_pipeline import (
    build_constituent_batch_plan,
    resolve_constituent_issuer,
    run_constituent_batch_pipeline,
)
from backend.app.data_sources.constituent_pipeline import (
    OfficialConstituentImportResult,
)
from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.models.etf_constituent import ETFConstituentSnapshotCreate
from backend.app.repositories.etf_constituent_repository import (
    save_constituent_snapshot,
)
from backend.app.services.constituent_data_quality import (
    ConstituentQualityThreshold,
    evaluate_constituent_data_quality,
)


class ConstituentBatchTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "constituents.db"
        initialize_database(self.database_path)

    def tearDown(self):
        self.directory.cleanup()

    def insert_etfs(self, rows):
        connection = get_connection(self.database_path)
        connection.executemany(
            "INSERT INTO etf_master (code, name, is_bond) VALUES (?, ?, ?);",
            rows,
        )
        connection.executemany(
            """
            INSERT INTO etf_performance (
                etf_code, as_of_date, period_code, metric_code,
                return_pct, source_id
            ) VALUES (?, '2026-08-14', '6M', 'PRICE_RETURN', 10, 'test');
            """,
            [(row[0],) for row in rows],
        )
        connection.commit()
        connection.close()

    @staticmethod
    def payload(etf_code: str, as_of_date: date = date(2026, 8, 14)):
        return ETFConstituentSnapshotCreate(
            etf_code=etf_code,
            as_of_date=as_of_date,
            source_id=(
                "yuanta_official_pcf" if etf_code == "0050" else "uob_official_pcf"
            ),
            source_url="https://example.test/official",
            fetched_at=datetime(2026, 8, 14, 8, tzinfo=timezone.utc),
            positions=[
                {
                    "constituent_id": "2330",
                    "constituent_name": "台積電",
                    "weight_pct": "90",
                }
            ],
        )

    def test_resolves_reviewed_issuer_markers(self):
        self.assertEqual(resolve_constituent_issuer("主動國泰動能高息"), "cathay")
        self.assertEqual(resolve_constituent_issuer("FH美國金融股"), "fuh_hwa")
        self.assertEqual(resolve_constituent_issuer("FT臺灣永續高息"), "franklin")
        self.assertEqual(
            resolve_constituent_issuer("臺灣中小A級動能50 ETF基金", "00733"),
            "fubon",
        )
        self.assertIsNone(resolve_constituent_issuer("未識別品牌ETF"))

    def test_plan_keeps_unresolved_and_unsupported_items_visible(self):
        self.insert_etfs(
            [
                ("0050", "元大台灣50", 0),
                ("00878", "國泰永續高股息", 0),
                ("009813", "貝萊德標普500卓越50", 0),
                ("00631L", "元大台灣50正2", 0),
                ("00710B", "復華非投等債", 1),
                ("0060", "新台灣", 0),
            ]
        )
        statuses = {
            item.etf_code: item.status
            for item in build_constituent_batch_plan(self.database_path)
        }
        self.assertEqual(statuses["0050"], "ELIGIBLE_AUTOMATED")
        self.assertEqual(statuses["00878"], "ELIGIBLE_AUTOMATED")
        self.assertEqual(statuses["009813"], "SOURCE_NOT_AUTOMATED")
        self.assertEqual(statuses["00631L"], "NOT_EQUITY")
        self.assertEqual(statuses["00710B"], "NOT_EQUITY")
        self.assertEqual(statuses["0060"], "UNMAPPED_ISSUER")

    def test_missing_performance_baseline_is_not_import_eligible(self):
        connection = get_connection(self.database_path)
        connection.execute(
            "INSERT INTO etf_master (code, name) VALUES ('0060', '新台灣');"
        )
        connection.commit()
        connection.close()
        plan = build_constituent_batch_plan(self.database_path)
        self.assertEqual(plan[0].status, "MISSING_PERFORMANCE_BASELINE")

    def test_quality_rejects_missing_and_stale_snapshots(self):
        self.insert_etfs(
            [("0050", "元大台灣50", 0), ("00918", "大華優利高填息30", 0)]
        )
        save_constituent_snapshot(
            self.payload("0050", date(2026, 8, 1)), self.database_path
        )
        result = evaluate_constituent_data_quality(
            [
                {"etf_code": "0050", "issuer_key": "yuanta"},
                {"etf_code": "00918", "issuer_key": "uob"},
            ],
            self.database_path,
            evaluated_on=date(2026, 8, 14),
        )
        self.assertEqual(result["decision"], "NO_GO")
        reasons = {item["etf_code"]: item["reasons"] for item in result["items"]}
        self.assertIn("STALE_SNAPSHOT", reasons["0050"])
        self.assertIn("MISSING_SNAPSHOT", reasons["00918"])

    def test_quality_threshold_rejects_invalid_ranges(self):
        with self.assertRaisesRegex(ValueError, "max_age_days"):
            ConstituentQualityThreshold(max_age_days=-1)
        with self.assertRaisesRegex(ValueError, "minimum_etf_coverage_pct"):
            ConstituentQualityThreshold(minimum_etf_coverage_pct=101)

    def test_targeted_batch_import_can_pass_for_calculation_fixture(self):
        self.insert_etfs(
            [("0050", "元大台灣50", 0), ("00918", "大華優利高填息30", 0)]
        )

        def importer(issuer_key, etf_code, database_path):
            snapshot = save_constituent_snapshot(
                self.payload(etf_code), database_path
            )
            return OfficialConstituentImportResult(snapshot, "IMPORTED")

        result = run_constituent_batch_pipeline(
            self.database_path,
            etf_codes={"0050", "00918"},
            evaluated_on=date(2026, 8, 14),
            importer=importer,
        )
        self.assertEqual(result["imported_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(result["quality"]["decision"], "READY")
        self.assertEqual(result["database"], "constituents.db")

    def test_checkpoint_resume_retries_only_failed_codes(self):
        self.insert_etfs(
            [("0050", "元大台灣50", 0), ("00918", "大華優利高填息30", 0)]
        )
        checkpoint_path = Path(self.directory.name) / "constituents-checkpoint.json"
        first_calls = []

        def first_importer(issuer_key, etf_code, database_path):
            first_calls.append(etf_code)
            if etf_code == "00918":
                raise ConnectionError("x" * 2000)
            snapshot = save_constituent_snapshot(
                self.payload(etf_code), database_path
            )
            return OfficialConstituentImportResult(snapshot, "IMPORTED")

        first = run_constituent_batch_pipeline(
            self.database_path,
            evaluated_on=date(2026, 8, 14),
            checkpoint_path=checkpoint_path,
            importer=first_importer,
        )
        self.assertEqual(first_calls, ["0050", "00918"])
        self.assertEqual(first["attempted_count"], 2)
        self.assertEqual(first["failed_count"], 1)
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        failed = next(
            row for row in checkpoint["results"] if row["etf_code"] == "00918"
        )
        self.assertEqual(len(failed["error"]), 1000)

        resumed_calls = []

        def resumed_importer(issuer_key, etf_code, database_path):
            resumed_calls.append(etf_code)
            snapshot = save_constituent_snapshot(
                self.payload(etf_code), database_path
            )
            return OfficialConstituentImportResult(snapshot, "IMPORTED")

        resumed = run_constituent_batch_pipeline(
            self.database_path,
            evaluated_on=date(2026, 8, 14),
            checkpoint_path=checkpoint_path,
            resume=True,
            importer=resumed_importer,
        )
        self.assertEqual(resumed_calls, ["00918"])
        self.assertEqual(resumed["attempted_count"], 1)
        self.assertEqual(resumed["skipped_completed_count"], 1)
        self.assertEqual(resumed["imported_count"], 1)
        self.assertEqual(resumed["failed_count"], 0)
        self.assertEqual(resumed["quality"]["decision"], "READY")

    def test_resume_requires_matching_checkpoint_database(self):
        checkpoint_path = Path(self.directory.name) / "constituents-checkpoint.json"
        checkpoint_path.write_text(
            '{"schema_version": 1, "database": "other.db", "results": []}',
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "目標資料庫不符"):
            run_constituent_batch_pipeline(
                self.database_path,
                checkpoint_path=checkpoint_path,
                resume=True,
                importer=lambda *args: None,
            )


if __name__ == "__main__":
    unittest.main()
