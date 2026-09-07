"""ETF 成分股快照與加權重疊基礎測試。"""

import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.models.etf_constituent import (
    ETFConstituentPosition,
    ETFConstituentSnapshotCreate,
)
from backend.app.repositories.etf_constituent_repository import (
    get_latest_constituent_snapshot,
    save_constituent_snapshot,
)
from backend.app.services.constituent_overlap import (
    calculate_gated_pair_overlap,
    calculate_gated_portfolio_overlap,
    calculate_weighted_overlap,
)
from backend.app.services.constituent_data_quality import (
    evaluate_constituent_data_quality,
)


class TestETFConstituentFoundation(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "constituents.db"
        initialize_database(self.database_path)
        connection = get_connection(self.database_path)
        connection.executemany(
            "INSERT INTO etf_master (code, name) VALUES (?, ?);",
            [("0050", "元大台灣50"), ("006208", "富邦台50")],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_directory.cleanup()

    @staticmethod
    def payload(etf_code: str, positions):
        return ETFConstituentSnapshotCreate(
            etf_code=etf_code,
            as_of_date=date(2026, 8, 13),
            source_id="issuer_official_holdings",
            source_url="https://example.test/holdings",
            fetched_at=datetime(2026, 8, 13, 8, tzinfo=timezone.utc),
            positions=positions,
        )

    def test_snapshot_is_saved_with_source_date_and_weights(self):
        result = save_constituent_snapshot(
            self.payload(
                "0050",
                [
                    {
                        "constituent_id": "2330",
                        "constituent_name": "台積電",
                        "weight_pct": "55.5",
                        "rank": 1,
                    },
                    {
                        "constituent_id": "2317",
                        "constituent_name": "鴻海",
                        "weight_pct": "6.5",
                        "rank": 2,
                    },
                ],
            ),
            self.database_path,
        )

        self.assertEqual(result.etf_code, "0050")
        self.assertEqual(result.total_weight_pct, Decimal("62.0"))
        self.assertEqual(result.constituent_count, 2)
        latest = get_latest_constituent_snapshot("0050", self.database_path)
        self.assertEqual(latest.id, result.id)
        self.assertEqual(latest.positions[0].constituent_id, "2330")

    def test_same_source_and_date_cannot_overwrite_snapshot(self):
        payload = self.payload(
            "0050",
            [{"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 50}],
        )
        save_constituent_snapshot(payload, self.database_path)

        with self.assertRaises(sqlite3.IntegrityError):
            save_constituent_snapshot(payload, self.database_path)

    def save_dated(self, code, day, identifier="2330", weight="90"):
        payload = self.payload(code, [{
            "constituent_id": identifier,
            "constituent_name": "Test stock",
            "weight_pct": weight,
        }]).model_copy(update={"as_of_date": day})
        return save_constituent_snapshot(payload, self.database_path)

    def quality_on(self, day):
        return evaluate_constituent_data_quality(
            [{"etf_code": "0050", "issuer_key": "yuanta"}],
            self.database_path, evaluated_on=day,
        )

    def test_repository_cutoff_is_inclusive_and_default_remains_latest(self):
        past = self.save_dated("0050", date(2026, 8, 13))
        future = self.save_dated("0050", date(2026, 8, 15), "2454")
        self.assertEqual(get_latest_constituent_snapshot(
            "0050", self.database_path).id, future.id)
        self.assertEqual(get_latest_constituent_snapshot(
            "0050", self.database_path, on_or_before=date(2026, 8, 13)
        ).id, past.id)
        self.assertIsNone(get_latest_constituent_snapshot(
            "0050", self.database_path, on_or_before=date(2026, 8, 12)))

    def test_quality_uses_past_snapshot_despite_future_snapshot(self):
        self.save_dated("0050", date(2026, 8, 13))
        self.save_dated("0050", date(2026, 8, 15))
        quality = self.quality_on(date(2026, 8, 14))
        self.assertEqual(quality["decision"], "READY")
        self.assertEqual(quality["items"][0]["as_of_date"], "2026-08-13")

    def test_future_only_stays_unavailable_for_quality_and_overlap(self):
        for code in ("0050", "006208"):
            self.save_dated(code, date(2026, 8, 15))
        self.assertEqual(self.quality_on(date(2026, 8, 14))["items"][0]["reasons"],
                         ["FUTURE_DATED_SNAPSHOT"])
        pair = calculate_gated_pair_overlap(
            "0050", "006208", self.database_path, evaluated_on=date(2026, 8, 14))
        portfolio = calculate_gated_portfolio_overlap(
            [{"etf_code": "0050", "held_units": 1, "unit_price": 100}],
            "006208", self.database_path, evaluated_on=date(2026, 8, 14))
        for result in (pair, portfolio):
            self.assertEqual(result.decision, "NO_GO")
            self.assertIsNone(result.overlap_pct)
            self.assertIn("0050:FUTURE_DATED_SNAPSHOT", result.reasons)

    def test_future_snapshot_does_not_rescue_stale_past(self):
        self.save_dated("0050", date(2026, 8, 1))
        self.save_dated("0050", date(2026, 8, 15))
        quality = self.quality_on(date(2026, 8, 14))
        self.assertEqual(quality["decision"], "NO_GO")
        self.assertEqual(quality["items"][0]["reasons"], ["STALE_SNAPSHOT"])

    def test_low_weight_selected_snapshot_cannot_fall_back_to_older_good_one(self):
        self.save_dated("0050", date(2026, 8, 12))
        self.save_dated("0050", date(2026, 8, 13), weight="50")
        self.save_dated("0050", date(2026, 8, 15))
        quality = self.quality_on(date(2026, 8, 14))
        self.assertEqual(quality["decision"], "NO_GO")
        self.assertEqual(quality["items"][0]["reasons"],
                         ["INSUFFICIENT_DISCLOSED_WEIGHT"])

    def test_pair_and_portfolio_use_same_past_weights_as_quality_gate(self):
        for code in ("0050", "006208"):
            self.save_dated(code, date(2026, 8, 13))
        self.save_dated("0050", date(2026, 8, 15), "2454")
        self.save_dated("006208", date(2026, 8, 15), "2317")
        pair = calculate_gated_pair_overlap(
            "0050", "006208", self.database_path, evaluated_on=date(2026, 8, 14))
        portfolio = calculate_gated_portfolio_overlap(
            [{"etf_code": "0050", "held_units": 1, "unit_price": 100}],
            "006208", self.database_path, evaluated_on=date(2026, 8, 14))
        for result in (pair, portfolio):
            self.assertEqual(result.decision, "READY")
            self.assertEqual(result.overlap_pct, Decimal("90.000000"))
            self.assertEqual(set(result.snapshot_dates), {date(2026, 8, 13)})

    def test_weighted_overlap_uses_smaller_disclosed_weight(self):
        left = save_constituent_snapshot(
            self.payload(
                "0050",
                [
                    {"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 55},
                    {"constituent_id": "2317", "constituent_name": "鴻海", "weight_pct": 8},
                ],
            ),
            self.database_path,
        )
        right = save_constituent_snapshot(
            self.payload(
                "006208",
                [
                    {"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 60},
                    {"constituent_id": "2454", "constituent_name": "聯發科", "weight_pct": 7},
                ],
            ),
            self.database_path,
        )

        result = calculate_weighted_overlap(left, right)

        self.assertEqual(result.overlap_pct, Decimal("55.000000"))
        self.assertEqual(result.shared_constituent_count, 1)
        self.assertEqual(result.shared_constituents[0].constituent_id, "2330")
        self.assertEqual(result.method, "SUM_MIN_DISCLOSED_WEIGHTS_V1")

    def test_disjoint_complete_snapshots_return_formal_zero_overlap(self):
        left = save_constituent_snapshot(
            self.payload(
                "0050",
                [
                    {
                        "constituent_id": "2330",
                        "constituent_name": "台積電",
                        "weight_pct": 90,
                    }
                ],
            ),
            self.database_path,
        )
        right = save_constituent_snapshot(
            self.payload(
                "006208",
                [
                    {
                        "constituent_id": "2454",
                        "constituent_name": "聯發科",
                        "weight_pct": 90,
                    }
                ],
            ),
            self.database_path,
        )

        direct = calculate_weighted_overlap(left, right)
        gated = calculate_gated_pair_overlap(
            "0050",
            "006208",
            self.database_path,
            evaluated_on=date(2026, 8, 14),
        )

        self.assertEqual(direct.overlap_pct, Decimal("0.000000"))
        self.assertEqual(direct.shared_constituent_count, 0)
        self.assertEqual(direct.shared_constituents, [])
        self.assertEqual(gated.decision, "READY")
        self.assertEqual(gated.overlap_pct, Decimal("0.000000"))
        self.assertEqual(gated.reasons, ())

    def test_duplicate_constituent_and_excess_total_are_rejected(self):
        with self.assertRaises(ValidationError):
            self.payload(
                "0050",
                [
                    {"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 60},
                    {"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 40},
                ],
            )
        with self.assertRaises(ValidationError):
            self.payload(
                "0050",
                [
                    {"constituent_id": "2330", "constituent_name": "台積電", "weight_pct": 60},
                    {"constituent_id": "2317", "constituent_name": "鴻海", "weight_pct": 41},
                ],
            )

    def test_gated_pair_overlap_requires_fresh_complete_snapshots(self):
        self.assertEqual(
            calculate_gated_pair_overlap(
                "0050",
                "006208",
                self.database_path,
                evaluated_on=date(2026, 8, 14),
            ).decision,
            "NO_GO",
        )
        for code, tsmc_weight, other_id in (
            ("0050", "55", "2317"),
            ("006208", "60", "2454"),
        ):
            save_constituent_snapshot(
                self.payload(
                    code,
                    [
                        {
                            "constituent_id": "2330",
                            "constituent_name": "台積電",
                            "weight_pct": tsmc_weight,
                        },
                        {
                            "constituent_id": other_id,
                            "constituent_name": "其他",
                            "weight_pct": Decimal("90")
                            - Decimal(tsmc_weight),
                        },
                    ],
                ),
                self.database_path,
            )

        result = calculate_gated_pair_overlap(
            "0050",
            "006208",
            self.database_path,
            evaluated_on=date(2026, 8, 14),
        )
        self.assertEqual(result.decision, "READY")
        self.assertEqual(result.overlap_pct, Decimal("55.000000"))

    def test_portfolio_overlap_uses_current_market_value_weights(self):
        connection = get_connection(self.database_path)
        connection.execute(
            "INSERT INTO etf_master (code, name) VALUES (?, ?);",
            ("00878", "國泰永續高股息"),
        )
        connection.commit()
        connection.close()
        for code, positions in (
            (
                "0050",
                [
                    {
                        "constituent_id": "2330",
                        "constituent_name": "台積電",
                        "weight_pct": 60,
                    },
                    {
                        "constituent_id": "2317",
                        "constituent_name": "鴻海",
                        "weight_pct": 30,
                    },
                ],
            ),
            (
                "006208",
                [
                    {
                        "constituent_id": "2330",
                        "constituent_name": "台積電",
                        "weight_pct": 40,
                    },
                    {
                        "constituent_id": "2454",
                        "constituent_name": "聯發科",
                        "weight_pct": 50,
                    },
                ],
            ),
            (
                "00878",
                [
                    {
                        "constituent_id": "2330",
                        "constituent_name": "台積電",
                        "weight_pct": 50,
                    },
                    {
                        "constituent_id": "2881",
                        "constituent_name": "富邦金",
                        "weight_pct": 40,
                    },
                ],
            ),
        ):
            save_constituent_snapshot(
                self.payload(code, positions),
                self.database_path,
            )

        result = calculate_gated_portfolio_overlap(
            [
                {"etf_code": "0050", "held_units": 1, "unit_price": 75},
                {"etf_code": "006208", "held_units": 1, "unit_price": 25},
            ],
            "00878",
            self.database_path,
            evaluated_on=date(2026, 8, 14),
        )

        self.assertEqual(result.decision, "READY")
        self.assertEqual(result.overlap_pct, Decimal("50.000000"))
        self.assertEqual(
            result.method,
            "PORTFOLIO_VALUE_WEIGHTED_SUM_MIN_DISCLOSED_WEIGHTS_V1",
        )


if __name__ == "__main__":
    unittest.main()
