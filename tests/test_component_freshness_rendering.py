"""Render the real tax-result component and verify its stale-ACTUAL warning."""

import unittest
from streamlit.testing.v1 import AppTest


class TestComponentFreshnessRendering(unittest.TestCase):
    def test_real_renderer_shows_freshness_and_estimate_warnings(self):
        payload = {
            "status": "AVAILABLE",
            "warnings": ["歷史正式配息組成（2023-09-11）已過期；本次改用估計組成。"],
            "historical_facts": {
                "component_calculation_basis": "ESTIMATED_FALLBACK",
                "component_source_date": "2026-06-12",
                "component_source_event_id": "estimate-2",
            },
            "calculation": {
                "rule_version": "synthetic", "rule_effective_date": "2026-01-01",
                "projection_years": 1, "currency": "TWD",
                "scenarios": [{"policy": policy} for policy in (
                    "NO_REINVESTMENT", "EXCESS_ONLY", "CUSTOM_PERCENTAGE", "FULL_REINVESTMENT",
                )],
            },
        }
        app = AppTest.from_string(
            "from frontend.pages.etf_detail import _render_tax_reinvestment_result\n"
            f"_render_tax_reinvestment_result({payload!r})"
        ).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any("2023-09-11" in warning.value for warning in app.warning))
        self.assertTrue(any("54C" in warning.value and "76W" in warning.value for warning in app.warning))
