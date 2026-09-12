"""Read-only projections of selected responses; never imports or calls a solver."""

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from backend.app.models.budget_allocation import BudgetAllocationResponse
from backend.app.models.integer_allocation import IntegerAllocationResponse
from backend.app.models.planning_metrics import PlanningMetrics
from backend.app.models.public_planner import PublicPlannerIssue


def _issue(code: str, message: str, field: str | None = None) -> PublicPlannerIssue:
    return PublicPlannerIssue(code=code, message=message, field=field)


def _summarize(result, *, mode, months, capital, limit, expected_codes):
    unavailable = result.status == "UNAVAILABLE"
    attainment = ("NOT_APPLICABLE" if mode == "BUDGET" else
                  "UNAVAILABLE" if unavailable else
                  "MET" if result.status == "TARGET_MET" else "NOT_MET")
    metrics = PlanningMetrics(
        mode=mode, source_status=result.status, selected_months=list(months),
        target_attainment=attainment, capital_limit_twd=limit,
    )
    if mode == "BUDGET":
        metrics.issues.append(_issue(
            "NO_CASH_TARGET_IN_BUDGET_MODE", "預算模式未設定配息目標，不計算達標、缺口或超額。",
            "target_attainment",
        ))
    if unavailable:
        metrics.issues.append(_issue(
            "ALLOCATION_FACTS_UNAVAILABLE", "配置所需事實不足，指標維持缺漏；原始回應仍保留已知事實。",
        ))
        return metrics

    metrics.additional_capital_twd = capital
    metrics.added_etf_count = len(result.additions)
    if limit is None:
        metrics.issues.append(_issue(
            "NO_CAPITAL_LIMIT", "未設定新增資金上限，不計算剩餘額或使用率。", "capital_usage_pct",
        ))
    else:
        metrics.remaining_capital_twd = limit - capital
        if limit > 0:
            metrics.capital_usage_pct = (capital / limit * 100).quantize(
                Decimal(".01"), rounding=ROUND_HALF_UP,
            )
        else:
            metrics.issues.append(_issue(
                "ZERO_CAPITAL_DENOMINATOR", "資金上限為零，使用率沒有可用分母。", "capital_usage_pct",
            ))

    rows = result.monthly_results
    if (len(rows) != len(months) or {r.month for r in rows} != set(months)
            or any(r.modeled_after_tax_cash is None for r in rows)):
        metrics.issues.append(_issue(
            "MONTH_CASH_UNAVAILABLE", "所選月份現金流不完整，不彙總部分月份為完整結果。",
            "total_selected_month_cash_twd",
        ))
    else:
        cash = [r.modeled_after_tax_cash for r in rows]
        metrics.minimum_month_cash_twd = min(cash)
        metrics.maximum_month_cash_twd = max(cash)
        metrics.total_selected_month_cash_twd = sum(cash, Decimal(0))
        metrics.month_cash_spread_twd = max(cash) - min(cash)
        if mode == "CASH_TARGET":
            metrics.total_shortfall_twd = sum((r.shortfall for r in rows), Decimal(0))
            metrics.total_overshoot_twd = sum((
                max(r.modeled_after_tax_cash - r.target_after_tax_cash, Decimal(0)) for r in rows
            ), Decimal(0))

    holdings = result.resulting_holdings
    required_codes = set(expected_codes) | {a.etf_code for a in result.additions}
    if holdings is None or {h.etf_code for h in holdings} != required_codes:
        metrics.issues.append(_issue(
            "RESULTING_POSITIONS_UNAVAILABLE", "缺少完整配置後部位，不推估檔數或集中度。",
            "max_resulting_position_pct",
        ))
    else:
        metrics.resulting_etf_count = len(holdings)
        if holdings:
            # Reuse the existing portfolio calculation, including original units;
            # do not renormalize rounded values or derive a risk label.
            metrics.max_resulting_position_pct = max(h.allocation_pct for h in holdings)
        else:
            metrics.issues.append(_issue(
                "NO_RESULTING_POSITIONS", "沒有配置後部位，集中度不適用。", "max_resulting_position_pct",
            ))
    return metrics


def summarize_cash_target_plan(
    result: IntegerAllocationResponse, *, existing_codes: Sequence[str],
) -> PlanningMetrics:
    return _summarize(
        result, mode="CASH_TARGET", months=result.target_months,
        capital=result.total_required_additional_capital,
        limit=result.assumptions.max_additional_capital_twd, expected_codes=existing_codes,
    )


def summarize_budget_plan(result: BudgetAllocationResponse) -> PlanningMetrics:
    return _summarize(
        result, mode="BUDGET", months=result.selected_months, capital=result.used_budget_twd,
        limit=result.investable_budget_twd, expected_codes=[h.etf_code for h in result.existing_holdings],
    )
