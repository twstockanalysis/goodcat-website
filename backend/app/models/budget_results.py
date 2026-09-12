"""Additive budget strategy contract; no cash target or risk-grade inference."""

from decimal import Decimal
from typing import Literal

from pydantic import Field

from backend.app.models.budget_allocation import BudgetAllocationResponse
from backend.app.models.public_planner import PublicPlannerBaseModel, PublicPlannerIssue
from backend.app.models.planning_metrics import PlanMetricsEntry


BudgetAlternateObjective = Literal["MONTHLY_BALANCED", "TOTAL_MONTH_CASH"]


class BudgetStrategyResponse(BudgetAllocationResponse):
    objective: BudgetAlternateObjective
    minimum_month_cash_floor: Decimal | None = Field(default=None, ge=0)
    tradeoff: str


class BudgetStrategySearchEvidence(PublicPlannerBaseModel):
    objective: BudgetAlternateObjective
    explored_states: int = Field(ge=0, le=20000)
    truncated: bool
    duplicate_of: Literal["MINIMUM_THEN_TOTAL_MONTH_CASH", "MONTHLY_BALANCED"] | None = None
    omission_reason: Literal["DUPLICATE", "NO_ADDITIONS"] | None = None


class BudgetResultsResponse(PublicPlannerBaseModel):
    primary: BudgetAllocationResponse
    alternatives: list[BudgetStrategyResponse] = Field(default_factory=list, max_length=2)
    alternate_searches: list[BudgetStrategySearchEvidence] = Field(default_factory=list, max_length=2)
    max_explored_states_per_strategy: Literal[20000] = 20000
    max_total_explored_states: Literal[60000] = 60000
    issues: list[PublicPlannerIssue] = Field(default_factory=list)
    plan_metrics: list[PlanMetricsEntry] = Field(default_factory=list, max_length=3)
