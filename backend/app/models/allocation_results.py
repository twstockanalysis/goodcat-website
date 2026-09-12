"""V3-4 多種配置結果與排除理由的公開契約。"""

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from backend.app.models.integer_allocation import (
    IntegerAllocationRequest,
    IntegerAllocationResponse,
)
from backend.app.models.market_eligibility import MarketEligibilityReason
from backend.app.models.public_planner import PublicPlannerBaseModel, PublicPlannerIssue
from backend.app.models.planning_metrics import PlanMetricsEntry


class AllocationStrategy(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    BALANCED = "BALANCED"
    FOCUSED = "FOCUSED"


class AllocationStrategyPlan(PublicPlannerBaseModel):
    strategy: AllocationStrategy
    label: str
    simple_explanation: str
    result: IntegerAllocationResponse


class AllocationExcludedCandidate(PublicPlannerBaseModel):
    etf_code: str
    name: str
    reasons: list[MarketEligibilityReason] = Field(default_factory=list)


class AllocationResultsRequest(IntegerAllocationRequest):
    pass


class AllocationResultsResponse(PublicPlannerBaseModel):
    profile_scope: Literal["PUBLIC_STATELESS"] = "PUBLIC_STATELESS"
    request_persisted: Literal[False] = False
    broker_connected: Literal[False] = False
    methodology: Literal["EXPLAINABLE_ALLOCATION_RESULTS_V3_4"] = (
        "EXPLAINABLE_ALLOCATION_RESULTS_V3_4"
    )
    snapshot_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    plans: list[AllocationStrategyPlan] = Field(min_length=1, max_length=3)
    excluded_candidates: list[AllocationExcludedCandidate] = Field(
        default_factory=list
    )
    strategy_issues: list[PublicPlannerIssue] = Field(default_factory=list)
    plan_metrics: list[PlanMetricsEntry] = Field(default_factory=list, max_length=3)
    estimate_label: str = (
        "依歷史資料建立的配置情境，非投資建議、下單指示或未來績效保證"
    )

    @model_validator(mode="after")
    def require_recommended_first_and_unique_strategies(self):
        strategies = [plan.strategy for plan in self.plans]
        if strategies[0] != AllocationStrategy.RECOMMENDED:
            raise ValueError("第一個方案必須是資金精簡方案")
        if len(strategies) != len(set(strategies)):
            raise ValueError("配置策略不可重複")
        return self
