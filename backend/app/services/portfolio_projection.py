"""V3-6 整體持股的稅務與再投入情境。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from backend.app.models.allocation_results import AllocationStrategyPlan
from backend.app.models.long_term_scenario import AllocationPlanLongTermEvidence
from backend.app.models.portfolio_projection import (
    AllocationPlanPortfolioProjection,
    DividendTaxMethod,
    PortfolioHoldingTaxFact,
    PortfolioMarketProjection,
    PortfolioProjectionRequest,
    PortfolioProjectionResponse,
    PortfolioProjectionStatus,
    PortfolioProjectionYearPoint,
    PortfolioReinvestmentResult,
)
from backend.app.models.public_planner import PublicPlannerIssue
from backend.app.models.tax_reinvestment import (
    ComponentCalculationBasis,
    ReinvestmentPolicy,
)
from backend.app.repositories.dividend_repository import (
    list_etf_component_history,
    list_etf_dividends,
)
from backend.app.services.long_term_scenario import build_long_term_scenarios
from backend.app.services.dividend_component_data import (
    select_planning_component_mix,
)
from backend.app.utils.date_tools import shift_months


_HUNDRED = Decimal("100")
_MONEY = Decimal("0.01")
_PCT = Decimal("0.000001")
_PREMIUM_RATE = Decimal("2.11")
_PREMIUM_THRESHOLD = Decimal("20000")
_PREMIUM_CAP = Decimal("10000000")
_DIVIDEND_CREDIT_RATE = Decimal("8.5")
_SEPARATE_DIVIDEND_RATE = Decimal("28")


@dataclass(slots=True)
class _HoldingState:
    fact: PortfolioHoldingTaxFact
    units: Decimal
    price: Decimal


def _money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY, rounding=ROUND_HALF_UP)


def _pct(value: Decimal) -> Decimal:
    return value.quantize(_PCT, rounding=ROUND_HALF_UP)


def _issue(code: str, message: str, etf_code: str | None = None) -> PublicPlannerIssue:
    return PublicPlannerIssue(code=code, message=message, etf_code=etf_code)


def _parsed_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            return None
    return None


def _event_reference_date(event: dict) -> date | None:
    return next(
        (
            parsed
            for field in ("ex_dividend_date", "record_date", "announcement_date")
            if (parsed := _parsed_date(event.get(field))) is not None
        ),
        None,
    )


def _holding_fact(
    holding,
    request: PortfolioProjectionRequest,
    database_path: str | Path,
    analysis_date: date,
) -> PortfolioHoldingTaxFact:
    start = shift_months(analysis_date, -12 * request.history_years)
    issues: list[PublicPlannerIssue] = []
    events = list_etf_dividends(holding.etf_code, database_path, limit=10_000)
    included: list[dict] = []
    for event in events:
        payment_date = _parsed_date(event.get("payment_date"))
        reference_date = _event_reference_date(event)
        if payment_date is None:
            if reference_date is not None and start <= reference_date <= analysis_date:
                issues.append(
                    _issue(
                        "MISSING_PAYMENT_DATE",
                        "歷史區間內有配息缺少付款日，無法可靠年化。",
                        holding.etf_code,
                    )
                )
            continue
        if start <= payment_date <= analysis_date:
            if event.get("currency") != "TWD":
                issues.append(
                    _issue(
                        "MIXED_CURRENCY",
                        "歷史區間含非 TWD 配息，無法直接合併。",
                        holding.etf_code,
                    )
                )
            included.append(event)

    initial_value = Decimal(holding.resulting_value)
    annual_cash: Decimal | None = None
    annual_rate: Decimal | None = None
    payments: int | None = None
    if not any(item.code in {"MISSING_PAYMENT_DATE", "MIXED_CURRENCY"} for item in issues):
        total_per_unit = sum(
            (Decimal(str(event.get("amount_per_unit") or 0)) for event in included),
            Decimal("0"),
        )
        annual_cash = total_per_unit * Decimal(holding.resulting_shares) / Decimal(
            request.history_years
        )
        annual_rate = annual_cash / initial_value * _HUNDRED
        if included:
            payments = max(
                1,
                int(
                    (Decimal(len(included)) / Decimal(request.history_years)).quantize(
                        Decimal("1"), rounding=ROUND_HALF_UP
                    )
                ),
            )
        elif annual_cash == 0:
            payments = 1

    selection = select_planning_component_mix(
        list_etf_component_history(holding.etf_code, database_path),
        analysis_date=analysis_date,
    )
    if annual_cash is not None and annual_cash > 0 and selection is None:
        issues.append(
            _issue(
                "COMPONENT_MIX_UNAVAILABLE",
                "有歷史配息，但缺少新鮮、已付款且完整的正式或估算配息組成。",
                holding.etf_code,
            )
        )

    if selection is not None and selection.freshness_warning:
        issues.append(_issue(
            "STALE_ACTUAL_COMPONENTS_FALLBACK", selection.freshness_warning,
            holding.etf_code,
        ))

    return PortfolioHoldingTaxFact(
        etf_code=holding.etf_code,
        units=holding.resulting_shares,
        initial_unit_price=holding.reference_price,
        initial_value=_money(initial_value),
        history_start_date=start,
        history_end_date=analysis_date,
        annual_gross_distribution_rate_pct=(
            _pct(annual_rate) if annual_rate is not None else None
        ),
        annual_gross_distribution_cash=(
            _money(annual_cash) if annual_cash is not None else None
        ),
        estimated_payments_per_year=payments,
        component_calculation_basis=(
            ComponentCalculationBasis(selection.basis) if selection else None
        ),
        component_source_event_id=(selection.source_event_id if selection else None),
        component_source_date=(selection.source_date if selection else None),
        calculation_component_mix=(selection.mix if selection else None),
        issues=issues,
    )


def _component_cash(state: _HoldingState, gross_cash: Decimal) -> dict[str, Decimal]:
    mix = state.fact.calculation_component_mix or []
    return {
        component.component_code: gross_cash * component.ratio_pct / _HUNDRED
        for component in mix
    }


def _is_supplementary_premium_component(code: str) -> bool:
    return code.startswith("54") or code in {
        "5A",
        "5B",
        "5C",
        "52",
        "71_G",
        "73_G",
        "EST_DIVIDEND",
        "EST_INTEREST",
    }


def _annual_tax(
    states: list[_HoldingState],
    request: PortfolioProjectionRequest,
) -> tuple[Decimal, Decimal, list[Decimal]]:
    gross_by_holding = [
        state.units
        * state.price
        * (state.fact.annual_gross_distribution_rate_pct or Decimal("0"))
        / _HUNDRED
        for state in states
    ]
    income_tax = Decimal("0")
    dividend_credit = Decimal("0")
    premium = Decimal("0")
    for state, gross_cash in zip(states, gross_by_holding, strict=True):
        components = _component_cash(state, gross_cash)
        for code, cash in components.items():
            if code == "76W" or code == "EST_REALIZED_CAPITAL_GAIN":
                continue
            if code == "54C" or code == "EST_DIVIDEND":
                if request.dividend_tax_method == DividendTaxMethod.SEPARATE_28:
                    income_tax += cash * _SEPARATE_DIVIDEND_RATE / _HUNDRED
                else:
                    income_tax += cash * request.marginal_income_tax_rate_pct / _HUNDRED
                    dividend_credit += cash * _DIVIDEND_CREDIT_RATE / _HUNDRED
            else:
                income_tax += cash * request.other_income_tax_rate_pct / _HUNDRED

        if not request.supplementary_premium_exempt:
            premium_base = sum(
                (
                    cash
                    for code, cash in components.items()
                    if _is_supplementary_premium_component(code)
                ),
                Decimal("0"),
            )
            payments = Decimal(state.fact.estimated_payments_per_year or 1)
            payment_base = premium_base / payments
            if payment_base >= _PREMIUM_THRESHOLD:
                premium += min(payment_base, _PREMIUM_CAP) * _PREMIUM_RATE / _HUNDRED * payments

    if request.dividend_tax_method == DividendTaxMethod.COMBINED_WITH_CREDIT:
        income_tax = max(
            income_tax
            - min(dividend_credit, request.remaining_annual_dividend_credit_cap_twd),
            Decimal("0"),
        )
    return income_tax, premium, gross_by_holding


def _reinvested_amount(
    policy: ReinvestmentPolicy,
    after_tax_cash: Decimal,
    annual_cash_target: Decimal,
    custom_pct: Decimal,
) -> Decimal:
    if policy == ReinvestmentPolicy.NO_REINVESTMENT:
        return Decimal("0")
    if policy == ReinvestmentPolicy.EXCESS_ONLY:
        return max(after_tax_cash - annual_cash_target, Decimal("0"))
    if policy == ReinvestmentPolicy.FULL_REINVESTMENT:
        return after_tax_cash
    return after_tax_cash * custom_pct / _HUNDRED


def _project_policy(
    facts: list[PortfolioHoldingTaxFact],
    request: PortfolioProjectionRequest,
    annual_total_return_pct: Decimal,
    annual_distribution_rate_pct: Decimal,
    annual_cash_target: Decimal,
    policy: ReinvestmentPolicy,
) -> PortfolioReinvestmentResult:
    states = [
        _HoldingState(fact=fact, units=fact.units, price=fact.initial_unit_price)
        for fact in facts
    ]
    initial_value = sum((state.units * state.price for state in states), Decimal("0"))
    price_return = annual_total_return_pct - annual_distribution_rate_pct
    cumulative_usable = Decimal("0")
    cumulative_reinvested = Decimal("0")
    cumulative_tax = Decimal("0")
    cumulative_premium = Decimal("0")
    points = [
        PortfolioProjectionYearPoint(
            year=0,
            ending_value=_money(initial_value),
            usable_cash=0,
            reinvested_cash=0,
            modeled_income_tax=0,
            modeled_supplementary_premium=0,
        )
    ]

    for year in range(1, request.projection_years + 1):
        income_tax, premium, gross_by_holding = _annual_tax(states, request)
        gross_cash = sum(gross_by_holding, Decimal("0"))
        after_tax_cash = max(gross_cash - income_tax - premium, Decimal("0"))
        reinvested = _reinvested_amount(
            policy,
            after_tax_cash,
            annual_cash_target,
            request.custom_reinvestment_pct,
        )
        usable = after_tax_cash - reinvested

        price_factor = Decimal("1") + price_return / _HUNDRED
        for state in states:
            state.price *= price_factor
        if reinvested > 0 and gross_cash > 0:
            for state, holding_cash in zip(states, gross_by_holding, strict=True):
                allocated = reinvested * holding_cash / gross_cash
                if state.price > 0:
                    state.units += allocated / state.price

        cumulative_usable += usable
        cumulative_reinvested += reinvested
        cumulative_tax += income_tax
        cumulative_premium += premium
        ending_value = sum((state.units * state.price for state in states), Decimal("0"))
        points.append(
            PortfolioProjectionYearPoint(
                year=year,
                ending_value=_money(ending_value),
                usable_cash=_money(cumulative_usable),
                reinvested_cash=_money(cumulative_reinvested),
                modeled_income_tax=_money(cumulative_tax),
                modeled_supplementary_premium=_money(cumulative_premium),
            )
        )

    ending_value = sum((state.units * state.price for state in states), Decimal("0"))
    gain_loss = ending_value + cumulative_usable - initial_value
    return PortfolioReinvestmentResult(
        policy=policy,
        custom_reinvestment_pct=(
            request.custom_reinvestment_pct
            if policy == ReinvestmentPolicy.CUSTOM_PERCENTAGE
            else None
        ),
        usable_cash=_money(cumulative_usable),
        reinvested_cash=_money(cumulative_reinvested),
        ending_value=_money(ending_value),
        modeled_income_tax=_money(cumulative_tax),
        modeled_supplementary_premium=_money(cumulative_premium),
        modeled_tax_cost=_money(cumulative_tax + cumulative_premium),
        after_tax_total_gain_loss=_money(gain_loss),
        after_tax_total_return_pct=_pct(gain_loss / initial_value * _HUNDRED),
        year_points=points,
    )


def _official_component_total(
    facts: list[PortfolioHoldingTaxFact],
    component_code: str,
) -> Decimal | None:
    actual_facts = [
        fact
        for fact in facts
        if fact.component_calculation_basis == ComponentCalculationBasis.ACTUAL
        and (fact.annual_gross_distribution_cash or 0) > 0
    ]
    if not actual_facts:
        return None
    total = Decimal("0")
    for fact in actual_facts:
        matching = [
            item
            for item in fact.calculation_component_mix or []
            if item.component_code == component_code
        ]
        if not matching:
            return None
        total += (
            (fact.annual_gross_distribution_cash or Decimal("0"))
            * matching[0].ratio_pct
            / _HUNDRED
        )
    return _money(total)


def _plan_projection(
    plan: AllocationStrategyPlan,
    evidence: AllocationPlanLongTermEvidence,
    request: PortfolioProjectionRequest,
    database_path: str | Path,
    analysis_date: date,
) -> AllocationPlanPortfolioProjection:
    facts = [
        _holding_fact(holding, request, database_path, analysis_date)
        for holding in plan.result.resulting_holdings
    ]
    issues = [issue for fact in facts for issue in fact.issues]
    initial_value = sum((fact.initial_value for fact in facts), Decimal("0"))
    if not facts:
        issues.append(_issue("NO_RESULTING_HOLDINGS", "配置結果沒有可投影的持股。"))
    if not evidence.scenarios:
        issues.append(_issue("MARKET_SCENARIOS_UNAVAILABLE", "缺少足夠歷史資料建立市場情境。"))
    unavailable_facts = [
        fact
        for fact in facts
        if fact.annual_gross_distribution_rate_pct is None
        or (
            (fact.annual_gross_distribution_cash or 0) > 0
            and fact.calculation_component_mix is None
        )
    ]
    annual_distribution_cash = sum(
        (fact.annual_gross_distribution_cash or Decimal("0") for fact in facts),
        Decimal("0"),
    )
    annual_distribution_rate = (
        annual_distribution_cash / initial_value * _HUNDRED
        if initial_value > 0
        else None
    )
    status = (
        PortfolioProjectionStatus.AVAILABLE
        if facts and not unavailable_facts and evidence.scenarios
        else PortfolioProjectionStatus.UNAVAILABLE
    )
    annual_cash_target = request.target_after_tax_cash_twd * Decimal(
        len(request.target_months)
    )
    market_projections = []
    if status == PortfolioProjectionStatus.AVAILABLE and annual_distribution_rate is not None:
        for scenario in evidence.scenarios:
            price_return = (
                scenario.annual_total_return_assumption_pct - annual_distribution_rate
            )
            if price_return < Decimal("-100"):
                issues.append(
                    _issue(
                        "DERIVED_PRICE_RETURN_BELOW_MINUS_100",
                        f"{scenario.label} 無法拆分為有效的價格與配息報酬。",
                    )
                )
                status = PortfolioProjectionStatus.UNAVAILABLE
                market_projections = []
                break
            market_projections.append(
                PortfolioMarketProjection(
                    band=scenario.band,
                    label=scenario.label,
                    gross_annual_total_return_assumption_pct=(
                        scenario.annual_total_return_assumption_pct
                    ),
                    derived_annual_price_return_pct=_pct(price_return),
                    reinvestment_results=[
                        _project_policy(
                            facts,
                            request,
                            scenario.annual_total_return_assumption_pct,
                            annual_distribution_rate,
                            annual_cash_target,
                            policy,
                        )
                        for policy in ReinvestmentPolicy
                    ],
                )
            )

    return AllocationPlanPortfolioProjection(
        strategy=plan.strategy,
        status=status,
        initial_value=_money(initial_value),
        annual_cash_target=_money(annual_cash_target),
        weighted_annual_gross_distribution_rate_pct=(
            _pct(annual_distribution_rate)
            if annual_distribution_rate is not None
            else None
        ),
        official_54c_annual_cash=_official_component_total(facts, "54C"),
        official_76w_annual_cash=_official_component_total(facts, "76W"),
        actual_component_holding_count=sum(
            fact.component_calculation_basis == ComponentCalculationBasis.ACTUAL
            for fact in facts
        ),
        estimated_component_holding_count=sum(
            fact.component_calculation_basis
            == ComponentCalculationBasis.ESTIMATED_FALLBACK
            for fact in facts
        ),
        unavailable_component_holding_count=sum(
            fact.component_calculation_basis is None for fact in facts
        ),
        holding_facts=facts,
        market_projections=market_projections,
        issues=issues,
    )


def build_portfolio_projections(
    request: PortfolioProjectionRequest,
    database_path: str | Path,
    *,
    as_of_date: date | None = None,
) -> PortfolioProjectionResponse:
    analysis_date = as_of_date or date.today()
    long_term = build_long_term_scenarios(
        request,
        database_path,
        as_of_date=analysis_date,
    )
    evidence_by_strategy = {
        item.strategy: item for item in long_term.plan_evidence
    }
    return PortfolioProjectionResponse(
        projection_years=request.projection_years,
        dividend_tax_method=request.dividend_tax_method,
        long_term_scenarios=long_term,
        plan_projections=[
            _plan_projection(
                plan,
                evidence_by_strategy[plan.strategy],
                request,
                database_path,
                analysis_date,
            )
            for plan in long_term.allocation_results.plans
        ],
    )
