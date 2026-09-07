"""V3-1 公開試算的唯讀現有持股基線。"""

from backend.app.exceptions import ETFNotFoundError

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.app.models.public_planner import (
    PublicPlannerHoldingFact,
    PublicPlannerIssue,
    PublicPlannerMonthResult,
    PublicPlannerRequest,
    PublicPlannerResponse,
    PublicPlannerStatus,
)
from backend.app.repositories.daily_close_repository import get_latest_daily_close
from backend.app.repositories.etf_repository import get_etf_by_code
from backend.app.services.target_analysis_data import load_target_analysis_data


_HUNDRED = Decimal("100")
_MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _issue(
    code: str,
    message: str,
    *,
    field: str | None = None,
    etf_code: str | None = None,
) -> PublicPlannerIssue:
    return PublicPlannerIssue(
        code=code,
        message=message,
        field=field,
        etf_code=etf_code,
    )


def analyze_public_planner_baseline(
    request: PublicPlannerRequest,
    database_path: str | Path,
    *,
    as_of_date: date | None = None,
) -> PublicPlannerResponse:
    """只讀取市場資料，建立現有持股的逐月歷史年化基線。"""

    analysis_date = as_of_date or date.today()
    target_months = set(request.target_months)

    if not request.existing_holdings:
        monthly = [
            PublicPlannerMonthResult(
                month=month,
                selected=month in target_months,
                gross_cash=Decimal("0.00"),
                after_tax_cash=Decimal("0.00"),
                target_after_tax_cash=(
                    request.target_after_tax_cash_twd
                    if month in target_months
                    else Decimal("0")
                ),
                shortfall=(
                    request.target_after_tax_cash_twd
                    if month in target_months
                    else Decimal("0")
                ),
            )
            for month in range(1, 13)
        ]
        return PublicPlannerResponse(
            status=PublicPlannerStatus.AVAILABLE,
            analysis_date=analysis_date,
            target_after_tax_cash_twd=request.target_after_tax_cash_twd,
            target_months=request.target_months,
            history_years=request.history_years,
            cash_deduction_rate_pct=request.cash_deduction_rate_pct,
            total_current_value=Decimal("0"),
            holdings=[],
            monthly_cash_flow=monthly,
        )

    facts: list[PublicPlannerHoldingFact] = []
    issues: list[PublicPlannerIssue] = []
    total_current_value = Decimal("0")
    current_value_complete = True
    monthly_totals = {month: Decimal("0") for month in range(1, 13)}
    monthly_complete = {month: True for month in range(1, 13)}

    for holding in request.existing_holdings:
        etf = get_etf_by_code(holding.etf_code, database_path)
        if etf is None:
            raise ETFNotFoundError(holding.etf_code)

        holding_issues: list[PublicPlannerIssue] = []
        latest_close = get_latest_daily_close(holding.etf_code, database_path)
        unit_price = _decimal(latest_close["close_price"]) if latest_close else None
        current_value = (
            _money(unit_price * holding.held_units)
            if unit_price is not None
            else None
        )
        if current_value is None:
            current_value_complete = False
            holding_issues.append(
                _issue(
                    "MISSING_REFERENCE_PRICE",
                    "尚無可信的已保存官方收盤價。",
                    field="current_value",
                    etf_code=holding.etf_code,
                )
            )
        else:
            total_current_value += current_value

        loaded = load_target_analysis_data(
            etf_code=holding.etf_code,
            database_path=database_path,
            history_years=request.history_years,
            as_of_date=analysis_date,
        )
        distribution = loaded.monthly_income
        cash_available = (
            distribution.get("analysis_event_count", 0) > 0
            and distribution.get("analysis_currency") == "TWD"
            and not distribution.get("has_mixed_currencies", False)
            and distribution.get("missing_payment_date_count", 0) == 0
        )
        historical_payment_months = [
            int(item["month"])
            for item in distribution.get("months", [])
            if int(item.get("event_count", 0)) > 0
        ]

        if not cash_available:
            if distribution.get("missing_payment_date_count", 0) > 0:
                code = "MISSING_PAYMENT_DATE"
                message = "部分配息事件缺少付款日，無法完整歸入月份。"
            elif (
                distribution.get("has_mixed_currencies", False)
                or distribution.get("analysis_currency") not in (None, "TWD")
            ):
                code = "MIXED_CURRENCY"
                message = "配息資料幣別不相容，無法直接合併。"
            else:
                code = "MISSING_DIVIDEND_DATA"
                message = "沒有可用且具付款日的 TWD 配息資料。"
            holding_issues.append(
                _issue(
                    code,
                    message,
                    field="monthly_cash_flow",
                    etf_code=holding.etf_code,
                )
            )
            for month in range(1, 13):
                monthly_complete[month] = False
        else:
            rows_by_month = {
                int(item["month"]): item
                for item in distribution["months"]
            }
            for month in range(1, 13):
                row = rows_by_month[month]
                total_per_unit = _decimal(row.get("total_amount_per_unit"))
                if total_per_unit is None:
                    total_per_unit = Decimal("0")
                annualized = (
                    total_per_unit
                    * holding.held_units
                    / Decimal(request.history_years)
                )
                monthly_totals[month] += annualized

        cash_flow_warning_fields = {
            "payment_date",
            "dividend_history",
            "analysis_currency",
        }
        for warning in loaded.warnings:
            if not cash_flow_warning_fields.intersection(warning.affected_fields):
                continue
            warning_code = getattr(warning.code, "value", str(warning.code))
            holding_issues.append(
                _issue(
                    warning_code,
                    warning.message,
                    etf_code=holding.etf_code,
                )
            )

        deduplicated_holding_issues = list(
            {
                (item.code, item.message, item.field): item
                for item in holding_issues
            }.values()
        )
        issues.extend(deduplicated_holding_issues)
        facts.append(
            PublicPlannerHoldingFact(
                etf_code=holding.etf_code,
                name=str(etf["name"]),
                held_units=holding.held_units,
                unit_price=unit_price,
                price_as_of_date=(latest_close["trade_date"] if latest_close else None),
                price_source_id=(latest_close["source_id"] if latest_close else None),
                current_value=current_value,
                historical_payment_months=historical_payment_months,
                issues=deduplicated_holding_issues,
            )
        )

    deduction_factor = (
        Decimal("1") - request.cash_deduction_rate_pct / _HUNDRED
    )
    monthly_results: list[PublicPlannerMonthResult] = []
    for month in range(1, 13):
        selected = month in target_months
        target = request.target_after_tax_cash_twd if selected else Decimal("0")
        gross_cash = _money(monthly_totals[month]) if monthly_complete[month] else None
        after_tax_cash = (
            _money(gross_cash * deduction_factor)
            if gross_cash is not None
            else None
        )
        shortfall = (
            _money(max(target - after_tax_cash, Decimal("0")))
            if after_tax_cash is not None
            else None
        )
        monthly_results.append(
            PublicPlannerMonthResult(
                month=month,
                selected=selected,
                gross_cash=gross_cash,
                after_tax_cash=after_tax_cash,
                target_after_tax_cash=target,
                shortfall=shortfall,
            )
        )

    if not current_value_complete:
        issues.append(
            _issue(
                "INCOMPLETE_CURRENT_VALUE",
                "部分持股缺少官方收盤價，總持股價值無法計算。",
                field="total_current_value",
            )
        )

    return PublicPlannerResponse(
        status=(PublicPlannerStatus.PARTIAL if issues else PublicPlannerStatus.AVAILABLE),
        analysis_date=analysis_date,
        target_after_tax_cash_twd=request.target_after_tax_cash_twd,
        target_months=request.target_months,
        history_years=request.history_years,
        cash_deduction_rate_pct=request.cash_deduction_rate_pct,
        total_current_value=(
            _money(total_current_value) if current_value_complete else None
        ),
        holdings=facts,
        monthly_cash_flow=monthly_results,
        issues=issues,
    )
