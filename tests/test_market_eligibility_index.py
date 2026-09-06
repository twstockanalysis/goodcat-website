"""V3-2 全市場資格與內部排序索引測試。"""

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.app.database.connection import get_connection
from backend.app.database.init_db import initialize_database
from backend.app.models.market_eligibility import MarketEligibilityIndexRequest
from backend.app.services.market_eligibility_index import (
    build_market_eligibility_index,
)


class TestMarketEligibilityIndex(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "market-index.db"
        initialize_database(self.database_path)
        connection = get_connection(self.database_path)
        connection.executemany(
            """
            INSERT INTO etf_master (code, name, is_active, is_bond)
            VALUES (?, ?, 0, 0);
            """,
            [
                ("0050", "元大台灣50"),
                ("0056", "元大高股息"),
                ("00632R", "元大台灣50反1"),
                ("00878", "國泰永續高股息"),
            ],
        )
        connection.commit()
        connection.close()
        self._insert_ready_history("0050", actual=True, one_year_return=8)
        self._insert_ready_history("0056", actual=False, one_year_return=4)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def _insert_ready_history(
        self,
        code: str,
        *,
        actual: bool,
        one_year_return: int,
    ) -> None:
        connection = get_connection(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO etf_daily_close (
                    etf_code, trade_date, close_price, source_id
                ) VALUES (?, '2026-01-01', 20, 'twse_stock_day');
                """,
                (code,),
            )
            connection.executemany(
                """
                INSERT INTO etf_performance (
                    etf_code, as_of_date, period_code, metric_code,
                    return_pct, source_id
                ) VALUES (?, '2026-01-01', ?, 'PRICE_RETURN', ?, 'twse_stock_day');
                """,
                [
                    (code, "1M", 1),
                    (code, "3M", 2),
                    (code, "6M", 3),
                    (code, "1Y", one_year_return),
                ],
            )
            dividend_ids = []
            for year in (2023, 2024, 2025, 2026):
                cursor = connection.execute(
                    """
                    INSERT INTO etf_dividend (
                        etf_code, source_event_id, payment_date,
                        amount_per_unit, currency, source_id
                    ) VALUES (?, ?, ?, 1, 'TWD', 'TEST');
                    """,
                    (code, f"{code}-{year}", f"{year}-01-01"),
                )
                dividend_ids.append(int(cursor.lastrowid))
            connection.execute(
                """
                INSERT INTO etf_dividend_component (
                    dividend_id, component_code, component_basis,
                    ratio_pct, source_id
                ) VALUES (?, ?, ?, 100, 'TEST');
                """,
                (
                    dividend_ids[-1],
                    "76W" if actual else "EST_DIVIDEND",
                    "ACTUAL" if actual else "ESTIMATED",
                ),
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def request(**updates) -> MarketEligibilityIndexRequest:
        values = {
            "target_after_tax_cash_twd": 3000,
            "target_months": [1, 7],
            "existing_holdings": [],
            "history_years": 3,
            "cash_deduction_rate_pct": 0,
        }
        values.update(updates)
        return MarketEligibilityIndexRequest(**values)

    def test_builds_full_master_index_and_keeps_scores_internal(self) -> None:
        built = build_market_eligibility_index(
            self.request(),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        )

        response = built.response
        self.assertEqual(response.universe_count, 4)
        self.assertEqual(response.supported_product_count, 3)
        self.assertEqual(response.eligible_count, 2)
        self.assertEqual(response.actual_component_count, 1)
        self.assertEqual(response.estimated_component_fallback_count, 1)
        self.assertEqual(
            [item.public_item.etf_code for item in built.ranked_eligible_candidates],
            ["0050", "0056"],
        )
        self.assertTrue(
            all(
                item.quality_score is not None
                for item in built.ranked_eligible_candidates
            )
        )
        self.assertTrue(
            all(
                item.public_item.historical_quality_grade.status == "UNRATED"
                for item in built.ranked_eligible_candidates
            )
        )
        self.assertTrue(
            all(
                "低於校準門檻" in (
                    item.public_item.historical_quality_grade.unavailable_evidence[0]
                )
                for item in built.ranked_eligible_candidates
            )
        )
        serialized = response.model_dump(mode="json")
        self.assertNotIn("quality_score", json_text(serialized))
        self.assertNotIn("confidence", json_text(serialized))
        self.assertIn("historical_quality_grade", json_text(serialized))

    def test_unsupported_and_missing_data_have_stable_exclusion_codes(self) -> None:
        response = build_market_eligibility_index(
            self.request(),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        ).response
        by_code = {item.etf_code: item for item in response.candidates}
        self.assertEqual(
            by_code["00632R"].reasons[0].code,
            "LEVERAGED_INVERSE_OR_FUTURES",
        )
        missing_codes = {item.code for item in by_code["00878"].reasons}
        self.assertIn("MISSING_REFERENCE_PRICE", missing_codes)
        self.assertIn("MISSING_COMPLETE_DIVIDEND_COMPONENTS", missing_codes)
        self.assertFalse(by_code["00878"].eligible_for_addition)
        self.assertEqual(
            by_code["00878"].historical_quality_grade.status,
            "UNRATED",
        )

    def test_existing_holdings_require_real_portfolio_overlap(self) -> None:
        response = build_market_eligibility_index(
            self.request(
                existing_holdings=[{"etf_code": "0050", "held_units": 100}]
            ),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        ).response
        candidate = next(item for item in response.candidates if item.etf_code == "0056")
        self.assertEqual(candidate.holding_overlap_status, "UNAVAILABLE")
        self.assertIn(
            "HOLDING_OVERLAP_UNAVAILABLE",
            {item.code for item in candidate.reasons},
        )
        self.assertFalse(candidate.eligible_for_addition)

    def test_snapshot_id_is_reproducible(self) -> None:
        request = self.request()
        first = build_market_eligibility_index(
            request, self.database_path, as_of_date=date(2026, 1, 1)
        ).response
        second = build_market_eligibility_index(
            request, self.database_path, as_of_date=date(2026, 1, 1)
        ).response
        self.assertEqual(first.snapshot_id, second.snapshot_id)
        self.assertTrue(first.snapshot_id.startswith("sha256:"))

    def test_existing_etf_can_be_added_without_inventing_missing_overlap(self) -> None:
        response = build_market_eligibility_index(
            self.request(existing_holdings=[{"etf_code": "0050", "held_units": 100}]),
            self.database_path, as_of_date=date(2026, 1, 1),
        ).response
        held = next(item for item in response.candidates if item.etf_code == "0050")
        self.assertTrue(held.eligible_for_addition)
        self.assertIsNone(held.holding_overlap_pct)
        self.assertEqual(held.holding_overlap_status, "UNAVAILABLE")
        warning = next(r for r in held.reasons if r.code == "HOLDING_OVERLAP_UNAVAILABLE")
        self.assertEqual(warning.kind, "TRADEOFF")

    def test_self_overlap_is_warning_but_distinct_etf_overlap_still_excludes(self) -> None:
        from backend.app.services.constituent_overlap import GatedConstituentOverlap

        evidence = GatedConstituentOverlap(
            decision="READY", overlap_pct=Decimal("96.513"), reasons=(),
            snapshot_dates=(date(2026, 1, 1),),
        )
        with patch(
            "backend.app.services.market_eligibility_index.calculate_gated_portfolio_overlap",
            return_value=evidence,
        ):
            response = build_market_eligibility_index(
                self.request(existing_holdings=[{"etf_code": "0050", "held_units": 100}]),
                self.database_path, as_of_date=date(2026, 1, 1),
            ).response
        items = {item.etf_code: item for item in response.candidates}
        self.assertTrue(items["0050"].eligible_for_addition)
        self.assertEqual(items["0050"].holding_overlap_pct, Decimal("96.513"))
        self.assertFalse(items["0056"].eligible_for_addition)
        self.assertIn("EXCESSIVE_HOLDING_OVERLAP", {r.code for r in items["0056"].reasons})

    def test_existing_etf_still_requires_cash_and_component_evidence(self) -> None:
        response = build_market_eligibility_index(
            self.request(existing_holdings=[{"etf_code": "00878", "held_units": 100}]),
            self.database_path, as_of_date=date(2026, 1, 1),
        ).response
        item = next(item for item in response.candidates if item.etf_code == "00878")
        self.assertFalse(item.eligible_for_addition)
        self.assertIn("MISSING_COMPLETE_DIVIDEND_COMPONENTS", {r.code for r in item.reasons})

    def test_future_dated_market_facts_fail_closed(self) -> None:
        connection = get_connection(self.database_path)
        try:
            connection.execute(
                """
                UPDATE etf_performance
                SET as_of_date = '2026-01-02'
                WHERE etf_code = '0050';
                """
            )
            connection.commit()
        finally:
            connection.close()
        response = build_market_eligibility_index(
            self.request(),
            self.database_path,
            as_of_date=date(2026, 1, 1),
        ).response
        item = next(
            candidate
            for candidate in response.candidates
            if candidate.etf_code == "0050"
        )
        self.assertFalse(item.eligible_for_addition)
        self.assertIn("FUTURE_PERFORMANCE_DATA", {reason.code for reason in item.reasons})

    def test_future_announced_dividend_is_not_paid_history(self) -> None:
        connection = get_connection(self.database_path)
        try:
            connection.execute(
                """
                INSERT INTO etf_master (code, name, is_active, is_bond)
                VALUES ('00929', '復華台灣科技優息', 0, 0);
                """
            )
            connection.commit()
        finally:
            connection.close()
        self._insert_ready_history("00929", actual=True, one_year_return=5)
        connection = get_connection(self.database_path)
        try:
            connection.executemany(
                """
                INSERT INTO etf_dividend (
                    etf_code, source_event_id, payment_date,
                    amount_per_unit, currency, source_id
                ) VALUES ('00929', ?, ?, 0.38, 'TWD', 'TEST');
                """,
                [
                    ("00929-2026-07", "2026-07-13"),
                    ("00929-2026-08", "2026-08-14"),
                    ("00929-2026-09-announced", "2026-09-14"),
                ],
            )
            connection.execute(
                """
                UPDATE etf_daily_close
                SET trade_date = '2026-08-31'
                WHERE etf_code = '00929';
                """
            )
            connection.execute(
                """
                UPDATE etf_performance
                SET as_of_date = '2026-08-31'
                WHERE etf_code = '00929';
                """
            )
            connection.commit()
        finally:
            connection.close()

        response = build_market_eligibility_index(
            self.request(),
            self.database_path,
            as_of_date=date(2026, 8, 31),
        ).response
        item = next(
            candidate
            for candidate in response.candidates
            if candidate.etf_code == "00929"
        )

        self.assertTrue(item.supported_product)
        self.assertFalse(item.is_active)
        self.assertEqual(item.latest_payment_date, date(2026, 8, 14))
        self.assertNotIn(
            "FUTURE_DIVIDEND_DATA",
            {reason.code for reason in item.reasons},
        )


def json_text(value: object) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, sort_keys=True)


if __name__ == "__main__":
    unittest.main()
