from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.models.etf_price import ETFDailyCloseRecord
from backend.app.repositories import daily_close_repository
from backend.app.repositories.daily_close_repository import (
    get_latest_daily_close,
    list_daily_closes,
    upsert_daily_close_records,
)


class TestDailyCloseRepository(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_directory.cleanup)
        self.database_path = Path(self.temp_directory.name) / "daily-close.db"
        initialize_database(self.database_path)
        connection = get_connection(self.database_path)
        connection.execute(
            "INSERT INTO etf_master (code, name) VALUES ('0056', '元大高股息');"
        )
        connection.commit()
        connection.close()

    def record(self, trade_date: str, close_price: str):
        return ETFDailyCloseRecord(
            etf_code="0056",
            trade_date=trade_date,
            close_price=close_price,
            source_id="twse_stock_day",
        )

    def test_upsert_is_idempotent_and_latest_keeps_source(self):
        first = upsert_daily_close_records(
            [self.record("2026-08-07", "35"), self.record("2026-08-08", "36")],
            self.database_path,
        )
        second = upsert_daily_close_records(
            [self.record("2026-08-08", "36.5")],
            self.database_path,
        )
        self.assertEqual(first.inserted_records, 2)
        self.assertEqual(second.updated_records, 1)
        latest = get_latest_daily_close("0056", self.database_path)
        self.assertEqual(latest["trade_date"], "2026-08-08")
        self.assertEqual(latest["close_price"], Decimal("36.5"))
        self.assertEqual(latest["source_id"], "twse_stock_day")
        self.assertEqual(len(list_daily_closes("0056", self.database_path)), 2)

    def test_missing_close_stays_missing(self):
        self.assertIsNone(get_latest_daily_close("0056", self.database_path))

    def test_empty_generator_does_not_create_database(self):
        unused_path = Path(self.temp_directory.name) / "unused.db"
        summary = upsert_daily_close_records(iter(()), unused_path)
        self.assertEqual(
            (summary.total_records, summary.inserted_records, summary.updated_records),
            (0, 0, 0),
        )
        self.assertFalse(unused_path.exists())

    def test_duplicate_keys_use_last_price_and_keep_sources_distinct(self):
        original = self.record("2026-08-07", "35.123456")
        upsert_daily_close_records([original], self.database_path)
        other_source = original.model_copy(update={"source_id": "other_source"})
        summary = upsert_daily_close_records(
            iter([original, other_source, self.record("2026-08-07", "36.654321")]),
            self.database_path,
        )
        self.assertEqual(
            (summary.total_records, summary.inserted_records, summary.updated_records),
            (2, 1, 1),
        )
        prices = {
            row["source_id"]: row["close_price"]
            for row in list_daily_closes("0056", self.database_path)
        }
        self.assertEqual(prices, {
            "twse_stock_day": Decimal("36.654321"),
            "other_source": Decimal("35.123456"),
        })

    def test_large_batch_counts_unchanged_updates_and_new_dates(self):
        records = [
            self.record((date(2020, 1, 1) + timedelta(days=i)).isoformat(), "35")
            for i in range(605)
        ]
        upsert_daily_close_records(records[::2], self.database_path)
        summary = upsert_daily_close_records(iter(records), self.database_path)
        self.assertEqual(
            (summary.total_records, summary.inserted_records, summary.updated_records),
            (605, 302, 303),
        )
        self.assertEqual(len(list_daily_closes("0056", self.database_path)), 605)

    def test_foreign_key_failure_rolls_back_inserts_and_updates(self):
        original = self.record("2026-08-07", "35")
        upsert_daily_close_records([original], self.database_path)
        unknown_etf = original.model_copy(update={"etf_code": "9999"})
        with self.assertRaises(sqlite3.IntegrityError):
            upsert_daily_close_records([
                self.record("2026-08-07", "36"),
                self.record("2026-08-08", "37"),
                unknown_etf,
            ], self.database_path)
        rows = list_daily_closes("0056", self.database_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close_price"], Decimal("35"))
        # A new write also verifies that the failed transaction released its lock.
        summary = upsert_daily_close_records(
            [self.record("2026-08-08", "37")], self.database_path,
        )
        self.assertEqual(summary.inserted_records, 1)

    def test_small_upsert_does_not_scan_unrelated_history(self):
        records = [
            self.record((date(2020, 1, 1) + timedelta(days=i)).isoformat(), "35")
            for i in range(2000)
        ]
        upsert_daily_close_records(records, self.database_path)
        connection = get_connection(self.database_path)
        # Bound SQLite VM work, not wall time: a full history scan exceeds this
        # budget, while a primary-key lookup and one upsert are comfortably below.
        connection.set_progress_handler(lambda: 1, 2000)
        with patch(
            "backend.app.repositories.daily_close_repository.get_connection",
            return_value=connection,
        ):
            summary = upsert_daily_close_records([records[0]], self.database_path)
        self.assertEqual(summary.updated_records, 1)

    def test_other_writer_cannot_change_keys_between_count_and_upsert(self):
        count_existing = daily_close_repository._count_existing_keys
        competitor = sqlite3.connect(self.database_path, timeout=0)
        self.addCleanup(competitor.close)

        def count_then_attempt_competing_write(connection, keys):
            count = count_existing(connection, keys)
            try:
                with self.assertRaises(sqlite3.OperationalError) as error:
                    competitor.execute(
                        """
                        INSERT INTO etf_daily_close
                            (etf_code, trade_date, close_price, source_id)
                        VALUES ('0056', '2026-08-07', 99, 'twse_stock_day');
                        """
                    )
                self.assertEqual(error.exception.sqlite_errorcode, sqlite3.SQLITE_BUSY)
            finally:
                competitor.rollback()
            return count

        with patch.object(
            daily_close_repository, "_count_existing_keys",
            side_effect=count_then_attempt_competing_write,
        ):
            summary = upsert_daily_close_records(
                [self.record("2026-08-07", "35")], self.database_path,
            )
        self.assertEqual(summary.inserted_records, 1)
        self.assertEqual(summary.updated_records, 0)


if __name__ == "__main__":
    unittest.main()
