"""TWSE 個股日成交資訊測試。"""

import tempfile
import unittest
from datetime import (
    date,
    datetime,
    timezone,
)
from pathlib import Path
from unittest.mock import Mock, patch

from backend.app.data_sources.twse_stock_day import (
    fetch_stock_day_month,
    parse_stock_day_records,
    parse_twse_trade_date,
    save_price_history_snapshot,
)


class TestTWSEStockDay(unittest.TestCase):
    """測試 TWSE 歷史價格解析。"""

    def build_payload(self) -> dict:
        """建立合法 TWSE 測試回應。"""

        return {
            "stat": "OK",
            "title": (
                "115年07月 0050 "
                "元大台灣50 各日成交資訊"
            ),
            "fields": [
                "日期",
                "成交股數",
                "成交金額",
                "開盤價",
                "最高價",
                "最低價",
                "收盤價",
                "漲跌價差",
                "成交筆數",
            ],
            "data": [
                [
                    "115/07/01",
                    "100,000",
                    "5,000,000",
                    "50.00",
                    "51.00",
                    "49.50",
                    "50.50",
                    "+0.50",
                    "1,000",
                ],
                [
                    "115/07/02",
                    "120,000",
                    "6,000,000",
                    "50.50",
                    "52.00",
                    "50.00",
                    "51.25",
                    "+0.75",
                    "1,200",
                ],
            ],
        }

    def test_roc_date_is_converted(
        self,
    ) -> None:
        """確認交易日期轉成西元。"""

        result = parse_twse_trade_date(
            "115/07/29"
        )

        self.assertEqual(
            result,
            date(2026, 7, 29),
        )

    def test_payload_is_parsed(
        self,
    ) -> None:
        """確認成交資訊可轉成價格資料。"""

        records = parse_stock_day_records(
            self.build_payload(),
            "0050",
        )

        self.assertEqual(
            len(records),
            2,
        )

        self.assertEqual(
            records[0].trade_date,
            date(2026, 7, 1),
        )

        self.assertEqual(
            str(records[0].close_price),
            "50.50",
        )

    def test_no_data_returns_empty_list(
        self,
    ) -> None:
        """確認無資料月份不會失敗。"""

        records = parse_stock_day_records(
            {
                "stat": (
                    "很抱歉，沒有符合條件的資料!"
                ),
            },
            "0050",
        )

        self.assertEqual(
            records,
            [],
        )

    def test_missing_close_field_is_rejected(
        self,
    ) -> None:
        """確認缺少收盤價欄位被拒絕。"""

        payload = self.build_payload()
        payload["fields"].remove(
            "收盤價"
        )

        with self.assertRaises(
            ValueError
        ):
            parse_stock_day_records(
                payload,
                "0050",
            )

    @patch(
        "backend.app.data_sources."
        "twse_stock_day.httpx.get"
    )
    def test_fetch_stock_day_month(
        self,
        mock_get: Mock,
    ) -> None:
        """確認下載器送出正確參數。"""

        response = Mock()
        response.json.return_value = (
            self.build_payload()
        )
        response.raise_for_status.return_value = (
            None
        )

        mock_get.return_value = response

        records = fetch_stock_day_month(
            etf_code="0050",
            month_start=date(
                2026,
                7,
                1,
            ),
        )

        self.assertEqual(
            len(records),
            2,
        )

        params = mock_get.call_args.kwargs[
            "params"
        ]

        self.assertEqual(
            params["date"],
            "20260701",
        )

        self.assertEqual(
            params["stockNo"],
            "0050",
        )

        self.assertFalse(
            mock_get.call_args.kwargs[
                "follow_redirects"
            ]
        )

    @patch(
        "backend.app.data_sources."
        "twse_stock_day.time.sleep"
    )
    @patch(
        "backend.app.data_sources."
        "twse_stock_day.httpx.get"
    )
    def test_fetch_retries_transient_redirect(
        self,
        mock_get: Mock,
        mock_sleep: Mock,
    ) -> None:
        """暫時重新導向需退避重試，不可形成自動迴圈。"""

        redirect = Mock()
        redirect.status_code = 308
        redirect.headers = {}

        success = Mock()
        success.status_code = 200
        success.headers = {}
        success.json.return_value = (
            self.build_payload()
        )
        success.raise_for_status.return_value = None

        mock_get.side_effect = [redirect, success]

        records = fetch_stock_day_month(
            etf_code="0050",
            month_start=date(2026, 7, 1),
            retry_backoff_seconds=0.25,
        )

        self.assertEqual(len(records), 2)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(0.25)
        self.assertTrue(
            all(
                not call.kwargs["follow_redirects"]
                for call in mock_get.call_args_list
            )
        )

    @patch("backend.app.data_sources.twse_stock_day.time.sleep")
    @patch("backend.app.data_sources.twse_stock_day.httpx.get")
    def test_redirect_retries_are_bounded_and_never_follow_location(
        self, mock_get: Mock, mock_sleep: Mock,
    ) -> None:
        for status in (307, 308):
            with self.subTest(status=status):
                mock_get.reset_mock()
                mock_sleep.reset_mock()
                response = Mock()
                response.status_code = status
                response.headers = {"Location": "https://example.invalid/other"}
                response.raise_for_status.side_effect = RuntimeError("redirect exhausted")
                mock_get.return_value = response
                with self.assertRaisesRegex(RuntimeError, "redirect exhausted"):
                    fetch_stock_day_month("0050", date(2026, 7, 1),
                                          max_attempts=3, retry_backoff_seconds=0.25)
                self.assertEqual(mock_get.call_count, 3)
                self.assertEqual(mock_sleep.call_count, 2)
                self.assertTrue(all(not call.kwargs["follow_redirects"]
                                    for call in mock_get.call_args_list))
                self.assertEqual(len({call.args[0] for call in mock_get.call_args_list}), 1)
                self.assertNotIn("example.invalid", mock_get.call_args.args[0])

    def test_snapshot_is_saved(
        self,
    ) -> None:
        """確認價格快照可以保存。"""

        records = parse_stock_day_records(
            self.build_payload(),
            "0050",
        )

        with tempfile.TemporaryDirectory() as directory:
            snapshot = (
                save_price_history_snapshot(
                    etf_code="0050",
                    records=records,
                    output_root=Path(
                        directory
                    ),
                    downloaded_at=datetime(
                        2026,
                        7,
                        29,
                        tzinfo=timezone.utc,
                    ),
                )
            )

            self.assertTrue(
                snapshot.data_path.exists()
            )

            self.assertTrue(
                snapshot.metadata_path.exists()
            )

            self.assertEqual(
                snapshot.record_count,
                2,
            )


if __name__ == "__main__":
    unittest.main()
