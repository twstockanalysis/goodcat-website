"""Descriptive plan facts, deliberately not a score or suitability assessment."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from backend.app.models.public_planner import PublicPlannerBaseModel, PublicPlannerIssue


class PlanningMetrics(PublicPlannerBaseModel):
    methodology: Literal["DESCRIPTIVE_PLAN_METRICS_V5_4"] = "DESCRIPTIVE_PLAN_METRICS_V5_4"
    mode: Literal["CASH_TARGET", "BUDGET"]
    source_status: str
    amount_basis: Literal["DISPLAYED_RESPONSE_AMOUNTS"] = "DISPLAYED_RESPONSE_AMOUNTS"
    target_attainment: Literal["MET", "NOT_MET", "NOT_APPLICABLE", "UNAVAILABLE"]
    selected_months: list[int] = Field(min_length=1, max_length=12)
    minimum_month_cash_twd: Decimal | None = Field(default=None, ge=0)
    maximum_month_cash_twd: Decimal | None = Field(default=None, ge=0)
    total_selected_month_cash_twd: Decimal | None = Field(default=None, ge=0)
    month_cash_spread_twd: Decimal | None = Field(default=None, ge=0)
    total_shortfall_twd: Decimal | None = Field(default=None, ge=0)
    total_overshoot_twd: Decimal | None = Field(default=None, ge=0)
    additional_capital_twd: Decimal | None = Field(default=None, ge=0)
    capital_limit_twd: Decimal | None = Field(default=None, ge=0)
    remaining_capital_twd: Decimal | None = Field(default=None, ge=0)
    capital_usage_pct: Decimal | None = Field(default=None, ge=0, le=100)
    added_etf_count: int | None = Field(default=None, ge=0)
    resulting_etf_count: int | None = Field(default=None, ge=0)
    max_resulting_position_pct: Decimal | None = Field(default=None, ge=0, le=100)
    issues: list[PublicPlannerIssue] = Field(default_factory=list)
    interpretation: str = (
        "僅整理此配置的客觀數值，不是總分、評等、個人適合度或買賣建議；"
        "資金使用率與集中度不代表品質或風險等級。"
    )


class PlanMetricsEntry(PublicPlannerBaseModel):
    plan_key: Literal[
        "RECOMMENDED", "BALANCED", "FOCUSED", "MINIMUM_THEN_TOTAL_MONTH_CASH",
        "MONTHLY_BALANCED", "TOTAL_MONTH_CASH",
    ]
    metrics: PlanningMetrics
