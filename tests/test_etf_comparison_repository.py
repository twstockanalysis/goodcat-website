"""ETF 比較 Repository 測試。"""

import tempfile
import unittest
from backend.app.exceptions import ETFNotFoundError

from pathlib import Path

from backend.app.database.connection import (
    get_connection,
)
from backend.app.database.init_db import (
    initialize_database,
)
from backend.app.repositories.etf_comparison_repository import (
    build_etf_comparison,
    normalize_comparison_codes,
)


class TestETFComparisonRepository(
    unittest.TestCase
):
    """驗證 ETF 比較 Read Model。"""

    def setUp(self) -> None:
        """建立隔離資料庫與兩檔 ETF。"""

        self.temp_directory = (
            tempfile.TemporaryDirectory()
        )
        self.database_path = (
            Path(self.temp_directory.name)
            / "etf_comparison.db"
        )
        initialize_database(
            self.database_path
        )

        connection = get_connection(
            self.database_path
        )

        try:
            connection.executescript(
                """
                INSERT INTO etf_master (
                    code,
                    name,
                    is_active,
                    is_bond,
                    listing_date,
                    fund_size,
                    expense_ratio
                )
                VALUES
                    (
                        '0050',
                        '元大台灣50',
                        0,
                        0,
                        '2003-06-30',
                        5000,
                        0.43
                    ),
                    (
                        '0056',
                        '元大高股息',
                        0,
                        0,
                        '2007-12-26',
                        3000,
                        0.45
                    );

                INSERT INTO etf_performance (
                    etf_code,
                    as_of_date,
                    period_code,
                    metric_code,
                    return_pct,
                    source_id
                )
                VALUES
                    (
                        '0050',
                        '2026-07-30',
                        '1M',
                        'PRICE_RETURN',
                        5,
                        'twse_stock_day'
                    ),
                    (
                        '0050',
                        '2026-07-30',
                        '6M',
                        'PRICE_RETURN',
                        12,
                        'twse_stock_day'
                    );

                INSERT INTO etf_dividend (
                    id,
                    etf_code,
                    source_event_id,
                    ex_dividend_date,
                    payment_date,
                    amount_per_unit,
                    currency,
                    source_id
                )
                VALUES (
                    1,
                    '0050',
                    '0050-2026-1',
                    '2026-07-15',
                    '2026-08-10',
                    0.7,
                    'TWD',
                    'twse_etfortune_dividend'
                );

                INSERT INTO etf_dividend_component (
                    dividend_id,
                    component_code,
                    component_basis,
                    component_name,
                    ratio_pct,
                    source_id
                )
                VALUES (
                    1,
                    '76W',
                    'ACTUAL',
                    '資本利得',
                    0,
                    'manual_actual_dividend_notice'
                );
                """
            )
            connection.commit()

        finally:
            connection.close()

    def tearDown(self) -> None:
        """移除測試資料庫。"""

        self.temp_directory.cleanup()

    def test_codes_are_normalized_stably(
        self,
    ) -> None:
        """確認去重、轉大寫與原順序。"""

        self.assertEqual(
            normalize_comparison_codes(
                [
                    " 0056 ",
                    "0050",
                    "0056",
                ]
            ),
            (
                "0056",
                "0050",
            ),
        )

    def test_comparison_preserves_missing_semantics(
        self,
    ) -> None:
        """確認缺少績效與 76W 不轉成零。"""

        result = build_etf_comparison(
            [
                "0050",
                "0056",
            ],
            self.database_path,
        )

        self.assertEqual(
            result["codes"],
            [
                "0050",
                "0056",
            ],
        )
        self.assertEqual(
            result["periods"],
            [
                "1M",
                "3M",
                "6M",
                "1Y",
            ],
        )

        first = result["items"][0]
        second = result["items"][1]

        self.assertEqual(
            first["actual_76w"][
                "latest_ratio_pct"
            ],
            0.0,
        )
        self.assertEqual(
            second["performance_items"],
            [],
        )
        self.assertIsNone(
            second["actual_76w"][
                "latest_ratio_pct"
            ]
        )
        self.assertIn(
            "市價績效",
            second["completeness"][
                "missing_sections"
            ],
        )

    def test_missing_code_raises_key_error(
        self,
    ) -> None:
        """確認不存在 ETF 不會被靜默略過。"""

        with self.assertRaises(ETFNotFoundError):
            build_etf_comparison(
                [
                    "0050",
                    "UNKNOWN",
                ],
                self.database_path,
            )


if __name__ == "__main__":
    unittest.main()
