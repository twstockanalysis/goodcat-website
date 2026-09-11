"""Independent, target-free public budget allocation contract."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import Field, field_validator, model_validator

from backend.app.models.integer_allocation import IntegerAllocationHoldingResult
from backend.app.models.market_eligibility import MarketEligibilityItem
from backend.app.models.public_planner import (
    PublicPlannerBaseModel, PublicPlannerHoldingFact, PublicPlannerHoldingInput,
    PublicPlannerIssue,
)
from backend.app.models.quality_grade import ETFHistoricalQualityGrade


class BudgetAllocationRequest(PublicPlannerBaseModel):
    investable_budget_twd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    selected_months: list[int] = Field(min_length=1, max_length=12)
    existing_holdings: list[PublicPlannerHoldingInput] = Field(
        default_factory=list, max_length=500,
    )
    history_years: int = Field(default=3, ge=1, le=10)
    cash_deduction_rate_pct: Decimal = Field(default=0, ge=0, le=100)
    currency: Literal["TWD"] = "TWD"

    @field_validator("existing_holdings", mode="before")
    @classmethod
    def reject_non_text_codes(cls, value):
        # The shared legacy code normalizer raises TypeError for non-strings;
        # keep malformed budget JSON within the sanitized validation boundary.
        if isinstance(value, list) and any(
            isinstance(holding, dict) and "etf_code" in holding
            and not isinstance(holding["etf_code"], str) for holding in value
        ):
            raise ValueError("ETF codes must be text")
        return value

    @field_validator("selected_months")
    @classmethod
    def normalize_months(cls, value: list[int]) -> list[int]:
        if any(month < 1 or month > 12 for month in value):
            raise ValueError("selected months must be between one and twelve")
        return sorted(set(value))

    @model_validator(mode="after")
    def reject_duplicate_holdings(self):
        codes = [holding.etf_code for holding in self.existing_holdings]
        if len(codes) != len(set(codes)):
            raise ValueError("existing holdings must have unique ETF codes")
        return self


class BudgetAllocationAssumptions(PublicPlannerBaseModel):
    history_years: int = Field(ge=1, le=10)
    cash_deduction_rate_pct: Decimal = Field(ge=0, le=100)
    cash_basis: Literal["HISTORICAL_SAME_CALENDAR_MONTH"] = (
        "HISTORICAL_SAME_CALENDAR_MONTH"
    )
    transaction_cost_rate_pct: Decimal = Field(default=Decimal("0"), ge=0, le=0)
    transaction_cost_note: str = "尚未納入券商手續費，交易成本固定以 0 元試算。"
    concentration_limit_enforced: Literal[False] = False
    max_added_etfs: Literal[5] = 5
    beam_width: Literal[64] = 64
    max_explored_states: Literal[20000] = 20000


class BudgetAllocationAddition(PublicPlannerBaseModel):
    etf_code: str
    name: str
    additional_shares: int = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    reference_price_as_of: date
    reference_price_source_id: str
    required_capital: Decimal = Field(ge=0)
    estimated_transaction_cost: Decimal = Field(default=Decimal("0"), ge=0, le=0)
    supported_months: list[int]
    historical_quality_grade: ETFHistoricalQualityGrade
    holding_overlap_pct: Decimal | None = Field(default=None, ge=0, le=100)
    constituent_snapshot_dates: list[date] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class BudgetAllocationMonthResult(PublicPlannerBaseModel):
    month: int = Field(ge=1, le=12)
    current_after_tax_cash: Decimal | None = Field(ge=0)
    added_after_tax_cash: Decimal = Field(ge=0)
    modeled_after_tax_cash: Decimal | None = Field(ge=0)


class BudgetAllocationResponse(PublicPlannerBaseModel):
    profile_scope: Literal["PUBLIC_STATELESS"] = "PUBLIC_STATELESS"
    request_persisted: Literal[False] = False
    broker_connected: Literal[False] = False
    methodology: Literal["BOUNDED_BUDGET_PORTFOLIO_V5_4"] = "BOUNDED_BUDGET_PORTFOLIO_V5_4"
    objective: Literal["MINIMUM_THEN_TOTAL_MONTH_CASH"] = "MINIMUM_THEN_TOTAL_MONTH_CASH"
    status: Literal["AVAILABLE", "NO_ADDITIONS", "NO_ELIGIBLE_ALLOCATION", "UNAVAILABLE"]
    optimality: Literal["BOUNDED_BEST_EFFORT", "NOT_APPLICABLE"]
    analysis_date: date
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    currency: Literal["TWD"] = "TWD"
    investable_budget_twd: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    used_budget_twd: Decimal = Field(ge=0)
    remaining_budget_twd: Decimal = Field(ge=0)
    selected_months: list[int] = Field(min_length=1, max_length=12)
    assumptions: BudgetAllocationAssumptions
    universe_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    candidate_evidence: list[MarketEligibilityItem]
    existing_holdings: list[PublicPlannerHoldingFact]
    resulting_holdings: list[IntegerAllocationHoldingResult] | None = None
    additions: list[BudgetAllocationAddition] = Field(default_factory=list, max_length=5)
    monthly_results: list[BudgetAllocationMonthResult]
    search_explored_states: int = Field(default=0, ge=0, le=20000)
    search_truncated: bool = False
    issues: list[PublicPlannerIssue] = Field(default_factory=list)
    estimate_label: str = "依歷史資料建立的預算配置情境，非投資建議、下單指示或未來配息保證"

    @model_validator(mode="after")
    def reconcile_budget(self):
        if self.used_budget_twd > self.investable_budget_twd:
            raise ValueError("modeled additions exceed the submitted budget")
        if self.used_budget_twd + self.remaining_budget_twd != self.investable_budget_twd:
            raise ValueError("used and remaining capital must reconcile to the budget")
        if sum((item.required_capital for item in self.additions), Decimal(0)) != self.used_budget_twd:
            raise ValueError("addition costs must reconcile to used budget")
        exact_costs = [item.reference_price * item.additional_shares for item in self.additions]
        if sum(exact_costs, Decimal(0)) > self.investable_budget_twd:
            raise ValueError("exact investment exceeds the submitted budget")
        if any(cost.quantize(Decimal(".01"), rounding=ROUND_HALF_UP) != item.required_capital
               for cost, item in zip(exact_costs, self.additions, strict=True)):
            raise ValueError("addition costs must match rounded whole-share investment")
        return self
