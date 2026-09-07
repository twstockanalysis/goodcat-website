"""Synthetic evidence only; no source PDFs or personal notices committed."""
from datetime import date
import unittest

from backend.app.data_sources.cathay_actual_dividend_discovery import CathayAnnouncementCandidate
from backend.app.data_sources.cathay_actual_evidence import screen_cathay_document


class TestCathayActualEvidence(unittest.TestCase):
    def screen(self, pages, declared=date(2026, 8, 13)):
        candidate = CathayAnnouncementCandidate(
            1, "收益分配公告", declared,
            "https://cwapi.cathaysite.com.tw/uploads/test.pdf", "test-1", "application/pdf")
        return screen_cathay_document(candidate, etf_code="00878",
                                      evaluated_on=date(2026, 9, 6), page_texts=pages)

    def test_actual_amount_and_76w_do_not_promote_estimated_attachment(self):
        result = self.screen(["證券代號：00878 每受益權單位實際配發金額",
                              "預估收益分配組成占比", "76W 預估每單位受益權 發放金額"])
        self.assertIn("ESTIMATED_COMPONENTS_NOT_ACTUAL", result["reasons"])
        self.assertFalse(result["actual_import_allowed"])

    def test_explicit_actual_still_requires_human_review(self):
        result = self.screen(["證券代號：00878 實際配發金額組成如下 54C 76W"])
        self.assertEqual(result["routing"], "HUMAN_REVIEW_REQUIRED")
        self.assertFalse(result["actual_import_allowed"])

    def test_estimates_override_actual_wording(self):
        result = self.screen(["證券代號：00878 實際收益分配組成", "預估占比"])
        self.assertEqual(result["routing"], "EXCLUDED_FROM_ACTUAL")

    def test_future_document_is_excluded(self):
        result = self.screen(["證券代號：00878 實際配息組成"], date(2026, 9, 7))
        self.assertIn("FUTURE_DOCUMENT", result["reasons"])

    def test_missing_or_conflicting_identity_is_excluded(self):
        for text in ("實際配息組成", "證券代號：00878 證券代號：0050 實際配息組成",
                     "證券代號：008780 實際配息組成"):
            with self.subTest(text=text):
                self.assertIn("ETF_IDENTITY_UNVERIFIED", self.screen([text])["reasons"])

    def test_empty_page_requires_extraction_review(self):
        for pages in ([], ["證券代號：00878 實際配息組成", "  "]):
            self.assertIn("INCOMPLETE_TEXT_EXTRACTION", self.screen(pages)["reasons"])

    def test_amount_only_is_not_actual_composition(self):
        self.assertIn("NO_EXPLICIT_ACTUAL_COMPOSITION",
                      self.screen(["證券代號：00878 實際配發金額 1.00"])["reasons"])

    def test_split_whitespace_cannot_hide_estimated_wording(self):
        result = self.screen(["證券代號：00878", "預估收益分\n配組成 占比"])
        self.assertIn("ESTIMATED_COMPONENTS_NOT_ACTUAL", result["reasons"])
