"""Read-only budget orchestration using unchanged evidence and eligibility gates."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from backend.app.models.budget_allocation import (
    BudgetAllocationAddition, BudgetAllocationAssumptions, BudgetAllocationMonthResult,
    BudgetAllocationRequest, BudgetAllocationResponse,
)
from backend.app.models.integer_allocation import IntegerAllocationRequest
from backend.app.models.budget_results import (
    BudgetResultsResponse, BudgetStrategyResponse, BudgetStrategySearchEvidence,
)
from backend.app.services.complete_portfolio_solver import (
    CompletePortfolioCandidate, solve_budget_frontier,
)
from backend.app.services.integer_allocation import _issue, _money, _resulting_holdings
from backend.app.services.market_eligibility_index import build_market_eligibility_index
from backend.app.services.public_planner import analyze_public_planner_baseline
from backend.app.models.planning_metrics import PlanMetricsEntry
from backend.app.services.planning_metrics import summarize_budget_plan


def build_budget_allocation(
    request: BudgetAllocationRequest, database_path: str | Path,
    *, as_of_date: date | None = None,
) -> BudgetAllocationResponse:
    analysis_date = as_of_date or date.today()
    facts = _load_budget_facts(request, database_path, analysis_date)
    return _build_budget_allocation(request, analysis_date, *facts)[0]


def _load_budget_facts(request, database_path, analysis_date):
    # Compatibility envelope for read-only fact loaders only. The zero target
    # is neither submitted by the user nor passed to an allocation solver;
    # baseline target/shortfall fields are discarded. Budget never becomes target.
    facts_request = IntegerAllocationRequest(
        target_after_tax_cash_twd=0, target_months=request.selected_months,
        existing_holdings=request.existing_holdings, history_years=request.history_years,
        cash_deduction_rate_pct=request.cash_deduction_rate_pct, currency=request.currency,
    )
    baseline = analyze_public_planner_baseline(
        facts_request, database_path, as_of_date=analysis_date,
    )
    built = build_market_eligibility_index(
        facts_request, database_path, as_of_date=analysis_date,
    )
    return facts_request, baseline, built


def _build_budget_allocation(
    request, analysis_date, facts_request, baseline, built,
    objective="MINIMUM_THEN_TOTAL_MONTH_CASH", seed_plan=None,
):
    index = built.response
    current = {m: baseline.monthly_cash_flow[m - 1].after_tax_cash for m in request.selected_months}
    issues = list(baseline.issues)
    common = dict(
        analysis_date=analysis_date, snapshot_id=index.snapshot_id,
        investable_budget_twd=request.investable_budget_twd,
        selected_months=request.selected_months,
        assumptions=BudgetAllocationAssumptions(
            history_years=request.history_years,
            cash_deduction_rate_pct=request.cash_deduction_rate_pct,
        ),
        universe_count=index.universe_count, eligible_count=index.eligible_count,
        candidate_evidence=index.candidates, existing_holdings=baseline.holdings,
    )
    empty_months = [BudgetAllocationMonthResult(
        month=m, current_after_tax_cash=cash, added_after_tax_cash=0,
        modeled_after_tax_cash=cash,
    ) for m, cash in current.items()]
    if any(cash is None for cash in current.values()) or any(
        fact.current_value is None for fact in baseline.holdings
    ):
        issues.append(_issue(
            "CURRENT_HOLDING_FACTS_UNAVAILABLE",
            "現有持股缺少可計算的現金流或參考價格；保留原持股與缺漏，不建立新增配置。",
            "existing_holdings",
        ))
        return BudgetAllocationResponse(
            **common, status="UNAVAILABLE", optimality="NOT_APPLICABLE",
            used_budget_twd=0, remaining_budget_twd=request.investable_budget_twd,
            monthly_results=empty_months, issues=issues,
        ), None

    candidates = {c.public_item.etf_code: c for c in built.ranked_eligible_candidates}
    prices = {code: c.public_item.reference_price for code, c in candidates.items()}
    search = solve_budget_frontier(
        tuple(CompletePortfolioCandidate(
            code, prices[code], c.monthly_after_tax_cash_per_share,
        ) for code, c in candidates.items()),
        selected_months=request.selected_months,
        investable_budget=request.investable_budget_twd,
        current_cash_by_month=current,
        **({"objective": objective, "seed_plan": seed_plan} if seed_plan is not None else {}),
    )
    plan = search.frontier[0]
    shares = dict(plan.shares)
    added_cash = dict(plan.monthly_added_cash)
    additions = []
    for code, quantity in plan.shares:
        candidate = candidates[code]
        item = candidate.public_item
        additions.append(BudgetAllocationAddition(
            etf_code=code, name=item.name, additional_shares=quantity,
            reference_price=prices[code], reference_price_as_of=item.reference_price_as_of,
            reference_price_source_id=item.reference_price_source_id or "UNKNOWN",
            required_capital=_money(prices[code] * quantity),
            supported_months=[m for m in request.selected_months
                              if candidate.monthly_after_tax_cash_per_share[m - 1] > 0],
            historical_quality_grade=item.historical_quality_grade,
            holding_overlap_pct=item.holding_overlap_pct,
            constituent_snapshot_dates=item.constituent_snapshot_dates,
            reasons=["通過既有資料門檻，用於預算內的所選月份歷史現金流試算。"],
            risks=[reason.message for reason in item.reasons],
        ))
    used = sum((item.required_capital for item in additions), Decimal(0))
    status = "AVAILABLE" if additions else "NO_ADDITIONS"
    if request.investable_budget_twd == 0:
        issues.append(_issue("ZERO_INVESTABLE_BUDGET", "新增預算為零，僅呈現原持股現金流。"))
    elif not candidates:
        status = "NO_ELIGIBLE_ALLOCATION"
        issues.append(_issue("NO_ELIGIBLE_CANDIDATE", "沒有通過既有資料與風險門檻的可新增 ETF。"))
    elif not additions:
        issues.append(_issue(
            "NO_BUDGET_ADDITIONS_FOUND",
            "本次搜尋未找到預算內可增加所選月份現金流的整股配置；不代表已證明不存在可行方案。",
        ))
    if request.investable_budget_twd > 0 and candidates:
        issues.append(_issue(
            "V5_4_BOUNDED_BUDGET_SEARCH",
            "採有界整股批次搜尋，並非全域最大現金流保證；未截斷也不代表窮舉所有股數。",
        ))
    response_type = BudgetAllocationResponse
    if seed_plan is not None:
        response_type = BudgetStrategyResponse
        common.update(
            objective=objective,
            minimum_month_cash_floor=(seed_plan.minimum_month_cash
                                      if objective == "MONTHLY_BALANCED" else None),
            tradeoff=(
                "以主方案的最低月現金流為下限，優先縮小所選月份差距；不代表風險較低。"
                if objective == "MONTHLY_BALANCED" else
                "優先增加所選月份現金流總額，個別月份可能較少；不等同高風險評等。"
            ),
        )
    return response_type(
        **common, status=status,
        optimality=("BOUNDED_BEST_EFFORT" if request.investable_budget_twd > 0 and candidates
                    else "NOT_APPLICABLE"),
        used_budget_twd=used, remaining_budget_twd=request.investable_budget_twd - used,
        additions=additions,
        resulting_holdings=_resulting_holdings(
            baseline, facts_request, shares, prices,
            {code: (c.public_item.reference_price_as_of,
                    c.public_item.reference_price_source_id or "UNKNOWN")
             for code, c in candidates.items()},
        ),
        monthly_results=[BudgetAllocationMonthResult(
            month=m, current_after_tax_cash=_money(current[m]),
            added_after_tax_cash=_money(added_cash[m]),
            modeled_after_tax_cash=_money(current[m] + added_cash[m]),
        ) for m in request.selected_months],
        search_explored_states=search.explored_states, search_truncated=search.truncated,
        issues=issues,
    ), search


def build_budget_results(
    request: BudgetAllocationRequest, database_path: str | Path,
    *, as_of_date: date | None = None,
) -> BudgetResultsResponse:
    analysis_date = as_of_date or date.today()
    facts = _load_budget_facts(request, database_path, analysis_date)
    primary, search = _build_budget_allocation(request, analysis_date, *facts)
    result = BudgetResultsResponse(primary=primary, plan_metrics=[PlanMetricsEntry(
        plan_key=primary.objective, metrics=summarize_budget_plan(primary),
    )])
    if primary.status != "AVAILABLE":
        return result
    seed = search.frontier[0]
    seen = {seed.shares: primary.objective}
    for objective in ("MONTHLY_BALANCED", "TOTAL_MONTH_CASH"):
        response, alternate = _build_budget_allocation(
            request, analysis_date, *facts, objective=objective, seed_plan=seed,
        )
        signature = alternate.frontier[0].shares
        duplicate = seen.get(signature)
        result.alternate_searches.append(BudgetStrategySearchEvidence(
            objective=objective, explored_states=alternate.explored_states,
            truncated=alternate.truncated, duplicate_of=duplicate,
            omission_reason=("DUPLICATE" if duplicate is not None else
                             "NO_ADDITIONS" if response.status != "AVAILABLE" else None),
        ))
        if duplicate is not None:
            result.issues.append(_issue(
                "DUPLICATE_BUDGET_STRATEGY_OMITTED",
                f"{objective} 與 {duplicate} 的新增股數完全相同，省略重複方案。",
            ))
            continue
        if response.status != "AVAILABLE":
            result.issues.append(_issue(
                "NO_ADDITION_BUDGET_STRATEGY_OMITTED",
                f"{objective} 選出不新增的情境，未建立一般新增配置方案；不代表無其他可行配置。",
            ))
            continue
        seen[signature] = objective
        result.alternatives.append(response)
        result.plan_metrics.append(PlanMetricsEntry(
            plan_key=response.objective, metrics=summarize_budget_plan(response),
        ))
    return result
