"""Planning freshness must not rewrite historical source precedence."""

import copy
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.app.services.dividend_component_data import (
    select_planning_component_mix, select_composite_component_mix,
    select_composite_realized_gain_history,
)
from backend.app.services.portfolio_projection import _holding_fact
from backend.app.models.portfolio_projection import PortfolioProjectionRequest

DAY = date(2026, 9, 6)


def event(identifier, paid, basis="ACTUAL", ratio=100):
    return {"dividend_id": identifier, "source_event_id": f"event-{identifier}",
            "payment_date": paid, "component_basis": basis,
            "component_code": "76W" if basis == "ACTUAL" else "EST_REALIZED_CAPITAL_GAIN",
            "ratio_pct": ratio}


class TestPlanningComponentFreshness(unittest.TestCase):
    def test_stale_actual_uses_fresh_estimate_with_warning_and_no_mutation(self):
        rows = [event(1, "2023-09-11"), event(2, "2026-06-12", "ESTIMATED")]
        before = copy.deepcopy(rows)
        result = select_planning_component_mix(rows, analysis_date=DAY)
        self.assertEqual(result.basis, "ESTIMATED_FALLBACK")
        self.assertEqual(result.source_date, date(2026, 6, 12))
        self.assertEqual(result.stale_actual_source_date, date(2023, 9, 11))
        self.assertIn("2023-09-11", result.freshness_warning)
        self.assertEqual(result.mix[0].component_code, "EST_REALIZED_CAPITAL_GAIN")
        self.assertEqual(rows, before)

    def test_fresh_actual_still_precedes_newer_estimate(self):
        result = select_planning_component_mix([
            event(2, "2026-06-12", "ESTIMATED"), event(1, "2026-03-12"),
        ], analysis_date=DAY)
        self.assertEqual(result.basis, "ACTUAL")
        self.assertIsNone(result.freshness_warning)

    def test_newest_within_basis_does_not_depend_on_input_order(self):
        result = select_planning_component_mix([
            event(1, "2026-01-01"), event(2, "2026-08-01"),
        ], analysis_date=DAY)
        self.assertEqual(result.dividend_id, 2)

    def test_exact_18_month_boundary_is_inclusive(self):
        row = event(1, "2025-03-06")
        self.assertIsNotNone(select_planning_component_mix([row], analysis_date=DAY))
        self.assertIsNone(select_planning_component_mix([row], analysis_date=date(2026, 9, 7)))

    def test_calendar_month_end_not_fixed_day_count(self):
        rows = [event(1, "2024-08-31")]
        self.assertIsNotNone(select_planning_component_mix(rows, analysis_date=date(2026, 2, 28)))
        self.assertIsNone(select_planning_component_mix(rows, analysis_date=date(2026, 3, 1)))

    def test_no_fresh_source_remains_unavailable(self):
        self.assertIsNone(select_planning_component_mix([
            event(1, "2023-09-11"), event(2, "2024-06-12", "ESTIMATED"),
        ], analysis_date=DAY))

    def test_future_or_missing_payment_cannot_fallback_to_other_dates(self):
        for paid in (None, "invalid", "2026-09-11"):
            row = event(1, paid)
            row["ex_dividend_date"] = "2026-08-01"
            self.assertIsNone(select_planning_component_mix([row], analysis_date=DAY))

    def test_future_actual_does_not_trigger_stale_actual_warning(self):
        result = select_planning_component_mix([
            event(1, "2026-09-11"), event(2, "2026-06-12", "ESTIMATED"),
        ], analysis_date=DAY)
        self.assertEqual(result.basis, "ESTIMATED_FALLBACK")
        self.assertIsNone(result.freshness_warning)

    def test_incomplete_fresh_actual_does_not_block_complete_estimate(self):
        result = select_planning_component_mix([
            event(1, "2026-08-01", ratio=None), event(2, "2026-06-12", "ESTIMATED"),
        ], analysis_date=DAY)
        self.assertEqual(result.basis, "ESTIMATED_FALLBACK")

    def test_incomplete_mixes_never_combine(self):
        self.assertIsNone(select_planning_component_mix([
            event(1, "2026-08-01", ratio=60), event(1, "2026-08-01", "ESTIMATED", ratio=40),
        ], analysis_date=DAY))

    def test_formal_zero_preserved(self):
        zero = event(1, "2026-08-01", ratio=0)
        dividend = {**zero, "component_code": "54C", "ratio_pct": 100}
        result = select_planning_component_mix([zero, dividend], analysis_date=DAY)
        self.assertEqual(result.mix[0].ratio_pct, Decimal("0"))

    def test_historical_selector_and_76w_history_keep_stale_actual(self):
        rows = [event(1, "2023-09-11"), event(2, "2026-06-12", "ESTIMATED")]
        self.assertEqual(select_composite_component_mix(rows).basis, "ACTUAL")
        history = select_composite_realized_gain_history(rows)
        actual = next(item for item in history if item.basis == "ACTUAL")
        self.assertEqual(actual.component_code, "76W")
        self.assertEqual(actual.source_date, date(2023, 9, 11))

    def test_portfolio_fact_uses_same_fresh_mix_and_warning(self):
        rows = [event(1, "2023-09-11"), event(2, "2026-06-12", "ESTIMATED")]
        request = PortfolioProjectionRequest(target_after_tax_cash_twd=100,
            target_months=[1], existing_holdings=[], history_years=3,
            cash_deduction_rate_pct=0)
        holding = SimpleNamespace(etf_code="00878", resulting_value=20000,
            resulting_shares=1000, reference_price=20)
        module = "backend.app.services.portfolio_projection."
        with patch(module + "list_etf_component_history", return_value=rows), patch(
            module + "list_etf_dividends", return_value=[{
                "payment_date": "2026-06-12", "amount_per_unit": 1, "currency": "TWD",
            }],
        ):
            fact = _holding_fact(holding, request, Path("unused.db"), DAY)
        self.assertEqual(fact.component_calculation_basis, "ESTIMATED_FALLBACK")
        self.assertEqual(fact.component_source_date, date(2026, 6, 12))
        self.assertIn("STALE_ACTUAL_COMPONENTS_FALLBACK", [i.code for i in fact.issues])
