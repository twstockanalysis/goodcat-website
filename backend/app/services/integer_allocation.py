"""V3-3 確定性整數股數配置求解器。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.app.models.integer_allocation import (
    IntegerAllocationAddition,
    IntegerAllocationAssumptions,
    IntegerAllocationHoldingResult,
    IntegerAllocationMonthResult,
    IntegerAllocationOptimality,
    IntegerAllocationRequest,
    IntegerAllocationResponse,
    IntegerAllocationStatus,
)
from backend.app.models.public_planner import (
    PublicPlannerIssue,
    PublicPlannerResponse,
)
from backend.app.services.market_eligibility_index import (
    build_market_eligibility_index,
)
from backend.app.services.complete_portfolio_solver import (
    CompletePortfolioCandidate,
    CompletePortfolioPlan,
    cash_target_plan_order,
    solve_cash_target_frontier,
)
from backend.app.services.public_planner import analyze_public_planner_baseline


_MONEY = Decimal("0.01")
_PCT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _issue(code: str, message: str, field: str | None = None) -> PublicPlannerIssue:
    return PublicPlannerIssue(code=code, message=message, field=field)


def _select_plan(
    plans: tuple[CompletePortfolioPlan, ...],
    objective: str,
    current_cash: dict[int, Decimal],
) -> CompletePortfolioPlan:
    del current_cash  # Resulting cash is retained in each complete solver plan.
    return min(plans, key=lambda plan: cash_target_plan_order(plan, objective))


def _resulting_holdings(
    baseline: PublicPlannerResponse,
    request: IntegerAllocationRequest,
    added_shares: dict[str, int],
    added_prices: dict[str, Decimal],
    added_market_facts: dict[str, tuple[date, str]] | None = None,
) -> list[IntegerAllocationHoldingResult]:
    existing_units = {
        holding.etf_code: holding.held_units for holding in request.existing_holdings
    }
    values = {
        holding.etf_code: holding.current_value
        for holding in baseline.holdings
        if holding.current_value is not None
    }
    for code, shares in added_shares.items():
        if shares > 0:
            values[code] = values.get(code, Decimal("0")) + added_prices[code] * shares
    total = sum(values.values(), Decimal("0"))
    results = []
    for code in sorted(values):
        fact = next(
            (holding for holding in baseline.holdings if holding.etf_code == code),
            None,
        )
        price = added_prices.get(code) or (fact.unit_price if fact else None)
        if price is None or total <= 0:
            continue
        existing = existing_units.get(code, 0)
        additional = added_shares.get(code, 0)
        market_fact = (added_market_facts or {}).get(code)
        if fact is not None:
            price_as_of = fact.price_as_of_date
            price_source = fact.price_source_id
        elif market_fact is not None:
            price_as_of, price_source = market_fact
        else:
            price_as_of = None
            price_source = None
        if price_as_of is None or price_source is None:
            continue
        results.append(
            IntegerAllocationHoldingResult(
                etf_code=code,
                existing_shares=existing,
                additional_shares=additional,
                resulting_shares=existing + additional,
                reference_price=price,
                reference_price_as_of=price_as_of,
                reference_price_source_id=price_source,
                resulting_value=_money(values[code]),
                allocation_pct=(
                    values[code] / total * Decimal("100")
                ).quantize(_PCT, rounding=ROUND_HALF_UP),
            )
        )
    return results


def build_integer_allocation(
    request: IntegerAllocationRequest,
    database_path: str | Path,
    *,
    as_of_date: date | None = None,
    preferred_candidate_order: tuple[str, ...] | None = None,
    preference_first: bool = False,
    plan_objective: str = "CAPITAL_EFFICIENT",
) -> IntegerAllocationResponse:
    # V3 strategy preferences remain accepted for API compatibility. V5-4 no
    # longer lets a pre-ranked ETF list choose feasibility.
    del preferred_candidate_order, preference_first
    analysis_date = as_of_date or date.today()
    baseline = analyze_public_planner_baseline(
        request, database_path, as_of_date=analysis_date
    )
    built_index = build_market_eligibility_index(
        request, database_path, as_of_date=analysis_date
    )
    index = built_index.response
    assumptions = IntegerAllocationAssumptions(
        max_additional_capital_twd=request.max_additional_capital_twd,
        cash_deduction_rate_pct=request.cash_deduction_rate_pct,
        max_candidate_allocation_pct=index.rules.max_candidate_allocation_pct,
    )
    selected = tuple(request.target_months)
    current_cash: dict[int, Decimal] = {}
    unavailable_months = []
    for month in selected:
        row = baseline.monthly_cash_flow[month - 1]
        if row.after_tax_cash is None:
            unavailable_months.append(month)
        else:
            current_cash[month] = row.after_tax_cash

    empty_months = [
        IntegerAllocationMonthResult(
            month=month,
            current_after_tax_cash=current_cash.get(month, Decimal("0")),
            added_after_tax_cash=Decimal("0"),
            modeled_after_tax_cash=current_cash.get(month, Decimal("0")),
            target_after_tax_cash=request.target_after_tax_cash_twd,
            shortfall=max(
                request.target_after_tax_cash_twd
                - current_cash.get(month, Decimal("0")),
                Decimal("0"),
            ),
        )
        for month in selected
    ]
    common = dict(
        analysis_date=analysis_date,
        snapshot_id=index.snapshot_id,
        target_after_tax_cash_twd=request.target_after_tax_cash_twd,
        target_months=list(selected),
        assumptions=assumptions,
        universe_count=index.universe_count,
        eligible_count=index.eligible_count,
    )
    missing_holding_values = [
        holding.etf_code
        for holding in baseline.holdings
        if holding.current_value is None
    ]
    if unavailable_months or missing_holding_values:
        unavailable_issues = list(baseline.issues)
        if unavailable_months:
            unavailable_issues.append(
                _issue(
                    "CURRENT_CASH_UNAVAILABLE",
                    "現有持股在部分目標月份缺少可計算的歷史現金流。",
                    "existing_holdings",
                )
            )
        if missing_holding_values:
            unavailable_issues.append(
                _issue(
                    "CURRENT_VALUE_UNAVAILABLE",
                    "現有持股缺少參考價格，無法驗證配置後集中度與所需資金。",
                    "existing_holdings",
                )
            )
        return IntegerAllocationResponse(
            **common,
            status=IntegerAllocationStatus.UNAVAILABLE,
            optimality=IntegerAllocationOptimality.NOT_APPLICABLE,
            total_required_additional_capital=Decimal("0"),
            monthly_results=empty_months,
            issues=unavailable_issues,
        )

    target = request.target_after_tax_cash_twd
    already_met = all(current_cash[month] >= target for month in selected)
    candidates = built_index.ranked_eligible_candidates
    if already_met:
        return IntegerAllocationResponse(
            **common,
            status=IntegerAllocationStatus.TARGET_MET,
            optimality=IntegerAllocationOptimality.PROVED_OPTIMAL,
            total_required_additional_capital=Decimal("0"),
            monthly_results=empty_months,
            resulting_holdings=_resulting_holdings(
                baseline, request, {}, {}
            ),
            issues=baseline.issues,
        )
    if not candidates:
        return IntegerAllocationResponse(
            **common,
            status=IntegerAllocationStatus.NO_ELIGIBLE_ALLOCATION,
            optimality=IntegerAllocationOptimality.NOT_APPLICABLE,
            total_required_additional_capital=Decimal("0"),
            monthly_results=empty_months,
            issues=[
                *baseline.issues,
                _issue(
                    "NO_ELIGIBLE_CANDIDATE",
                    "目前沒有通過全市場資料與風險門檻的可新增 ETF。",
                )
            ],
        )

    candidates_by_code = {
        item.public_item.etf_code: item for item in candidates
    }
    prices = {
        code: candidate.public_item.reference_price
        for code, candidate in candidates_by_code.items()
        if candidate.public_item.reference_price is not None
    }
    solver_candidates = tuple(
        CompletePortfolioCandidate(
            etf_code=code,
            reference_price=price,
            monthly_cash_per_share=(
                candidates_by_code[code].monthly_after_tax_cash_per_share
            ),
        )
        for code, price in prices.items()
    )
    search = solve_cash_target_frontier(
        solver_candidates,
        selected_months=selected,
        target_cash_by_month={month: target for month in selected},
        current_cash_by_month=current_cash,
        current_value_by_code={
            holding.etf_code: holding.current_value
            for holding in baseline.holdings
            if holding.current_value is not None
        },
        max_added_etfs=5,
        objective=plan_objective,
        max_additional_capital=request.max_additional_capital_twd,
    )
    selected_plan = _select_plan(search.frontier, plan_objective, current_cash)
    selected_shares = dict(selected_plan.shares)
    added_cash = dict(selected_plan.monthly_added_cash)
    additions = []
    for code in sorted(selected_shares):
        quantity = selected_shares[code]
        if quantity <= 0:
            continue
        candidate = candidates_by_code[code]
        price = prices[code]
        supported = [
            month
            for month in selected
            if candidate.monthly_after_tax_cash_per_share[month - 1] > 0
        ]
        risks = [reason.message for reason in candidate.public_item.reasons]
        additions.append(
            IntegerAllocationAddition(
                etf_code=code,
                name=candidate.public_item.name,
                historical_quality_grade=(
                    candidate.public_item.historical_quality_grade
                ),
                additional_shares=quantity,
                reference_price=price,
                reference_price_as_of=candidate.public_item.reference_price_as_of,
                reference_price_source_id=(
                    candidate.public_item.reference_price_source_id or "UNKNOWN"
                ),
                estimated_transaction_cost=Decimal("0"),
                required_capital=_money(price * quantity),
                supported_target_months=supported,
                holding_overlap_pct=candidate.public_item.holding_overlap_pct,
                constituent_snapshot_dates=(
                    candidate.public_item.constituent_snapshot_dates
                ),
                reasons=["通過全市場資料門檻，並用於縮小目標月份現金流缺口。"],
                risks=risks,
            )
        )

    total_capital = sum(
        (item.required_capital for item in additions), Decimal("0")
    )
    added_market_facts = {
        code: (
            candidate.public_item.reference_price_as_of,
            candidate.public_item.reference_price_source_id or "UNKNOWN",
        )
        for code, candidate in candidates_by_code.items()
        if candidate.public_item.reference_price_as_of is not None
    }
    holdings = _resulting_holdings(
        baseline,
        request,
        selected_shares,
        prices,
        added_market_facts,
    )

    month_results = []
    total_shortfall = Decimal("0")
    for month in selected:
        modeled = current_cash[month] + added_cash[month]
        shortfall = max(target - modeled, Decimal("0"))
        total_shortfall += shortfall
        month_results.append(
            IntegerAllocationMonthResult(
                month=month,
                current_after_tax_cash=_money(current_cash[month]),
                added_after_tax_cash=_money(added_cash[month]),
                modeled_after_tax_cash=_money(modeled),
                target_after_tax_cash=target,
                shortfall=_money(shortfall),
            )
        )
    status = (
        IntegerAllocationStatus.TARGET_MET
        if total_shortfall <= 0
        else IntegerAllocationStatus.PARTIAL
    )
    issues = list(baseline.issues)
    if search.truncated:
        issues.append(
            _issue(
                "V5_4_BOUNDED_SEARCH",
                "完整配置使用有界確定性搜尋；結果不得描述為全域最低資金。",
            )
        )
    if status == IntegerAllocationStatus.PARTIAL:
        issues.append(
            _issue(
                ("NO_COMPLETE_PLAN_WITHIN_CAP"
                 if request.max_additional_capital_twd is not None
                 else "TARGET_MONTH_COVERAGE_INCOMPLETE"),
                ("本次有界搜尋未在新增資金上限內找到所有目標月份達標的完整方案；"
                 "目前結果仍有缺口，不代表已證明不存在可行方案。"
                 if request.max_additional_capital_twd is not None
                 else "通過門檻的候選 ETF 無法涵蓋所有目標月份。"),
                ("max_additional_capital_twd"
                 if request.max_additional_capital_twd is not None else None),
            )
        )
    return IntegerAllocationResponse(
        **common,
        status=status,
        optimality=IntegerAllocationOptimality.BOUNDED_BEST_EFFORT,
        search_explored_states=search.explored_states,
        search_truncated=search.truncated,
        additions=additions,
        total_required_additional_capital=_money(total_capital),
        monthly_results=month_results,
        resulting_holdings=holdings,
        issues=issues,
    )
