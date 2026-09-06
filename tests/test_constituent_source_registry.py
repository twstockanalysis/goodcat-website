"""All-issuer constituent-source coverage tests."""

import unittest
from urllib.parse import urlparse

from backend.app.data_sources.actual_dividend_source_registry import (
    TWSE_ETF_ISSUERS,
)
from backend.app.data_sources.constituent_source_registry import (
    CONSTITUENT_SOURCES,
    ConstituentSourceStatus,
    get_constituent_source,
)


class TestConstituentSourceRegistry(unittest.TestCase):
    def test_every_twse_issuer_has_a_reviewed_constituent_source(self):
        self.assertEqual(set(CONSTITUENT_SOURCES), set(TWSE_ETF_ISSUERS))
        self.assertEqual(len(CONSTITUENT_SOURCES), 23)
        for issuer_key, source in CONSTITUENT_SOURCES.items():
            with self.subTest(issuer_key=issuer_key):
                self.assertEqual(source.issuer_key, issuer_key)
                self.assertEqual(source.issuer_name, TWSE_ETF_ISSUERS[issuer_key])
                self.assertEqual(urlparse(source.official_url).scheme, "https")
                self.assertTrue(source.representative_etf_code)
                self.assertTrue(source.locator)
                self.assertTrue(source.note)

    def test_statuses_do_not_overstate_automation(self):
        automated = {
            key for key, value in CONSTITUENT_SOURCES.items()
            if value.status is ConstituentSourceStatus.AUTOMATED
        }
        not_applicable = {
            key for key, value in CONSTITUENT_SOURCES.items()
            if value.status is ConstituentSourceStatus.NOT_APPLICABLE
        }
        self.assertEqual(
            automated,
            {
                "yuanta", "fubon", "sinopac", "taishin", "ctbc", "nomura",
                "mega", "fuh_hwa", "uob", "esun",
                "franklin", "jpmorgan", "alliancebernstein", "hnh", "allianz",
                "union", "first", "capital", "upam", "kgi", "cathay",
            },
        )
        self.assertEqual(not_applicable, {"jko"})

        full_disclosure = {
            key for key, value in CONSTITUENT_SOURCES.items()
            if value.status is ConstituentSourceStatus.FULL_DISCLOSURE_VERIFIED
        }
        entrypoint_only = {
            key for key, value in CONSTITUENT_SOURCES.items()
            if value.status is ConstituentSourceStatus.ENTRYPOINT_VERIFIED
        }
        self.assertEqual(
            full_disclosure,
            set(TWSE_ETF_ISSUERS)
            - {
                "yuanta", "fubon", "sinopac", "taishin", "ctbc", "nomura",
                "mega", "fuh_hwa", "uob", "esun", "jko",
                "franklin", "jpmorgan", "alliancebernstein", "hnh", "allianz",
                "union", "first", "capital", "upam", "kgi", "cathay",
            },
        )
        self.assertEqual(entrypoint_only, set())

    def test_lookup_normalizes_key_and_rejects_unknown_values(self):
        self.assertEqual(get_constituent_source(" CATHAY ").issuer_key, "cathay")
        with self.assertRaisesRegex(KeyError, "找不到 ETF 成分股來源"):
            get_constituent_source("unknown")


if __name__ == "__main__":
    unittest.main()
