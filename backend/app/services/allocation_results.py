"""V5-4 完整組合的主配置結果。"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from backend.app.models.allocation_results import (
    AllocationExcludedCandidate,
    AllocationResultsRequest,
    AllocationResultsResponse,
    AllocationStrategy,
    AllocationStrategyPlan,
)
from backend.app.models.public_planner import PublicPlannerIssue
from backend.app.services.integer_allocation import build_integer_allocation
from backend.app.services.market_eligibility_index import (
    build_market_eligibility_index,
)


def _issue(code: str, message: str) -> PublicPlannerIssue:
    return PublicPlannerIssue(code=code, message=message)


def build_allocation_results(
    request: AllocationResultsRequest,
    database_path: str | Path,
    *,
    as_of_date: date | None = None,
) -> AllocationResultsResponse:
    analysis_date = as_of_date or date.today()
    built_index = build_market_eligibility_index(
        request,
        database_path,
        as_of_date=analysis_date,
    )
    plan_definitions = (
        (
            AllocationStrategy.RECOMMENDED,
            "資金精簡方案",
            "CAPITAL_EFFICIENT",
            "完整達成目標後，優先降低新增資金、超額現金流與管理檔數。",
        ),
        (
            AllocationStrategy.BALANCED,
            "穩定均衡方案",
            "MONTHLY_BALANCED",
            "完整達成目標後，優先降低目標月份之間的現金流落差。",
        ),
        (
            AllocationStrategy.FOCUSED,
            "分散防護方案",
            "DIVERSIFIED_PROTECTION",
            "完整達成目標後，優先降低包含原持股在內的單一部位集中度。",
        ),
    )
    plans = []
    signatures: set[tuple[tuple[str, int], ...]] = set()
    for strategy, label, objective, explanation in plan_definitions:
        result = build_integer_allocation(
            request,
            database_path,
            as_of_date=analysis_date,
            plan_objective=objective,
        )
        signature = tuple(
            sorted((item.etf_code, item.additional_shares) for item in result.additions)
        )
        if plans and (result.status.value != "TARGET_MET" or signature in signatures):
            continue
        signatures.add(signature)
        plans.append(
            AllocationStrategyPlan(
                strategy=strategy,
                label=label,
                simple_explanation=explanation,
                result=result,
            )
        )
    recommended_result = plans[0].result
    strategy_issues: list[PublicPlannerIssue] = []
    if not recommended_result.additions:
        strategy_issues.append(
            _issue(
                "ALTERNATIVE_UNAVAILABLE_WITHOUT_PRIMARY_ALLOCATION",
                "主結果沒有新增標的，因此不產生重複的其他配置。",
            )
        )
    elif len(plans) < len(plan_definitions):
        strategy_issues.append(
            _issue(
                "MATERIALLY_DISTINCT_ALTERNATIVES_LIMITED",
                f"有界搜尋目前只產生 {len(plans)} 個股數組合不同的方案；"
                "不為湊滿三張卡片製造重複結果。",
            )
        )

    excluded = [
        AllocationExcludedCandidate(
            etf_code=item.etf_code,
            name=item.name,
            reasons=item.reasons,
        )
        for item in built_index.response.candidates
        if not item.eligible_for_addition
    ]
    return AllocationResultsResponse(
        snapshot_id=built_index.response.snapshot_id,
        plans=plans,
        excluded_candidates=excluded,
        strategy_issues=strategy_issues,
    )
