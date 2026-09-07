"""國泰投信正式配息公告自動發現測試。"""

import unittest
from unittest.mock import patch

from backend.app.data_sources.cathay_actual_dividend_discovery import (
    build_cathay_announcement_list_url,
    discover_cathay_actual_dividend_announcements,
    fetch_cathay_announcement_page,
)


class TestCathayActualDividendDiscovery(unittest.TestCase):
    @staticmethod
    def payload(*items: dict, total_page: int = 1) -> dict:
        return {
            "totalCount": len(items),
            "totalPage": total_page,
            "result": list(items),
            "success": True,
            "returnMessage": "成功",
        }

    def test_url_uses_bounded_code_search(self) -> None:
        url = build_cathay_announcement_list_url(
            etf_code=" 00878 ", page=2, page_size=50
        )

        self.assertIn("Keyword=00878", url)
        self.assertIn("CurrentPage=2", url)
        self.assertIn("PerPageCount=50", url)
        self.assertIn("AnnouncementType=1", url)

    def test_rejects_unbounded_page_values(self) -> None:
        with self.assertRaises(ValueError):
            build_cathay_announcement_list_url(
                etf_code="00878", page=21, page_size=50
            )

        with self.assertRaises(ValueError):
            build_cathay_announcement_list_url(
                etf_code="00878", page=1, page_size=101
            )

    def test_actual_pdf_candidate_excludes_preannouncement(self) -> None:
        result = discover_cathay_actual_dividend_announcements(
            etf_code="00878",
            page_payloads=[
                self.payload(
                    {
                        "id": 5991,
                        "title": "國泰台灣ESG永續高股息ETF基金115年4月收益分配公告",
                        "declareTime": "2026/05/14",
                        "filePath": "/uploads/07cathaynews__online/5991.pdf",
                        "isPDF": True,
                    },
                    {
                        "id": 5981,
                        "title": "國泰台灣ESG永續高股息ETF基金115年4月收益分配期前公告",
                        "declareTime": "2026-04-30",
                        "filePath": "/uploads/07cathaynews__online/5981.pdf",
                        "isPDF": True,
                    },
                )
            ],
        )

        self.assertEqual(len(result.candidates), 1)
        candidate = result.candidates[0]
        self.assertEqual(candidate.announcement_id, 5991)
        self.assertEqual(candidate.document_id, "cathay-announcement-5991")
        self.assertEqual(
            candidate.document_url,
            "https://cwapi.cathaysite.com.tw/uploads/07cathaynews__online/5991.pdf",
        )
        self.assertEqual(len(result.rejections), 1)
        self.assertIn("期前", result.rejections[0].reason)

    def test_non_pdf_and_unrelated_titles_are_rejected(self) -> None:
        result = discover_cathay_actual_dividend_announcements(
            etf_code="00878",
            page_payloads=[
                self.payload(
                    {
                        "id": 1,
                        "title": "修訂公開說明書",
                        "declareTime": "2026-01-01",
                        "filePath": "/announcement/1",
                        "isPDF": False,
                    },
                    {
                        "id": 2,
                        "title": "配息組成公告",
                        "declareTime": "2026-01-02",
                        "filePath": "/announcement/2",
                        "isPDF": False,
                    },
                )
            ],
        )

        self.assertEqual(result.candidates, ())
        self.assertEqual(len(result.rejections), 2)

    def test_interim_announcement_is_candidate_not_actual_approval(self):
        result = discover_cathay_actual_dividend_announcements(
            etf_code="00878", page_payloads=[self.payload({
                "id": 5524, "title": "國泰ETF收益分配期中公告",
                "declareTime": "2024-11-13", "isPDF": True,
                "filePath": "/uploads/07cathaynews__online/5524.pdf",
            }, {
                "id": 1, "title": "國泰ETF預估收益分配期中公告",
                "declareTime": "2024-11-01", "isPDF": True,
                "filePath": "/uploads/07cathaynews__online/1.pdf",
            })])
        self.assertEqual([c.announcement_id for c in result.candidates], [5524])
        self.assertEqual(len(result.rejections), 1)

    def test_duplicate_candidates_are_deduplicated(self) -> None:
        item = {
            "id": 5991,
            "title": "國泰ETF基金收益分配公告",
            "declareTime": "2026-05-14",
            "filePath": "/uploads/07cathaynews__online/5991.pdf",
            "isPDF": True,
        }
        result = discover_cathay_actual_dividend_announcements(
            etf_code="00878",
            max_pages=2,
            page_payloads=[
                self.payload(item, total_page=2),
                self.payload(item, total_page=2),
            ],
        )

        self.assertEqual(result.pages_fetched, 2)
        self.assertEqual(len(result.candidates), 1)

    def test_network_requires_explicit_permission(self) -> None:
        with self.assertRaisesRegex(ValueError, "allow_network=True"):
            fetch_cathay_announcement_page(
                etf_code="00878", page=1, page_size=10
            )

    @patch(
        "backend.app.data_sources.cathay_actual_dividend_discovery.httpx.get"
    )
    def test_network_response_must_remain_on_official_domain(
        self, mock_get
    ) -> None:
        response = mock_get.return_value
        response.url = "https://example.com/redirected"
        response.json.return_value = self.payload()

        with self.assertRaisesRegex(ValueError, "不在允許網域"):
            fetch_cathay_announcement_page(
                etf_code="00878",
                page=1,
                page_size=10,
                allow_network=True,
            )


if __name__ == "__main__":
    unittest.main()
