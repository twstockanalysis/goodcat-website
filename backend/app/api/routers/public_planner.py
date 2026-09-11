"""V3-1 公開且不儲存資料的現金流試算 API。"""

from pathlib import Path

from fastapi import APIRouter, Depends

from backend.app.api.dependencies import get_database_path
from backend.app.models.public_planner import PublicPlannerRequest, PublicPlannerResponse
from backend.app.models.market_eligibility import (
    MarketEligibilityIndexRequest,
    MarketEligibilityIndexResponse,
)
from backend.app.models.integer_allocation import (
    IntegerAllocationRequest,
    IntegerAllocationResponse,
)
from backend.app.models.allocation_results import (
    AllocationResultsRequest,
    AllocationResultsResponse,
)
from backend.app.services.allocation_results import build_allocation_results
from backend.app.models.long_term_scenario import (
    LongTermScenarioRequest,
    LongTermScenarioResponse,
)
from backend.app.services.long_term_scenario import build_long_term_scenarios
from backend.app.models.portfolio_projection import (
    PortfolioProjectionRequest,
    PortfolioProjectionResponse,
)
from backend.app.services.portfolio_projection import build_portfolio_projections
from backend.app.services.integer_allocation import build_integer_allocation
from backend.app.services.market_eligibility_index import (
    build_market_eligibility_index,
)
from backend.app.services.public_planner import analyze_public_planner_baseline
from backend.app.models.budget_allocation import BudgetAllocationRequest, BudgetAllocationResponse
from backend.app.services.budget_allocation import build_budget_allocation


router = APIRouter(prefix="/api/v1/allocation-plans", tags=["Public Planner"])


@router.post(
    "/budget-allocation",
    response_model=BudgetAllocationResponse,
    summary="建立無配息目標的預算內整股配置情境",
)
def create_budget_allocation(
    request: BudgetAllocationRequest,
    database_path: Path = Depends(get_database_path),
) -> BudgetAllocationResponse:
    return build_budget_allocation(request, database_path)


@router.post(
    "/baseline",
    response_model=PublicPlannerResponse,
    summary="建立不儲存資料的現有持股現金流基線",
)
def analyze_public_baseline(
    request: PublicPlannerRequest,
    database_path: Path = Depends(get_database_path),
) -> PublicPlannerResponse:
    return analyze_public_planner_baseline(request, database_path)


@router.post(
    "/eligibility-index",
    response_model=MarketEligibilityIndexResponse,
    summary="建立不含內部評分的全市場候選資格索引",
)
def read_market_eligibility_index(
    request: MarketEligibilityIndexRequest,
    database_path: Path = Depends(get_database_path),
) -> MarketEligibilityIndexResponse:
    return build_market_eligibility_index(request, database_path).response


@router.post(
    "/integer-allocation",
    response_model=IntegerAllocationResponse,
    summary="建立全市場整數股數配置情境",
)
def create_integer_allocation(
    request: IntegerAllocationRequest,
    database_path: Path = Depends(get_database_path),
) -> IntegerAllocationResponse:
    return build_integer_allocation(request, database_path)


@router.post(
    "/allocation-results",
    response_model=AllocationResultsResponse,
    summary="建立推薦、平衡與集中配置結果",
)
def create_allocation_results(
    request: AllocationResultsRequest,
    database_path: Path = Depends(get_database_path),
) -> AllocationResultsResponse:
    return build_allocation_results(request, database_path)


@router.post(
    "/long-term-scenarios",
    response_model=LongTermScenarioResponse,
    summary="建立配置後組合的歷史含息績效與十年情境",
)
def create_long_term_scenarios(
    request: LongTermScenarioRequest,
    database_path: Path = Depends(get_database_path),
) -> LongTermScenarioResponse:
    return build_long_term_scenarios(request, database_path)


@router.post(
    "/portfolio-projections",
    response_model=PortfolioProjectionResponse,
    summary="建立整體組合 1 至 20 年稅務與再投入情境",
)
def create_portfolio_projections(
    request: PortfolioProjectionRequest,
    database_path: Path = Depends(get_database_path),
) -> PortfolioProjectionResponse:
    return build_portfolio_projections(request, database_path)
